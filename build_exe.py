"""
P2P Tunnel Standalone Executable Builder.
Uses --collect-all for kcp and cryptography to include all Cython .pyd and C extensions.
"""

import argparse
import os
import shutil
import subprocess
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DIST_DIR = os.path.join(BASE_DIR, "dist")
BUILD_DIR = os.path.join(BASE_DIR, "build")


def clean_build_artifacts():
    for folder in [BUILD_DIR]:
        if os.path.exists(folder):
            shutil.rmtree(folder, ignore_errors=True)


def build_client(target_name: str = None):
    print("\n" + "=" * 60)
    print("      WINDOWS ISTEMCI (CLIENT) DERLENIYOR...")
    print("=" * 60)

    icon_path = os.path.join(BASE_DIR, "assets", "app_icon.ico")
    assets_dir = os.path.join(BASE_DIR, "assets")

    if target_name:
        exe_name = os.path.splitext(os.path.basename(target_name))[0]
    else:
        exe_name = "P2P_Tunnel_Client"

    # Generate Windows PE Version Info
    try:
        from core.version_info import generate_version_info_file
        from core.updater import APP_VERSION
        version_info_file = os.path.join(BUILD_DIR, "client_version_info.txt")
        os.makedirs(BUILD_DIR, exist_ok=True)
        generate_version_info_file(
            filepath=version_info_file,
            version_str=APP_VERSION,
            exe_name=exe_name,
            description="P2P High-Performance Tunnel Client"
        )
        has_version_info = True
    except Exception as e:
        print(f"[!] Version info hazirlanamadi: {e}")
        has_version_info = False

    sep = os.pathsep
    cmd = [
        sys.executable, "-m", "PyInstaller",
        f"--name={exe_name}",
        "--onefile",
        "--windowed",
        "--clean",
        f"--icon={icon_path}",
        f"--distpath={DIST_DIR}",
        f"--workpath={BUILD_DIR}",
        f"--add-data={os.path.join(BASE_DIR, 'core')}{sep}core",
        f"--add-data={os.path.join(BASE_DIR, 'client')}{sep}client",
        f"--add-data={assets_dir}{sep}assets",
        "--collect-all=kcp",            # Crucial: Collects all Cython .pyd binaries!
        "--collect-all=cryptography",   # Crucial: Collects all OpenSSL C-bindings!
        "--hidden-import=PyQt6",
        "--hidden-import=PyQt6.QtCore",
        "--hidden-import=PyQt6.QtWidgets",
        "--hidden-import=PyQt6.QtGui",
        "--exclude-module=tkinter",
        "--exclude-module=matplotlib",
        "--exclude-module=numpy",
    ]

    if has_version_info and os.path.exists(version_info_file):
        cmd.append(f"--version-file={version_info_file}")

    cmd.append(os.path.join(BASE_DIR, "run_client.py"))

    print(f"[*] Derleme komutu calistiriliyor ({exe_name}.exe)...")
    res = subprocess.run(cmd, cwd=BASE_DIR)
    if res.returncode == 0:
        exe_ext = ".exe" if sys.platform == "win32" else ""
        final_exe_path = os.path.join(DIST_DIR, f"{exe_name}{exe_ext}")
        print(f"\n[+] BASARILI: Istemci binary hazir -> {final_exe_path}")
        return True
    return False


def build_server():
    print("\n" + "=" * 60)
    print("      WINDOWS SUNUCU (SERVER) DERLENIYOR...")
    print("=" * 60)

    icon_path = os.path.join(BASE_DIR, "assets", "app_icon.ico")
    assets_dir = os.path.join(BASE_DIR, "assets")

    # Generate Windows PE Version Info for Server
    try:
        from core.version_info import generate_version_info_file
        version_info_file = os.path.join(BUILD_DIR, "server_version_info.txt")
        os.makedirs(BUILD_DIR, exist_ok=True)
        generate_version_info_file(
            filepath=version_info_file,
            version_str="2.1.0",
            exe_name="P2P_Tunnel_Server",
            description="P2P High-Performance Tunnel Server Daemon"
        )
        has_version_info = True
    except Exception as e:
        print(f"[!] Server version info hazirlanamadi: {e}")
        has_version_info = False

    sep = os.pathsep
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name=P2P_Tunnel_Server",
        "--onefile",
        "--console",
        "--clean",
        f"--icon={icon_path}",
        f"--distpath={DIST_DIR}",
        f"--workpath={BUILD_DIR}",
        f"--add-data={os.path.join(BASE_DIR, 'core')}{sep}core",
        f"--add-data={os.path.join(BASE_DIR, 'server')}{sep}server",
        f"--add-data={assets_dir}{sep}assets",
        "--collect-all=kcp",
        "--collect-all=cryptography",
        "--exclude-module=PyQt6",
        "--exclude-module=tkinter",
        "--exclude-module=matplotlib",
    ]

    if has_version_info and os.path.exists(version_info_file):
        cmd.append(f"--version-file={version_info_file}")

    cmd.append(os.path.join(BASE_DIR, "run_server.py"))

    print("[*] Komut koşturuluyor...")
    res = subprocess.run(cmd, cwd=BASE_DIR)
    if res.returncode == 0:
        exe_ext = ".exe" if sys.platform == "win32" else ""
        exe_path = os.path.join(DIST_DIR, f"P2P_Tunnel_Server{exe_ext}")
        print(f"\n[+] BASARILI: Sunucu binary hazir -> {exe_path}")
        return True
    return False


def main():
    parser = argparse.ArgumentParser(description="P2P Tunnel Windows EXE Compiler")
    parser.add_argument("--client", action="store_true", help="Build only Client GUI EXE")
    parser.add_argument("--server", action="store_true", help="Build only Server CLI EXE")
    parser.add_argument("--all", action="store_true", help="Build both Client and Server")
    parser.add_argument("--name", help="Custom executable name for Client (e.g. 'P2P Tunnel v2.1.1.exe')")
    args = parser.parse_args()

    build_both = args.all or (not args.client and not args.server)

    os.makedirs(DIST_DIR, exist_ok=True)
    clean_build_artifacts()

    success = True
    if args.client or build_both:
        success = build_client(target_name=args.name) and success

    if args.server or build_both:
        success = build_server() and success

    clean_build_artifacts()

    if success:
        if sys.platform == "win32":
            try:
                import ctypes
                # Notify Windows Shell to invalidate icon cache for newly built exes
                ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)
            except Exception:
                pass

        print("\n" + "=" * 60)
        print(f"  TUM HEDEFLER BASARIYLA DERLENDI!")
        print(f"  Cikti Klasoru: {DIST_DIR}")
        print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
