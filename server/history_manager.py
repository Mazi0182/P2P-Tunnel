"""
P2P Tunnel Client Connection History Manager.
Tracks and stores persistent records of all authenticated users who have connected to the server.
Enables administrators to view offline/historical users and apply HWID bans even after disconnection.
"""

import os
import json
import time
import datetime
from typing import Dict, List, Optional, Any
from core.paths import get_server_config_path, get_app_data_dir


class ClientHistoryManager:
    """Manages persistent history of connected clients (online and offline)."""

    def __init__(self, config_dir: Optional[str] = None):
        if not config_dir:
            cfg_path = get_server_config_path()
            self.config_dir = os.path.dirname(os.path.abspath(cfg_path))
        else:
            self.config_dir = config_dir

        self.history_file = os.path.join(self.config_dir, "client_history.json")
        self._history: Dict[str, dict] = {}
        self.load_history()

    def load_history(self):
        """Loads client history from disk."""
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        self._history = data
                    elif isinstance(data, list):
                        self._history = {item.get("hwid") or item.get("username") or str(i): item for i, item in enumerate(data)}
            except Exception:
                self._history = {}
        else:
            self._history = {}

    def _save_history(self):
        """Saves history to JSON atomically."""
        try:
            os.makedirs(os.path.dirname(self.history_file), exist_ok=True)
            tmp_file = self.history_file + ".tmp"
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(self._history, f, indent=2, ensure_ascii=False)
            if os.path.exists(self.history_file):
                os.replace(tmp_file, self.history_file)
            else:
                os.rename(tmp_file, self.history_file)
        except Exception:
            pass

    def record_login(self, client_info: dict, peer_addr: tuple):
        """Records an authenticated client session."""
        username = str(client_info.get("username") or "Bilinmeyen").strip()
        hwid = str(client_info.get("hwid") or "").strip().upper()
        hwid_details = client_info.get("hwid_details") or {}
        ip = peer_addr[0] if peer_addr else ""
        port = peer_addr[1] if peer_addr else 0
        now_iso = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Determine unique key: prefer full HWID, fallback to username
        key = hwid if (hwid and len(hwid) > 10) else f"USER_{username.lower()}"

        existing = self._history.get(key)
        if not existing:
            # Check by username as well
            for k, v in list(self._history.items()):
                if v.get("username", "").lower() == username.lower():
                    existing = v
                    key = k
                    break

        first_seen = existing.get("first_seen", now_iso) if existing else now_iso
        login_count = (existing.get("login_count", 0) + 1) if existing else 1

        record = {
            "key": key,
            "username": username,
            "computer_name": client_info.get("computer_name") or (existing.get("computer_name") if existing else "-"),
            "hwid": hwid or (existing.get("hwid") if existing else "N/A"),
            "hwid_details": hwid_details or (existing.get("hwid_details") if existing else {}),
            "os": client_info.get("os") or (existing.get("os") if existing else "Bilinmiyor"),
            "version": client_info.get("version") or (existing.get("version") if existing else "-"),
            "ip": ip or (existing.get("ip") if existing else "-"),
            "port": port or (existing.get("port") if existing else 0),
            "peer_addr": f"{ip}:{port}" if ip else "-",
            "first_seen": first_seen,
            "last_seen": now_iso,
            "last_seen_ts": time.time(),
            "is_online": True,
            "login_count": login_count,
        }

        self._history[key] = record
        self._save_history()

    def record_disconnect(self, peer_addr: Optional[tuple] = None, hwid: Optional[str] = None, username: Optional[str] = None):
        """Marks client as offline upon disconnection."""
        now_iso = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        addr_str = f"{peer_addr[0]}:{peer_addr[1]}" if peer_addr else ""

        changed = False
        for key, record in self._history.items():
            match = False
            if addr_str and record.get("peer_addr") == addr_str:
                match = True
            elif hwid and record.get("hwid", "").upper() == hwid.upper():
                match = True
            elif username and record.get("username", "").lower() == username.lower():
                match = True

            if match:
                record["is_online"] = False
                record["last_seen"] = now_iso
                record["last_seen_ts"] = time.time()
                changed = True

        if changed:
            self._save_history()

    def seed_entry(self, entry: dict):
        """Adds or updates an entry manually (e.g. from memory or logs)."""
        username = entry.get("username", "Bilinmeyen")
        hwid = str(entry.get("hwid", "")).strip().upper()
        key = hwid if (hwid and len(hwid) > 10) else f"USER_{username.lower()}"

        existing = self._history.get(key)
        if existing:
            # Merge fields if new entry has richer data
            for k, v in entry.items():
                if v and (not existing.get(k) or existing.get(k) in ("-", "N/A", {})):
                    existing[k] = v
        else:
            if "first_seen" not in entry:
                entry["first_seen"] = entry.get("last_seen", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            if "login_count" not in entry:
                entry["login_count"] = 1
            if "is_online" not in entry:
                entry["is_online"] = False
            entry["key"] = key
            self._history[key] = entry
        self._save_history()

    def get_history(self, ban_manager: Optional[Any] = None) -> List[dict]:
        """Returns sorted list of all historical clients, with is_banned flag."""
        items = list(self._history.values())
        for it in items:
            it["is_banned"] = False
            if ban_manager:
                banned, _ = ban_manager.is_banned(hwid=it.get("hwid"), hwid_details=it.get("hwid_details"))
                it["is_banned"] = banned

        # Sort: online first, then latest last_seen
        items.sort(key=lambda x: (not x.get("is_online", False), x.get("last_seen_ts", 0)), reverse=True)
        return items
