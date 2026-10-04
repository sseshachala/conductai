"""Encrypted, verified S3-compatible archives with authenticated checkpoints."""

import gzip
import hashlib
import hmac
import io
import json
import os
from datetime import datetime
from urllib.parse import urlparse
from uuid import UUID

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class ArchiveIntegrityError(ValueError):
    pass


def canonical(value) -> bytes:
    def encode(item):
        if isinstance(item, (UUID, datetime)):
            return item.isoformat() if isinstance(item, datetime) else str(item)
        raise TypeError("Unsupported archive value")
    return json.dumps(value, default=encode, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _secret(value) -> str:
    return value.get_secret_value() if hasattr(value, "get_secret_value") else value or ""


def archive_keys(settings):
    signing = _secret(settings.guard_audit_archive_signing_key)
    encryption = _secret(settings.guard_audit_archive_encryption_key)
    if len(signing) < 32 or len(encryption) < 32:
        raise ValueError("Audit archive signing and encryption keys must each contain at least 32 characters")
    if hmac.compare_digest(signing, encryption):
        raise ValueError("Use separate archive signing and encryption keys")
    return signing.encode(), hashlib.sha256(b"conduct-audit-v1:" + encryption.encode()).digest()


def sign_manifest(manifest: dict, key: bytes) -> str:
    return hmac.new(key, canonical(manifest), hashlib.sha256).hexdigest()


def manifest_object_key(manifest: dict) -> str:
    return manifest["object_key"] + "." + digest(canonical(manifest)) + ".manifest.json"


def verify_manifest(manifest: dict, signature: str, key: bytes, *, workspace_id: str,
                    previous_hash: str | None = None) -> None:
    if not hmac.compare_digest(sign_manifest(manifest, key), signature):
        raise ArchiveIntegrityError("Archive checkpoint authentication failed")
    if manifest.get("version") != 1 or manifest.get("workspace_id") != str(workspace_id):
        raise ArchiveIntegrityError("Archive checkpoint scope mismatch")
    if previous_hash is not None and manifest.get("previous_manifest_hash") != previous_hash:
        raise ArchiveIntegrityError("Archive checkpoint chain is broken")


def encrypt_payload(payload: bytes, key: bytes, *, workspace_id: str) -> bytes:
    nonce = os.urandom(12)
    return nonce + AESGCM(key).encrypt(nonce, gzip.compress(payload, mtime=0), str(workspace_id).encode())


def decrypt_payload(payload: bytes, key: bytes, *, workspace_id: str, max_bytes: int) -> bytes:
    try:
        compressed = AESGCM(key).decrypt(payload[:12], payload[12:], str(workspace_id).encode())
        with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as stream:
            plain = stream.read(max_bytes + 1)
        if len(plain) > max_bytes:
            raise ArchiveIntegrityError("Archive exceeds configured size limit")
        return plain
    except ArchiveIntegrityError:
        raise
    except Exception as exc:
        raise ArchiveIntegrityError("Archive payload authentication failed") from exc


class S3ArchiveStore:
    def __init__(self, settings, *, client=None):
        if not settings.guard_audit_archive_bucket:
            raise ValueError("GUARD_AUDIT_ARCHIVE_BUCKET is required")
        if settings.guard_audit_archive_endpoint:
            endpoint = urlparse(settings.guard_audit_archive_endpoint)
            if endpoint.scheme != "https" or not endpoint.hostname or endpoint.username or endpoint.password:
                raise ValueError("Archive endpoint must be an HTTPS URL without credentials")
        self.bucket = settings.guard_audit_archive_bucket
        self.max_bytes = settings.guard_audit_archive_max_bytes + 1024
        if client is None:
            import boto3
            from botocore.config import Config
            credentials = {}
            for field, argument in (("access_key_id", "aws_access_key_id"),
                                    ("secret_access_key", "aws_secret_access_key"),
                                    ("session_token", "aws_session_token")):
                value = _secret(getattr(settings, "guard_audit_archive_" + field))
                if value:
                    credentials[argument] = value
            client = boto3.client(
                "s3", endpoint_url=settings.guard_audit_archive_endpoint or None,
                region_name=settings.guard_audit_archive_region,
                verify=settings.guard_audit_archive_ca_bundle or True,
                config=Config(signature_version="s3v4", connect_timeout=settings.guard_audit_archive_timeout_seconds,
                              read_timeout=settings.guard_audit_archive_timeout_seconds,
                              retries={"total_max_attempts": 2, "mode": "standard"},
                              s3={"addressing_style": "path" if settings.guard_audit_archive_path_style else "auto"}),
                **credentials,
            )
        self.client = client

    def read(self, key: str) -> bytes:
        response = self.client.get_object(Bucket=self.bucket, Key=key)
        body = response["Body"]
        try:
            value = body.read(self.max_bytes + 1)
            if len(value) > self.max_bytes:
                raise ArchiveIntegrityError("Stored archive exceeds configured size limit")
            return value
        finally:
            body.close()

    def put_once(self, key: str, body: bytes) -> bytes:
        """Never overwrite an object; always read back what storage persisted."""
        if len(body) > self.max_bytes:
            raise ArchiveIntegrityError("Archive exceeds configured size limit")
        try:
            self.client.put_object(Bucket=self.bucket, Key=key, Body=body,
                                   ContentType="application/octet-stream", IfNoneMatch="*")
        except Exception as exc:
            response = getattr(exc, "response", {})
            if response.get("Error", {}).get("Code") not in ("PreconditionFailed", "412"):
                raise
        return self.read(key)


def persist_archive(rows: list[dict], previous_manifest_hash: str, ordinal: int,
                    settings, store) -> tuple[dict, str]:
    signing, encryption = archive_keys(settings)
    workspace_id = rows[0]["workspace_id"]
    plain = canonical({"version": 1, "workspace_id": workspace_id, "events": rows})
    if len(plain) > settings.guard_audit_archive_max_bytes:
        raise ArchiveIntegrityError("Archive batch exceeds configured size limit")
    prefix = settings.guard_audit_archive_prefix.strip("/")
    if not prefix or ".." in prefix.split("/"):
        raise ValueError("Invalid archive prefix")
    object_key = f"{prefix}/{workspace_id}/{digest(plain)}.aesgcm"
    stored = store.put_once(object_key, encrypt_payload(plain, encryption, workspace_id=workspace_id))
    recovered = decrypt_payload(stored, encryption, workspace_id=workspace_id,
                                max_bytes=settings.guard_audit_archive_max_bytes)
    if not hmac.compare_digest(digest(recovered), digest(plain)):
        raise ArchiveIntegrityError("Archive read-back differs from source snapshot")
    chained = [row for row in rows if row["entry_hash"]]
    manifest = {
        "version": 1, "workspace_id": workspace_id, "ordinal": ordinal,
        "previous_manifest_hash": previous_manifest_hash,
        "object_key": object_key, "plaintext_sha256": digest(plain), "ciphertext_sha256": digest(stored),
        "event_count": len(rows), "event_ids": [row["id"] for row in rows],
        "first_ts": rows[0]["ts"], "last_ts": rows[-1]["ts"],
        "first_previous_hash": chained[0]["previous_hash"] or "" if chained else None,
        "last_entry_hash": chained[-1]["entry_hash"] if chained else None,
    }
    signature = sign_manifest(manifest, signing)
    envelope = {"manifest": manifest, "signature": signature}
    manifest_key = manifest_object_key(manifest)
    if store.put_once(manifest_key, canonical(envelope)) != canonical(envelope):
        raise ArchiveIntegrityError("Archive manifest read-back failed")
    return manifest, signature


def read_verified_archive(manifest: dict, signature: str, settings, store, *, workspace_id: str) -> list[dict]:
    signing, encryption = archive_keys(settings)
    verify_manifest(manifest, signature, signing, workspace_id=workspace_id)
    if store.read(manifest_object_key(manifest)) != canonical({"manifest": manifest, "signature": signature}):
        raise ArchiveIntegrityError("Stored archive checkpoint differs from authenticated metadata")
    stored = store.read(manifest["object_key"])
    if not hmac.compare_digest(digest(stored), manifest["ciphertext_sha256"]):
        raise ArchiveIntegrityError("Archive object digest mismatch")
    plain = decrypt_payload(stored, encryption, workspace_id=workspace_id,
                            max_bytes=settings.guard_audit_archive_max_bytes)
    if not hmac.compare_digest(digest(plain), manifest["plaintext_sha256"]):
        raise ArchiveIntegrityError("Archive source digest mismatch")
    envelope = json.loads(plain)
    rows = envelope["events"]
    if envelope["workspace_id"] != str(workspace_id) or len(rows) != manifest["event_count"]:
        raise ArchiveIntegrityError("Archive source scope/count mismatch")
    if [row["id"] for row in rows] != manifest["event_ids"]:
        raise ArchiveIntegrityError("Archive event IDs mismatch")
    return rows
