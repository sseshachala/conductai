"""
AES-256-GCM encryption for credential storage.
Key is derived via HKDF-SHA256 from settings.encryption_key so any-length
passphrase produces a full-entropy 32-byte key. Startup fails fast if the
default dev key is used in production.
"""
import base64
import json
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.core.config import settings

_DEV_KEY = "dev-only-32-byte-key-change-this!"


def _key() -> bytes:
    raw = settings.encryption_key
    if raw == _DEV_KEY and os.getenv("ENVIRONMENT", "development") == "production":
        raise RuntimeError(
            "ENCRYPTION_KEY is still the default dev value in production. "
            "Set a random 32-byte ENCRYPTION_KEY environment variable."
        )
    return HKDF(
        algorithm=SHA256(),
        length=32,
        salt=b"conductai-vault-v1",
        info=b"credential-encryption",
    ).derive(raw.encode())


def encrypt(data: dict) -> str:
    nonce = os.urandom(12)
    ct = AESGCM(_key()).encrypt(nonce, json.dumps(data).encode(), None)
    return base64.b64encode(nonce + ct).decode()


def decrypt(blob: str) -> dict:
    raw = base64.b64decode(blob)
    nonce, ct = raw[:12], raw[12:]
    plaintext = AESGCM(_key()).decrypt(nonce, ct, None)
    return json.loads(plaintext)
