"""
AES-256-GCM encryption for credential storage.
Key is truncated/padded to 32 bytes from settings.encryption_key.
The ENCRYPTION_KEY env var should be a strong random 32+ byte value (use
`python3 -c "import secrets; print(secrets.token_hex(32))"` to generate one).
Startup fails fast if the default dev key is used in production.
"""
import base64
import json
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings

_DEV_KEY = "dev-only-32-byte-key-change-this!"


def _key() -> bytes:
    raw = settings.encryption_key
    if raw == _DEV_KEY and os.getenv("ENVIRONMENT", "development") == "production":
        raise RuntimeError(
            "ENCRYPTION_KEY is still the default dev value in production. "
            "Set a random 32-byte ENCRYPTION_KEY environment variable."
        )
    raw_bytes = raw.encode()
    if len(raw_bytes) < 32:
        raise RuntimeError(
            f"ENCRYPTION_KEY must be at least 32 bytes (got {len(raw_bytes)}). "
            "Generate one with: python3 -c \"import secrets; print(secrets.token_hex(32))\""
        )
    return raw_bytes[:32]


def encrypt(data: dict) -> str:
    nonce = os.urandom(12)
    ct = AESGCM(_key()).encrypt(nonce, json.dumps(data).encode(), None)
    return base64.b64encode(nonce + ct).decode()


def decrypt(blob: str) -> dict:
    raw = base64.b64decode(blob)
    nonce, ct = raw[:12], raw[12:]
    plaintext = AESGCM(_key()).decrypt(nonce, ct, None)
    return json.loads(plaintext)
