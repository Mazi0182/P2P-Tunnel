"""
P2P_MC Multiplexing Protocol & Packet Definitions.
Frame Structure (Inside Encrypted Payload):
  [ 4B Stream ID ] + [ 1B Cmd ] + [ 2B Port ] + [ 2B Payload Length ] + [ Payload Data ]
"""

import struct
from enum import IntEnum

# Frame Commands
class Cmd(IntEnum):
    CONNECT   = 0x01  # Open new TCP stream to specified target port
    DATA      = 0x02  # Stream data payload
    CLOSE     = 0x03  # Close TCP stream (FIN)
    PING      = 0x04  # Latency keep-alive ping (Carries 8B timestamp)
    PONG      = 0x05  # Latency keep-alive pong
    AUTH      = 0x06  # Handshake & Role authentication
    AUTH_OK   = 0x07  # Authentication accepted
    AUTH_FAIL = 0x08  # Authentication rejected
    DISCONNECT= 0x09  # Graceful tunnel disconnection / shutdown

# Role Definitions
class Role(IntEnum):
    PLAYER = 0x01  # Strictly limited to port 25565 only
    ADMIN  = 0x02  # Full port access (SSH 22, etc.)

HEADER_STRUCT = struct.Struct("!IBHH")  # stream_id (4B), cmd (1B), target_port (2B), length (2B)
HEADER_LEN = HEADER_STRUCT.size  # 9 bytes


def encode_frame(stream_id: int, cmd: Cmd, target_port: int = 0, payload: bytes = b"") -> bytes:
    """Encodes a multiplexed stream frame."""
    return HEADER_STRUCT.pack(stream_id, cmd, target_port, len(payload)) + payload


def decode_frame(data: bytes):
    """
    Decodes a multiplexed stream frame.
    Returns: (stream_id, cmd, target_port, payload, remaining_data) or None if incomplete.
    """
    if len(data) < HEADER_LEN:
        return None
    
    stream_id, cmd_raw, target_port, length = HEADER_STRUCT.unpack_from(data, 0)
    try:
        cmd = Cmd(cmd_raw)
    except ValueError:
        return None

    if len(data) < HEADER_LEN + length:
        return None  # Incomplete payload
    
    payload = data[HEADER_LEN : HEADER_LEN + length]
    remainder = data[HEADER_LEN + length :]
    return stream_id, cmd, target_port, payload, remainder
