"""
P2P Tunnel Rendezvous & Signaling Module.
Handles peer endpoint exchange (Public IP & Port + Local LAN Port) across CGNAT and Firewalls.
Features:
- Zero-Configuration HTTPS Signaling via ntfy.sh (port 443, never blocked by mobile/CGNAT firewalls)
- End-to-End ChaCha20-Poly1305 encryption (Zero-Knowledge: signaling servers see only encrypted hex)
- Deterministic Room IDs derived from connection codes/endpoints
- Background streaming listener with automatic reconnection and fallback polling
"""

import json
import logging
import threading
import time
import urllib.request
import urllib.error
from typing import Optional, Callable, Dict, Any

from core.crypto import PacketCipher, derive_key

logger = logging.getLogger("P2P_Signaling")


def get_room_id_from_code(code_or_addr: str) -> str:
    """
    Computes a deterministic room ID for any server key or endpoint format.
    """
    from core.invite import derive_credentials_from_key, short_code_to_ip_port, ip_port_to_short_code

    clean = code_or_addr.strip().replace(" ", "").upper()
    if ":" in clean:
        parts = clean.split(":")
        try:
            ip = parts[0]
            port = int(parts[1])
            sc = ip_port_to_short_code(ip, port)
            return f"p2ptun_{sc.replace('-', '').lower()}"
        except Exception:
            pass

    short_pair = short_code_to_ip_port(clean)
    if short_pair:
        clean_hex = clean.replace("-", "").lower()
        return f"p2ptun_{clean_hex}"

    room_id, _, _ = derive_credentials_from_key(clean)
    return room_id


DEFAULT_BROKERS = ["https://ntfy.envs.net", "https://ntfy.sh"]


class SignalingClient:
    """
    Encrypted signaling client using HTTPS pub-sub for fast peer discovery.
    Supports concurrent multi-broker listening and broadcast fallback to prevent HTTP 429 rate-limiting.
    """

    def __init__(self, room_id: str, room_secret: str, broker_base: Optional[str] = None):
        import secrets
        self.room_id = room_id
        self.room_secret = room_secret
        self.cipher = PacketCipher(derive_key(room_secret))
        if broker_base:
            self.brokers = [broker_base.rstrip("/")]
        else:
            self.brokers = list(DEFAULT_BROKERS)
        self.broker_base = self.brokers[0]
        self._stop_event = threading.Event()
        self._listener_threads = []
        self._seen_ids = set()
        self._seen_lock = threading.Lock()

    def publish(self, msg_type: str, payload_dict: Dict[str, Any], timeout: float = 3.5) -> bool:
        """
        Encrypts and broadcasts a signaling message across available brokers.
        Returns True if at least one broker accepted the message.
        """
        import secrets
        payload_dict["type"] = msg_type
        payload_dict["ts"] = time.time()
        payload_dict.setdefault("msg_id", secrets.token_hex(8))

        success = False
        try:
            raw_json = json.dumps(payload_dict).encode("utf-8")
            encrypted = self.cipher.encrypt(raw_json)
            body = encrypted.hex().encode("utf-8")

            for broker in self.brokers:
                try:
                    url = f"{broker}/{self.room_id}"
                    req = urllib.request.Request(
                        url,
                        data=body,
                        headers={"Title": "P2P_Signal", "Priority": "urgent", "User-Agent": "P2PTunnel/2.0"}
                    )
                    with urllib.request.urlopen(req, timeout=timeout) as resp:
                        if resp.status == 200:
                            success = True
                            break
                except urllib.error.HTTPError as he:
                    if he.code == 429:
                        continue
                except Exception:
                    continue
        except Exception:
            pass

        return success

    def publish_nowait(self, msg_type: str, payload_dict: Dict[str, Any]):
        """Asynchronously publishes message in a background daemon thread without blocking caller."""
        threading.Thread(target=self.publish, args=(msg_type, payload_dict), daemon=True).start()

    def start_listening(self, on_message: Callable[[Dict[str, Any]], None]):
        """
        Starts background streaming listeners concurrently on all brokers.
        Uses since=30s to only receive real-time messages and ignore historical backlogs.
        """
        self._stop_event.clear()

        def _worker_for_broker(broker_url: str):
            url = f"{broker_url}/{self.room_id}/json?since=60s"
            while not self._stop_event.is_set():
                try:
                    req = urllib.request.Request(url, headers={"User-Agent": "P2PTunnel/2.0"})
                    with urllib.request.urlopen(req, timeout=45) as resp:
                        for line in resp:
                            if self._stop_event.is_set():
                                break
                            line_str = line.decode("utf-8", errors="ignore").strip()
                            if not line_str:
                                continue
                            try:
                                d = json.loads(line_str)
                                if d.get("event") == "message" and d.get("message"):
                                    self._dispatch_raw_message(d["message"], on_message)
                            except Exception:
                                continue
                except urllib.error.HTTPError as he:
                    if he.code == 429:
                        time.sleep(10.0)
                    else:
                        time.sleep(2.0)
                except Exception:
                    time.sleep(2.0)

        for broker in self.brokers:
            t = threading.Thread(target=_worker_for_broker, args=(broker,), daemon=True)
            t.start()
            self._listener_threads.append(t)

    def _dispatch_raw_message(self, hex_payload: str, callback: Callable[[Dict[str, Any]], None]):
        import hashlib
        try:
            encrypted = bytes.fromhex(hex_payload.strip())
            decrypted = self.cipher.decrypt(encrypted)
            data = json.loads(decrypted.decode("utf-8"))

            # Discard stale messages older than 60 seconds
            msg_ts = data.get("ts")
            if msg_ts and (time.time() - msg_ts > 60.0):
                return
            
            # Message deduplication across multi-broker reception
            msg_id = data.get("msg_id") or hashlib.sha256(decrypted).hexdigest()
            with self._seen_lock:
                if msg_id in self._seen_ids:
                    return
                self._seen_ids.add(msg_id)
                if len(self._seen_ids) > 500:
                    self._seen_ids.clear()
            
            callback(data)
        except Exception:
            pass

    def poll_messages(self, timeout: float = 2.0) -> list:
        """
        One-shot poll of recent messages (past 60s) in the room with multi-broker aggregation and deduplication.
        """
        import hashlib
        messages = []
        for broker in self.brokers:
            url = f"{broker}/{self.room_id}/json?poll=1&since=5m"
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "P2PTunnel/2.0"})
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    content = resp.read().decode("utf-8")
                    for line in content.splitlines():
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            d = json.loads(line)
                            if d.get("event") == "message" and d.get("message"):
                                encrypted = bytes.fromhex(d["message"].strip())
                                decrypted = self.cipher.decrypt(encrypted)
                                data = json.loads(decrypted.decode("utf-8"))
                                msg_ts = data.get("ts")
                                if msg_ts and (time.time() - msg_ts > 60.0):
                                    continue
                                msg_id = data.get("msg_id") or hashlib.sha256(decrypted).hexdigest()
                                with self._seen_lock:
                                    if msg_id not in self._seen_ids:
                                        self._seen_ids.add(msg_id)
                                        messages.append(data)
                        except Exception:
                            pass
            except Exception:
                continue
        return messages

    def stop(self):
        """Stops all background listener threads."""
        self._stop_event.set()


# Backward compatibility alias
RendezvousClient = SignalingClient

