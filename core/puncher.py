"""
P2P_MC UDP Hole Puncher & NAT Traversal Engine.
Punches bidirectional UDP pinholes through CGNAT firewalls and locks peer endpoints.
"""

import time
import socket
from typing import Tuple, Optional, Callable
from core.crypto import PacketCipher

# Punching Control Opcode
PUNCH_SYN = b"P2P_MC_PUNCH_SYN"
PUNCH_ACK = b"P2P_MC_PUNCH_ACK"


class UDPPuncher:
    """
    Manages active hole punching and NAT binding verification.
    """

    def __init__(self, sock: socket.socket, cipher: PacketCipher):
        self.sock = sock
        self.cipher = cipher
        self.peer_endpoint: Optional[Tuple[str, int]] = None
        self.is_connected = False
        self.last_rtt_ms = 0.0

    def punch(
        self,
        target_ip: str,
        target_port: int,
        timeout: float = 15.0,
        burst_interval: float = 0.15,
        on_attempt: Optional[Callable[[int], None]] = None,
    ) -> bool:
        """
        Sends repeated encrypted SYN/ACK probes to target until bidirectional lock-in is confirmed.
        """
        target = (target_ip, target_port)
        syn_pkt = self.cipher.encrypt(PUNCH_SYN)
        ack_pkt = self.cipher.encrypt(PUNCH_ACK)

        start_time = time.time()
        orig_timeout = self.sock.gettimeout()
        self.sock.settimeout(burst_interval)

        attempt = 0
        try:
            while time.time() - start_time < timeout:
                attempt += 1
                if on_attempt:
                    on_attempt(attempt)

                # Send punch probe
                try:
                    self.sock.sendto(syn_pkt, target)
                except OSError:
                    pass

                # Listen for incoming response from peer
                try:
                    data, addr = self.sock.recvfrom(2048)
                    try:
                        decrypted = self.cipher.decrypt(data)
                        if decrypted in (PUNCH_SYN, PUNCH_ACK):
                            # Received peer punch! Send ACK back
                            self.sock.sendto(ack_pkt, addr)
                            self.sock.sendto(ack_pkt, addr)
                            self.peer_endpoint = addr
                            self.is_connected = True
                            return True
                    except Exception:
                        pass
                except socket.timeout:
                    continue
        finally:
            self.sock.settimeout(orig_timeout)

        return False
