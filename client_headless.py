#!/usr/bin/env python3
"""
P2P Tunnel Headless Linux & Terminal Client.
Pure asynchronous CLI - Zero GUI dependencies.
"""

import argparse
import asyncio
import os
import signal
import sys
import time

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from client.client_core import P2PMCClientCore
from core.paths import get_client_config_path
from core.protocol import Role


BANNER = r"""
================================================================
                  P2P TÜNEL İSTEMCİSİ
================================================================
"""


class HeadlessClientApp:
    def __init__(self, config_path: str = None, server_code: str = "", admin_key: str = ""):
        self.core = P2PMCClientCore(config_path=config_path)
        self.server_code = server_code
        self.admin_key = admin_key
        self._last_ping_print = 0.0
        self._running = True

    def setup_callbacks(self):
        self.core.on_state_change = self._on_state_change
        self.core.on_connected = self._on_connected
        self.core.on_ping_update = self._on_ping_update
        self.core.on_error = self._on_error
        self.core.on_disconnected = self._on_disconnected

    def _on_state_change(self, text: str):
        print(f"[*] Durum: {text}")

    def _on_connected(self, role: Role, rtt: float):
        role_label = "Yönetici (ADMIN)" if role == Role.ADMIN else "Standart Oyuncu (PLAYER)"
        print("\n" + "=" * 64)
        print("                  P2P TÜNEL BAĞLANTISI KURULDU")
        print("=" * 64)
        print(f"  Yetki Seviyesi   : {role_label}")
        print(f"  Başlangıç Ping   : {rtt:.1f} ms")
        print(f"  Minecraft Oyunu  : 127.0.0.1:{self.core.local_game_port}")

        if role == Role.ADMIN:
            print(f"  Yönetici SSH     : 127.0.0.1:{self.core.local_ssh_port}")
            print(f"  Web Arayüzü      : http://127.0.0.1 (veya :8080)")
            print(f"  Yönetici Paneli  : http://127.0.0.1:{self.core.local_web_port}")
            print(f"  Güvenli Port 8443: https://127.0.0.1:{self.core.local_8443_port}")
        print("=" * 64)
        print("  [*] Tünel devrede. Çıkmak için Ctrl+C tuşlarına basın.\n")

    def _on_ping_update(self, rtt: float):
        now = time.time()
        # Throttled live ping update every 3 seconds to keep terminal clean
        if now - self._last_ping_print >= 3.0:
            self._last_ping_print = now
            sys.stdout.write(f"\r[~] Gecikme: {rtt:5.1f} ms | Tünel Aktif (KCP)   ")
            sys.stdout.flush()

    def _on_error(self, err_msg: str):
        print(f"\n[!] HATA: {err_msg}")

    def _on_disconnected(self):
        print("\n[*] Bağlantı sonlandırıldı.")

    def select_server_interactively(self) -> bool:
        saved = self.core.saved_servers
        print("\n" + "-" * 64)
        print("  KAYITLI SUNUCU LİSTESİ")
        print("-" * 64)
        if saved:
            for idx, s in enumerate(saved, 1):
                s_name = s.get("name") or "Sunucu"
                s_code = s.get("code") or ""
                has_admin = " [ADMIN]" if s.get("admin_key") else ""
                print(f"  [{idx}] {s_name} ({s_code}){has_admin}")
        else:
            print("  (Henüz kayıtlı sunucu yok)")

        print("  [+] Yeni bir sunucu adresi girin")
        print("  [Q] Çıkış")
        print("-" * 64)

        try:
            choice = input("\nSeçiminiz: ").strip()
        except (KeyboardInterrupt, EOFError):
            return False

        if not choice or choice.lower() == "q":
            return False

        if choice == "+":
            try:
                name = input("Sunucu Adı: ").strip() or "Sunucu"
                code = input("Bağlantı Kodu: ").strip()
                if not code:
                    print("[!] Bağlantı kodu boş olamaz.")
                    return False
                admin = input("Yönetici Anahtarı: ").strip()
                self.core.save_server_config(name, code, admin)
                self.server_code = code
                self.admin_key = admin
                return True
            except (KeyboardInterrupt, EOFError):
                return False

        if choice.isdigit():
            idx = int(choice)
            if 1 <= idx <= len(saved):
                target = saved[idx - 1]
                self.core.save_server_config(
                    target.get("name", "Sunucu"),
                    target.get("code", ""),
                    target.get("admin_key", ""),
                )
                self.server_code = target.get("code", "")
                self.admin_key = target.get("admin_key", "")
                return True

        # Assume direct code entered
        self.core.save_server_config("Sunucu", choice, "")
        self.server_code = choice
        self.admin_key = ""
        return True

    async def run_async(self):
        self.setup_callbacks()

        if not self.server_code:
            # Check if default server exists in config, otherwise prompt
            if self.core.server_code:
                self.server_code = self.core.server_code
                self.admin_key = self.core.admin_key
                print(f"[*] Varsayılan sunucu kullanılıyor: {self.core.server_name} ({self.server_code})")
                if self.admin_key:
                    print("[*] Yönetici (ADMIN) anahtarı devrede.")
            else:
                ok = self.select_server_interactively()
                if not ok:
                    print("[*] İptal edildi.")
                    return

        if self.admin_key:
            self.core.admin_key = self.admin_key

        self.core.server_code = self.server_code

        # Clean shutdown handler
        loop = asyncio.get_running_loop()

        def handle_sig():
            if self._running:
                self._running = False
                print("\n\n[*] Kapatma sinyali alındı. Tünel güvenli şekilde kapatılıyor...")
                asyncio.create_task(self.core.disconnect_async())

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, handle_sig)
            except NotImplementedError:
                # Windows signal compatibility
                pass

        try:
            await self.core.connect_async()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"[!] İstisna: {e}")
        finally:
            if self.core.is_connected:
                await self.core.disconnect_async()


