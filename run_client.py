"""
P2P Tunnel Client Launcher.
Launches the modern PyQt6 animated GUI by default, or headless CLI if requested.
"""

import argparse
import asyncio
import os
import sys

from core.paths import get_client_config_path

def main():
    parser = argparse.ArgumentParser(description="P2P Tunnel Client Launcher")
    parser.add_argument("server_code", nargs="?", default="", help="Sunucu Bağlantı Kodu")
    parser.add_argument("-a", "--admin", dest="admin_key", default="", help="Yönetici Anahtarı")
    parser.add_argument("--config", default=None, help="Özel ayar JSON dosya yolu")
    parser.add_argument("--cli", action="store_true", help="Grafik arayüz (GUI) yerine konsol / headless modunda çalıştır")
    parser.add_argument("--updated", action="store_true", help="Güncelleme sonrası başlatma bayrağı")
    args, _ = parser.parse_known_args()

    # Detect if GUI is available
    use_cli = args.cli or bool(args.server_code)
    if not use_cli:
        try:
            import PyQt6
            # Test if a display server is available on Linux/Unix
            if sys.platform != "win32" and not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
                use_cli = True
        except ImportError:
            use_cli = True

    if use_cli:
        from client_headless import HeadlessClientApp, BANNER
        print(BANNER)
        app = HeadlessClientApp(
            config_path=args.config,
            server_code=args.server_code,
            admin_key=args.admin_key,
        )
        try:
            asyncio.run(app.run_async())
        except KeyboardInterrupt:
            print("\n[*] İstemci durduruldu.")
    else:
        from client.gui.app import run_gui
        run_gui(config_path=args.config)


if __name__ == "__main__":
    main()
