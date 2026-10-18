r"""
P2P Tunnel Server Daemon.
Headless background daemon for Ubuntu Server, OpenWrt (Pi 4), and Windows.
Stores config persistently in C:\ProgramData\P2PTunnel.
Displays clean, human-friendly short connection codes.
"""

import asyncio
import json
import os
import socket
import subprocess
import sys
import secrets
import string
import time
from typing import Optional

from core.crypto import PacketCipher, derive_key
from core.invite import ip_port_to_short_code, derive_room_credentials
from core.kcp import KCPPeer
from core.logger import server_logger
from core.paths import get_server_config_path
from core.signaling import SignalingClient, get_room_id_from_code
from core.stun import get_public_endpoint, parse_stun_response, create_stun_request
from core.tunnel import P2PTunnel, disable_udp_connreset, tune_udp_socket
from server.acl import ServerACL
from server.web_panel import WebAdminPanel

DEFAULT_SECRET = "P2P_SHARED_SECRET_2026"
DEFAULT_TOKEN = "P2P_PLAYER_SECRET_2026"


def ensure_virtual_ip_subnet():
    """Configures 100.0.0.0/16 in the Linux local route table for local virtual IP binding."""
    if not sys.platform.startswith("linux"):
        return
    try:
        res = subprocess.run(
            ["ip", "route", "show", "table", "local"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=2.0
        )
        if "100.0.0.0/16" in res.stdout or "100.0.0.0/24" in res.stdout:
            return

        cmd = ["ip", "route", "add", "local", "100.0.0.0/16", "dev", "lo"]
        r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=2.0)
        if r.returncode != 0:
            subprocess.run(["sudo", "-n"] + cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=2.0)
    except Exception:
        pass


def generate_admin_secret(length: int = 20) -> str:
    """
    Generates a cryptographically secure 20-character secret with
    uppercase, lowercase, digits, and symbols (*!?@#$%^&_-).
    """
    chars = string.ascii_letters + string.digits + "*!?@#$%^&_-"
    required = [
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.digits),
        secrets.choice("*!?@#$%^&_-"),
    ]
    rest = [secrets.choice(chars) for _ in range(length - len(required))]
    combined = required + rest
    secrets.SystemRandom().shuffle(combined)
    return "".join(combined)


def prompt_or_generate_admin_secret() -> str:
    """
    Prompts the user for a custom admin password on first run.
    If the user presses Enter without typing anything (or non-interactive),
    generates a secure random 20-character secret.
    """
    is_interactive = False
    try:
        is_interactive = sys.stdin and hasattr(sys.stdin, "isatty") and sys.stdin.isatty()
    except Exception:
        is_interactive = False

    if is_interactive:
        print("\n" + "=" * 68)
        print("          P2P SUNUCU ILK KURULUM YAPILANDIRMASI")
        print("=" * 68)
        print("  [?] Bu sunucu icin bir Yonetici (Admin) Sifresi belirleyin.")
        print("      (SSH ve tam yetkili port erisimi icin kullanilir)")
        print()
        print("      * Ozel bir sifre girmek istemiyorsaniz dogrudan [ENTER]'a basin.")
        print("      * Bos birakirsaniz sistem guclu ve rastgele bir sifre uretecektir.")
        print("-" * 68)
        try:
            user_input = input("  Yonetici Sifresi [Rastgele icin Enter]: ").strip()
        except (EOFError, KeyboardInterrupt):
            user_input = ""
        print("=" * 68)

        if user_input:
            print(f"  [+] Ozel yonetici sifreniz kaydedildi: {user_input}\n")
            return user_input

    secret = generate_admin_secret(20)
    return secret


def detect_mazipanel_installed() -> bool:
    """Checks whether maziPanel is installed on the current system."""
    if os.path.isdir("/mazideveloper") or os.path.isfile("/etc/systemd/system/mazipanel.service"):
        return True
    return False


