"""
P2P Tunnel Auto-Updater Engine.
Handles zero-friction In-App OTA updates across Windows executables without requiring GitHub.
Compatible with Cloudflare Tunnel (cloudflared), Cloudflare R2, or any static HTTP/S endpoint.
"""

import hashlib
import json
import logging
import os
import subprocess
import sys
import tempfile
import urllib.request
import urllib.error
from typing import Optional, Callable, Dict, Any

logger = logging.getLogger("P2P_Updater")

# Current application semantic version
APP_VERSION = "4.1"

# Public R2 Update Endpoint
DEFAULT_UPDATE_URL = "https://updates.mazidev.xyz/version.json"


def is_version_newer(remote_ver: str, current_ver: str = APP_VERSION) -> bool:
    """Compares semantic versions e.g. '2.5' > '2.1' or '2.5.1' > '2.5.0'."""
    def parse_ver(v: str):
        v = str(v).lstrip("v").strip()
        parts = []
        for x in v.split("."):
            try:
                parts.append(int(x))
            except ValueError:
                parts.append(0)
        while len(parts) < 3:
            parts.append(0)
        return parts

    return parse_ver(remote_ver) > parse_ver(current_ver)


def fetch_version_manifest(update_url: Optional[str] = None, timeout: float = 4.0) -> Optional[Dict[str, Any]]:
    """
    Fetches the remote version.json manifest with cache-busting headers.
    """
    url = (update_url or DEFAULT_UPDATE_URL).strip()
    if not url or not url.startswith("http"):
        return None

    try:
        import time
        sep = "&" if "?" in url else "?"
        cache_buster_url = f"{url}{sep}_cb={int(time.time() * 1000)}"

        req = urllib.request.Request(
            cache_buster_url,
            headers={
                "User-Agent": f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) P2PTunnelClient/{APP_VERSION}",
                "Cache-Control": "no-cache, no-store, max-age=0, must-revalidate",
                "Pragma": "no-cache",
            }
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        logger.debug(f"Manifest fetch failed (silent): {e}")

    return None


def check_for_updates(update_url: Optional[str] = None, timeout: float = 4.0) -> Optional[Dict[str, Any]]:
    """
    Checks remote version.json manifest and returns it if a newer version is available.
    """
    data = fetch_version_manifest(update_url=update_url, timeout=timeout)
    if data:
        remote_ver = str(data.get("version", "")).strip()
        if remote_ver and is_version_newer(remote_ver, APP_VERSION):
            return data
    return None


def download_file(
    url: str,
    dest_path: str,
    expected_sha256: Optional[str] = None,
    progress_callback: Optional[Callable[[int], None]] = None,
    timeout: float = 60.0
) -> bool:
    """Downloads remote binary to dest_path with progress callback and optional sha256 verification."""
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) P2PTunnelClient/{APP_VERSION}",
                "Accept-Encoding": "identity"
            }
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            total_size = int(resp.headers.get("content-length", 0))
            downloaded = 0
            hasher = hashlib.sha256() if expected_sha256 else None
            last_pct = -1

            temp_dest = dest_path + ".tmp"
            if os.path.exists(temp_dest):
                try:
                    os.remove(temp_dest)
                except Exception:
                    pass

            with open(temp_dest, "wb") as f:
                while True:
                    chunk = resp.read(131072)  # 128 KB buffer
                    if not chunk:
                        break
                    f.write(chunk)
                    if hasher:
                        hasher.update(chunk)
                    downloaded += len(chunk)
                    if total_size > 0 and progress_callback:
                        pct = int((downloaded / total_size) * 100)
                        if pct != last_pct:
                            last_pct = pct
                            progress_callback(min(pct, 100))

            if expected_sha256 and hasher:
                calc_hash = hasher.hexdigest().lower()
                if calc_hash != expected_sha256.lower().strip():
                    logger.error(f"SHA256 mismatch: got {calc_hash}, expected {expected_sha256}")
                    if os.path.exists(temp_dest):
                        try:
                            os.remove(temp_dest)
                        except Exception:
                            pass
                    return False

            # Validate that downloaded file is a valid Windows executable (size > 100KB, magic b"MZ")
            if dest_path.lower().endswith(".exe") or sys.platform == "win32":
                file_size = os.path.getsize(temp_dest) if os.path.exists(temp_dest) else 0
                if file_size < 100 * 1024:
                    logger.error(f"Download validation failed: file size too small ({file_size} bytes)")
                    if os.path.exists(temp_dest):
                        try:
                            os.remove(temp_dest)
                        except Exception:
                            pass
                    return False

                with open(temp_dest, "rb") as check_f:
                    magic_bytes = check_f.read(2)
                if magic_bytes != b"MZ":
                    logger.error(f"Download validation failed: invalid PE magic header ({magic_bytes!r}, expected b'MZ')")
                    if os.path.exists(temp_dest):
                        try:
                            os.remove(temp_dest)
                        except Exception:
                            pass
                    return False

            if os.path.exists(dest_path):
                try:
                    os.remove(dest_path)
                except Exception:
                    pass
            os.rename(temp_dest, dest_path)
            return True
    except Exception as e:
        logger.error(f"Download failed: {e}")
        return False


