"""
P2P Tunnel High-Performance Asynchronous Tunnel Engine.
Cross-platform asyncio.DatagramProtocol integration for Windows (IOCP) and Linux (Epoll).
Bridges local TCP sockets (Minecraft 25565 / SSH 22) across KCP and encrypted P2P UDP.
"""

import asyncio
import hashlib
import hmac
import json
import secrets
import socket
import struct
import time
from typing import Dict, Tuple, Optional, Callable, Any

from core.crypto import PacketCipher, derive_session_key
from core.kcp import KCPPeer
from core.logger import client_logger, server_logger
from core.protocol import Cmd, Role, encode_frame, decode_frame
from server.acl import ServerACL

SOCKET_BUFFER_SIZE = 8 * 1024 * 1024  # 8 MB high-performance buffer


def disable_udp_connreset(sock: socket.socket):
    """Disables SIO_UDP_CONNRESET on Windows to prevent WSAECONNRESET (10054) on ICMP unreachable."""
    import sys
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes
            SIO_UDP_CONNRESET = 0x9800000C
            b_new_behavior = wintypes.BOOL(False)
            cb_bytes_returned = wintypes.DWORD()
            ctypes.windll.ws2_32.WSAIoctl(
                sock.fileno(),
                SIO_UDP_CONNRESET,
                ctypes.byref(b_new_behavior),
                ctypes.sizeof(b_new_behavior),
                None,
                0,
                ctypes.byref(cb_bytes_returned),
                None,
                None
            )
        except Exception:
            pass


def tune_udp_socket(sock: socket.socket):
    """Enlarges kernel UDP send and receive buffers to prevent burst packet drops during chunk loads."""
    for buf_size in (16 * 1024 * 1024, 8 * 1024 * 1024, 4 * 1024 * 1024, 2 * 1024 * 1024, 1024 * 1024):
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, buf_size)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, buf_size)
            break
        except OSError:
            continue


def tune_tcp_socket(sock: socket.socket):
    """Disables Nagle algorithm and enlarges kernel socket buffers for zero ping spike."""
    try:
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    except OSError:
        pass
    for buf_size in (8 * 1024 * 1024, 4 * 1024 * 1024, 2 * 1024 * 1024, 1024 * 1024):
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, buf_size)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, buf_size)
            break
        except OSError:
            continue


_VPN_KEYWORDS = (
    "wintun", "wireguard", "tap-", "tap0901", "openvpn", "vpn", "warp",
    "cloudflare", "proton", "mullvad", "nord", "anyconnect", "cisco",
    "forti", "globalprotect", "pangp", "tailscale", "zerotier", "windscribe",
    "surfshark", "expressvpn", "cyberghost", "pia", "adguard", "hamachi",
    "radmin", "clash", "sing-box", "nekoray", "v2ray", "outline", "psiphon",
    "kaspersky", "bitdefender vpn", "avast secureline", "hide.me", "ivpn",
    "softether", "sstp", "l2tp", "ikev2", "wan miniport", "amnezia",
    "hiddify", "proxifier", "tun2socks", "shadowsocks", "xray", "trojan",
    "goodbyedpi", "byedpi", "zapret", "ultrasurf", "hotspot shield",
    "betternet", "urban", "zenmate", "browsec", "touch vpn", "planet vpn",
    "octohide", "privado", "astrill", "vypr", "torguard", "airvpn",
    "perfect privacy", "ovpn",
)

_LOCAL_BRIDGE_KEYWORDS = (
    "vethernet", "wsl", "hyper-v", "vmware", "virtualbox", "vboxnet",
    "docker", "bluetooth", "npcap", "loopback",
)


def _is_private_ip(ip_str: str) -> bool:
    """Checks if IP belongs to private 10.0.0.0/8 or 172.16.0.0/12 ranges."""
    try:
        parts = [int(x) for x in ip_str.split(".")]
        if len(parts) == 4:
            if parts[0] == 10:
                return True
            if parts[0] == 172 and 16 <= parts[1] <= 31:
                return True
    except Exception:
        pass
    return False


def _is_cgnat_or_tun_ip(ip_str: str) -> bool:
    """Checks if IP belongs to RFC 6598 (100.64.0.0/10) or TUN benchmark (198.18.0.0/15) ranges used by VPNs."""
    try:
        parts = [int(x) for x in ip_str.split(".")]
        if len(parts) != 4:
            return False
        # 100.64.0.0/10 (Cloudflare WARP, Tailscale, etc.)
        if parts[0] == 100 and 64 <= parts[1] <= 127:
            return True
        # 198.18.0.0/15 (Clash, sing-box, NekoRay TUN)
        if parts[0] == 198 and parts[1] in (18, 19):
            return True
    except Exception:
        pass
    return False


