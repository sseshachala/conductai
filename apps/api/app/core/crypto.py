"""
AES-256-GCM encryption for credential storage.
Key is padded/truncated to 32 bytes from settings.encryption_key.
"""
import base64
import json
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings


def _key() -> bytes:
    raw = settings.encryption_key.encode()
    return (raw + b"\x00" * 32)[:32]


def encrypt(data: dict) -> str:
    nonce = os.urandom(12)
    ct = AESGCM(_key()).encrypt(nonce, json.dumps(data).encode(), None)
    return base64.b64encode(nonce + ct).decode()


def decrypt(blob: str) -> dict:
    raw = base64.b64decode(blob)
    nonce, ct = raw[:12], raw[12:]
    plaintext = AESGCM(_key()).decrypt(nonce, ct, None)
    return json.loads(plaintext)
