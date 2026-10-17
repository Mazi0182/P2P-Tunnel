"""
P2P_MC Core Cryptography & Anti-DPI Obfuscation Engine.
OpenSSL C-bindings (cryptography) ile ultra-düşük gecikmeli şifreleme sağlar.
"""

import os
import struct
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes

NONCE_SIZE = 12  # ChaCha20-Poly1305 standard nonce size
KEY_SIZE = 32    # 256-bit key


def derive_key(secret: str, salt: bytes = b"P2P_MC_ANTI_DPI_SALT_2026") -> bytes:
    """Derives a 256-bit encryption key from a passphrase/token using HKDF-SHA256."""
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=KEY_SIZE,
        salt=salt,
        info=b"p2p-mc-tunnel-v1",
    )
    return hkdf.derive(secret.encode("utf-8") if isinstance(secret, str) else secret)


class PacketCipher:
    """
    AEAD ChaCha20-Poly1305 packet encryptor/decryptor with dynamic padding.
    Packets are completely indistinguishable from high-entropy random white noise.
    No static magic bytes or protocol signatures.
    """

    def __init__(self, key: bytes):
        if len(key) != KEY_SIZE:
            raise ValueError(f"Key must be exactly {KEY_SIZE} bytes")
        self.key = key
        self.aead = ChaCha20Poly1305(self.key)

    def encrypt(self, plaintext: bytes) -> bytes:
        """
        Encrypts plaintext with dynamic padding and random nonce.
        Packet structure: [ 12B Nonce ] + [ Encrypted (Payload + Padding + 1B PadLen) + 16B Poly1305 Tag ]
        """
        # Dynamic padding: 8 to 24 bytes of random noise to defeat packet-length fingerprinting
        pad_len = os.urandom(1)[0] % 16 + 8
        padding = os.urandom(pad_len)
        
        # Payload format: raw_payload + padding + 1 byte padding length
        padded_payload = plaintext + padding + bytes([pad_len])
        
        nonce = os.urandom(NONCE_SIZE)
        ciphertext = self.aead.encrypt(nonce, padded_payload, None)
        
        return nonce + ciphertext

    def decrypt(self, packet: bytes) -> bytes:
        """
        Decrypts packet, verifies Poly1305 MAC and strips dynamic padding.
        Returns original plaintext. Raises InvalidTag if corrupted/tampered.
        """
        if len(packet) < NONCE_SIZE + 16 + 1:  # Nonce + Tag + Min PadLen
            raise ValueError("Packet too short")
        
        nonce = packet[:NONCE_SIZE]
        ciphertext = packet[NONCE_SIZE:]
        
        padded_payload = self.aead.decrypt(nonce, ciphertext, None)
        
        # Extract padding length
        pad_len = padded_payload[-1]
        if pad_len + 1 > len(padded_payload):
            raise ValueError("Corrupted padding")
            
        return padded_payload[: -(pad_len + 1)]