def detect_vpn_and_mtu(peer_ip: str = "8.8.8.8") -> Tuple[int, bool, str]:
    """
    Universal, brand-independent VPN & Interface MTU detector.
    Inspects OS kernel network interfaces (IfType, hardware MTU, active route IPs, and tunnel drivers).
    Returns: (optimal_kcp_mtu, is_vpn_active, description)
      - Standard connection (no VPN): 1350 MTU
      - Any VPN / tunnel active: 1100 MTU (or lower if interface MTU < 1220)
    """
    import os
    import sys

    # 1. Discover active outbound local IP(s) across both 0.0.0.0/1 and 128.0.0.0/1 route halves
    route_ips = set()
    probe_targets = ["1.1.1.1", "130.0.0.1"]
    if peer_ip and peer_ip not in ("127.0.0.1", "0.0.0.0") and not peer_ip.startswith("192.168."):
        probe_targets.insert(0, peer_ip)

    for tgt in probe_targets:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect((tgt, 80))
            lip = s.getsockname()[0]
            s.close()
            if lip and lip != "127.0.0.1" and not lip.startswith("169.254."):
                route_ips.add(lip)
        except Exception:
            pass

    for lip in route_ips:
        if _is_cgnat_or_tun_ip(lip):
            return 1100, True, f"TUN/CGNAT Rotasi ({lip})"

    if len(route_ips) > 1:
        return 1100, True, f"Coklu Aktif Rota/VPN Algilandi ({', '.join(sorted(route_ips))})"

    # 2. Windows Kernel Adapter Inspection via iphlpapi.GetAdaptersAddresses
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes

            GAA_FLAGS = 0x0002 | 0x0004 | 0x0008  # Skip Anycast, Multicast, DNS
            AF_INET = 2
            IfOperStatusUp = 1

            class SOCKET_ADDRESS(ctypes.Structure):
                _fields_ = [("lpSockaddr", ctypes.c_void_p), ("iSockaddrLength", ctypes.c_int)]

            class IP_ADAPTER_UNICAST_ADDRESS(ctypes.Structure):
                pass

            IP_ADAPTER_UNICAST_ADDRESS._fields_ = [
                ("Length", wintypes.ULONG),
                ("Flags", wintypes.DWORD),
                ("Next", ctypes.POINTER(IP_ADAPTER_UNICAST_ADDRESS)),
                ("Address", SOCKET_ADDRESS),
            ]

            class IP_ADAPTER_ADDRESSES(ctypes.Structure):
                pass

            IP_ADAPTER_ADDRESSES._fields_ = [
                ("Length", wintypes.ULONG),
                ("IfIndex", wintypes.DWORD),
                ("Next", ctypes.POINTER(IP_ADAPTER_ADDRESSES)),
                ("AdapterName", ctypes.c_char_p),
                ("FirstUnicastAddress", ctypes.POINTER(IP_ADAPTER_UNICAST_ADDRESS)),
                ("FirstAnycastAddress", ctypes.c_void_p),
                ("FirstMulticastAddress", ctypes.c_void_p),
                ("FirstDnsServerAddress", ctypes.c_void_p),
                ("DnsSuffix", ctypes.c_wchar_p),
                ("Description", ctypes.c_wchar_p),
                ("FriendlyName", ctypes.c_wchar_p),
                ("PhysicalAddress", ctypes.c_ubyte * 8),
                ("PhysicalAddressLength", wintypes.DWORD),
                ("Flags", wintypes.DWORD),
                ("Mtu", wintypes.DWORD),
                ("IfType", wintypes.DWORD),
                ("OperStatus", ctypes.c_int),
            ]

            size = wintypes.ULONG(32768)
            buf = ctypes.create_string_buffer(size.value)
            ret = ctypes.windll.iphlpapi.GetAdaptersAddresses(
                AF_INET, GAA_FLAGS, None, ctypes.byref(buf), ctypes.byref(size)
            )
            if ret == 111:  # ERROR_BUFFER_OVERFLOW
                buf = ctypes.create_string_buffer(size.value)
                ret = ctypes.windll.iphlpapi.GetAdaptersAddresses(
                    AF_INET, GAA_FLAGS, None, ctypes.byref(buf), ctypes.byref(size)
                )

            if ret == 0:
                curr = ctypes.cast(buf, ctypes.POINTER(IP_ADAPTER_ADDRESSES))
                while curr:
                    a = curr.contents
                    curr = a.Next
                    if a.OperStatus != IfOperStatusUp or a.IfType == 24:  # Skip down or loopback
                        continue

                    fname = (a.FriendlyName or "").strip()
                    desc = (a.Description or "").strip()
                    combined = f"{fname} {desc}".lower()

                    if any(b_kw in combined for b_kw in _LOCAL_BRIDGE_KEYWORDS):
                        continue

                    ips = []
                    u = a.FirstUnicastAddress
                    while u:
                        sa = u.contents.Address
                        if sa.lpSockaddr and sa.iSockaddrLength >= 8:
                            raw = ctypes.string_at(sa.lpSockaddr, 8)
                            fam = struct.unpack("<H", raw[:2])[0]
                            if fam == AF_INET:
                                ip_s = socket.inet_ntoa(raw[4:8])
                                if not ip_s.startswith("169.254.") and ip_s != "127.0.0.1":
                                    ips.append(ip_s)
                        u = u.contents.Next

                    if not ips:
                        continue

                    is_active_route = bool(route_ips.intersection(ips))
                    iface_mtu = int(a.Mtu) if 576 <= int(a.Mtu) <= 65535 else 1500
                    # IfType: 23 = PPP (Windows VPN), 53 = PROP_VIRTUAL (Wintun/WireGuard/TAP/WARP), 131 = TUNNEL
                    is_tunnel_iftype = int(a.IfType) in (23, 53, 131)
                    has_vpn_keyword = any(kw in combined for kw in _VPN_KEYWORDS)
                    has_cgnat_ip = any(_is_cgnat_or_tun_ip(ip_s) for ip_s in ips)
                    has_low_mtu = iface_mtu < 1480
                    is_virtual_non_standard = (int(a.IfType) not in (6, 71)) and any(_is_private_ip(ip_s) for ip_s in ips)

                    if is_active_route and (is_tunnel_iftype or has_vpn_keyword or has_cgnat_ip or has_low_mtu or is_virtual_non_standard):
                        kcp_mtu = min(1100, max(900, iface_mtu - 120)) if iface_mtu < 1220 else 1100
                        return kcp_mtu, True, f"{fname or desc} (Arayuz MTU={iface_mtu})"

                    if is_tunnel_iftype or has_vpn_keyword or has_cgnat_ip or is_virtual_non_standard or (has_low_mtu and int(a.IfType) not in (6, 71)):
                        kcp_mtu = min(1100, max(900, iface_mtu - 120)) if iface_mtu < 1220 else 1100
                        return kcp_mtu, True, f"{fname or desc} (Arayuz MTU={iface_mtu})"
        except Exception:
            pass
    else:
        # 3. Linux / POSIX /sys/class/net inspection
        try:
            net_dir = "/sys/class/net"
            if os.path.isdir(net_dir):
                for ifname in os.listdir(net_dir):
                    low_name = ifname.lower()
                    if low_name == "lo" or low_name.startswith(("docker", "veth", "br-", "virbr")):
                        continue
                    oper_path = os.path.join(net_dir, ifname, "operstate")
                    mtu_path = os.path.join(net_dir, ifname, "mtu")
                    type_path = os.path.join(net_dir, ifname, "type")
                    iface_mtu = 1500
                    if os.path.isfile(mtu_path):
                        with open(mtu_path, "r") as f:
                            iface_mtu = int(f.read().strip() or "1500")
                    if_type = 1
                    if os.path.isfile(type_path):
                        with open(type_path, "r") as f:
                            if_type = int(f.read().strip() or "1")
                    if low_name.startswith(("tun", "tap", "wg", "ppp", "utun", "warp", "proton", "nord", "tailscale")) or if_type in (512, 65534) or iface_mtu < 1480:
                        kcp_mtu = min(1100, max(900, iface_mtu - 120)) if iface_mtu < 1220 else 1100
                        return kcp_mtu, True, f"{ifname} (Arayuz MTU={iface_mtu})"
        except Exception:
            pass

    return 1350, False, "Standart Baglanti (MTU 1500)"


