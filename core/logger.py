r"""
P2P Tunnel High-Precision Disk & Console Logger.
Stores persistent, chronological forensic logs in C:\ProgramData\P2PTunnel\*.log.
"""

import datetime
import os
import sys
import threading
from typing import Optional

from core.paths import get_app_data_dir


class P2PLogger:
    def __init__(self, log_filename: str = "tunnel.log"):
        self.log_filename = log_filename
        self.log_dir = get_app_data_dir()
        self.log_path = os.path.join(self.log_dir, self.log_filename)
        self._file_lock = threading.Lock()
        self._listeners = []
        
        # Ensure Windows console supports UTF-8 characters cleanly
        if sys.platform == "win32":
            try:
                if hasattr(sys.stdout, "reconfigure"):
                    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
                if hasattr(sys.stderr, "reconfigure"):
                    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass

    def log(self, level: str, message: str):
        now_dt = datetime.datetime.now()
        now_str = now_dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        file_line = f"[{now_str}] [{level.upper()}] {message}\n"

        # Console print: strictly INFO, WARN, ERROR (DEBUG never pollutes console)
        # Calm, compact, professional timestamp [HH:MM:SS]
        if level.upper() in ("INFO", "WARN", "ERROR"):
            time_str = now_dt.strftime("%H:%M:%S")
            console_line = f"[{time_str}] [{level.upper()}] {message}\n"
            try:
                sys.stdout.write(console_line)
                sys.stdout.flush()
            except Exception:
                pass

        # File append: All levels with full forensic timestamp
        try:
            with self._file_lock:
                with open(self.log_path, "a", encoding="utf-8", errors="replace") as f:
                    f.write(file_line)
                    f.flush()
        except Exception:
            pass

        # Dispatch to active listeners (e.g. Web Admin Console)
        for cb in list(self._listeners):
            try:
                cb(message)
            except Exception:
                pass

    def add_listener(self, callback):
        if callback not in self._listeners:
            self._listeners.append(callback)

    def remove_listener(self, callback):
        if callback in self._listeners:
            self._listeners.remove(callback)

    def info(self, msg: str):
        self.log("INFO", msg)

    def debug(self, msg: str):
        self.log("DEBUG", msg)

    def warning(self, msg: str):
        self.log("WARN", msg)

    def warn(self, msg: str):
        self.log("WARN", msg)

    def error(self, msg: str):
        self.log("ERROR", msg)


# Pre-configured loggers for Client and Server
client_logger = P2PLogger("client.log")
server_logger = P2PLogger("server.log")

