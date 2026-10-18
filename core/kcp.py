"""
P2P Tunnel Fast ARQ Reliable Stream Layer.
Optimized for zero packet loss, zero corrupted frames, and ultra-low latency.
Includes Cython C-acceleration with fully transparent pure-Python ARQ fallback.
"""

import time
import struct
from typing import Callable, Optional, Generator

HAS_CYTHON_KCP = False
try:
    from kcp.extension import KCP as CKCP
    HAS_CYTHON_KCP = True
except Exception:
    try:
        import kcp
        from kcp import KCP as CKCP
        HAS_CYTHON_KCP = True
    except Exception:
        HAS_CYTHON_KCP = False


KCP_HEADER_STRUCT = struct.Struct("<IBBHIIII")
KCP_HEADER_SIZE = 24

IKCP_CMD_PUSH = 81
IKCP_CMD_ACK = 82
IKCP_CMD_WASK = 83
IKCP_CMD_WINS = 84


class _PurePythonARQ:
    """
    Robust pure-Python Sliding-Window ARQ fallback.
    100% wire-compatible with standard C-KCP (24-byte little-endian header <IBBHIIII).
    Allows seamless interoperability between Cython C-KCP and pure-Python peers.
    """

    def __init__(
        self,
        conv_or_cb,
        outbound_callback: Optional[Callable[[bytes], None]] = None,
        max_chunk: int = 1300,
    ):
        if callable(conv_or_cb):
            self.conv_id = 2026
            self.outbound_callback = conv_or_cb
        else:
            self.conv_id = int(conv_or_cb)
            self.outbound_callback = outbound_callback
        self.max_chunk = max(500, max_chunk)
        self.send_seq = 0
        self.recv_seq = 0
        self.wnd = 512
        self.unacked = {}  # sn -> (timestamp, data_frame)
        self.receive_buffer = {}  # sn -> payload
        self.received_queue = []

    def enqueue(self, data: bytes):
        max_chunk = self.max_chunk
        now_ts = int(time.time() * 1000) & 0xFFFFFFFF
        for i in range(0, len(data), max_chunk):
            chunk = data[i : i + max_chunk]
            header = KCP_HEADER_STRUCT.pack(
                self.conv_id,
                IKCP_CMD_PUSH,
                0,              # frg
                self.wnd,       # wnd
                now_ts,         # ts
                self.send_seq,  # sn
                self.recv_seq,  # una
                len(chunk),     # len
            )
            frame = header + chunk
            self.unacked[self.send_seq] = (time.time(), frame)
            self.send_seq = (self.send_seq + 1) & 0xFFFFFFFF
            if self.outbound_callback:
                self.outbound_callback(frame)

    def flush(self):
        pass

    def update(self):
        now = time.time()
        # Retransmit lost packets after 150ms timeout
        for sn, (ts, frame) in list(self.unacked.items()):
            if now - ts > 0.15:
                if self.outbound_callback:
                    self.outbound_callback(frame)
                self.unacked[sn] = (now, frame)

    def receive(self, packet: bytes):
        pkt_len = len(packet)
        offset = 0
        while offset + KCP_HEADER_SIZE <= pkt_len:
            conv, cmd, frg, wnd, ts, sn, una, length = KCP_HEADER_STRUCT.unpack_from(packet, offset)
            offset += KCP_HEADER_SIZE
            if offset + length > pkt_len:
                break
            payload = packet[offset : offset + length]
            offset += length

            if self.conv_id == 0 or conv == self.conv_id:
                self.conv_id = conv

            # Process cumulative ACK una: all packets strictly before una are acknowledged
            for old_sn in list(self.unacked.keys()):
                if (una - old_sn) & 0xFFFFFFFF < 0x7FFFFFFF and old_sn != una:
                    self.unacked.pop(old_sn, None)

            if cmd == IKCP_CMD_ACK:
                # Direct ACK for segment sn
                self.unacked.pop(sn, None)
            elif cmd == IKCP_CMD_PUSH:
                # Send immediate ACK segment back with received segment's ts
                ack_seg = KCP_HEADER_STRUCT.pack(
                    conv,
                    IKCP_CMD_ACK,
                    0,
                    self.wnd,
                    ts,
                    sn,
                    self.recv_seq,
                    0,
                )
                if self.outbound_callback:
                    self.outbound_callback(ack_seg)

                if length > 0:
                    if sn >= self.recv_seq and sn not in self.receive_buffer:
                        self.receive_buffer[sn] = payload

                    while self.recv_seq in self.receive_buffer:
                        self.received_queue.append(self.receive_buffer.pop(self.recv_seq))
                        self.recv_seq = (self.recv_seq + 1) & 0xFFFFFFFF
            elif cmd == IKCP_CMD_WASK:
                wins_seg = KCP_HEADER_STRUCT.pack(
                    conv,
                    IKCP_CMD_WINS,
                    0,
                    self.wnd,
                    int(time.time() * 1000) & 0xFFFFFFFF,
                    0,
                    self.recv_seq,
                    0,
                )
                if self.outbound_callback:
                    self.outbound_callback(wins_seg)

    def get_outbound_packets(self) -> int:
        return len(self.unacked)

    def get_all_received(self) -> Generator[bytes, None, None]:
        while self.received_queue:
            yield self.received_queue.pop(0)


