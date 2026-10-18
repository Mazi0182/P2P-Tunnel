"""
P2P Tunnel RFC 5389 STUN Client.
Sorgulanan UDP soketinin CGNAT dışındaki Public IP ve Port bilgisini anında çözer.
"""

import os
import socket
import struct
from typing import Optional, Tuple

# RFC 5389 Constants
MAGIC_COOKIE = 0x2112A442
BINDING_REQUEST = 0x0001
BINDING_RESPONSE = 0x0101
ATTR_MAPPED_ADDRESS = 0x0001
ATTR_XOR_MAPPED_ADDRESS = 0x0020

DEFAULT_STUN_SERVERS = [
    ("stun.l.google.com", 19302),
    ("stun1.l.google.com", 19302),
    ("stun2.l.google.com", 19302),
    ("stun.cloudflare.com", 3478),
]


def create_stun_request() -> Tuple[bytes, bytes]:
    """Generates an RFC 5389 Binding Request packet and 12-byte Transaction ID."""
    trans_id = os.urandom(12)
    packet = struct.pack("!HHI", BINDING_REQUEST, 0, MAGIC_COOKIE) + trans_id
    return packet, trans_id


def parse_stun_response(data: bytes, trans_id: Optional[bytes] = None) -> Optional[Tuple[str, int]]:
    """Parses STUN Binding Response and extracts public IP and port."""
    if len(data) < 20:
        return None

    msg_type, msg_len, magic = struct.unpack("!HHI", data[:8])
    if magic != MAGIC_COOKIE or msg_type != BINDING_RESPONSE:
        return None

    resp_trans_id = data[8:20]
    if trans_id is not None and resp_trans_id != trans_id:
        return None

    offset = 20
    end = 20 + msg_len

    while offset + 4 <= end and offset + 4 <= len(data):
        attr_type, attr_len = struct.unpack("!HH", data[offset : offset + 4])
        attr_val = data[offset + 4 : offset + 4 + attr_len]
        offset += 4 + attr_len
        # Pad to 4-byte boundary
        if attr_len % 4 != 0:
            offset += 4 - (attr_len % 4)

        if attr_type == ATTR_XOR_MAPPED_ADDRESS and len(attr_val) >= 8:
            _, family, xport = struct.unpack("!BBH", attr_val[:4])
            port = xport ^ (MAGIC_COOKIE >> 16)
            if family == 1 and len(attr_val) >= 8:  # IPv4
                xip = struct.unpack("!I", attr_val[4:8])[0]
                ip = socket.inet_ntoa(struct.pack("!I", xip ^ MAGIC_COOKIE))
                return ip, port

        elif attr_type == ATTR_MAPPED_ADDRESS and len(attr_val) >= 8:
            _, family, port = struct.unpack("!BBH", attr_val[:4])
            if family == 1:  # IPv4
                ip = socket.inet_ntoa(attr_val[4:8])
                return ip, port

    return None


def get_public_endpoint(sock: socket.socket, servers=DEFAULT_STUN_SERVERS, timeout=2.0) -> Optional[Tuple[str, int]]:
    """
    Queries STUN servers using the specified bound UDP socket.
    Returns (public_ip, public_port) or None if all servers fail.
    """
    orig_timeout = sock.gettimeout()
    sock.settimeout(timeout)

    try:
        for host, port in servers:
            try:
                dest_ip = socket.gethostbyname(host)
                packet, trans_id = create_stun_request()
                sock.sendto(packet, (dest_ip, port))

                resp_data, _ = sock.recvfrom(2048)
                endpoint = parse_stun_response(resp_data, trans_id)
                if endpoint:
                    return endpoint
            except (socket.timeout, OSError):
                continue
    finally:
        sock.settimeout(orig_timeout)

    return None
