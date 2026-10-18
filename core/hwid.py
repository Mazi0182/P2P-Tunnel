"""
P2P Tunnel Hardware Identifier (HWID) & System Identity Module.
Collects invariant hardware components across Windows and Linux:
- Motherboard UUID & Product (Win32_ComputerSystemProduct / BIOS)
- Windows MachineGuid (HKLM\\SOFTWARE\\Microsoft\\Cryptography)
- Primary Drive Volume Serial Number
- CPU Processor Identifier
- Hardware MAC Address
- Computer Name & Windows Username (Purely for display/identification)
"""

import os
import sys
import uuid
import hashlib
import platform
import getpass
import subprocess
from typing import Dict, Any


def get_windows_machine_guid() -> str:
    """Reads Windows Cryptography MachineGuid from Registry."""
    if sys.platform != "win32":
        return ""
    try:
        import winreg
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Cryptography",
            0,
            winreg.KEY_READ | winreg.KEY_WOW64_64KEY
        ) as key:
            val, _ = winreg.QueryValueEx(key, "MachineGuid")
            return str(val).strip()
    except Exception:
        return ""


def get_windows_volume_serial() -> str:
    """Gets the volume serial number of the primary system drive (C:\\)."""
    if sys.platform != "win32":
        return ""
    try:
        import ctypes
        vol_serial = ctypes.c_ulong()
        ret = ctypes.windll.kernel32.GetVolumeInformationW(
            ctypes.c_wchar_p("C:\\"),
            None,
            0,
            ctypes.byref(vol_serial),
            None,
            None,
            None,
            0
        )
        if ret:
            return hex(vol_serial.value)
    except Exception:
        pass
    return ""


def get_motherboard_details() -> Dict[str, str]:
    """Retrieves Motherboard UUID, Product name, and BIOS details."""
    details = {
        "uuid": "",
        "product": "",
        "manufacturer": "",
        "bios_version": "",
    }

    if sys.platform == "win32":
        # 1. Fast Registry Check for BaseBoard & BIOS
        try:
            import winreg
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"HARDWARE\DESCRIPTION\System\BIOS",
                0,
                winreg.KEY_READ | winreg.KEY_WOW64_64KEY
            ) as key:
                def _get_val(vname):
                    try:
                        return str(winreg.QueryValueEx(key, vname)[0]).strip()
                    except Exception:
                        return ""

                details["manufacturer"] = _get_val("BaseBoardManufacturer") or _get_val("SystemManufacturer")
                details["product"] = _get_val("BaseBoardProduct") or _get_val("SystemProductName")
                details["bios_version"] = _get_val("BIOSVersion")
        except Exception:
            pass

        # 2. Motherboard / System UUID via PowerShell (silent, no window)
        try:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            cmd = [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy", "Bypass",
                "-Command",
                "(Get-CimInstance Win32_ComputerSystemProduct).UUID"
            ]
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=4,
                startupinfo=startupinfo,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
            )
            out = res.stdout.strip()
            if out and len(out) > 8 and "error" not in out.lower():
                details["uuid"] = out
        except Exception:
            pass

        # 3. Registry fallback for system hardware UUID if PowerShell was blocked/empty
        if not details["uuid"]:
            try:
                import winreg
                with winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE,
                    r"SYSTEM\CurrentControlSet\Control\SystemInformation",
                    0,
                    winreg.KEY_READ | winreg.KEY_WOW64_64KEY
                ) as key:
                    hw_id = str(winreg.QueryValueEx(key, "ComputerHardwareId")[0]).strip()
                    if hw_id:
                        details["uuid"] = hw_id.strip("{}")
            except Exception:
                pass

    elif sys.platform.startswith("linux"):
        # Linux hardware identification
        for p in ("/sys/class/dmi/id/product_uuid", "/etc/machine-id", "/var/lib/dbus/machine-id"):
            if os.path.exists(p):
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        val = f.read().strip()
                        if val:
                            details["uuid"] = val
                            break
                except Exception:
                    pass

        for p, key in (
            ("/sys/class/dmi/id/board_name", "product"),
            ("/sys/class/dmi/id/board_vendor", "manufacturer"),
            ("/sys/class/dmi/id/bios_version", "bios_version"),
        ):
            if os.path.exists(p):
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        details[key] = f.read().strip()
                except Exception:
                    pass

    return details


