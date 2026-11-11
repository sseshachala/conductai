"""Signed audit chain-head checkpoints (#2524 item 2).

A checkpoint pins ``(head_entry_hash, row_count)`` of one workspace's audit
chain at a point in time with an asymmetric signature, so deleting the tail of
the chain (which leaves every remaining hash valid) is detectable: the verifier
sees a signed head that is no longer reachable.

Signed payload, canonical JSON (sorted keys, no whitespace, UTF-8)::

    {workspace_id, ts, head_entry_hash, row_count, hash_version, key_id, alg}

``ts`` is ``YYYY-MM-DDTHH:MM:SS.ffffffZ`` (UTC). ``row_count`` counts rows with
chain fields (``entry_hash IS NOT NULL``), so archival does not change it.
``alg`` is part of the payload so a verifier knows how to check the signature:

* ``Ed25519``            pure Ed25519 (settings key, or AWS KMS ECC_NIST_EDWARDS25519
                         with ED25519_SHA_512 in RAW mode, which is pure Ed25519)
* ``ECDSA-P256-SHA256``  AWS KMS ECC_NIST_P256 / ECDSA_SHA_256 (DER signature)

Signatures and public keys are standard base64 (signature bytes as produced by
the backend; public key as SubjectPublicKeyInfo DER). Private key material never
leaves its backend object and is never logged or returned.

``conduct audit verify`` (packages/conduct-cli) re-implements ``payload_bytes``
and ``verify_signature``; tests pin both to the same vectors.
"""
from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Protocol
from uuid import UUID, uuid4

import structlog
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.workspace_context import set_workspace_rls
from app.modules.guard.audit_chain import format_ts

log = structlog.get_logger(__name__)

ALG_ED25519 = "Ed25519"
ALG_ECDSA_P256 = "ECDSA-P256-SHA256"
PAYLOAD_FIELDS = ("workspace_id", "ts", "head_entry_hash", "row_count", "hash_version", "key_id", "alg")
PUBLIC_FIELDS = PAYLOAD_FIELDS + ("signature",)


class CheckpointError(Exception):
    """A checkpoint cannot be created or does not verify."""

    def __init__(self, reason: str, status: str = "invalid_signature"):
        super().__init__(reason)
        self.reason = reason
        self.status = status


# ── Canonical payload + verification (pure) ─────────────────────────────────

def payload_bytes(cp: Mapping[str, Any]) -> bytes:
    body = {
        "workspace_id": str(UUID(str(cp["workspace_id"]))),
        "ts": format_ts(cp["ts"]),
        "head_entry_hash": str(cp["head_entry_hash"]),
        "row_count": int(cp["row_count"]),
        "hash_version": int(cp["hash_version"]),
        "key_id": str(cp["key_id"]),
        "alg": str(cp["alg"]),
    }
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def key_id_for(public_key_der: bytes) -> str:
    """Stable id derived from the public key: never reveals a KMS ARN."""
    return hashlib.sha256(public_key_der).hexdigest()[:32]


def verify_signature(cp: Mapping[str, Any], public_key_b64: str) -> None:
    """Raise CheckpointError unless ``cp['signature']`` is valid over its payload."""
    try:
        key = serialization.load_der_public_key(base64.b64decode(public_key_b64))
        signature = base64.b64decode(cp["signature"])
        message = payload_bytes(cp)
        alg = cp["alg"]
        if alg == ALG_ED25519 and isinstance(key, ed25519.Ed25519PublicKey):
            key.verify(signature, message)
        elif alg == ALG_ECDSA_P256 and isinstance(key, ec.EllipticCurvePublicKey) \
                and isinstance(key.curve, ec.SECP256R1):
            key.verify(signature, message, ec.ECDSA(hashes.SHA256()))
        else:
            raise CheckpointError(f"algorithm {alg!r} does not match the key type")
    except CheckpointError:
        raise
    except InvalidSignature as exc:
        raise CheckpointError("signature does not match the checkpoint contents") from exc
    except (ValueError, TypeError, KeyError) as exc:
        raise CheckpointError(f"unverifiable checkpoint: {exc}") from exc


def verify_checkpoint(cp: Mapping[str, Any], keys: Mapping[str, Mapping[str, Any]]) -> None:
    """Verify ``cp`` against ``keys`` (key_id -> {alg, public_key, ...})."""
    entry = keys.get(cp.get("key_id"))
    if entry is None:
        raise CheckpointError(f"unknown signing key {cp.get('key_id')!r}", status="unknown_key")
    if entry.get("alg") != cp.get("alg"):
        raise CheckpointError("checkpoint algorithm differs from the published key's algorithm")
    verify_signature(cp, entry["public_key"])


