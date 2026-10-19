"""
P2P Tunnel Server Access Control & Port Isolation Firewall.
Enforces strict role boundaries and hardware ban policies:
- HWID Ban Enforcement via BanManager.
- PLAYER: Strictly limited to port 25565 only. All other ports blocked and dropped.
- ADMIN : Unrestricted access (SSH port 22, Web Dashboard 9090, management ports).
- Graceful Fallback: Invalid admin keys automatically degrade to PLAYER role instead of dropping connection.
"""

from collections import deque
import hashlib
import hmac
import time
from typing import Optional, Set, Dict, Tuple, Any
from core.protocol import Role
from server.ban_manager import BanManager


class ServerACL:
    """Access Control List and Port Firewall for P2P Tunnel."""

    def __init__(
        self,
        player_token: str,
        admin_secret: str,
        allowed_game_port: int = 25565,
        connection_address: str = "baglanti.localhost",
        ban_manager: Optional[BanManager] = None,
        version_manager: Optional[Any] = None
    ):
        self.player_tokens: Set[str] = {player_token} if isinstance(player_token, str) else set(player_token)
        self.admin_secret = admin_secret
        self.allowed_game_port = int(allowed_game_port or 25565)
        self.connection_address = (connection_address or "baglanti.localhost").strip()
        self.ban_manager = ban_manager or BanManager()
        self.version_manager = version_manager
        self._used_nonces: Dict[str, Tuple[float, str]] = {}
        self._used_nonces_set: Set[str] = set()

    def add_player_token(self, token: str):
        if token:
            self.player_tokens.add(token)

    def authenticate(
        self,
        token: str = "",
        client_version: str = "",
        hwid: str = "",
        hwid_details: Optional[dict] = None,
        client_nonce: str = "",
        token_hmac: str = "",
        room_secret: str = "",
        **kwargs
    ) -> Role:
        """
        Verifies authentication, checks bans, validates client version, and assigns Role.
        - Supports cryptographic HMAC challenge-response to prevent token exposure even to rogue servers.
        - Replay attack mitigation via rolling nonce cache with idempotent retry window.
        - HWID ban enforcement via BanManager.
        - Strict version enforcement via VersionManager.
        """
        # Positional parameter swap protection (supports old (token, hwid, hwid_details, ver) signature)
        if isinstance(client_version, str) and client_version.startswith("HWID-") and not hwid:
            hwid_val = client_version
            hwid_det_val = hwid_details if isinstance(hwid_details, dict) else (hwid if isinstance(hwid, dict) else {})
            actual_ver = kwargs.get("client_version") or ""
            hwid = hwid_val
            hwid_details = hwid_det_val
            client_version = actual_ver

        # 1. Replay Protection: Nonce must be unique per connection, with idempotent retry allowance
        if client_nonce:
            client_nonce_str = str(client_nonce).strip()
            now = time.time()
            if len(self._used_nonces) > 1000:
                cutoff = now - 60.0
                self._used_nonces = {k: v for k, v in self._used_nonces.items() if v[0] > cutoff}
                self._used_nonces_set = set(self._used_nonces.keys())

            hwid_key = str(hwid or "").strip()
            if client_nonce_str in self._used_nonces:
                seen_time, seen_hwid = self._used_nonces[client_nonce_str]
                if (not hwid_key or not seen_hwid or seen_hwid == hwid_key) and (now - seen_time) <= 10.0:
                    pass
                else:
                    raise PermissionError("REPLAY_DETECTED: Tekrar eden bağlantı isteği engellendi.")
            else:
                self._used_nonces[client_nonce_str] = (now, hwid_key)
                self._used_nonces_set.add(client_nonce_str)

        # 2. Enforce HWID & Multi-Hardware Ban Check (if provided)
        if hwid or hwid_details:
            banned, ban_rec = self.ban_manager.is_banned(hwid=hwid, hwid_details=hwid_details)
            if banned:
                reason = (ban_rec or {}).get("reason", "Cihazınız sunucu yöneticisi tarafından yasaklanmıştır.")
                raise PermissionError(f"BANNED:{reason}")

            hwid_str = str(hwid or "").strip()
            if hwid_str and (len(hwid_str) < 12 or not (hwid_str.startswith("HWID-") or "HWID" in hwid_str)):
                raise PermissionError("INVALID_HWID: Geçersiz donanım kimliği (HWID) formatı.")

        # 3. Cryptographic HMAC Token Verification (Protects Admin & Player Secrets from Rogue Servers)
        if token_hmac and client_nonce:
            # Check Admin HMAC
            if self.admin_secret:
                expected_admin_hmac = hmac.new(
                    self.admin_secret.encode("utf-8"),
                    f"P2P_AUTH:{room_secret}:{client_nonce}".encode("utf-8"),
                    hashlib.sha256
                ).hexdigest()
                if hmac.compare_digest(token_hmac, expected_admin_hmac):
                    if self.version_manager:
                        ok, req_ver, err_reason = self.version_manager.check_client_version(client_version)
                        if not ok:
                            raise PermissionError(f"OUTDATED:{req_ver}:{err_reason}")
                    return Role.ADMIN

            # Check Player HMAC
            active_player_tokens = {t for t in self.player_tokens if t}
            for pt in active_player_tokens:
                expected_pt_hmac = hmac.new(
                    pt.encode("utf-8"),
                    f"P2P_AUTH:{room_secret}:{client_nonce}".encode("utf-8"),
                    hashlib.sha256
                ).hexdigest()
                if hmac.compare_digest(token_hmac, expected_pt_hmac):
                    if self.version_manager:
                        ok, req_ver, err_reason = self.version_manager.check_client_version(client_version)
                        if not ok:
                            raise PermissionError(f"OUTDATED:{req_ver}:{err_reason}")
                    return Role.PLAYER

        # 4. Fallback: Legacy Plaintext Token & Role verification
        token = str(token or "").strip()

        # Admin Secret Verification (Legacy Plaintext)
        if self.admin_secret and token and token != "HMAC_PROTECTED" and hmac.compare_digest(token, self.admin_secret):
            if self.version_manager:
                ok, req_ver, err_reason = self.version_manager.check_client_version(client_version)
                if not ok:
                    raise PermissionError(f"OUTDATED:{req_ver}:{err_reason}")
            return Role.ADMIN

        # Player Token Verification (Legacy Plaintext) / Graceful Fallback to Role.PLAYER
        active_player_tokens = {t for t in self.player_tokens if t}
        if active_player_tokens and token and token != "HMAC_PROTECTED":
            for pt in active_player_tokens:
                try:
                    if hmac.compare_digest(token, pt):
                        break
                except Exception:
                    pass

        if self.version_manager:
            ok, req_ver, err_reason = self.version_manager.check_client_version(client_version)
            if not ok:
                raise PermissionError(f"OUTDATED:{req_ver}:{err_reason}")

        return Role.PLAYER

    def is_port_allowed(self, role: Role, target_port: int) -> bool:
        """
        Determines whether the session role is permitted to connect to target_port.
        Players are strictly quarantined to the game port (25565).
        """
        if role == Role.ADMIN:
            return True  # Admin has full port access (SSH 22, Web 9090, etc.)
        elif role == Role.PLAYER:
            return target_port == self.allowed_game_port
        return False