def _apply_windows_update(new_binary_path: str, target_filename: Optional[str] = None):
    """
    On Windows:
    Safely and silently updates the running executable in its original folder.
    Cleans PyInstaller _MEIPASS environment variables to prevent Python DLL load failures.
    Includes automated rollback protection if moving the new binary fails.
    Uses a hidden VBS runner so zero CMD windows pop up.
    """
    if sys.platform != "win32":
        logger.warning("Auto-restart replacement currently designed for Windows.")
        return

    if not os.path.exists(new_binary_path):
        logger.error(f"Update binary not found: {new_binary_path}")
        return

    if os.path.getsize(new_binary_path) < 100 * 1024:
        logger.error("Update binary is corrupted (size < 100KB).")
        return

    try:
        with open(new_binary_path, "rb") as f:
            if f.read(2) != b"MZ":
                logger.error("Update binary is corrupted (missing MZ header).")
                return
    except Exception as e:
        logger.error(f"Failed to verify binary header: {e}")
        return

    current_exe = os.path.abspath(sys.executable)
    # If in python interpreter dev mode, notify only
    if not getattr(sys, "frozen", False):
        logger.info(f"[Dev Mode] New binary downloaded to: {new_binary_path}")
        return

    target_dir = os.path.dirname(current_exe)
    if target_filename:
        # Strip any directory path just in case
        clean_name = os.path.basename(target_filename.strip())
        final_target = os.path.join(target_dir, clean_name)
    else:
        final_target = current_exe

    current_pid = os.getpid()
    bat_dir = tempfile.gettempdir()
    bat_file = os.path.join(bat_dir, "p2p_update_runner.bat")
    vbs_file = os.path.join(bat_dir, "p2p_silent_launcher.vbs")

    bat_content = f"""@echo off
setlocal
chcp 65001 >nul

:: CRUCIAL: Clear PyInstaller runtime variables so the new exe creates fresh temp unpack
set _MEIPASS2=
set _MEIPASS=

set "OLDEXE={current_exe}"
set "TARGET={final_target}"
set "NEWFILE={new_binary_path}"

:: 1. Force kill current PID instantly to release all file locks
taskkill /F /PID {current_pid} >nul 2>&1

:: 2. Wait 1 second silently for OS file release
ping 127.0.0.1 -n 2 >nul

:: 3. Backup old executable if target name differs
if /i not "%OLDEXE%"=="%TARGET%" (
    if exist "%OLDEXE%" (
        move /y "%OLDEXE%" "%OLDEXE%.old" >nul 2>&1
    )
)

:: 4. Backup existing target executable before replacing
if exist "%TARGET%" (
    move /y "%TARGET%" "%TARGET%.old" >nul 2>&1
)

:: 5. Place new binary into the exact directory
move /y "%NEWFILE%" "%TARGET%" >nul 2>&1
if errorlevel 1 goto ROLLBACK
if not exist "%TARGET%" goto ROLLBACK

:: 6. Success: Clean up temporary backup files
del /f /q "%OLDEXE%.old" >nul 2>&1
del /f /q "%TARGET%.old" >nul 2>&1
goto FINISH

:ROLLBACK
:: Rollback: restore previous executable on failure, keeping .old intact
if not exist "%TARGET%" (
    if exist "%TARGET%.old" (
        move /y "%TARGET%.old" "%TARGET%" >nul 2>&1
    ) else if exist "%OLDEXE%.old" (
        move /y "%OLDEXE%.old" "%TARGET%" >nul 2>&1
    )
)

:FINISH
(goto) 2>nul & del "%~f0"
"""

    with open(bat_file, "w", encoding="utf-8") as f:
        f.write(bat_content)

    # Completely hidden VBScript runner using Chr(34) for rock-solid path quoting:
    # 1. Runs the batch script hidden (0) and WAITS for it to finish (True)
    # 2. Then launches the updated executable visible (1) with --updated flag
    vbs_content = (
        'Set ws = CreateObject("Wscript.Shell")\n'
        f'ws.Run "cmd.exe /c " & Chr(34) & "{bat_file}" & Chr(34), 0, True\n'
        f'ws.Run Chr(34) & "{final_target}" & Chr(34) & " --updated", 1, False\n'
    )
    with open(vbs_file, "w", encoding="utf-8") as f:
        f.write(vbs_content)

    # Execute silent VBScript launcher detached
    subprocess.Popen(
        ["wscript.exe", vbs_file],
        creationflags=0x08000000 | 0x00000008,
        close_fds=True
    )

    # Immediately terminate current process at OS level
    os._exit(0)


def apply_update_and_restart(new_binary_path: str, target_filename: Optional[str] = None):
    """Public wrapper to apply update and restart executable."""
    return _apply_windows_update(new_binary_path, target_filename)
