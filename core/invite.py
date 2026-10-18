"""
P2P Tunnel Invite Code & Key Formatter.
"""

import base64
import hashlib
import json
import secrets
import socket
import struct
from typing import Optional, Dict

DEFAULT_ROOM_SECRET = "sec_p2p_default_fallback"
DEFAULT_PLAYER_TOKEN = "tok_p2p_player_fallback"


def generate_server_key(length: int = 12) -> str:
    """
    Generates a unique, high-entropy persistent server key.
    Standard: 12 hex characters (48-bit entropy) -> XXXX-XXXX-XXXX.
    """
    h = secrets.token_hex(6).upper()
    return f"{h[:4]}-{h[4:8]}-{h[8:12]}"


def normalize_server_key(key: str) -> str:
    """
    Normalizes server key by removing dashes/spaces and formatting into standard XXXX-XXXX-XXXX (12 hex characters).
    """
    clean = (key or "").strip().replace("-", "").replace(" ", "").upper()
    if len(clean) == 12:
        return f"{clean[:4]}-{clean[4:8]}-{clean[8:12]}"
    return clean


def derive_credentials_from_key(key: str) -> tuple:
    """
    Derives deterministic (room_id, room_secret, player_token) strictly from persistent server key.
    Strictly accepts standard 12 hex character keys (XXXX-XXXX-XXXX).
    """
    clean = key.strip().replace("-", "").replace(" ", "").upper()
    if len(clean) != 12:
        raise ValueError("Geçersiz bağlantı kodu! Standart XXXX-XXXX-XXXX (12 karakter) formatında olmalıdır.")
    h = hashlib.sha256(f"P2P_TUNNEL_KEY_{clean}".encode("utf-8")).hexdigest()
    room_id = f"p2ptun_{h[:16]}"
    room_secret = f"SEC_{h[16:40]}"
    player_token = f"TOK_{h[40:56]}"
    return room_id, room_secret, player_token


def derive_room_credentials(ip: str, port: int) -> tuple:
    """Legacy fallback for direct IP:port."""
    raw = f"P2P_TUNNEL_KEY_{ip}_{port}"
    h = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    code_hex = ip_port_to_short_code(ip, port).replace("-", "").lower()
    room_id = f"p2ptun_{code_hex}"
    room_secret = f"SEC_{h[:24]}"
    player_token = f"TOK_{h[24:40]}"
    return room_id, room_secret, player_token


def ip_port_to_short_code(ip: str, port: int) -> str:
    """Encodes IPv4 and port (6 bytes) into a 12-char hex string: XXXX-XXXX-XXXX."""
    try:
        ip_bytes = socket.inet_aton(ip)
        port_bytes = struct.pack("!H", port)
        raw = (ip_bytes + port_bytes).hex().upper()
        return f"{raw[:4]}-{raw[4:8]}-{raw[8:12]}"
    except Exception:
        return f"{ip}:{port}"


def short_code_to_ip_port(code: str) -> Optional[tuple]:
    """Decodes 12-char hex string into (ip, port)."""
    code = code.strip().replace("-", "").replace(" ", "").upper()
    if len(code) == 12:
        try:
            raw = bytes.fromhex(code)
            ip = socket.inet_ntoa(raw[:4])
            port = struct.unpack("!H", raw[4:6])[0]
            return ip, port
        except Exception:
            pass
    return None


def parse_invite_code(input_str: str) -> Optional[Dict]:
    """
    Universally parses server connection string:
    1. Persistent Server Key (XXXX-YYYY)
    2. Direct IP:Port
    3. Short Hex Code
    """
    input_str = input_str.strip()
    if not input_str:
        return None

    clean = normalize_server_key(input_str)

    if "@" in input_str:
        key_part, addr_part = input_str.split("@", 1)
        key_part = normalize_server_key(key_part)
        addr_part = addr_part.strip()
        try:
            room_id, room_sec, play_tok = derive_credentials_from_key(key_part)
        except ValueError:
            return None
        target_ip = addr_part
        target_port = 25566
        if ":" in addr_part:
            p_ip, p_port = addr_part.split(":", 1)
            target_ip = p_ip.strip()
            try:
                target_port = int(p_port.strip())
            except ValueError:
                pass
        return {
            "name": f"Sunucu ({key_part})",
            "key": key_part,
            "ip": target_ip,
            "port": target_port,
            "local_port": target_port,
            "sec": room_sec,
            "tok": play_tok,
            "room": room_id,
        }

    if not clean.startswith("P2P-") and not clean.startswith("P2P_") and ":" not in clean:
        try:
            room_id, room_sec, play_tok = derive_credentials_from_key(clean)
            return {
                "name": f"Sunucu ({clean})",
                "key": clean,
                "ip": None,
                "port": None,
                "local_port": None,
                "sec": room_sec,
                "tok": play_tok,
                "room": room_id,
            }
        except ValueError:
            pass

    if ":" in input_str and not input_str.startswith("P2P-") and not input_str.startswith("p2p-"):
        parts = input_str.split(":")
        if len(parts) == 2:
            ip = parts[0].strip()
            try:
                port = int(parts[1].strip())
                room_id, room_sec, play_tok = derive_room_credentials(ip, port)
                return {
                    "name": f"Sunucu ({ip}:{port})",
                    "key": clean,
                    "ip": ip,
                    "port": port,
                    "local_port": port,
                    "sec": room_sec,
                    "tok": play_tok,
                    "room": room_id,
                }
            except ValueError:
                pass

    short_res = short_code_to_ip_port(input_str)
    if short_res:
        ip, port = short_res
        room_id, room_sec, play_tok = derive_room_credentials(ip, port)
        return {
            "name": f"Sunucu ({ip}:{port})",
            "key": clean,
            "ip": ip,
            "port": port,
            "local_port": 25566,
            "sec": room_sec,
            "tok": play_tok,
            "room": room_id,
        }

    clean_b64 = input_str
    if clean_b64.startswith("P2P-") or clean_b64.startswith("p2p-"):
        clean_b64 = clean_b64[4:]
    pad = (4 - len(clean_b64) % 4) % 4
    clean_b64 += "=" * pad

    try:
        raw = base64.urlsafe_b64decode(clean_b64.encode("utf-8"))
        data = json.loads(raw.decode("utf-8"))
        ip = data.get("ip", "127.0.0.1")
        port = int(data.get("p", data.get("port", 25566)))
        return {
            "name": data.get("n", data.get("name", "Sunucu")),
            "ip": ip,
            "port": port,
            "local_port": int(data.get("lp", data.get("local_port", 25566))),
            "sec": data.get("s", data.get("sec", DEFAULT_ROOM_SECRET)),
            "tok": data.get("t", data.get("tok", DEFAULT_PLAYER_TOKEN)),
            "room": data.get("r", data.get("room", "p2p_default")),
        }
    except Exception:
        return None