def prompt_or_detect_panel_mode() -> str:
    """
    Prompts the user once on interactive terminal whether maziPanel is used.
    In non-interactive environments (systemd service), auto-detects /mazideveloper.
    """
    is_interactive = False
    try:
        is_interactive = bool(sys.stdin and hasattr(sys.stdin, "isatty") and sys.stdin.isatty())
    except Exception:
        is_interactive = False

    if is_interactive:
        try:
            ans = input("Yönetim için maziPanel kullanıyor musunuz? [e/H]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            ans = ""
        if ans in ("e", "evet", "y", "yes"):
            return "mazipanel"
        return "standalone"

    if detect_mazipanel_installed():
        return "mazipanel"
    return "standalone"


class P2PMCServer:
    def __init__(
        self,
        config_path: Optional[str] = None,
        admin_secret: Optional[str] = None,
        panel_mode: Optional[str] = None,
    ):
        self.config_path = config_path or get_server_config_path()
        self._config_mtime: float = 0.0
        self._on_signal_cb = None
        self.config = self._load_config(
            admin_secret_override=admin_secret,
            panel_mode_override=panel_mode,
        )
        try:
            if os.path.exists(self.config_path):
                self._config_mtime = os.path.getmtime(self.config_path)
        except Exception:
            pass

        self.server_name = self.config.get("server_name", "P2P Oyun Sunucusu")
        self.player_token = self.config.get("player_token", DEFAULT_TOKEN)
        self.admin_secret = self.config.get("admin_secret") or generate_admin_secret(20)
        self.panel_mode = self.config.get("panel_mode", "standalone")

        from server.version_manager import VersionManager
        update_url = self.config.get("update_url", "")
        manual_min_ver = self.config.get("min_client_version")
        self.version_manager = VersionManager(
            update_url=update_url,
            manual_min_version=manual_min_ver
        )

        self.acl = ServerACL(
            player_token=self.player_token,
            admin_secret=self.admin_secret,
            allowed_game_port=self.config.get("game_port", 25565),
            connection_address=self.config.get("connection_address", "baglanti.localhost"),
            version_manager=self.version_manager,
        )
        self.room_secret = self.config.get("room_secret", DEFAULT_SECRET)
        self.local_udp_port = self.config.get("server_udp_port", 25566)
        self.cipher = PacketCipher(derive_key(self.room_secret))

        self.server_key = self.config.get("server_key", "")
        self.short_code = self.server_key
        self.sock: Optional[socket.socket] = None
        self.public_endpoint: Optional[tuple] = None
        self.clients: Dict[Tuple[str, int], P2PTunnel] = {}
        self.signaling: Optional[SignalingClient] = None
        self.client_candidates: Dict[Tuple[str, int], float] = {}

        self.start_time = time.time()
        self.logger = server_logger

        from server.history_manager import ClientHistoryManager
        cfg_dir = os.path.dirname(os.path.abspath(self.config_path))
        self.history_manager = ClientHistoryManager(config_dir=cfg_dir)

        self.web_port = self.config.get("web_port", 9090)
        self.web_panel = WebAdminPanel(
            server=self,
            port=self.web_port,
            panel_mode=self.panel_mode,
        )
        server_logger.add_listener(self.web_panel.append_log)

    def restart_signaling(self):
        """Re-initializes signaling client when server_key / room credentials change."""
        try:
            from core.invite import derive_credentials_from_key
            room_id, room_sec, play_tok = derive_credentials_from_key(self.server_key)
            self.room_secret = room_sec
            self.player_token = play_tok
            self.cipher = PacketCipher(derive_key(self.room_secret))
            self.acl.player_token = play_tok
            self.acl.add_player_token(play_tok)
            if self.signaling:
                try:
                    self.signaling.stop()
                except Exception:
                    pass
            self.signaling = SignalingClient(room_id, self.room_secret)
            if self._on_signal_cb:
                self.signaling.start_listening(self._on_signal_cb)
                self.signaling.publish_nowait("server_hello", self.get_server_hello_payload())
        except Exception as e:
            server_logger.debug(f"Signaling yeniden başlatma hatası: {e}")

    def sync_config_from_disk(self) -> bool:
        """Hot-reloads server_config.json if modified on disk by external bridges (e.g. maziPanel)."""
        if not self.config_path or not os.path.exists(self.config_path):
            return False
        try:
            mtime = os.path.getmtime(self.config_path)
            if mtime <= self._config_mtime:
                return False
            with open(self.config_path, "r", encoding="utf-8") as f:
                disk_cfg = json.load(f)
            if not isinstance(disk_cfg, dict):
                return False
            self._config_mtime = mtime
        except Exception:
            return False

        from core.invite import normalize_server_key, derive_credentials_from_key

        self.config.update(disk_cfg)
        if disk_cfg.get("server_name"):
            self.server_name = str(disk_cfg["server_name"]).strip()

        if disk_cfg.get("admin_secret") and str(disk_cfg["admin_secret"]).strip():
            cleaned_admin = str(disk_cfg["admin_secret"]).strip()
            self.admin_secret = cleaned_admin
            self.acl.admin_secret = cleaned_admin

        if disk_cfg.get("game_port"):
            try:
                p_val = int(disk_cfg["game_port"])
                if 1 <= p_val <= 65535:
                    self.acl.allowed_game_port = p_val
            except Exception:
                pass

        if disk_cfg.get("connection_address") and str(disk_cfg["connection_address"]).strip():
            self.acl.connection_address = str(disk_cfg["connection_address"]).strip().lower()

        if disk_cfg.get("panel_mode") in ("standalone", "mazipanel"):
            self.panel_mode = disk_cfg["panel_mode"]
            if hasattr(self, "web_panel") and self.web_panel:
                self.web_panel.panel_mode = disk_cfg["panel_mode"]

        disk_key = normalize_server_key(str(disk_cfg.get("server_key", "")))
        clean_disk = disk_key.replace("-", "").replace(" ", "").upper()
        if clean_disk and len(clean_disk) == 12 and disk_key != self.server_key:
            self.server_key = disk_key
            self.short_code = disk_key
            self.restart_signaling()

        return True

    @property
    def tunnel(self) -> Optional[P2PTunnel]:
        if self.clients:
            return next(iter(self.clients.values()))
        return None

    def _load_config(
        self,
        admin_secret_override: Optional[str] = None,
        panel_mode_override: Optional[str] = None,
    ) -> dict:
        from core.invite import generate_server_key, derive_credentials_from_key, normalize_server_key

        cfg = None
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
            except Exception:
                cfg = None

        if not isinstance(cfg, dict):
            server_key = generate_server_key()
            _, derived_room_sec, derived_player_tok = derive_credentials_from_key(server_key)
            cfg = {
                "server_name": "P2P Sunucusu",
                "server_key": server_key,
                "game_port": 25565,
                "connection_address": "baglanti.localhost",
                "server_udp_port": 25566,
                "web_port": 9090,
                "player_token": derived_player_tok,
                "admin_secret": "",
                "room_secret": derived_room_sec,
            }

        # Check and migrate legacy / missing server_key (upgrade 8-char keys to standard 12-char)
        raw_key = str(cfg.get("server_key", "")).strip()
        clean_key = raw_key.replace("-", "").replace(" ", "").upper()
        if len(clean_key) != 12:
            server_key = generate_server_key()
            server_logger.info(f"Eski/geçersiz bağlantı kodu ({raw_key or 'Yok'}) standart 12 karakterli yeni koda güncellendi: {server_key}")
        else:
            server_key = normalize_server_key(raw_key)
        cfg["server_key"] = server_key

        if not cfg.get("connection_address"):
            cfg["connection_address"] = "baglanti.localhost"

        _, derived_room_sec, derived_player_tok = derive_credentials_from_key(server_key)

        # Migrate old static placeholder secrets to clean deterministic credentials
        if cfg.get("player_token") in (None, "", "MC_PLAYER_SECRET_2026", "P2P_PLAYER_SECRET_2026"):
            cfg["player_token"] = derived_player_tok
        if cfg.get("room_secret") in (None, "", "P2P_MC_SHARED_SECRET_2026", "P2P_SHARED_SECRET_2026"):
            cfg["room_secret"] = derived_room_sec

        # Check admin_secret
        if admin_secret_override:
            cfg["admin_secret"] = admin_secret_override
        else:
            current_admin = cfg.get("admin_secret")
            if not current_admin or current_admin in ("MC_ADMIN_SUPER_SECRET_2026", "P2P_ADMIN_SUPER_SECRET_2026"):
                cfg["admin_secret"] = prompt_or_generate_admin_secret()

        # Check panel_mode ("standalone" or "mazipanel")
        if panel_mode_override in ("standalone", "mazipanel"):
            cfg["panel_mode"] = panel_mode_override
        else:
            current_mode = str(cfg.get("panel_mode", "")).strip().lower()
            if current_mode not in ("standalone", "mazipanel"):
                cfg["panel_mode"] = prompt_or_detect_panel_mode()
            else:
                cfg["panel_mode"] = current_mode

        try:
            os.makedirs(os.path.dirname(os.path.abspath(self.config_path)), exist_ok=True)
            with open(self.config_path, "w", encoding="utf-8") as fw:
                json.dump(cfg, fw, indent=2, ensure_ascii=False)
        except Exception:
            pass

        return cfg

    def setup_socket(self):
        for attempt in range(15):
            try:
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                disable_udp_connreset(self.sock)
                tune_udp_socket(self.sock)
                self.sock.bind(("0.0.0.0", self.local_udp_port))
                server_logger.debug(f"Yerel UDP soketi bağlandı: port {self.sock.getsockname()[1]}")
                return
            except OSError as e:
                if self.sock:
                    try:
                        self.sock.close()
                    except Exception:
                        pass
                    self.sock = None
                if attempt < 14:
                    time.sleep(0.25)
                else:
                    server_logger.error(f"Port {self.local_udp_port} bağlanamadı: {e}")
                    raise

    def discover_public_endpoint(self) -> tuple:
        server_logger.debug("STUN üzerinden dış IP ve Port çözülüyor...")
        try:
            endpoint = get_public_endpoint(self.sock, timeout=1.5)
        except Exception as e:
            server_logger.debug(f"STUN çözümü başarısız: {e}")
            endpoint = None

        if not endpoint:
            local_ip = "127.0.0.1"
            endpoint = (local_ip, self.sock.getsockname()[1])
            server_logger.warning(f"STUN çözülemedi. Yerel adres kullanılıyor: {endpoint[0]}:{endpoint[1]}")
        else:
            server_logger.debug(f"STUN ile Dış Public Endpoint Çözüldü: {endpoint[0]}:{endpoint[1]}")
        self.public_endpoint = endpoint
        return endpoint

    def display_invite_code(self):
        self.server_key = self.config.get("server_key")
        self.short_code = self.server_key
        pub_str = f"{self.public_endpoint[0]}:{self.public_endpoint[1]}" if self.public_endpoint else "Bilinmiyor"
        loc_port = self.sock.getsockname()[1] if self.sock else self.local_udp_port
        web_url = f"http://127.0.0.1:{self.web_port}"
        panel_mode = getattr(self, "panel_mode", self.config.get("panel_mode", "standalone"))

        print("\n" + "=" * 64)
        print("                  P2P TÜNEL SUNUCUSU")
        print("=" * 64)
        print(f"  Sunucu Adı       : {self.server_name}")
        print(f"  Yerel UDP Portu  : {loc_port}")
        print(f"  Dış Ağ (STUN)    : {pub_str}")
        if panel_mode == "mazipanel":
            print(f"  Yönetim Paneli : maziPanel Entegrasyonu Aktif (Yerel Köprü: 127.0.0.1:{self.web_port})")
        else:
            print(f"  Web Yönetim Paneli : {web_url} (Giriş şifresi: admin_secret)")
        print("-" * 64)
        print("  [PAYLAŞILACAK BAĞLANTI ANAHTARI] (Oyuncular İçin):")
        print(f"  >> {self.server_key}")
        print()
        print("  [GİZLİ YÖNETİCİ ANAHTARI] (Kimseyle paylaşmayın!):")
        print(f"  >> {self.acl.admin_secret}")
        print("=" * 64 + "\n")
        server_logger.info(f"Sunucu hazır. Bağlantı Anahtarı: {self.server_key}")

    def get_lan_ip(self) -> str:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"

    def get_server_hello_payload(self) -> dict:
        return {
            "ip": self.public_endpoint[0] if self.public_endpoint else "127.0.0.1",
            "port": self.public_endpoint[1] if self.public_endpoint else self.sock.getsockname()[1],
            "lan_ip": self.get_lan_ip(),
            "local_port": self.sock.getsockname()[1]
        }

    def _create_client_tunnel(self, addr: tuple) -> P2PTunnel:
        """Creates and starts an isolated P2PTunnel session for an incoming peer."""
        self.sync_config_from_disk()
        now = time.time()
        for old_addr, old_tunnel in list(self.clients.items()):
            if old_addr != addr and old_addr[0] == addr[0]:
                if now - getattr(old_tunnel, "last_inbound_time", 0) > 3.0:
                    server_logger.debug(f"Eski/sessiz istemci oturumu temizlendi: {old_addr} (Yeni: {addr})")
                    asyncio.create_task(old_tunnel.stop())
                    self.clients.pop(old_addr, None)

        tunnel = P2PTunnel(
            udp_sock=self.sock,
            peer_addr=addr,
            cipher=PacketCipher(derive_key(self.room_secret)),
            conv_id=2026,
            is_server=True,
            acl=self.acl,
            shared_socket=True,
            room_secret=self.room_secret,
            target_host="127.0.0.1",
        )
        tunnel.running = True

        def _on_tunnel_disconnect():
            cur_addr = getattr(tunnel, "peer_addr", addr)
            if hasattr(self, "history_manager") and self.history_manager:
                self.history_manager.record_disconnect(peer_addr=cur_addr)
            self.clients.pop(cur_addr, None)
            self.clients.pop(addr, None)
            server_logger.info(f"İstemci ayrıldı: {cur_addr[0]}:{cur_addr[1]} (Aktif İstemci: {len(self.clients)})")

        def _on_tunnel_authenticated(client_info: dict):
            cur_addr = getattr(tunnel, "peer_addr", addr)
            hwid = client_info.get("hwid", "")
            username = client_info.get("username", "")
            if hasattr(self, "history_manager") and self.history_manager:
                v_ip = self.history_manager.get_or_assign_virtual_ip(hwid, username)
                tunnel.virtual_ip = v_ip
                client_info["virtual_ip"] = v_ip
                self.history_manager.record_login(client_info, cur_addr)

        tunnel.on_disconnect = _on_tunnel_disconnect
        tunnel.on_authenticated = _on_tunnel_authenticated
        tunnel.on_state_change = lambda msg, a=addr: server_logger.debug(f"[{a[0]}:{a[1]}] {msg}")
        self.clients[addr] = tunnel
        task = asyncio.create_task(tunnel.start())
        def _task_done(t):
            try:
                if not t.cancelled():
                    exc = t.exception()
                    if exc:
                        server_logger.error(f"[TUNNEL-CRASH] {addr}: {exc}")
            except Exception:
                pass
        task.add_done_callback(_task_done)
        server_logger.debug(f"Yeni istemci tüneli oluşturuldu: {addr[0]}:{addr[1]}")
        return tunnel

    def _handle_inbound_packet(self, data: bytes, addr: tuple):
        # Handle STUN Response packets dynamically
        if (len(data) >= 8 and data[4:8] == b"\x21\x12\xa4\x42") or (len(data) >= 20 and data[:2] == b"\x01\x01"):
            endpoint = parse_stun_response(data)
            if endpoint:
                new_ip, new_port = endpoint
                if self.public_endpoint != (new_ip, new_port):
                    server_logger.info(
                        f"Dış IP/Port güncellendi: {self.public_endpoint} -> ({new_ip}:{new_port})"
                    )
                    self.public_endpoint = (new_ip, new_port)
                    if hasattr(self, "signaling") and self.signaling:
                        self.signaling.publish_nowait("server_hello", self.get_server_hello_payload())
            return

        tunnel = self.clients.get(addr)
        decrypted = None
        if tunnel:
            try:
                decrypted = tunnel.cipher.decrypt(data)
            except Exception:
                decrypted = None

        if decrypted is None:
            try:
                decrypted = self.cipher.decrypt(data)
            except Exception:
                decrypted = None

        if decrypted is None:
            # Check other client tunnels' ciphers (for roaming NAT from same client)
            for t in self.clients.values():
                try:
                    decrypted = t.cipher.decrypt(data)
                    break
                except Exception:
                    pass

        if decrypted is None:
            return

        # Handle Hole-Punching probes
        if decrypted in (b"P2P_TUN_PUNCH_SYN", b"P2P_TUN_PUNCH_ACK") or decrypted.startswith(b"P2P_TUN_PUNCH_"):
            punch_ack = self.cipher.encrypt(b"P2P_TUN_PUNCH_ACK")
            for _ in range(4):
                try:
                    self.sock.sendto(punch_ack, addr)
                except OSError:
                    pass

            if addr not in self.clients:
                self._create_client_tunnel(addr)
                server_logger.debug(f"UDP delme sinyali eşleşti: {addr[0]}:{addr[1]}")
                if self.signaling:
                    locked_payload = self.get_server_hello_payload()
                    locked_payload["client_addr"] = addr
                    self.signaling.publish_nowait("server_locked", locked_payload)
            return

        # Route packet to existing client session, migrate roaming NAT port, or create a new session
        if addr not in self.clients:
            roaming_tunnel = None
            same_ip_tunnels = [
                (old_addr, t) for old_addr, t in self.clients.items()
                if old_addr[0] == addr[0] and getattr(t, "authenticated", False) and getattr(t, "running", False)
            ]
            if len(same_ip_tunnels) == 1:
                is_mid_session = False
                if decrypted.startswith((b"P2P_TUN_OOB_PING:", b"P2P_TUN_OOB_PONG:", b"P2P_TUN_OOB_MTU:", b"\xff\xffP2P_PING", b"\xff\xffP2P_PONG")):
                    is_mid_session = True
                elif len(decrypted) >= 24:
                    import struct
                    conv, _cmd, _frg, _wnd, _ts, sn, una, _length = struct.unpack("<IBBHIIII", decrypted[:24])
                    if conv == 2026 and (sn > 0 or una > 0):
                        is_mid_session = True
                if is_mid_session:
                    old_addr, roaming_tunnel = same_ip_tunnels[0]
                    self.clients.pop(old_addr, None)
                    self.clients[addr] = roaming_tunnel

            if roaming_tunnel is None:
                self._create_client_tunnel(addr)

        tunnel = self.clients.get(addr)
        if tunnel:
            tunnel.feed_datagram(decrypted, addr)

    async def _udp_dispatcher_loop(self):
        """Asynchronous central UDP packet receiver and demultiplexer."""
        loop = asyncio.get_running_loop()
        last_err_time = 0.0
        while True:
            try:
                data, addr = await loop.sock_recvfrom(self.sock, 65535)
                self._handle_inbound_packet(data, addr)
                await asyncio.sleep(0)
            except asyncio.CancelledError:
                break
            except Exception as e:
                now_t = time.time()
                if now_t - last_err_time > 5.0:
                    last_err_time = now_t
                    server_logger.error(f"[UDP-DISPATCH-ERR] Soket alma hatası: {e}")
                await asyncio.sleep(0.005)

    async def _punch_and_keepalive_loop(self):
        """Background keepalive loop for router NAT mapping and proactive punching."""
        last_nat_keepalive = time.time()
        last_server_hello = time.time()
        last_cfg_sync = time.time()
        stun_idx = 0

        # Pre-resolve STUN IP addresses
        stun_addrs = []
        for host, port in [
            ("stun.l.google.com", 19302),
            ("stun1.l.google.com", 19302),
            ("stun2.l.google.com", 19302),
            ("stun.cloudflare.com", 3478),
        ]:
            try:
                ip = socket.gethostbyname(host)
                stun_addrs.append((ip, port))
            except Exception:
                pass
        if not stun_addrs:
            stun_addrs = [("74.125.250.129", 19302)]

        while True:
            now = time.time()

            if now - last_cfg_sync > 1.5:
                last_cfg_sync = now
                self.sync_config_from_disk()

            # Refresh router STUN NAT pinhole every 5s with proper RFC 5389 request
            if now - last_nat_keepalive > 5.0:
                last_nat_keepalive = now
                target_stun = stun_addrs[stun_idx % len(stun_addrs)]
                stun_idx += 1
                try:
                    req_packet, _ = create_stun_request()
                    self.sock.sendto(req_packet, target_stun)
                except OSError:
                    pass

            # Refresh server endpoint signal periodically for new joining clients (every 900s / 15m to preserve ntfy quota)
            if now - last_server_hello > 900.0:
                last_server_hello = now
                if self.signaling:
                    self.signaling.publish_nowait("server_hello", self.get_server_hello_payload())

            # Purge expired candidates and candidates already connected
            expired = [c for c, exp in self.client_candidates.items() if now > exp or c in self.clients]
            for c in expired:
                self.client_candidates.pop(c, None)

            # Proactively punch towards active candidates that have not established an active tunnel yet
            if self.client_candidates:
                punch_syn = self.cipher.encrypt(b"P2P_TUN_PUNCH_SYN")
                for cand in list(self.client_candidates.keys()):
                    if cand not in self.clients:
                        ip, port = cand
                        try:
                            self.sock.sendto(punch_syn, cand)
                        except OSError:
                            pass
                        # If WAN candidate (external IP), probe nearby ports to punch through Symmetric CGNAT!
                        if ip != "127.0.0.1" and not ip.startswith("192.168.") and not ip.startswith("10."):
                            for delta in range(-5, 41):
                                if delta == 0:
                                    continue
                                target_p = port + delta
                                if 1024 <= target_p <= 65535:
                                    try:
                                        self.sock.sendto(punch_syn, (ip, target_p))
                                    except OSError:
                                        pass

            await asyncio.sleep(0.1)

    async def run(self):
        server_logger.debug("P2P Sunucu Servisi Başlatılıyor...")
        ensure_virtual_ip_subnet()
        self.setup_socket()
        self.discover_public_endpoint()
        self.sock.setblocking(False)
        self.display_invite_code()

        # Derive 100% matching credentials strictly from persistent server key (Zero IP exposure!)
        from core.invite import derive_credentials_from_key
        room_id, room_sec, play_tok = derive_credentials_from_key(self.server_key)
        self.room_secret = room_sec
        self.player_token = play_tok
        self.cipher = PacketCipher(derive_key(self.room_secret))
        self.acl.add_player_token(play_tok)
        self.acl.add_player_token(self.config.get("player_token", DEFAULT_TOKEN))
        self.acl.add_player_token(DEFAULT_TOKEN)

        self.signaling = SignalingClient(room_id, self.room_secret)

        last_hello_publish = 0.0

        def _on_signal(msg: dict):
            nonlocal last_hello_publish
            mtype = msg.get("type")
            if mtype == "client_hello":
                now_ts = time.time()
                msg_ts = msg.get("ts", 0)
                if msg_ts and (now_ts - msg_ts > 60.0):
                    return

                cip = msg.get("ip")
                cport = msg.get("port")
                clan = msg.get("lan_ip")
                lport = msg.get("local_port")
                cid = msg.get("client_id", "")

                # If client shares the exact same public IP (Local LAN / Same NAT), prioritize LAN directly,
                # BUT ALWAYS ALSO record the WAN candidate to support CGNAT & VPN peers sharing the same external IP!
                is_same_lan = bool(cip and self.public_endpoint and cip == self.public_endpoint[0])
                if is_same_lan and clan and lport:
                    lan_addr = (clan, int(lport))
                    self.client_candidates[lan_addr] = now_ts + 30.0
                    server_logger.debug(f"İstemci yerel ağ adresi kaydedildi (Aynı Ağ): {clan}:{lport}")

                if cip and cport and cip != "127.0.0.1":
                    wan_addr = (cip, int(cport))
                    self.client_candidates[wan_addr] = now_ts + 30.0
                    server_logger.debug(f"İstemci dış bağlantı sinyali kaydedildi: {cip}:{cport}")
                    # Immediate punch burst to open firewall pinholes without delay
                    try:
                        punch_syn = self.cipher.encrypt(b"P2P_TUN_PUNCH_SYN")
                        self.sock.sendto(punch_syn, wan_addr)
                        for delta in range(-5, 41):
                            if delta == 0:
                                continue
                            target_p = int(cport) + delta
                            if 1024 <= target_p <= 65535:
                                self.sock.sendto(punch_syn, (cip, target_p))
                    except OSError:
                        pass

                # Rate-limited response to client_hello with our server endpoint
                if now_ts - last_hello_publish > 0.5:
                    last_hello_publish = now_ts
                    if self.signaling:
                        payload = self.get_server_hello_payload()
                        if cid:
                            payload["client_id"] = cid
                        self.signaling.publish_nowait("server_hello", payload)

        self._on_signal_cb = _on_signal
        self.signaling.start_listening(_on_signal)
        for prev_msg in self.signaling.poll_messages(timeout=1.0):
            _on_signal(prev_msg)

        self.signaling.publish("server_hello", self.get_server_hello_payload())
        server_logger.info("Sunucu dinlemede. İstemci bağlantıları bekleniyor...")

        await self.web_panel.start()

        bg_tasks = [
            asyncio.create_task(self._udp_dispatcher_loop()),
            asyncio.create_task(self._punch_and_keepalive_loop()),
            asyncio.create_task(self.version_manager.refresh_loop()),
        ]

        try:
            await asyncio.gather(*bg_tasks)
        finally:
            if hasattr(self, "web_panel") and self.web_panel:
                await self.web_panel.stop()
            for t in bg_tasks:
                t.cancel()
            for client in list(self.clients.values()):
                try:
                    await client.stop()
                except Exception:
                    pass
            self.clients.clear()


if __name__ == "__main__":
    server = P2PMCServer()
    asyncio.run(server.run())