# ── Signing backends ────────────────────────────────────────────────────────

class Signer(Protocol):
    key_id: str
    alg: str
    backend: str
    public_key_b64: str

    def sign(self, message: bytes) -> bytes: ...


class LocalEd25519Signer:
    """Settings-held Ed25519 key (on-prem/dev). Offline-verifiable, not operator-proof."""
    backend = "local"
    alg = ALG_ED25519

    def __init__(self, private_key: ed25519.Ed25519PrivateKey):
        self._key = private_key
        der = private_key.public_key().public_bytes(
            serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
        self.public_key_b64 = base64.b64encode(der).decode()
        self.key_id = key_id_for(der)

    @classmethod
    def from_secret(cls, secret: str) -> "LocalEd25519Signer":
        """``secret`` is a PEM private key or base64 of the raw 32-byte seed."""
        text = secret.strip()
        try:
            if text.startswith("-----BEGIN"):
                key = serialization.load_pem_private_key(text.encode(), password=None)
            else:
                key = ed25519.Ed25519PrivateKey.from_private_bytes(base64.b64decode(text, validate=True))
        except Exception as exc:  # never echo the value
            raise CheckpointError("GUARD_AUDIT_CHECKPOINT_ED25519_PRIVATE_KEY is not a valid Ed25519 key",
                                  status="config") from exc
        if not isinstance(key, ed25519.Ed25519PrivateKey):
            raise CheckpointError("GUARD_AUDIT_CHECKPOINT_ED25519_PRIVATE_KEY must be an Ed25519 key",
                                  status="config")
        return cls(key)

    def sign(self, message: bytes) -> bytes:
        return self._key.sign(message)


# KMS key spec -> (checkpoint alg, KMS SigningAlgorithm)
_KMS_SPECS = {
    "ECC_NIST_EDWARDS25519": (ALG_ED25519, "ED25519_SHA_512"),
    "ECC_NIST_P256": (ALG_ECDSA_P256, "ECDSA_SHA_256"),
}


class KmsSigner:
    """AWS KMS asymmetric sign-only key. The key policy needs kms:Sign and
    kms:GetPublicKey only; the private key never leaves KMS."""
    backend = "kms"

    def __init__(self, key_id: str, client):
        self._kms_key = key_id
        self._client = client
        meta = client.get_public_key(KeyId=key_id)
        spec = meta.get("KeySpec")
        if spec not in _KMS_SPECS:
            raise CheckpointError(
                f"KMS key spec {spec!r} is not supported; use ECC_NIST_EDWARDS25519 or ECC_NIST_P256",
                status="config")
        if meta.get("KeyUsage") not in (None, "SIGN_VERIFY"):
            raise CheckpointError("KMS key must have KeyUsage SIGN_VERIFY", status="config")
        self.alg, self._kms_alg = _KMS_SPECS[spec]
        der = bytes(meta["PublicKey"])
        self.public_key_b64 = base64.b64encode(der).decode()
        self.key_id = key_id_for(der)

    def sign(self, message: bytes) -> bytes:
        reply = self._client.sign(KeyId=self._kms_key, Message=message, MessageType="RAW",
                                  SigningAlgorithm=self._kms_alg)
        return bytes(reply["Signature"])


def get_signer(settings_obj=settings, *, kms_client=None) -> Signer | None:
    """Build the configured signer, or None when checkpoints are off."""
    backend = settings_obj.guard_audit_checkpoint_backend
    if backend == "off":
        return None
    if backend == "local":
        secret = settings_obj.guard_audit_checkpoint_ed25519_private_key
        if secret is None:
            raise CheckpointError("GUARD_AUDIT_CHECKPOINT_ED25519_PRIVATE_KEY is required for backend=local",
                                  status="config")
        return LocalEd25519Signer.from_secret(secret.get_secret_value())
    key_id = settings_obj.guard_audit_checkpoint_kms_key_id
    if not key_id:
        raise CheckpointError("GUARD_AUDIT_CHECKPOINT_KMS_KEY_ID is required for backend=kms", status="config")
    if kms_client is None:
        import boto3
        kms_client = boto3.client("kms", region_name=settings_obj.guard_audit_checkpoint_kms_region)
    return KmsSigner(key_id, kms_client)


# ── Key registry + checkpoint storage ───────────────────────────────────────

def register_key(db, signer: Signer) -> None:
    """Record the signer's public key (idempotent). Old keys are never removed."""
    from sqlalchemy.dialects.postgresql import insert

    from app.modules.guard.models import GuardAuditSigningKey

    db.execute(insert(GuardAuditSigningKey).values(
        key_id=signer.key_id, alg=signer.alg, public_key=signer.public_key_b64,
        backend=signer.backend, created_at=datetime.now(timezone.utc),
    ).on_conflict_do_nothing(index_elements=["key_id"]))


def published_keys(db) -> dict:
    """key_id -> {alg, public_key, created_at}: public material only."""
    from app.modules.guard.models import GuardAuditSigningKey

    rows = db.query(GuardAuditSigningKey).order_by(GuardAuditSigningKey.created_at).all()
    return {r.key_id: {"alg": r.alg, "public_key": r.public_key,
                       "created_at": format_ts(r.created_at)} for r in rows}


def checkpoint_dict(row) -> dict:
    return {
        "workspace_id": str(row.workspace_id), "ts": format_ts(row.ts),
        "head_entry_hash": row.head_entry_hash, "row_count": int(row.row_count),
        "hash_version": int(row.hash_version), "key_id": row.key_id, "alg": row.alg,
        "signature": row.signature,
    }


def latest_checkpoint(db, workspace_id, *, until: datetime | None = None) -> dict | None:
    """Newest checkpoint for the workspace (taken at or before ``until`` if given)."""
    from app.modules.guard.models import GuardAuditCheckpoint as C

    q = db.query(C).filter(C.workspace_id == UUID(str(workspace_id)))
    if until is not None:
        q = q.filter(C.ts <= until)
    row = q.order_by(C.ts.desc(), C.id.desc()).first()
    return checkpoint_dict(row) if row else None


def bundle_for(db, workspace_id, *, until: datetime | None = None) -> dict | None:
    """``{"checkpoint": ..., "keys": ...}`` as bundled on feed pages and exports."""
    cp = latest_checkpoint(db, workspace_id, until=until)
    if cp is None:
        return None
    return {"checkpoint": cp, "keys": published_keys(db)}


def _read_head(db, workspace_id: UUID):
    """(head_entry_hash, hash_version, row_count) of the chained rows, or None. Caller holds the chain lock."""
    from sqlalchemy import func

    from app.modules.guard.models import GuardAuditEvent as E

    head = (db.query(E.entry_hash, E.hash_version)
            .filter(E.workspace_id == workspace_id, E.entry_hash.isnot(None))
            .order_by(E.ts.desc(), E.id.desc()).first())
    if head is None:
        return None
    count = (db.query(func.count(E.id))
             .filter(E.workspace_id == workspace_id, E.entry_hash.isnot(None)).scalar() or 0)
    return head[0], int(head[1] or 1), int(count)


def take_checkpoint(workspace_id, signer: Signer, *, session_factory=SessionLocal,
                    now: datetime | None = None) -> dict | None:
    """Create and store a signed checkpoint, or return None when there are no new rows.

    Head and count are read under the per-workspace chain lock (the one appends
    take), so they describe one consistent chain state. The lock is released
    before signing so a slow KMS call never stalls audit writes; the unique
    constraint on (workspace_id, head_entry_hash, row_count) makes concurrent
    workers idempotent.
    """
    from app.modules.guard.models import GuardAuditCheckpoint as C, _chain_lock

    workspace_id = UUID(str(workspace_id))
    now = (now or datetime.now(timezone.utc))
    with session_factory() as db:
        set_workspace_rls(db, workspace_id)
        _chain_lock(db, workspace_id)
        state = _read_head(db, workspace_id)
        if state is None:
            return None
        head_hash, hash_version, count = state
        last = (db.query(C.head_entry_hash, C.row_count).filter(C.workspace_id == workspace_id)
                .order_by(C.ts.desc(), C.id.desc()).first())
        db.rollback()  # releases the chain lock
    if last is not None and last.head_entry_hash == head_hash and int(last.row_count) == count:
        return None
    cp = {"workspace_id": str(workspace_id), "ts": format_ts(now), "head_entry_hash": head_hash,
          "row_count": count, "hash_version": hash_version, "key_id": signer.key_id, "alg": signer.alg}
    cp["signature"] = base64.b64encode(signer.sign(payload_bytes(cp))).decode()
    with session_factory() as db:
        set_workspace_rls(db, workspace_id)
        register_key(db, signer)
        from sqlalchemy.dialects.postgresql import insert
        db.execute(insert(C).values(
            id=uuid4(), workspace_id=workspace_id, ts=now.astimezone(timezone.utc),
            head_entry_hash=head_hash, row_count=count, hash_version=hash_version, key_id=signer.key_id,
            alg=signer.alg, signature=cp["signature"],
        ).on_conflict_do_nothing(constraint="uq_guard_audit_checkpoints_head"))
        db.commit()
    return cp


def verify_latest_checkpoint(db, workspace_id) -> dict:
    """Server-side check of the newest checkpoint against the live chain.

    status: none | valid | invalid_signature | unknown_key | truncated
    """
    from sqlalchemy import func

    from app.modules.guard.models import GuardAuditEvent as E

    workspace_id = UUID(str(workspace_id))
    cp = latest_checkpoint(db, workspace_id)
    if cp is None:
        return {"status": "none"}
    info = {"ts": cp["ts"], "row_count": cp["row_count"], "key_id": cp["key_id"], "alg": cp["alg"]}
    try:
        verify_checkpoint(cp, published_keys(db))
    except CheckpointError as exc:
        return {**info, "status": exc.status, "reason": exc.reason}
    count = (db.query(func.count(E.id))
             .filter(E.workspace_id == workspace_id, E.entry_hash.isnot(None)).scalar() or 0)
    head_present = db.query(E.id).filter(E.workspace_id == workspace_id,
                                         E.entry_hash == cp["head_entry_hash"]).first() is not None
    if count < cp["row_count"] or not head_present:
        return {**info, "status": "truncated",
                "reason": "the signed chain head is missing or the chain has fewer rows than checkpointed",
                "current_row_count": int(count)}
    return {**info, "status": "valid"}


# ── Worker job ──────────────────────────────────────────────────────────────

def cleanup_expired(*, session_factory=SessionLocal, retention_days: int | None = None,
                    now: datetime | None = None) -> int:
    """Delete checkpoints older than the retention window, always keeping each
    workspace's newest one so an idle workspace stays truncation-checkable."""
    from sqlalchemy import func

    from app.modules.guard.models import GuardAuditCheckpoint as C

    days = retention_days if retention_days is not None else settings.guard_audit_checkpoint_retention_days
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=days)
    with session_factory() as db:
        # RLS: this maintenance job runs with the DB owner role, like the retention job.
        newest = (db.query(C.workspace_id.label("ws"), func.max(C.ts).label("mx"))
                  .group_by(C.workspace_id).subquery())
        keep = (db.query(C.id).join(newest, (C.workspace_id == newest.c.ws) & (C.ts == newest.c.mx))
                .scalar_subquery())
        deleted = (db.query(C).filter(C.ts < cutoff, ~C.id.in_(keep))
                   .delete(synchronize_session=False))
        db.commit()
    return int(deleted)


