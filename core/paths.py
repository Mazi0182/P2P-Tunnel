r"""
P2P_MC System Path Management.
Ensures persistent configuration storage strictly in C:\ProgramData\P2PTunnel.
"""

import os
import sys

def get_app_data_dir() -> str:
    """
    Returns application data/configuration directory:
    - Custom override: $P2P_CONFIG_DIR
    - Windows: C:\\ProgramData\\P2PTunnel
    - Linux/Unix (root/systemd): /etc/p2ptunnel (if /etc/p2ptunnel exists or P2P_SYSTEM_DAEMON is set)
    - Linux/Unix (user): $XDG_CONFIG_HOME/p2ptunnel or ~/.config/p2ptunnel (fallback: ~/.p2ptunnel)
    """
    custom_dir = os.environ.get("P2P_CONFIG_DIR")
    if custom_dir:
        os.makedirs(custom_dir, exist_ok=True)
        return custom_dir

    if sys.platform == "win32":
        base = os.environ.get("ProgramData", r"C:\ProgramData")
        app_dir = os.path.join(base, "P2PTunnel")
    else:
        is_root = (hasattr(os, "geteuid") and os.geteuid() == 0)
        if is_root and (os.path.exists("/etc/p2ptunnel") or os.environ.get("P2P_SYSTEM_DAEMON")):
            app_dir = "/etc/p2ptunnel"
        else:
            legacy_dir = os.path.expanduser("~/.p2ptunnel")
            if os.path.exists(legacy_dir):
                app_dir = legacy_dir
            else:
                xdg_config = os.environ.get("XDG_CONFIG_HOME")
                if xdg_config:
                    app_dir = os.path.join(xdg_config, "p2ptunnel")
                else:
                    app_dir = os.path.expanduser("~/.config/p2ptunnel")

    try:
        os.makedirs(app_dir, exist_ok=True)
    except OSError:
        app_dir = os.path.expanduser("~/.p2ptunnel")
        os.makedirs(app_dir, exist_ok=True)

    return app_dir

def get_client_config_path() -> str:
    return os.path.join(get_app_data_dir(), "client_config.json")

def get_server_config_path() -> str:
    return os.path.join(get_app_data_dir(), "server_config.json")

def get_client_log_path() -> str:
    return os.path.join(get_app_data_dir(), "client.log")

def get_server_log_path() -> str:
    return os.path.join(get_app_data_dir(), "server.log")

def get_asset_path(filename: str) -> str:
    """Resolves asset paths cleanly across development and PyInstaller."""
    # 1. PyInstaller onefile temporary extraction directory
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        candidate = os.path.join(sys._MEIPASS, "assets", filename)
        if os.path.exists(candidate):
            return candidate

    # 2. Next to executable (standalone / portable directory)
    exe_dir = os.path.dirname(os.path.abspath(sys.executable))
    candidate = os.path.join(exe_dir, "assets", filename)
    if os.path.exists(candidate):
        return candidate

    # 3. Standard development / source tree
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidate = os.path.join(base, "assets", filename)
    if os.path.exists(candidate):
        return candidate

    return os.path.join(base, "assets", filename)

