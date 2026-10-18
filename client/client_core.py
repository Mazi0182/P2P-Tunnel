r"""
P2P Tunnel Client Core Engine.
Stores persistent settings in C:\ProgramData\P2PTunnel\client_config.json.
Supports Direct IP:Port and Short Hex Codes.
"""

import asyncio
import json
import os
import socket
import sys
import time
from typing import Optional, Callable, List, Tuple

from core.crypto import PacketCipher, derive_key
from core.hwid import get_client_identity
from core.invite import parse_invite_code, normalize_server_key
from core.kcp import KCPPeer
from core.logger import client_logger
from core.paths import get_client_config_path
from core.protocol import Role
from core.puncher import UDPPuncher
from core.signaling import SignalingClient, get_room_id_from_code
from core.stun import get_public_endpoint
from core.tunnel import P2PTunnel, tune_tcp_socket, disable_udp_connreset, tune_udp_socket
from core.updater import DEFAULT_UPDATE_URL, APP_VERSION

DEFAULT_SECRET = "sec_p2p_default_fallback"
DEFAULT_TOKEN = "tok_p2p_player_fallback"
DEFAULT_LOCAL_DOMAIN = "baglanti.localhost"


class P2PMCClientCore:
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or get_client_config_path()
        self.config = self._load_config()

        self.room_secret = self.config.get("room_secret", DEFAULT_SECRET)
        self.auth_token = self.config.get("auth_token", DEFAULT_TOKEN)
        self.admin_key = self.config.get("admin_key", "").strip()
        self.local_game_port = self.config.get("local_game_port", 25565)
        self.local_ssh_port = self.config.get("local_ssh_port", 22)
        self.local_8443_port = self.config.get("local_8443_port", 8443)
        self.local_web_port = self.config.get("local_web_port", 9090)
        self.server_code = normalize_server_key(self.config.get("server_code", ""))
        self.config["server_code"] = self.server_code
        self.server_name = self.config.get("server_name", "Sunucu")
        self.active_service_port = int(self.local_game_port)
        self.active_connection_address = DEFAULT_LOCAL_DOMAIN

        raw_saved = list(self.config.get("saved_servers", []))
        self.saved_servers = []
        for s in raw_saved:
            item = dict(s)
            if item.get("code"):
                item["code"] = normalize_server_key(item["code"])
            self.saved_servers.append(item)
        self.config["saved_servers"] = self.saved_servers

        self.client_identity = get_client_identity()
        self.client_identity["version"] = APP_VERSION

        # Auto-migrate existing single server into saved_servers if empty
        if not self.saved_servers and self.server_code:
            self.saved_servers = [{
                "name": self.server_name or "Sunucu",
                "code": self.server_code,
                "admin_key": self.admin_key,
            }]
            self.config["saved_servers"] = self.saved_servers

        self.cipher = PacketCipher(derive_key(self.room_secret))
        self.sock: Optional[socket.socket] = None
        self.public_endpoint: Optional[tuple] = None
        self.peer_endpoint: Optional[tuple] = None
        self.tunnel: Optional[P2PTunnel] = None
        self.signaling: Optional[SignalingClient] = None
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.is_connected = False
        self.tcp_servers: list = []
        self._manual_disconnect: bool = False
        self._reconnect_attempts: int = 0
        self._max_reconnect_attempts: int = 5
        self._reconnect_task: Optional[asyncio.Task] = None

        # Event callbacks
        self.on_state_change: Optional[Callable[[str], None]] = None
        self.on_connected: Optional[Callable[[Role, float], None]] = None
        self.on_ping_update: Optional[Callable[[float], None]] = None
        self.on_error: Optional[Callable[[str], None]] = None
        self.on_disconnected: Optional[Callable[[], None]] = None

    def _load_config(self) -> dict:
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if not data.get("update_url"):
                        data["update_url"] = DEFAULT_UPDATE_URL
                    return data
            except Exception:
                pass
        return {
            "server_name": "",
            "server_code": "",
            "admin_key": "",
            "saved_servers": [],
            "local_game_port": 25565,
            "local_ssh_port": 22,
            "local_8443_port": 8443,
            "room_secret": DEFAULT_SECRET,
            "auth_token": DEFAULT_TOKEN,
            "update_url": DEFAULT_UPDATE_URL,
        }

    def save_server_config(
        self,
        server_name: str,
        server_code: str,
        admin_key: str = "",
        saved_servers: list = None,
    ):
        r"""Saves configured server name, code, optional admin key, and saved servers list permanently in C:\ProgramData\P2PTunnel."""
        clean_code = normalize_server_key(server_code)
        self.config["server_name"] = server_name
        self.config["server_code"] = clean_code
        self.config["admin_key"] = admin_key.strip()
        self.server_code = clean_code
        self.server_name = server_name
        self.admin_key = admin_key.strip()

        if saved_servers is not None:
            self.saved_servers = []
            for s in saved_servers:
                item = dict(s)
                if item.get("code"):
                    item["code"] = normalize_server_key(item["code"])
                self.saved_servers.append(item)
            self.config["saved_servers"] = self.saved_servers
        else:
            found = False
            for s in self.saved_servers:
                if normalize_server_key(s.get("code", "")) == clean_code:
                    s["name"] = server_name
                    s["code"] = clean_code
                    s["admin_key"] = admin_key.strip()
                    found = True
                    break
            if not found and clean_code:
                self.saved_servers.append({
                    "name": server_name,
                    "code": clean_code,
                    "admin_key": admin_key.strip(),
                })
            self.config["saved_servers"] = self.saved_servers

        code_to_parse = clean_code
        if "#" in code_to_parse:
            parts = code_to_parse.split("#", 1)
            code_to_parse = parts[0].strip()
            if parts[1].strip() and not self.admin_key:
                self.admin_key = parts[1].strip()
                self.config["admin_key"] = self.admin_key

        parsed = parse_invite_code(code_to_parse)
        if parsed:
            if "sec" in parsed:
                self.config["room_secret"] = parsed["sec"]
                self.room_secret = parsed["sec"]
                self.cipher = PacketCipher(derive_key(self.room_secret))
            if "tok" in parsed and not self.admin_key:
                self.config["auth_token"] = parsed["tok"]
                self.auth_token = parsed["tok"]

        try:
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=2)
            client_logger.debug(f"Ayarlar kaydedildi: {self.config_path}")
        except Exception as e:
            client_logger.error(f"Kayıt hatası: {e}")

    def setup_socket(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        disable_udp_connreset(self.sock)
        tune_udp_socket(self.sock)
        self.sock.bind(("0.0.0.0", 0))
        client_logger.debug(f"Yerel UDP soketi bağlandı: port {self.sock.getsockname()[1]}")

    def discover_public_endpoint(self) -> tuple:
        client_logger.debug("STUN üzerinden dış IP ve Port keşfediliyor...")
        try:
            endpoint = get_public_endpoint(self.sock, timeout=1.5)
        except Exception as e:
            client_logger.warning(f"STUN çözümü başarısız: {e}")
            endpoint = None

        if not endpoint:
            endpoint = ("127.0.0.1", self.sock.getsockname()[1])
            client_logger.warning(f"STUN çözülemedi, yerel fallback: {endpoint}")
        else:
            client_logger.debug(f"STUN ile Dış Public Endpoint Çözüldü: {endpoint[0]}:{endpoint[1]}")
        self.public_endpoint = endpoint
        return endpoint

    async def connect_async(self):
        """Asynchronous connection flow."""
        self._manual_disconnect = False
        try:
            client_logger.info(f"Sunucuya bağlanılıyor: {self.server_code}")
            if not self.server_code:
                raise ValueError("Bağlantı kodu tanımlanmamış.")

            code_to_parse = self.server_code
            if "#" in code_to_parse:
                parts = code_to_parse.split("#", 1)
                code_to_parse = parts[0].strip()
                if parts[1].strip() and not self.admin_key:
                    self.admin_key = parts[1].strip()

            parsed = parse_invite_code(code_to_parse)
            if not parsed:
                raise ValueError(f"Geçersiz bağlantı kodu: {self.server_code}")

            self._set_state("Ağ hazırlanıyor...")
            self.setup_socket()
            self.discover_public_endpoint()

            self.room_secret = parsed.get("sec", self.room_secret)
            if self.admin_key:
                self.auth_token = self.admin_key
                client_logger.info("Yönetici anahtarı devrede (ADMIN modu talep ediliyor)...")
            else:
                self.auth_token = parsed.get("tok") or self.auth_token or self.config.get("auth_token") or DEFAULT_TOKEN
            self.cipher = PacketCipher(derive_key(self.room_secret))

            targets: List[Tuple[str, int]] = []
            if parsed.get("ip") and parsed.get("port"):
                targets.append((parsed["ip"], int(parsed["port"])))

            def get_local_lan_ip():
                try:
                    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    s.connect(("8.8.8.8", 80))
                    ip = s.getsockname()[0]
                    s.close()
                    return ip
                except Exception:
                    return "127.0.0.1"

            my_lan_ip = get_local_lan_ip()

            # Start encrypted HTTPS signaling
            room_id = parsed.get("room") or get_room_id_from_code(self.server_code)
            import secrets
            my_client_id = secrets.token_hex(4)
            client_logger.debug(f"HTTPS sinyalleşme başlatılıyor: oda={room_id} (Client ID={my_client_id})")
            self.signaling = SignalingClient(room_id, self.room_secret)
            server_confirmed_lock = False
            remote_lock_endpoint: Optional[Tuple[str, int]] = None
            server_endpoint_received = False
            is_same_lan = False
            connect_start_ts = time.time()

            def _on_server_signal(msg: dict):
                nonlocal server_confirmed_lock, remote_lock_endpoint, server_endpoint_received, is_same_lan
                msg_ts = msg.get("ts", 0)
                if msg_ts and (time.time() - msg_ts > 60.0):
                    return

                mtype = msg.get("type")
                cid = msg.get("client_id")
                # If message is specifically targeted to another client, ignore it
                if cid and cid != my_client_id:
                    return
                # Ignore stale server_locked messages created before our connection attempt started
                if mtype == "server_locked" and not cid and msg_ts and msg_ts < (connect_start_ts - 0.5):
                    return

                if mtype in ("server_hello", "server_locked"):
                    sip = msg.get("ip")
                    sport = msg.get("port")
                    slan = msg.get("lan_ip")
                    lport = msg.get("local_port")

                    # Check if client and server share the exact same public IP (Local LAN or CGNAT / Shared VPN)
                    is_same_lan = bool(sip and self.public_endpoint and sip == self.public_endpoint[0])
                    is_same_pc = bool(is_same_lan and slan and slan == my_lan_ip)

                    if is_same_lan:
                        # Local LAN connection: add direct LAN addresses
                        if is_same_pc and lport:
                            cand_pc = ("127.0.0.1", int(lport))
                            if cand_pc not in targets:
                                targets.insert(0, cand_pc)
                        if slan and lport:
                            cand_lan = (slan, int(lport))
                            if cand_lan not in targets:
                                targets.insert(0, cand_lan)

                    # ALWAYS also add WAN STUN endpoint to support CGNAT & VPN peers sharing the same external IP!
                    if sip and sport:
                        cand_wan = (sip, int(sport))
                        for old in list(targets):
                            if old[0] == sip and old[1] not in (int(sport), int(lport or 0)):
                                targets.remove(old)
                        if cand_wan not in targets:
                            targets.append(cand_wan)

                    # Also target server UDP port on public IP (e.g. 25566) in case router has port-forwarding
                    if sip and lport and int(lport) != int(sport):
                        cand_direct = (sip, int(lport))
                        if cand_direct not in targets:
                            targets.append(cand_direct)

                    server_endpoint_received = True

                    if mtype == "server_locked":
                        server_confirmed_lock = True
                        if is_same_lan and slan and lport:
                            remote_lock_endpoint = (slan, int(lport))
                        elif sip and sport:
                            remote_lock_endpoint = (sip, int(sport))
                        client_logger.debug(f"Sunucu kilidi doğrulandı: {remote_lock_endpoint}")

            self.signaling.start_listening(_on_server_signal)

            # Check existing server_hello messages in room immediately (fast-path discovery)
            for prev_msg in self.signaling.poll_messages(timeout=1.0):
                if prev_msg.get("type") == "server_hello":
                    _on_server_signal(prev_msg)

            # Notify server of our endpoint via encrypted signaling
            client_logger.debug(f"Sinyalleşme üzerinden istemci bilgisi gönderiliyor: {self.public_endpoint[0]}:{self.public_endpoint[1]} (Yerel LAN: {my_lan_ip})")
            self.signaling.publish_nowait("client_hello", {
                "client_id": my_client_id,
                "ip": self.public_endpoint[0],
                "port": self.public_endpoint[1],
                "lan_ip": my_lan_ip,
                "local_port": self.sock.getsockname()[1],
            })

            # If targets not yet known, wait for server endpoint from signaling
            if not targets:
                self._set_state("Sunucu aranıyor...")
                for poll_step in range(40):
                    if server_endpoint_received or targets:
                        break
                    if poll_step % 4 == 0:
                        self.signaling.publish_nowait("client_hello", {
                            "client_id": my_client_id,
                            "ip": self.public_endpoint[0],
                            "port": self.public_endpoint[1],
                            "lan_ip": my_lan_ip,
                            "local_port": self.sock.getsockname()[1],
                        })
                    await asyncio.sleep(0.3)

            if not targets:
                raise ConnectionError("Sunucu çevrimdışı veya anahtar geçersiz! Lütfen sunucunun açık olduğundan emin olun.")

            client_logger.debug(f"Keşfedilen hedef sunucu adresleri: {targets}")
            self._set_state("Bağlantı kuruluyor...")

            self.sock.setblocking(False)
            punched = False
            syn_pkt = self.cipher.encrypt(b"P2P_TUN_PUNCH_SYN")
            ack_pkt = self.cipher.encrypt(b"P2P_TUN_PUNCH_ACK")

            # Build punch candidate list with port deltas for WAN Symmetric NAT penetration
            punch_candidates = list(targets)
            for cand_ip, cand_port in list(targets):
                if cand_ip != "127.0.0.1" and not cand_ip.startswith("192.168.") and not cand_ip.startswith("10."):
                    for delta in (-2, -1, 1, 2, 3):
                        dp = cand_port + delta
                        if 1024 <= dp <= 65535:
                            cand = (cand_ip, dp)
                            if cand not in punch_candidates:
                                punch_candidates.append(cand)

            for attempt in range(120):
                # Probe all candidates (LAN direct and WAN STUN in parallel)
                for target in list(punch_candidates):
                    try:
                        self.sock.sendto(syn_pkt, target)
                    except OSError:
                        pass

                for _ in range(5):
                    try:
                        data, addr = self.sock.recvfrom(2048)
                        dec = self.cipher.decrypt(data)
                        if dec in (b"P2P_TUN_PUNCH_SYN", b"P2P_TUN_PUNCH_ACK"):
                            for _ in range(4):
                                self.sock.sendto(ack_pkt, addr)
                            punched = True
                            self.peer_endpoint = addr
                            client_logger.debug(f"UDP delme sinyali kilitlendi (tur {attempt}): {addr}")
                            break
                    except (BlockingIOError, OSError):
                        pass
                    await asyncio.sleep(0.02)

                if punched:
                    break

                if server_confirmed_lock:
                    if remote_lock_endpoint:
                        self.peer_endpoint = remote_lock_endpoint
                    elif targets:
                        self.peer_endpoint = targets[0]
                    for _ in range(4):
                        try:
                            self.sock.sendto(ack_pkt, self.peer_endpoint)
                        except OSError:
                            pass
                    break

                await asyncio.sleep(0.05)

            if self.signaling:
                self.signaling.stop()
                self.signaling = None

            if not self.peer_endpoint:
                if remote_lock_endpoint:
                    self.peer_endpoint = remote_lock_endpoint
                elif targets:
                    self.peer_endpoint = targets[0]
                else:
                    raise ConnectionError("Sunucu adresi bulunamadı!")

            client_logger.debug(f"P2PTunnel başlatılıyor... Hedef: {self.peer_endpoint}")
            self._set_state("Güvenli tünel kuruluyor...")
            self.tunnel = P2PTunnel(
                udp_sock=self.sock,
                peer_addr=self.peer_endpoint,
                cipher=self.cipher,
                conv_id=2026,
                is_server=False,
                auth_token=self.auth_token,
                client_identity=self.client_identity,
                room_secret=self.room_secret,
            )

            self.tunnel.on_ping_update = self._handle_ping_update
            self.tunnel.on_state_change = self._set_state
            self.tunnel.on_disconnect = self._on_remote_disconnect

            tunnel_task = asyncio.create_task(self.tunnel.start())

            client_logger.debug(f"Kimlik doğrulama gönderiliyor... Kullanıcı={self.client_identity.get('username')}")
            for auth_attempt in range(80):
                if self.tunnel.authenticated:
                    client_logger.info(f"Tünel bağlantısı kuruldu. Yetki: {self.tunnel.peer_role.name}")
                    break
                self.tunnel.send_auth()
                await asyncio.sleep(0.12)

            if not self.tunnel.authenticated:
                fail_reason = getattr(self.tunnel, "auth_fail_reason", "")
                if fail_reason:
                    client_logger.error(f"Kimlik doğrulama reddedildi: {fail_reason}")
                    raise ConnectionError(fail_reason)
                client_logger.error("Sunucuya ulaşılamadı veya sunucu kapalı.")
                raise ConnectionError("Sunucuya ulaşılamadı veya sunucu kapalı.")

            self.is_connected = True
            self._reconnect_attempts = 0
            self.disconnect_event = asyncio.Event()

            assigned_port = int(getattr(self.tunnel, "server_assigned_port", 0) or self.local_game_port or 25565)
            assigned_addr = str(getattr(self.tunnel, "server_assigned_address", "") or DEFAULT_LOCAL_DOMAIN).strip()
            self.active_service_port = assigned_port
            if assigned_port != 25565 and ":" not in assigned_addr:
                self.active_connection_address = f"{assigned_addr}:{assigned_port}"
            else:
                self.active_connection_address = assigned_addr

            self._set_state("Bağlı")

            await self._start_local_tcp_proxies()

            if self.on_connected:
                self.on_connected(self.tunnel.peer_role, self.tunnel.current_rtt_ms)

            # Keep loop and proxies alive until disconnect is requested
            await self.disconnect_event.wait()

        except Exception as e:
            client_logger.error(f"Bağlantı akışı sırasında istisna: {e}")
            if self.signaling:
                self.signaling.stop()
                self.signaling = None
            await self._cleanup_resources()
            self.is_connected = False
            self._set_state(f"Hata: {str(e)}")
            if self.on_error:
                self.on_error(str(e))

    async def _cleanup_resources(self):
        """Immediately closes and releases all local proxies, sockets, and tunnel resources."""
        if self.tunnel:
            try:
                await self.tunnel.stop()
            except Exception:
                pass
            self.tunnel = None

        if hasattr(self, "tcp_servers"):
            for srv in list(self.tcp_servers):
                try:
                    srv.close()
                    await srv.wait_closed()
                except Exception:
                    pass
            self.tcp_servers.clear()

        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None

        if hasattr(self, "disconnect_event") and self.disconnect_event:
            self.disconnect_event.set()

    def _on_remote_disconnect(self):
        if self.loop and self.loop.is_running():
            asyncio.run_coroutine_threadsafe(self._handle_unexpected_disconnect(), self.loop)

    async def _handle_unexpected_disconnect(self):
        """Handles remote or network-induced disconnect with automatic reconnection."""
        await self._cleanup_resources()
        if self.signaling:
            self.signaling.stop()
            self.signaling = None
        self.is_connected = False

        if not self._manual_disconnect and self._reconnect_attempts < self._max_reconnect_attempts:
            self._reconnect_attempts += 1
            retry_msg = f"Bağlantı koptu. Yeniden bağlanılıyor ({self._reconnect_attempts}/{self._max_reconnect_attempts})..."
            self._set_state(retry_msg)
            client_logger.info(f"[AUTO-RECONNECT] {retry_msg}")
            await asyncio.sleep(2.0)
            if not self._manual_disconnect:
                self._reconnect_task = asyncio.create_task(self.connect_async())
        else:
            self._set_state("Bağlantı kesildi.")
            if self.on_disconnected:
                self.on_disconnected()

    async def disconnect_async(self, reason: str = "Bağlı Değil"):
        """Gracefully disconnects tunnel and shuts down proxies."""
        self._manual_disconnect = True
        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()
            self._reconnect_task = None

        if not self.is_connected and not self.tunnel:
            return

        self.is_connected = False
        self._set_state("Bağlantı kesiliyor...")

        if self.tunnel:
            try:
                self.tunnel.send_disconnect()
            except Exception:
                pass

        await self._cleanup_resources()
        self._set_state(reason)
        if self.on_disconnected:
            self.on_disconnected()

    async def _start_local_tcp_proxies(self):
        self.tcp_servers = []
        target_port = int(getattr(self, "active_service_port", self.local_game_port) or 25565)
        server_svc = await asyncio.start_server(
            lambda r, w, p=target_port: self.tunnel.open_client_stream(p, r, w),
            "127.0.0.1",
            target_port,
        )
        self.tcp_servers.append(server_svc)
        client_logger.debug(f"Yerel TCP servis vekili dinleniyor: 127.0.0.1:{target_port}")

        if self.tunnel.peer_role == Role.ADMIN:
            # 1. Admin SSH Proxy (Local 22 -> Remote 22)
            try:
                server_ssh = await asyncio.start_server(
                    lambda r, w: self.tunnel.open_client_stream(22, r, w),
                    "127.0.0.1",
                    self.local_ssh_port,
                )
                self.tcp_servers.append(server_ssh)
                client_logger.debug(f"Yönetici SSH yerel TCP proxy dinliyor: 127.0.0.1:{self.local_ssh_port}")
            except Exception as e:
                client_logger.warning(f"SSH proxy port {self.local_ssh_port} açılamadı: {e}")

            # 2. Admin OpenWrt / Web UI Proxy (Local 80 & 8080 -> Remote 80)
            for web_port in (80, 8080):
                try:
                    server_web = await asyncio.start_server(
                        lambda r, w: self.tunnel.open_client_stream(80, r, w),
                        "127.0.0.1",
                        web_port,
                    )
                    self.tcp_servers.append(server_web)
                    client_logger.debug(f"OpenWrt Web Arayüzü proxy dinliyor: http://127.0.0.1:{web_port}")
                except Exception as e:
                    client_logger.warning(f"Web proxy port {web_port} açılamadı: {e}")

            # 3. Admin HTTPS / Management Proxy (Local 8443 -> Remote 8443)
            try:
                server_8443 = await asyncio.start_server(
                    lambda r, w: self.tunnel.open_client_stream(8443, r, w),
                    "127.0.0.1",
                    self.local_8443_port,
                )
                self.tcp_servers.append(server_8443)
                client_logger.debug(f"Yönetici Port 8443 yerel TCP proxy dinliyor: https://127.0.0.1:{self.local_8443_port}")
            except Exception as e:
                client_logger.warning(f"Port 8443 proxy açılamadı: {e}")

            # 4. Admin Web Management Dashboard (Local 9090 -> Remote 9090)
            try:
                server_9090 = await asyncio.start_server(
                    lambda r, w: self.tunnel.open_client_stream(9090, r, w),
                    "127.0.0.1",
                    self.local_web_port,
                )
                self.tcp_servers.append(server_9090)
                client_logger.debug(f"Yönetici Web Paneli yerel proxy dinliyor: http://127.0.0.1:{self.local_web_port}")
            except Exception as e:
                client_logger.warning(f"Port {self.local_web_port} Web Paneli proxy açılamadı: {e}")

    def _set_state(self, state: str):
        if self.on_state_change:
            self.on_state_change(state)

    def _handle_ping_update(self, rtt: float):
        if self.on_ping_update:
            self.on_ping_update(rtt)