def main():
    parser = argparse.ArgumentParser(
        description="P2P Tunnel Headless Terminal Client",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("server_code", nargs="?", default="", help="Sunucu Bağlantı Kodu")
    parser.add_argument("-a", "--admin", dest="admin_key", default="", help="Yönetici Anahtarı")
    parser.add_argument("-i", "--interactive", action="store_true", help="Kayıtlı sunuculardan interaktif seçim menüsü aç")
    parser.add_argument("-l", "--list", action="store_true", help="Kayıtlı sunucuları listele ve çık")
    parser.add_argument("-c", "--config", default=None, help="Özel ayar JSON dosya yolu")

    args = parser.parse_args()

    print(BANNER)

    config_path = args.config or get_client_config_path()

    if args.list:
        core = P2PMCClientCore(config_path=config_path)
        print("KAYITLI SUNUCULAR:")
        if not core.saved_servers:
            print("  (Kayıtlı sunucu bulunamadı)")
        for idx, s in enumerate(core.saved_servers, 1):
            admin_tag = " [ADMIN]" if s.get("admin_key") else ""
            print(f"  {idx}. {s.get('name', 'Sunucu')} -> {s.get('code', '')}{admin_tag}")
        sys.exit(0)

    code = args.server_code.strip()
    admin = args.admin_key.strip()

    # Handle hash formatted admin key (CODE#KEY)
    if "#" in code:
        parts = code.split("#", 1)
        code = parts[0].strip()
        if parts[1].strip() and not admin:
            admin = parts[1].strip()

    app = HeadlessClientApp(
        config_path=config_path,
        server_code="" if args.interactive else code,
        admin_key=admin,
    )

    try:
        asyncio.run(app.run_async())
    except KeyboardInterrupt:
        print("\n[*] İstemci kullanıcı tarafından durduruldu.")


if __name__ == "__main__":
    main()
