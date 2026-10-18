"""
P2P Tunnel Server Launcher.
Runs headless server daemon on Ubuntu Server, OpenWrt (Pi 4), or Windows.
"""

import argparse
import asyncio
import os
import sys
import time
from core.paths import get_server_config_path, get_app_data_dir
from server.server_daemon import P2PMCServer

def acquire_single_instance_mutex():
    if sys.platform == "win32":
        import ctypes
        mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "Global\\P2P_TUNNEL_SERVER_INSTANCE_MUTEX")
        if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
            print("\n" + "=" * 64)
            print("  [!] HATA: P2P Sunucu zaten başka bir pencerede veya")
            print("      arka planda çalışıyor!")
            print("  [!] Lütfen açık olan diğer sunucuyu kapatıp tekrar deneyin.")
            print("=" * 64 + "\n")
            sys.exit(1)
        return mutex
    else:
        # Linux/POSIX Single-Instance Flocking
        try:
            import fcntl
            lock_path = os.path.join(get_app_data_dir(), "server.lock")
            lock_fd = open(lock_path, "w")
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return lock_fd
        except (BlockingIOError, IOError):
            print("\n" + "=" * 64)
            print("  [!] HATA: P2P Sunucu zaten başka bir konsolda veya")
            print("      arka planda çalışıyor!")
            print("  [!] Lütfen açık olan diğer sunucuyu kapatıp tekrar deneyin.")
            print("=" * 64 + "\n")
            sys.exit(1)
        except Exception:
            return None

def main():
    parser = argparse.ArgumentParser(description="P2P Tunnel Headless Server Daemon")
    parser.add_argument("--config", default=None, help="Sunucu ayar JSON dosyası")
    parser.add_argument("--admin-key", default=None, help="Özel Yönetici Anahtarı")
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--mazipanel",
        action="store_true",
        help="Sunucuyu maziPanel entegrasyon modunda çalıştır ve kaydet",
    )
    mode_group.add_argument(
        "--standalone",
        action="store_true",
        help="Sunucuyu bağımsız (standalone) web paneli modunda çalıştır ve kaydet",
    )
    args = parser.parse_args()

    panel_mode = None
    if args.mazipanel:
        panel_mode = "mazipanel"
    elif args.standalone:
        panel_mode = "standalone"

    config_path = args.config or get_server_config_path()
    stop_flag = os.path.join(os.path.dirname(os.path.abspath(config_path)), ".stopped_by_panel")
    try:
        while os.path.exists(stop_flag):
            time.sleep(0.5)
    except KeyboardInterrupt:
        sys.exit(0)

    _server_mutex = acquire_single_instance_mutex()
    server = P2PMCServer(
        config_path=config_path,
        admin_secret=args.admin_key,
        panel_mode=panel_mode,
    )
    try:
        asyncio.run(server.run())
    except KeyboardInterrupt:
        print("\n[*] Sunucu durduruldu.")
        sys.exit(0)

if __name__ == "__main__":
    main()
