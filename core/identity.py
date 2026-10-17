"""
P2P_MC Machine Identity & Persistent Server Addressing.
Generates a deterministic, persistent server ID and secret per machine.
Ensures that the server address/room does not change across restarts.
"""

import hashlib
import json
import os
import uuid


from core.paths import get_server_config_path


def get_machine_identifier() -> str:
    """Returns a deterministic 12-character hex ID unique to this physical machine."""
    node = uuid.getnode()
    raw = f"P2P_MC_MACHINE_{node}_{os.environ.get('COMPUTERNAME', '')}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def get_or_create_server_identity(config_path: str = None) -> dict:
    """
    Loads or generates a persistent server identity.
    Guarantees the same invite code and room ID per machine forever.
    """
    config_path = config_path or get_server_config_path()
    machine_id = get_machine_identifier()
    default_config = {
        "server_name": f"P2P-Server-{machine_id[:6]}",
        "room_id": f"p2p_room_{machine_id}",
        "room_secret": hashlib.sha256(f"SEC_{machine_id}_P2P".encode()).hexdigest()[:24],
        "player_token": hashlib.sha256(f"TOK_{machine_id}_MC".encode()).hexdigest()[:16],
        "admin_secret": hashlib.sha256(f"ADM_{machine_id}_SSH".encode()).hexdigest()[:20],
        "game_port": 25565,
        "server_udp_port": 25566,
        "broker_url": "https://test.mosquitto.org:8081", # or HTTP broker
    }

    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                # Keep machine-consistent room_id if missing
                if not loaded.get("room_id"):
                    loaded["room_id"] = default_config["room_id"]
                if not loaded.get("room_secret"):
                    loaded["room_secret"] = default_config["room_secret"]
                if not loaded.get("player_token"):
                    loaded["player_token"] = default_config["player_token"]
                return loaded
        except Exception:
            pass

    # Save initial deterministic config
    os.makedirs(os.path.dirname(os.path.abspath(config_path)), exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(default_config, f, indent=2)
    return default_config