def get_mac_address() -> str:
    """Gets hardware MAC address as hexadecimal string."""
    try:
        node = uuid.getnode()
        return hex(node)
    except Exception:
        return ""


def get_persistent_device_id() -> str:
    """Retrieves or creates a persistent cryptographic device ID stored in app data dir."""
    try:
        from core.paths import get_app_data_dir
        app_dir = get_app_data_dir()
        dev_file = os.path.join(app_dir, ".device_id")
        if os.path.exists(dev_file):
            try:
                with open(dev_file, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    if len(content) >= 32:
                        return content
            except Exception:
                pass
        new_id = uuid.uuid4().hex
        try:
            with open(dev_file, "w", encoding="utf-8") as f:
                f.write(new_id)
        except Exception:
            pass
        return new_id
    except Exception:
        return ""


def get_cpu_identifier() -> str:
    """
    Gets CPU identifier string.
    Prioritizes Registry and platform information over environment variables to prevent tampering.
    """
    if sys.platform == "win32":
        # 1. Primary: Windows Registry CentralProcessor
        try:
            import winreg
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"HARDWARE\DESCRIPTION\System\CentralProcessor\0",
                0,
                winreg.KEY_READ | winreg.KEY_WOW64_64KEY
            ) as key:
                def _val(name):
                    try:
                        return str(winreg.QueryValueEx(key, name)[0]).strip()
                    except Exception:
                        return ""
                ident = _val("Identifier")
                vendor = _val("VendorIdentifier")
                name_str = _val("ProcessorNameString")
                if ident and vendor:
                    return f"{ident}, {vendor}"
                elif ident:
                    return ident
                elif name_str:
                    return name_str
        except Exception:
            pass

    # 2. Platform processor / machine
    proc = platform.processor().strip()
    if proc:
        return proc
    mach = platform.machine().strip()
    if mach:
        return mach

    # 3. Environment variable (last resort fallback only)
    if sys.platform == "win32":
        return os.environ.get("PROCESSOR_IDENTIFIER", "").strip()

    return ""


def get_client_identity() -> Dict[str, Any]:
    """
    Collects complete client identity and hardware profile.
    Returns:
      {
        "username": "Mert",
        "computer_name": "DESKTOP-SK29JB6",
        "hwid": "HWID-A23B-FA7C-7EA2-3B15-...",
        "hwid_details": {
          "motherboard_uuid": "...",
          "motherboard_product": "...",
          "machine_guid": "...",
          "volume_serial": "...",
          "cpu_id": "...",
          "mac": "..."
        },
        "os": "Windows 11",
        "platform": "win32"
      }
    """
    mb_details = get_motherboard_details()
    machine_guid = get_windows_machine_guid()
    vol_serial = get_windows_volume_serial()
    cpu_id = get_cpu_identifier()
    mac = get_mac_address()
    device_id = get_persistent_device_id()

    # User identification (display name)
    try:
        username = getpass.getuser() or os.environ.get("USERNAME") or os.environ.get("USER") or "Player"
    except Exception:
        username = os.environ.get("USERNAME") or "Player"

    comp_name = platform.node() or "PC"

    # Composite invariant hardware fingerprint
    # Salted with a static project seed for consistency
    fingerprint_raw = (
        f"UUID:{mb_details.get('uuid', '')}|"
        f"GUID:{machine_guid}|"
        f"VOL:{vol_serial}|"
        f"CPU:{cpu_id}|"
        f"MAC:{mac}|"
        f"MB:{mb_details.get('product', '')}"
    )

    h = hashlib.sha256(fingerprint_raw.encode("utf-8")).hexdigest().upper()
    hwid = f"HWID-{h[0:4]}-{h[4:8]}-{h[8:12]}-{h[12:16]}"

    try:
        from core.updater import APP_VERSION
        app_ver = APP_VERSION
    except Exception:
        app_ver = "2.6"

    return {
        "version": app_ver,
        "username": username,
        "computer_name": comp_name,
        "hwid": hwid,
        "hwid_details": {
            "motherboard_uuid": mb_details.get("uuid", ""),
            "motherboard_product": f"{mb_details.get('manufacturer', '')} {mb_details.get('product', '')}".strip(),
            "machine_guid": machine_guid,
            "volume_serial": vol_serial,
            "cpu_id": cpu_id,
            "mac": mac,
            "device_id": device_id,
        },
        "os": f"{platform.system()} {platform.release()}",
        "platform": sys.platform,
    }