class KCPPeer:
    """
    Dual-mode reliable peer:
    Uses Cython C-extension (hardware speed) when available,
    seamlessly falls back to pure-Python ARQ without crashing.
    """

    def __init__(
        self,
        conv_id: int,
        outbound_callback: Callable[[bytes], None],
        mtu: int = 1350,
        no_delay: bool = True,
        interval: int = 10,
        resend: int = 2,
        no_congestion: bool = True,
    ):
        self.conv_id = conv_id
        self.outbound_callback = outbound_callback
        self.mtu = mtu
        self.interval = interval

        if HAS_CYTHON_KCP:
            try:
                self._kcp = CKCP(
                    conv_id,
                    max_transmission=mtu,
                    no_delay=no_delay,
                    update_interval=interval,
                    resend_count=resend,
                    no_congestion_control=no_congestion,
                    send_window_size=512,
                    receive_window_size=1024,
                )
                self._kcp.include_outbound_handler(self._on_kcp_outbound)
                self.update()
                self._is_cython = True
            except Exception:
                self._kcp = _PurePythonARQ(self.conv_id, self.outbound_callback, max_chunk=max(500, mtu - 50))
                self._is_cython = False
        else:
            self._kcp = _PurePythonARQ(self.conv_id, self.outbound_callback, max_chunk=max(500, mtu - 50))
            self._is_cython = False

    def set_mtu(self, mtu: int):
        """Dynamically adjusts KCP MTU (e.g. 1350 normal <-> 1100 when VPN is active)."""
        mtu = max(900, min(1400, int(mtu)))
        if mtu == self.mtu:
            return
        self.mtu = mtu
        if self._is_cython:
            try:
                self._kcp.set_maximum_transmission(mtu)
            except Exception:
                pass
        else:
            self._kcp.max_chunk = max(500, mtu - 50)

    def _on_kcp_outbound(self, _inst, data: bytes):
        self.outbound_callback(data)

    def enqueue(self, data: bytes):
        self._kcp.enqueue(data)

    def flush(self):
        self._kcp.flush()

    def send(self, data: bytes):
        self._kcp.enqueue(data)
        self._kcp.flush()

    def receive(self, packet: bytes):
        self._kcp.receive(packet)

    def update(self):
        self._kcp.update()

    def get_outbound_count(self) -> int:
        if self._is_cython:
            try:
                return self._kcp.get_outbound_packets()
            except Exception:
                return 0
        return len(getattr(self._kcp, "unacked", {}))

    def get_received(self) -> Generator[bytes, None, None]:
        yield from self._kcp.get_all_received()
