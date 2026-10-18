"""
P2P Tunnel Ban Manager & Hardware Access Firewall.
Stores and validates hardware bans persistently in bans.json.
Enforces multi-factor hardware matching:
- Composite HWID
- Motherboard UUID
- Windows MachineGuid
- Disk Volume Serial
Note: Windows username is purely informative and is NOT used as a standalone ban filter.
"""

import os
import json
import time
import uuid
import datetime
from typing import Dict, List, Optional, Tuple, Any
from core.paths import get_server_config_path


class BanManager:
    """Manages persistent hardware bans."""

    def __init__(self, config_dir: Optional[str] = None):
        if not config_dir:
            cfg_path = get_server_config_path()
            self.config_dir = os.path.dirname(os.path.abspath(cfg_path))
        else:
            self.config_dir = config_dir

        self.bans_file = os.path.join(self.config_dir, "bans.json")
        self._bans: Dict[str, dict] = {}
        self.load_bans()

    def load_bans(self):
        """Loads bans from bans.json file."""
        if os.path.exists(self.bans_file):
            try:
                with open(self.bans_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        self._bans = data
                    elif isinstance(data, list):
                        self._bans = {b.get("id", str(i)): b for i, b in enumerate(data)}
            except Exception:
                self._bans = {}
        else:
            self._bans = {}

    def _save_bans(self):
        """Saves bans dictionary to bans.json atomically."""
        try:
            os.makedirs(os.path.dirname(self.bans_file), exist_ok=True)
            tmp_file = self.bans_file + ".tmp"
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(self._bans, f, indent=2, ensure_ascii=False)
            if os.path.exists(self.bans_file):
                os.replace(tmp_file, self.bans_file)
            else:
                os.rename(tmp_file, self.bans_file)
        except Exception:
            pass

    def is_banned(self, hwid: Optional[str] = None, hwid_details: Optional[dict] = None) -> Tuple[bool, Optional[dict]]:
        """
        Checks if the connecting client matches any active ban record.
        Multi-component matching:
        - HWID
        - Motherboard UUID
        - Windows MachineGuid
        - Volume Serial
        - Persistent Device ID
        """
        hwid = (hwid or "").strip()
        details = hwid_details if isinstance(hwid_details, dict) else {}

        mb_uuid = str(details.get("motherboard_uuid") or "").strip()
        m_guid = str(details.get("machine_guid") or "").strip()
        vol_serial = str(details.get("volume_serial") or "").strip()
        dev_id = str(details.get("device_id") or "").strip()

        # If both HWID is invalid/empty (<12 chars) and all details are empty,
        # return False safely. (Strict rejection happens at acl.py)
        if (not hwid or len(hwid) < 12) and not (mb_uuid or m_guid or vol_serial or dev_id):
            return False, None

        for ban_id, record in self._bans.items():
            b_hwid = str(record.get("hwid") or "").strip()
            b_mb_uuid = str(record.get("motherboard_uuid") or "").strip()
            b_m_guid = str(record.get("machine_guid") or "").strip()
            b_vol_serial = str(record.get("volume_serial") or "").strip()
            b_dev_id = str(record.get("device_id") or "").strip()

            # 1. Exact or prefix composite HWID match (strictly requiring >= 12 chars)
            if hwid and len(hwid) >= 12 and b_hwid and len(b_hwid) >= 12:
                clean_b_hwid = b_hwid.rstrip(".")
                if hwid.upper() == b_hwid.upper():
                    return True, record
                # Prefix match if ban record is a prefix (e.g. from logs HWID-XXXX-XXXX...)
                if (b_hwid.endswith("...") or len(clean_b_hwid) < 24) and len(clean_b_hwid) >= 12:
                    if hwid.upper().startswith(clean_b_hwid.upper()):
                        return True, record

            # 2. Motherboard UUID match (ignores generic "Default string" or empty)
            if mb_uuid and b_mb_uuid and len(mb_uuid) > 8 and mb_uuid.lower() not in (
                "default string", "none", "unknown", "to be filled by o.e.m."
            ):
                if mb_uuid.upper() == b_mb_uuid.upper():
                    return True, record

            # 3. Windows MachineGuid match
            if m_guid and b_m_guid and len(m_guid) > 12:
                if m_guid.upper() == b_m_guid.upper():
                    return True, record

            # 4. Volume serial match (if both non-empty)
            if vol_serial and b_vol_serial and len(vol_serial) > 4:
                if vol_serial.upper() == b_vol_serial.upper():
                    return True, record

            # 5. Persistent Device ID match
            if dev_id and b_dev_id and len(dev_id) >= 16:
                if dev_id.upper() == b_dev_id.upper():
                    return True, record

        return False, None

    def ban(
        self,
        hwid: str,
        hwid_details: Optional[dict] = None,
        username: str = "",
        reason: str = "Yönetici tarafından yasaklandı",
        banned_by: str = "Yönetici"
    ) -> dict:
        """Creates or updates a ban record."""
        details = hwid_details if isinstance(hwid_details, dict) else {}
        ban_id = f"ban_{uuid.uuid4().hex[:8]}"
        now_iso = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        record = {
            "id": ban_id,
            "hwid": (hwid or "").strip().upper(),
            "motherboard_uuid": str(details.get("motherboard_uuid") or "").strip().upper(),
            "motherboard_product": str(details.get("motherboard_product") or "").strip(),
            "machine_guid": str(details.get("machine_guid") or "").strip().upper(),
            "volume_serial": str(details.get("volume_serial") or "").strip().upper(),
            "mac": str(details.get("mac") or "").strip().upper(),
            "device_id": str(details.get("device_id") or "").strip().upper(),
            "username": username or "Bilinmeyen",
            "reason": reason.strip() or "Yönetici tarafından yasaklandı",
            "banned_at": now_iso,
            "banned_by": banned_by,
        }

        # Check if an existing ban for this HWID exists, update it if so
        existing_key = None
        for k, v in self._bans.items():
            if v.get("hwid") == record["hwid"] or (
                record["motherboard_uuid"] and v.get("motherboard_uuid") == record["motherboard_uuid"]
            ):
                existing_key = k
                break

        target_id = existing_key or ban_id
        record["id"] = target_id
        self._bans[target_id] = record
        self._save_bans()
        return record

    def unban(self, identifier: str) -> bool:
        """
        Removes ban by ban_id, hwid, or motherboard_uuid.
        Returns True if a ban was found and removed.
        """
        identifier = (identifier or "").strip().upper()
        if not identifier:
            return False

        to_delete = []
        for ban_id, record in self._bans.items():
            if (
                ban_id.upper() == identifier or
                record.get("hwid", "").upper() == identifier or
                record.get("motherboard_uuid", "").upper() == identifier
            ):
                to_delete.append(ban_id)

        if to_delete:
            for k in to_delete:
                self._bans.pop(k, None)
            self._save_bans()
            return True
        return False

    def get_bans(self) -> List[dict]:
        """Returns list of active bans, sorted newest first."""
        bans_list = list(self._bans.values())
        bans_list.sort(key=lambda x: x.get("banned_at", ""), reverse=True)
        return bans_list