class P2PTunnel:
    """
    Manages KCP transport over encrypted UDP,
    and multiplexes local TCP streams.
    Preserves the underlying UDP socket across reconnection cycles.
    """

    def __init__(
        self,
        udp_sock: socket.socket,
        peer_addr: Tuple[str, int],
        cipher: PacketCipher,
        conv_id: int = 2026,
        is_server: bool = False,
        acl: Optional[ServerACL] = None,
        auth_token: str = "",
        shared_socket: bool = False,
        client_identity: Optional[dict] = None,
        mtu: Optional[int] = None,
        room_secret: str = "",
        target_host: str = "127.0.0.1",
    ):
        self.udp_sock = udp_sock
        self.peer_addr = peer_addr
        self.cipher = cipher
        self.conv_id = conv_id
        self.is_server = is_server
        self.acl = acl
        self.auth_token = auth_token
        self.shared_socket = shared_socket
        self.client_identity = client_identity
        self.room_secret = room_secret
        self.target_host = target_host or "127.0.0.1"
        self.virtual_ip: Optional[str] = None
        self.client_info: Dict[str, Any] = {}
        self.auth_fail_reason = ""
        self.logger = server_logger if is_server else client_logger
        self.running = bool(shared_socket or udp_sock)
        self.authenticated = False
        self.peer_role: Optional[Role] = None
        self._sent_nonces: set = set()
        self.raw_rtt_ms = 0.0
        self.app_rtt_ms = 0.0
        self.current_rtt_ms = 0.0
        self.last_inbound_time = time.time()
        self._inbound_event = asyncio.Event()

        # TCP streams: stream_id -> (reader, writer)
        self.streams: Dict[int, Tuple[asyncio.StreamReader, asyncio.StreamWriter]] = {}
        self._connecting_streams: set = set()
        self._pending_stream_data: Dict[int, list] = {}
        self.next_stream_id = 1 if not is_server else 2
        self.inbound_buffer = bytearray()
        self._target_host_cache: Dict[int, str] = {}
        self._disconnect_called = False

        # Callbacks
        self.on_ping_update: Optional[Callable[[float], None]] = None
        self.on_state_change: Optional[Callable[[str], None]] = None
        self.on_disconnect: Optional[Callable[[], None]] = None
        self.on_authenticated: Optional[Callable[[dict], None]] = None

        # Strict FIFO Outbound Queue: Guarantees 100% in-order TCP stream integrity
        # Sized to 512 frames (~4 MB) for ultra-smooth jitter-free 60 FPS gameplay
        self.outbound_queue: asyncio.Queue = asyncio.Queue(maxsize=512)

        self._last_drop_log = 0.0
        self._last_mtu_check = time.time()

        if mtu is not None:
            self.mtu = max(900, min(1350, int(mtu)))
            self.is_vpn = self.mtu <= 1200
            self.mtu_reason = f"Manuel MTU ({self.mtu})"
        elif not is_server:
            det_mtu, det_vpn, det_reason = detect_vpn_and_mtu(peer_addr[0] if peer_addr else "8.8.8.8")
            self.mtu = det_mtu
            self.is_vpn = det_vpn
            self.mtu_reason = det_reason
            if self.is_vpn:
                self.logger.info(f"[VPN-MTU] VPN algılandı ({det_reason}) -> KCP MTU={self.mtu} olarak ayarlandı.")
            else:
                self.logger.debug(f"[MTU] Normal bağlantı -> KCP MTU={self.mtu}")
        else:
            self.mtu = 1350
            self.is_vpn = False
            self.mtu_reason = "Sunucu Varsayilan (MTU 1350)"

        # Initialize KCP with adaptive MTU (1350 normal, 1100 when VPN active)
        self.bg_tasks = []
        self.kcp = KCPPeer(
            conv_id=conv_id,
            outbound_callback=self._send_udp_encrypted,
            mtu=self.mtu,
            no_delay=True,
            interval=10,
            resend=2,
            no_congestion=True,
        )

    def set_mtu(self, new_mtu: int, reason: str = ""):
        """Dynamically updates KCP MTU for this tunnel session."""
        clamped = max(900, min(1350, int(new_mtu)))
        if clamped != self.mtu:
            old_mtu = self.mtu
            self.mtu = clamped
            self.is_vpn = clamped <= 1200
            self.kcp.set_mtu(clamped)
            extra = f" ({reason})" if reason else ""
            self.logger.info(f"[MTU-ADAPT] KCP MTU güncellendi: {old_mtu} -> {clamped}{extra}")

    def _send_udp_encrypted(self, kcp_packet: bytes):
        """Encrypts KCP packet and sends it over UDP to peer endpoint with micro-retry against buffer overflow."""
        if not self.running or not self.udp_sock:
            return
        try:
            encrypted = self.cipher.encrypt(kcp_packet)
            try:
                self.udp_sock.sendto(encrypted, self.peer_addr)
            except (BlockingIOError, InterruptedError):
                # Kernel UDP TX buffer momentarily full during massive chunk burst.
                # Micro-spin without blocking sleep allows NIC qdisc to drain immediately.
                sent = False
                for _ in range(4):
                    try:
                        self.udp_sock.sendto(encrypted, self.peer_addr)
                        sent = True
                        break
                    except (BlockingIOError, InterruptedError):
                        pass
                if not sent:
                    now = time.time()
                    if now - self._last_drop_log > 3.0:
                        self._last_drop_log = now
                        self.logger.warning(
                            f"[UDP-BUFFER-SATURATED] UDP tamponu anlık dolu ({self.peer_addr}). Paket KCP ARQ ile telafi edilecek."
                        )
        except OSError as e:
            if self.running:
                now = time.time()
                if now - self._last_drop_log > 3.0:
                    self._last_drop_log = now
                    self.logger.error(f"[UDP-SEND-FAIL] Hedefe gönderilemedi {self.peer_addr}: {e}")

    def handle_inbound_datagram(self, data: bytes, addr: Tuple[str, int]):
        """Called when an encrypted packet arrives."""
        if not self.running:
            return

        # Filter STUN responses (Google STUN or STUN magic cookie 0x2112A442)
        if (len(data) >= 8 and data[4:8] == b"\x21\x12\xa4\x42") or addr[0] in (
            "74.125.250.129", "172.253.115.129", "142.250.180.129"
        ):
            return

        try:
            decrypted = self.cipher.decrypt(data)
            self.handle_inbound_decrypted(decrypted, addr)
        except Exception as e:
            self.logger.debug(f"[UDP-DECRYPT-FAIL] {len(data)}B paket çözülemedi ({addr}): {e}")

    def feed_datagram(self, decrypted: bytes, addr: Tuple[str, int]):
        """Feeds already-decrypted packet directly from multi-client UDP dispatcher."""
        self.handle_inbound_decrypted(decrypted, addr)

    def handle_inbound_decrypted(self, decrypted: bytes, addr: Tuple[str, int]):
        """Handles decrypted packet (KCP, OOB Ping/Pong, NAT roaming)."""
        if not self.running:
            return

        self.last_inbound_time = time.time()

        # High-priority Out-Of-Band (OOB) UDP Ping/Pong (zero queue delay!)
        if decrypted.startswith(b"P2P_TUN_OOB_PING:"):
            pong_payload = decrypted[len(b"P2P_TUN_OOB_PING:"):]
            pong_pkt = self.cipher.encrypt(b"P2P_TUN_OOB_PONG:" + pong_payload)
            try:
                self.udp_sock.sendto(pong_pkt, addr)
            except OSError:
                pass
            return

        if decrypted.startswith(b"P2P_TUN_OOB_PONG:"):
            pong_payload = decrypted[len(b"P2P_TUN_OOB_PONG:"):]
            if len(pong_payload) >= 8:
                orig_ts = struct.unpack("!d", pong_payload[:8])[0]
                sample_rtt = max(0.5, (time.time() - orig_ts) * 1000.0)
                if self.raw_rtt_ms <= 0.0:
                    self.raw_rtt_ms = sample_rtt
                else:
                    self.raw_rtt_ms = 0.7 * self.raw_rtt_ms + 0.3 * sample_rtt
                self.current_rtt_ms = self.raw_rtt_ms
                if self.on_ping_update:
                    self.on_ping_update(self.current_rtt_ms)
            return

        if decrypted.startswith(b"P2P_TUN_OOB_MTU:"):
            try:
                req_mtu = int(decrypted[len(b"P2P_TUN_OOB_MTU:"):].decode("ascii", errors="ignore").strip())
                self.set_mtu(req_mtu, reason="Karşı uç VPN/MTU sinyali")
            except Exception:
                pass
            return

        # Automatic Endpoint Roaming for Symmetric NAT
        if self.is_server and self.peer_addr != addr:
            self.logger.debug(f"[PEER-ROAM] İstemci uç noktası güncellendi: {self.peer_addr} -> {addr}")
            self.peer_addr = addr

        # Filter residual hole-punching packets so they NEVER touch KCP!
        if decrypted in (b"P2P_TUN_PUNCH_SYN", b"P2P_TUN_PUNCH_ACK") or decrypted.startswith(b"P2P_TUN_PUNCH_"):
            return

        self.kcp.receive(decrypted)

    async def start(self):
        """Starts background tasks."""
        self.logger.debug(f"[TUNNEL-START] starting for peer {self.peer_addr} (shared={self.shared_socket}, is_server={self.is_server})")
        self.running = True
        self.last_inbound_time = time.time()
        self.udp_sock.setblocking(False)

        # Launch background tasks
        self.bg_tasks = [
            asyncio.create_task(self._kcp_update_loop()),
            asyncio.create_task(self._inbound_processor_loop()),
            asyncio.create_task(self._kcp_sender_loop()),
            asyncio.create_task(self._ping_keepalive_loop()),
        ]

        # Only standalone mode (e.g. client) reads directly from socket
        if not self.shared_socket:
            self.bg_tasks.append(asyncio.create_task(self._udp_recv_loop()))

        if not self.is_server:
            self.send_auth()

        await asyncio.gather(*self.bg_tasks, return_exceptions=True)

    def send_high_priority(self, frame: bytes):
        """Sends frame via the strict FIFO queue (preserves order)."""
        if not self.running:
            return
        try:
            self.outbound_queue.put_nowait(frame)
        except asyncio.QueueFull:
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self.outbound_queue.put(frame))
            except RuntimeError:
                self.kcp.send(frame)

    async def enqueue_data_frame(self, frame: bytes):
        """Enqueues frame into strict FIFO queue with backpressure to eliminate bufferbloat."""
        if not self.running:
            return
        # Backpressure: Yield smoothly only if KCP flight queue gets large (send window is 512)
        while self.running and self.kcp.get_outbound_count() > 384:
            await asyncio.sleep(0.001)
        await self.outbound_queue.put(frame)

    async def _kcp_sender_loop(self):
        """
        High-Speed FIFO KCP Dispatcher:
        Dispatches all frames in strict arrival order with paced flushing.
        """
        while self.running:
            try:
                frame = await self.outbound_queue.get()
                self.kcp.enqueue(frame)

                batch_count = 0
                while not self.outbound_queue.empty() and batch_count < 32:
                    frame = self.outbound_queue.get_nowait()
                    self.kcp.enqueue(frame)
                    batch_count += 1

                self.kcp.flush()
                await asyncio.sleep(0)
            except asyncio.CancelledError:
                break
            except Exception:
                if not self.running:
                    break
                await asyncio.sleep(0.001)

    async def _udp_recv_loop(self):
        """Asynchronously receives UDP packets using native IOCP sock_recvfrom."""
        loop = asyncio.get_running_loop()
        while self.running:
            try:
                data, addr = await loop.sock_recvfrom(self.udp_sock, 65535)
                self.handle_inbound_datagram(data, addr)
            except asyncio.CancelledError:
                break
            except Exception:
                if not self.running:
                    break
                await asyncio.sleep(0.005)

    def _send_oob_mtu(self):
        """Sends out-of-band MTU notification packet to peer."""
        if not self.running or not self.udp_sock or not self.peer_addr:
            return
        try:
            pkt = self.cipher.encrypt(f"P2P_TUN_OOB_MTU:{self.mtu}".encode("ascii"))
            self.udp_sock.sendto(pkt, self.peer_addr)
        except OSError:
            pass

    def send_auth(self):
        """Sends client authentication frame to server (including detected VPN/MTU state)."""
        if not self.is_server and not self.authenticated:
            tok = self.auth_token
            if not tok:
                from core.protocol import DEFAULT_TOKEN
                tok = DEFAULT_TOKEN

            if not getattr(self, "_client_nonce", None):
                client_nonce = secrets.token_hex(16)
                self._client_nonce = client_nonce
                if not hasattr(self, "_sent_nonces"):
                    self._sent_nonces = set()
                self._sent_nonces.add(client_nonce)
            else:
                client_nonce = self._client_nonce

            if self.client_identity:
                auth_data = dict(self.client_identity)
            else:
                try:
                    from core.updater import APP_VERSION
                    ver = APP_VERSION
                except Exception:
                    ver = "2.6"
                auth_data = {"version": ver}

            auth_data["nonce"] = client_nonce

            # Protect admin secret: NEVER send plain admin token over the wire!
            if tok and not tok.startswith(("tok_", "TOK_")):
                # Admin Secret: Send HMAC challenge-response only!
                auth_hmac = hmac.new(
                    tok.encode("utf-8"),
                    f"P2P_AUTH:{self.room_secret}:{client_nonce}".encode("utf-8"),
                    hashlib.sha256
                ).hexdigest()
                auth_data["token_hmac"] = auth_hmac
                auth_data["token"] = "HMAC_PROTECTED"
            else:
                # Player Token: Send token and HMAC
                auth_hmac = hmac.new(
                    tok.encode("utf-8"),
                    f"P2P_AUTH:{self.room_secret}:{client_nonce}".encode("utf-8"),
                    hashlib.sha256
                ).hexdigest()
                auth_data["token_hmac"] = auth_hmac
                auth_data["token"] = tok

            if not auth_data.get("version"):
                try:
                    from core.updater import APP_VERSION
                    auth_data["version"] = APP_VERSION
                except Exception:
                    auth_data["version"] = "2.6"

            auth_data["mtu"] = self.mtu
            auth_data["vpn"] = self.is_vpn
            payload = json.dumps(auth_data, ensure_ascii=False).encode("utf-8")
            if self.is_vpn:
                self._send_oob_mtu()
            auth_frame = encode_frame(0, Cmd.AUTH, payload=payload)
            self.send_high_priority(auth_frame)

    def send_disconnect(self):
        """Sends graceful disconnect frame to peer."""
        if self.running:
            try:
                frame = encode_frame(0, Cmd.DISCONNECT)
                self.kcp.send(frame)
                self.kcp.update()
            except Exception:
                pass

    async def stop(self):
        """Gracefully closes all streams and stops loops WITHOUT touching the underlying UDP socket."""
        self.running = False
        self._inbound_event.set()
        self._connecting_streams.clear()
        self._pending_stream_data.clear()
        for task in self.bg_tasks:
            if not task.done():
                task.cancel()
        for stream_id, (reader, writer) in list(self.streams.items()):
            try:
                reader.feed_eof()
            except Exception:
                pass
            try:
                writer.close()
                await writer.wait_closed()
            except (Exception, asyncio.CancelledError):
                pass
        self.streams.clear()
        if self.on_disconnect and not self._disconnect_called:
            self._disconnect_called = True
            try:
                self.on_disconnect()
            except Exception:
                pass

    async def _kcp_update_loop(self):
        """Runs the KCP clock every 5ms for minimal latency."""
        while self.running:
            self.kcp.update()
            has_chunk = False
            for chunk in self.kcp.get_received():
                self.inbound_buffer.extend(chunk)
                has_chunk = True
            if has_chunk:
                self._inbound_event.set()
            await asyncio.sleep(0.005)

    async def _inbound_processor_loop(self):
        """Processes assembled inbound KCP stream data into multiplexed protocol frames."""
        while self.running:
            try:
                await self._inbound_event.wait()
                self._inbound_event.clear()
                await self._process_inbound_buffer()
            except asyncio.CancelledError:
                break
            except Exception as e:
                if not self.running:
                    break
                self.logger.debug(f"[INBOUND-PROC-ERR] {e}")
                await asyncio.sleep(0.001)

    async def _ping_keepalive_loop(self):
        """Sends periodic high-priority UDP pings, monitors health, and adapts MTU if VPN state changes."""
        await asyncio.sleep(0.2)
        while self.running:
            now = time.time()
            # Heartbeat watchdog: If peer is silent for > 10.0s once authenticated, disconnect cleanly
            if self.authenticated and (now - self.last_inbound_time > 10.0):
                self.logger.warning(
                    f"Bağlantı zaman aşımı: Karşı taraftan {now - self.last_inbound_time:.1f} saniyedir yanıt alınamadı. Tünel sıfırlanıyor..."
                )
                if self.on_state_change:
                    self.on_state_change("Bağlantı zaman aşımına uğradı.")
                await self.stop()
                break

            # Server cleanup: Purge unauthenticated half-open sessions after 12s
            if self.is_server and not self.authenticated and (now - self.last_inbound_time > 12.0):
                await self.stop()
                break

            # Aggressive OOB probe burst if silence exceeds 4.0s to revive NAT pinhole
            if self.authenticated and (now - self.last_inbound_time > 4.0) and self.peer_addr:
                ts_bytes = struct.pack("!d", now)
                oob_ping = self.cipher.encrypt(b"P2P_TUN_OOB_PING:" + ts_bytes)
                try:
                    self.udp_sock.sendto(oob_ping, self.peer_addr)
                except OSError:
                    pass

            # Client-side live VPN/MTU watcher (every 3s): adapts automatically if user toggles VPN mid-session
            if not self.is_server and (now - self._last_mtu_check > 3.0):
                self._last_mtu_check = now
                det_mtu, det_vpn, det_reason = detect_vpn_and_mtu(
                    self.peer_addr[0] if self.peer_addr else "8.8.8.8"
                )
                if det_mtu != self.mtu:
                    self.set_mtu(det_mtu, reason=det_reason)
                    self._send_oob_mtu()

            if self.authenticated and self.peer_addr:
                ts_bytes = struct.pack("!d", now)
                # Send Out-Of-Band (OOB) UDP Ping packet directly (bypasses KCP queues completely!)
                oob_ping = self.cipher.encrypt(b"P2P_TUN_OOB_PING:" + ts_bytes)
                try:
                    self.udp_sock.sendto(oob_ping, self.peer_addr)
                except OSError:
                    pass

                # Also send fallback KCP ping frame for older clients
                ping_frame = encode_frame(0, Cmd.PING, payload=ts_bytes)
                self.send_high_priority(ping_frame)

            await asyncio.sleep(1.0)

    async def _process_inbound_buffer(self):
        """Parses multiplexed protocol frames from the assembled KCP stream."""
        while len(self.inbound_buffer) >= 9:
            frame = decode_frame(bytes(self.inbound_buffer))
            if frame is None:
                break
            stream_id, cmd, target_port, payload, remainder = frame
            self.inbound_buffer = bytearray(remainder)
            await self._handle_frame(stream_id, cmd, target_port, payload)

    async def _connect_server_stream(self, stream_id: int, target_port: int):
        """Asynchronously connects to local target port without blocking KCP loop."""
        connected = False
        reader = None
        writer = None
        target_host = self.target_host or "127.0.0.1"

        if self.running and stream_id in self._connecting_streams:
            if self.virtual_ip:
                # 1. Try real virtual IP binding (100.0.0.x)
                try:
                    reader, writer = await asyncio.wait_for(
                        asyncio.open_connection(target_host, target_port, local_addr=(self.virtual_ip, 0)),
                        timeout=2.0,
                    )
                    tune_tcp_socket(writer.get_extra_info("socket"))
                    connected = True
                except (OSError, Exception):
                    # 2. Smart loopback fallback (Windows / non-root Linux: e.g. 100.0.0.5 -> 127.100.0.5)
                    fallback_ip = None
                    try:
                        v_parts = self.virtual_ip.split(".")
                        if len(v_parts) == 4:
                            fallback_ip = f"127.100.{v_parts[2]}.{v_parts[3]}"
                    except Exception:
                        fallback_ip = "127.100.0.2"

                    if fallback_ip:
                        try:
                            reader, writer = await asyncio.wait_for(
                                asyncio.open_connection(target_host, target_port, local_addr=(fallback_ip, 0)),
                                timeout=2.0,
                            )
                            tune_tcp_socket(writer.get_extra_info("socket"))
                            connected = True
                        except Exception:
                            # 3. Last resort: connect without local_addr
                            try:
                                reader, writer = await asyncio.wait_for(
                                    asyncio.open_connection(target_host, target_port),
                                    timeout=2.0,
                                )
                                tune_tcp_socket(writer.get_extra_info("socket"))
                                connected = True
                            except Exception as e_last:
                                self.logger.error(f"Hedef porta bağlanılamadı ({target_host}:{target_port}): {e_last}")
                    else:
                        try:
                            reader, writer = await asyncio.wait_for(
                                asyncio.open_connection(target_host, target_port),
                                timeout=2.0,
                            )
                            tune_tcp_socket(writer.get_extra_info("socket"))
                            connected = True
                        except Exception as e_last:
                            self.logger.error(f"Hedef porta bağlanılamadı ({target_host}:{target_port}): {e_last}")
            else:
                try:
                    reader, writer = await asyncio.wait_for(
                        asyncio.open_connection(target_host, target_port),
                        timeout=2.0,
                    )
                    tune_tcp_socket(writer.get_extra_info("socket"))
                    connected = True
                except Exception as e:
                    self.logger.error(f"Hedef porta bağlanılamadı ({target_host}:{target_port}): {e}")

        if not self.running or stream_id not in self._connecting_streams:
            self._connecting_streams.discard(stream_id)
            self._pending_stream_data.pop(stream_id, None)
            if writer:
                try:
                    writer.close()
                except Exception:
                    pass
            return

        self._connecting_streams.discard(stream_id)
        pending_chunks = self._pending_stream_data.pop(stream_id, [])

        if not connected or not writer or not reader:
            close_frame = encode_frame(stream_id, Cmd.CLOSE)
            self.send_high_priority(close_frame)
            return

        self.streams[stream_id] = (reader, writer)
        if pending_chunks:
            try:
                for chunk in pending_chunks:
                    writer.write(chunk)
                transport = writer.transport
                if transport and transport.get_write_buffer_size() > 65536:
                    await writer.drain()
            except Exception:
                self._close_stream(stream_id)
                close_frame = encode_frame(stream_id, Cmd.CLOSE)
                self.send_high_priority(close_frame)
                return

        asyncio.create_task(self._forward_tcp_to_kcp(stream_id, reader))

    async def _handle_frame(self, stream_id: int, cmd: Cmd, target_port: int, payload: bytes):
        """Handles single protocol frame based on command and ACL."""
        if cmd == Cmd.PING:
            pong_frame = encode_frame(0, Cmd.PONG, payload=payload)
            self.send_high_priority(pong_frame)

        elif cmd == Cmd.PONG:
            if len(payload) >= 8:
                orig_ts = struct.unpack("!d", payload[:8])[0]
                sample_rtt = max(0.5, (time.time() - orig_ts) * 1000.0)
                if self.app_rtt_ms <= 0.0:
                    self.app_rtt_ms = sample_rtt
                else:
                    self.app_rtt_ms = 0.75 * self.app_rtt_ms + 0.25 * sample_rtt
                # Only use app_rtt_ms for user display if raw UDP RTT is not available
                if self.raw_rtt_ms <= 0.0:
                    self.current_rtt_ms = self.app_rtt_ms
                    if self.on_ping_update:
                        self.on_ping_update(self.current_rtt_ms)

        elif cmd == Cmd.AUTH and self.is_server:
            raw_payload = payload.decode("utf-8", errors="ignore")
            token = raw_payload
            hwid = ""
            hwid_details = {}
            username = "Bilinmeyen"
            computer_name = ""
            os_info = ""
            client_version = ""
            client_mtu = 1350
            client_vpn = False
            client_nonce = ""
            token_hmac = ""

            try:
                parsed = json.loads(raw_payload)
                if isinstance(parsed, dict):
                    token = parsed.get("token", "")
                    username = parsed.get("username", "Bilinmeyen")
                    hwid = parsed.get("hwid", "")
                    hwid_details = parsed.get("hwid_details", {})
                    computer_name = parsed.get("computer_name", "")
                    os_info = parsed.get("os", "")
                    client_version = str(parsed.get("version", "")).strip()
                    client_nonce = str(parsed.get("nonce", "")).strip()
                    token_hmac = str(parsed.get("token_hmac", "")).strip()
                    if parsed.get("mtu"):
                        client_mtu = int(parsed.get("mtu"))
                    client_vpn = bool(parsed.get("vpn", False))
            except Exception:
                pass

            self.set_mtu(client_mtu, reason="İstemci VPN aktif" if client_vpn else "İstemci standart bağlantı")

            self.client_info = {
                "username": username,
                "computer_name": computer_name,
                "hwid": hwid,
                "hwid_details": hwid_details,
                "os": os_info,
                "version": client_version,
                "ip": self.peer_addr[0],
                "port": self.peer_addr[1],
                "mtu": self.mtu,
                "vpn": client_vpn,
                "connected_at": time.time(),
            }

            if self.authenticated and self.peer_role:
                s_nonce = getattr(self, "_server_nonce", "")
                s_proof = getattr(self, "_server_proof", "")

                if client_nonce:
                    if client_nonce == getattr(self, "_last_client_nonce", "") and s_nonce and s_proof:
                        pass
                    else:
                        s_nonce = s_nonce or secrets.token_hex(16)
                        self._server_nonce = s_nonce
                        self._last_client_nonce = client_nonce
                        proof_secret = self.acl.admin_secret.encode("utf-8") if self.peer_role == Role.ADMIN else self.room_secret.encode("utf-8")
                        s_proof = hmac.new(
                            proof_secret,
                            f"P2P_SERVER_OK:{client_nonce}:{s_nonce}".encode("utf-8"),
                            hashlib.sha256
                        ).hexdigest()
                        self._server_proof = s_proof

                auth_ok_dict = {
                    "port": getattr(self.acl, "allowed_game_port", 25565),
                    "address": getattr(self.acl, "connection_address", "baglanti.localhost"),
                }
                if s_nonce and s_proof:
                    auth_ok_dict["server_nonce"] = s_nonce
                    auth_ok_dict["server_proof"] = s_proof

                auth_ok_payload = json.dumps(auth_ok_dict, ensure_ascii=False).encode("utf-8")
                resp = encode_frame(0, Cmd.AUTH_OK, target_port=int(self.peer_role), payload=auth_ok_payload)
                self.send_high_priority(resp)
                return

            self.logger.debug(f"İstemciden bağlantı isteği alındı: Kullanıcı={username}, Sürüm={client_version or 'Eski/Yok'}, MTU={self.mtu}, VPN={client_vpn}")
            try:
                role = self.acl.authenticate(
                    token,
                    hwid=hwid,
                    hwid_details=hwid_details,
                    client_version=client_version,
                    client_nonce=client_nonce,
                    token_hmac=token_hmac,
                    room_secret=self.room_secret,
                )
                self.peer_role = role
                self.authenticated = True
                self.client_info["role"] = role.name

                # Generate mutual auth proof & per-session encryption key
                server_nonce = secrets.token_hex(16)
                proof_secret = self.acl.admin_secret.encode("utf-8") if role == Role.ADMIN else self.room_secret.encode("utf-8")
                server_proof = hmac.new(
                    proof_secret,
                    f"P2P_SERVER_OK:{client_nonce}:{server_nonce}".encode("utf-8"),
                    hashlib.sha256
                ).hexdigest()

                self._server_nonce = server_nonce
                self._server_proof = server_proof
                self._last_client_nonce = client_nonce

                auth_ok_payload = json.dumps({
                    "port": getattr(self.acl, "allowed_game_port", 25565),
                    "address": getattr(self.acl, "connection_address", "baglanti.localhost"),
                    "server_nonce": server_nonce,
                    "server_proof": server_proof,
                }, ensure_ascii=False).encode("utf-8")
                resp = encode_frame(0, Cmd.AUTH_OK, target_port=int(role), payload=auth_ok_payload)
                self.kcp.send(resp)
                self.kcp.flush()
                self.kcp.update()

                # Set session key for isolated encryption after transmitting AUTH_OK with base key
                if client_nonce and server_nonce:
                    token_sec = self.acl.admin_secret if role == Role.ADMIN else self.room_secret
                    session_key = derive_session_key(self.room_secret, client_nonce, server_nonce, token_sec)
                    self.cipher.set_session_key(session_key)

                if self.on_authenticated:
                    try:
                        self.on_authenticated(self.client_info)
                    except Exception:
                        pass

                vip_str = f" -> Sanal IP: {self.virtual_ip}" if self.virtual_ip else ""
                self.logger.info(f"İstemci bağlandı: {username} ({self.peer_addr[0]}:{self.peer_addr[1]}{vip_str}) [Yetki: {role.name}, MTU: {self.mtu}]")
                if self.on_state_change:
                    self.on_state_change(f"İstemci bağlandı: {username} ({role.name})")
            except PermissionError as pe:
                err_msg = str(pe)
                self.logger.error(f"Kimlik doğrulama reddedildi: {err_msg}")
                resp = encode_frame(0, Cmd.AUTH_FAIL, payload=err_msg.encode("utf-8"))
                self.send_high_priority(resp)
                await asyncio.sleep(0.1)
                await self.stop()
            except Exception as e:
                self.logger.error(f"Kimlik doğrulama hatası: {e}")
                resp = encode_frame(0, Cmd.AUTH_FAIL, payload=b"Kimlik dogrulama hatasi")
                self.send_high_priority(resp)
                await asyncio.sleep(0.1)
                await self.stop()

        elif cmd == Cmd.AUTH_OK and not self.is_server:
            if not self.authenticated:
                self.authenticated = True
                self.peer_role = Role(target_port)
                server_nonce = ""
                server_proof = ""
                if payload:
                    try:
                        meta = json.loads(payload.decode("utf-8", errors="ignore"))
                        if isinstance(meta, dict):
                            if meta.get("port"):
                                self.server_assigned_port = int(meta["port"])
                            if meta.get("address"):
                                self.server_assigned_address = str(meta["address"]).strip()
                            server_nonce = meta.get("server_nonce", "")
                            server_proof = meta.get("server_proof", "")
                    except Exception:
                        pass

                # Mutual authentication & Session key derivation
                candidate_nonces = []
                curr_c_nonce = getattr(self, "_client_nonce", "")
                if curr_c_nonce:
                    candidate_nonces.append(curr_c_nonce)
                for sn in getattr(self, "_sent_nonces", set()):
                    if sn not in candidate_nonces:
                        candidate_nonces.append(sn)

                if server_nonce and server_proof and candidate_nonces:
                    proof_secret = self.auth_token.encode("utf-8") if self.peer_role == Role.ADMIN and self.auth_token else self.room_secret.encode("utf-8")
                    matched_nonce = None
                    for c_nonce in candidate_nonces:
                        expected_proof = hmac.new(
                            proof_secret,
                            f"P2P_SERVER_OK:{c_nonce}:{server_nonce}".encode("utf-8"),
                            hashlib.sha256
                        ).hexdigest()
                        if hmac.compare_digest(server_proof, expected_proof):
                            matched_nonce = c_nonce
                            break

                    if matched_nonce:
                        self._client_nonce = matched_nonce
                        token_sec = self.auth_token if self.peer_role == Role.ADMIN else self.room_secret
                        session_key = derive_session_key(self.room_secret, matched_nonce, server_nonce, token_sec)
                        self.cipher.set_session_key(session_key)
                        self.logger.debug(f"Oturum şifreleme anahtarı başarıyla kuruldu ({self.peer_role.name}).")
                    else:
                        self.logger.error("Sunucu kanıtı (proof) geçersiz! Olası sahte sunucu (rogue server) saldırısı tespit edildi.")
                        self.auth_fail_reason = "Sahte sunucu (rogue server) algılandı!"
                        if self.on_state_change:
                            self.on_state_change(self.auth_fail_reason)
                        await self.stop()
                        return

                self.logger.debug(f"Sunucu kimliğimizi onayladı. Rol: {self.peer_role.name}")
                if self.on_state_change:
                    self.on_state_change("Kimlik doğrulandı")

        elif cmd == Cmd.AUTH_FAIL and not self.is_server:
            self.authenticated = False
            raw_err = payload.decode("utf-8", errors="ignore").strip()
            if raw_err.startswith("BANNED:"):
                ban_reason = raw_err[len("BANNED:"):].strip()
                self.auth_fail_reason = f"Cihazınız bu sunucudan yasaklanmıştır! ({ban_reason})"
            elif raw_err.startswith("OUTDATED:"):
                outdated_content = raw_err[len("OUTDATED:"):].strip()
                if ":" in outdated_content:
                    parts = outdated_content.split(":", 1)
                    req_ver = parts[0].strip()
                    detail = parts[1].strip()
                    self.auth_fail_reason = f"OUTDATED: {detail}"
                else:
                    self.auth_fail_reason = f"OUTDATED: {outdated_content}"
            else:
                self.auth_fail_reason = raw_err or "Sunucu kimlik anahtarını reddetti!"

            self.logger.error(f"Sunucu reddetti: {self.auth_fail_reason}")
            if self.on_state_change:
                self.on_state_change(self.auth_fail_reason)
            await self.stop()

        elif cmd == Cmd.CONNECT and self.is_server:
            # Target port firewall enforcement!
            if not self.authenticated or not self.acl.is_port_allowed(self.peer_role, target_port):
                close_frame = encode_frame(stream_id, Cmd.CLOSE)
                self.send_high_priority(close_frame)
                return

            self._connecting_streams.add(stream_id)
            self._pending_stream_data[stream_id] = []
            asyncio.create_task(self._connect_server_stream(stream_id, target_port))

        elif cmd == Cmd.DATA:
            if stream_id in self.streams:
                _, writer = self.streams[stream_id]
                try:
                    writer.write(payload)
                    # Only yield/drain if the TCP transport write buffer is saturated (> 64 KB)
                    # Prevents stall/jitter on high-frequency small movement packets
                    transport = writer.transport
                    if transport and transport.get_write_buffer_size() > 65536:
                        await writer.drain()
                except Exception:
                    self._close_stream(stream_id)
                    close_frame = encode_frame(stream_id, Cmd.CLOSE)
                    self.send_high_priority(close_frame)
            elif stream_id in self._connecting_streams:
                self._pending_stream_data.setdefault(stream_id, []).append(payload)
            else:
                close_frame = encode_frame(stream_id, Cmd.CLOSE)
                self.send_high_priority(close_frame)

        elif cmd == Cmd.CLOSE:
            self._close_stream(stream_id)

        elif cmd == Cmd.DISCONNECT:
            self.logger.debug("Bağlantı karşı tarafça sonlandırıldı.")
            if self.on_state_change:
                self.on_state_change("Bağlantı karşı tarafça sonlandırıldı.")
            await self.stop()

    def _close_stream(self, stream_id: int):
        self._connecting_streams.discard(stream_id)
        self._pending_stream_data.pop(stream_id, None)
        if stream_id in self.streams:
            reader, writer = self.streams.pop(stream_id)
            try:
                reader.feed_eof()
            except Exception:
                pass
            try:
                writer.close()
            except Exception:
                pass

    async def _forward_tcp_to_kcp(self, stream_id: int, reader: asyncio.StreamReader):
        """Reads data from local TCP socket and pushes into FIFO queue with backpressure."""
        try:
            while self.running:
                data = await reader.read(8192)
                if not data:
                    break
                if self.mtu < 1300 and len(data) > 4096:
                    for offset in range(0, len(data), 4096):
                        chunk = data[offset : offset + 4096]
                        frame = encode_frame(stream_id, Cmd.DATA, payload=chunk)
                        await self.enqueue_data_frame(frame)
                else:
                    frame = encode_frame(stream_id, Cmd.DATA, payload=data)
                    await self.enqueue_data_frame(frame)
                await asyncio.sleep(0)
        except Exception:
            pass
        finally:
            if stream_id in self.streams:
                close_frame = encode_frame(stream_id, Cmd.CLOSE)
                self.send_high_priority(close_frame)
                self._close_stream(stream_id)

    async def open_client_stream(self, target_port: int, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """Called on client side when a local player connects to 127.0.0.1:25565."""
        stream_id = self.next_stream_id
        self.next_stream_id += 2
        tune_tcp_socket(writer.get_extra_info("socket"))
        self.streams[stream_id] = (reader, writer)

        # Send CONNECT frame to server
        connect_frame = encode_frame(stream_id, Cmd.CONNECT, target_port=target_port)
        self.send_high_priority(connect_frame)

        # Forward incoming player TCP packets to KCP
        await self._forward_tcp_to_kcp(stream_id, reader)