def run_checkpoints_once(*, session_factory=SessionLocal, settings_obj=settings, signer=None,
                         now: datetime | None = None) -> dict:
    from app.models.workspace import Workspace

    aggregate = {"workspaces": 0, "created": 0, "errors": 0, "deleted": 0}
    signer = signer or get_signer(settings_obj)
    if signer is None:
        return aggregate
    cursor = None
    while True:
        with session_factory() as db:
            query = db.query(Workspace.id).order_by(Workspace.id)
            if cursor:
                query = query.filter(Workspace.id > cursor)
            ids = [row.id for row in query.limit(100).all()]
        if not ids:
            break
        for workspace_id in ids:
            try:
                aggregate["workspaces"] += 1
                if take_checkpoint(workspace_id, signer, session_factory=session_factory, now=now):
                    aggregate["created"] += 1
            except Exception as exc:  # one workspace must not stop the pass; never log key/KMS detail
                aggregate["errors"] += 1
                log.error("guard.audit_checkpoint.failed", error_type=type(exc).__name__)
        cursor = ids[-1]
    try:
        aggregate["deleted"] = cleanup_expired(session_factory=session_factory,
                                               retention_days=settings_obj.guard_audit_checkpoint_retention_days,
                                               now=now)
    except Exception as exc:
        aggregate["errors"] += 1
        log.error("guard.audit_checkpoint.cleanup_failed", error_type=type(exc).__name__)
    log.info("guard.audit_checkpoint.completed", **aggregate)
    return aggregate


def audit_checkpoint_loop() -> None:
    """Hourly (configurable) worker thread. Exits quietly when backend=off."""
    import time

    if settings.guard_audit_checkpoint_backend == "off":
        return
    while True:
        try:
            run_checkpoints_once()
        except Exception as exc:  # misconfiguration: keep the worker alive, retry next cycle
            log.error("guard.audit_checkpoint.cycle_error", error_type=type(exc).__name__)
        time.sleep(settings.guard_audit_checkpoint_interval_seconds)
