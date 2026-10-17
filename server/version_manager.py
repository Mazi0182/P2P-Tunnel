"""
P2P Tunnel Version Manager & Strict Version Guard.
Ensures only clients running the latest released version are permitted to connect.
Automatically fetches the latest version manifest from Cloudflare R2 (https://updates.mazidev.xyz/version.json).
"""

import asyncio
import json
import logging
import re
import threading
import time
import urllib.request
import urllib.error
from typing import Optional, Tuple, Dict, Any

from core.updater import DEFAULT_UPDATE_URL, APP_VERSION

logger = logging.getLogger("P2P_VersionManager")


def parse_version(v: Optional[str]) -> tuple:
    """Parses semantic version string into a comparable tuple of integers."""
    if not v:
        return (0, 0, 0)
    cleaned = str(v).lstrip("v").strip()
    parts = []
    for token in re.split(r"[.\-_]", cleaned):
        try:
            parts.append(int(token))
        except ValueError:
            pass
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:4])


def compare_versions(v1: Optional[str], v2: Optional[str]) -> int:
    """
    Compares two semantic versions.
    Returns:
       -1 if v1 < v2
        0 if v1 == v2
        1 if v1 > v2
    """
    p1 = parse_version(v1)
    p2 = parse_version(v2)
    if p1 < p2:
        return -1
    elif p1 > p2:
        return 1
    return 0


class VersionManager:
    """
    Tracks and enforces the latest client version on the server.
    Caches the latest version fetched from R2 with automatic background polling.
    """

    def __init__(
        self,
        update_url: str = DEFAULT_UPDATE_URL,
        fallback_version: str = APP_VERSION,
        cache_ttl: float = 30.0,
        manual_min_version: Optional[str] = None
    ):
        self.update_url = update_url.strip() or DEFAULT_UPDATE_URL
        self.cached_latest_version: str = manual_min_version or fallback_version or "2.6"
        self.manual_min_version: Optional[str] = manual_min_version
        self.cache_ttl: float = cache_ttl
        self.last_fetch_time: float = 0.0
        self._lock = threading.Lock()
        self.last_error: Optional[str] = None

        # Fetch immediately in background on init
        self.refresh_sync()

    def set_manual_min_version(self, ver: Optional[str]):
        """Manually override or lock required version (e.g., via web panel). Set None for auto."""
        with self._lock:
            self.manual_min_version = ver.strip() if ver and ver.strip() and ver.strip().lower() != "auto" else None

    def refresh_sync(self, timeout: float = 3.5) -> Optional[str]:
        """Fetches the latest version manifest from Cloudflare R2 synchronously."""
        if not self.update_url or not self.update_url.startswith("http"):
            return None

        try:
            sep = "&" if "?" in self.update_url else "?"
            cache_buster_url = f"{self.update_url}{sep}_cb={int(time.time() * 1000)}"

            req = urllib.request.Request(
                cache_buster_url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) P2PTunnelServer/1.0",
                    "Cache-Control": "no-cache, no-store, max-age=0, must-revalidate",
                    "Pragma": "no-cache",
                }
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if resp.status == 200:
                    raw = resp.read().decode("utf-8")
                    data = json.loads(raw)
                    remote_ver = str(data.get("version", "")).strip()
                    if remote_ver:
                        with self._lock:
                            self.cached_latest_version = remote_ver
                            self.last_fetch_time = time.time()
                            self.last_error = None
                        logger.info(f"R2 en yeni istemci sürümü güncellendi: v{remote_ver}")
                        return remote_ver
        except Exception as e:
            with self._lock:
                self.last_error = str(e)
            logger.debug(f"Sürüm manifesti sorgulanamadı: {e}")

        return None

    def get_required_version(self, force_refresh: bool = False) -> str:
        """Returns the latest required version string."""
        with self._lock:
            if self.manual_min_version:
                return self.manual_min_version

            now = time.time()
            needs_refresh = force_refresh or (now - self.last_fetch_time > self.cache_ttl)

        if needs_refresh:
            self.refresh_sync()

        with self._lock:
            return self.cached_latest_version

    def check_client_version(self, client_version: Optional[str]) -> Tuple[bool, str, str]:
        """
        Validates client version against the latest required version.
        Returns:
            (is_allowed: bool, required_version: str, error_message: str)
        """
        required_ver = self.get_required_version()

        # Missing version: older client (legacy)
        if not client_version or not str(client_version).strip():
            return (
                False,
                required_ver,
                f"İstemciniz güncel değil! Sunucu en yeni sürümü (v{required_ver}) gerektiriyor. Lütfen istemcinizi güncelleyin."
            )

        client_ver = str(client_version).strip()

        # If client reports a newer version than cached, immediately check R2 to keep server in sync!
        if compare_versions(client_ver, required_ver) > 0 and not self.manual_min_version:
            refreshed = self.refresh_sync()
            if refreshed:
                required_ver = refreshed

        # Strict check: client must be >= required_version
        cmp_res = compare_versions(client_ver, required_ver)
        if cmp_res < 0:
            return (
                False,
                required_ver,
                f"İstemciniz güncel değil (Mevcut: v{client_ver}, Gerekli: v{required_ver})! Lütfen istemcinizi en yeni sürüme güncelleyin."
            )

        return (True, required_ver, "")

    async def refresh_loop(self):
        """Asynchronous background loop to periodically refresh the version from R2."""
        while True:
            try:
                await asyncio.sleep(45.0)
                await asyncio.to_thread(self.refresh_sync)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"Sürüm yenileme döngüsü hatası: {e}")
                await asyncio.sleep(10.0)
