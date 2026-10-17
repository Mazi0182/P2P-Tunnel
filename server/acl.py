"""
P2P_MC Server Access Control & Port Isolation Firewall.
Enforces strict role boundaries and hardware ban policies:
- HWID Ban Enforcement via BanManager.
- PLAYER: Strictly limited to port 25565 only. All other ports blocked and dropped.
- ADMIN : Unrestricted access (SSH port 22, Web Dashboard 9090, management ports).
- Graceful Fallback: Invalid admin keys automatically degrade to PLAYER role instead of dropping connection.
"""

import hmac
from typing import Optional, Set, Any
from core.protocol import Role
from server.ban_manager import BanManager


class ServerACL:
    """Access Control List and Port Firewall for P2P_MC."""

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

    def add_player_token(self, token: str):
        if token:
            self.player_tokens.add(token)

    def authenticate(
        self,
        token: str,
        hwid: Optional[str] = None,
        hwid_details: Optional[dict] = None,
        client_version: Optional[str] = None
    ) -> Role:
        """
        Verifies authentication, checks bans, validates client version, and assigns Role.
        - If client HWID or hardware components match ban list -> raises PermissionError('BANNED:...')
        - If client is not on the latest version -> raises PermissionError('OUTDATED:...')
        - If token matches admin_secret -> returns Role.ADMIN
        - If token is invalid or does not match admin_secret -> falls back to Role.PLAYER (graceful fallback)
        """
        # 1. Enforce HWID & Multi-Hardware Ban Check
        banned, ban_rec = self.ban_manager.is_banned(hwid=hwid, hwid_details=hwid_details)
        if banned:
            reason = ban_rec.get("reason", "Cihazınız sunucu yöneticisi tarafından yasaklanmıştır.")
            raise PermissionError(f"BANNED:{reason}")

        # 2. Strict Latest Client Version Check
        if self.version_manager:
            ok, req_ver, err_reason = self.version_manager.check_client_version(client_version)
            if not ok:
                raise PermissionError(f"OUTDATED:{req_ver}:{err_reason}")

        token = token or ""

        # 3. Strict Constant-Time Admin Key Verification
        if self.admin_secret and hmac.compare_digest(token, self.admin_secret):
            return Role.ADMIN

        # 3. Graceful Fallback:
        # If admin key is missing or incorrect, client is NOT disconnected.
        # Fallback to standard PLAYER role (strictly quarantined to game port 25565).
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
