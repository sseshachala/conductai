"""Signed audit chain-head checkpoint verification for `conduct audit verify` (#2524 item 2).

Re-implements ``apps/api/app/modules/guard/audit_signing.py`` (payload and signature
check); ``apps/api/tests/guard/test_audit_checkpoints.py`` and
``tests/test_audit_checkpoint.py`` pin both to the same fixture.

A checkpoint is a signature over canonical JSON (sorted keys, no whitespace, UTF-8)::

    {workspace_id, ts, head_entry_hash, row_count, hash_version, key_id, alg}

``alg`` is ``Ed25519`` or ``ECDSA-P256-SHA256`` (AWS KMS P-256 fallback, DER signature).
Public keys are base64 SubjectPublicKeyInfo DER. Verification needs the
``cryptography`` package, imported lazily so the hook path does not pay for it.
"""
from __future__ import annotations

import base64
import json
import urllib.request
from datetime import datetime, timezone
from uuid import UUID

ALG_ED25519 = "Ed25519"
ALG_ECDSA_P256 = "ECDSA-P256-SHA256"
TRAILER_KIND = "audit_checkpoint"
_FETCH_TIMEOUT = 15
_FETCH_MAX_BYTES = 1_048_576


class CheckpointError(Exception):
    def __init__(self, reason: str, status: str = "invalid"):
        super().__init__(reason)
        self.reason = reason
        self.status = status


def _format_ts(value) -> str:
    dt = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    dt = dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def payload_bytes(cp: dict) -> bytes:
    try:
        body = {
            "workspace_id": str(UUID(str(cp["workspace_id"]))),
            "ts": _format_ts(cp["ts"]),
            "head_entry_hash": str(cp["head_entry_hash"]),
            "row_count": int(cp["row_count"]),
            "hash_version": int(cp["hash_version"]),
            "key_id": str(cp["key_id"]),
            "alg": str(cp["alg"]),
        }
    except (KeyError, ValueError, TypeError) as exc:
        raise CheckpointError("malformed checkpoint: %s" % exc)
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def verify_signature(cp: dict, public_key_b64: str) -> None:
    """Raise CheckpointError unless the signature is valid for the checkpoint contents."""
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec, ed25519
    except ImportError:
        raise CheckpointError("the 'cryptography' package is required to verify checkpoints "
                              "(pip install cryptography)", status="unavailable")
    message = payload_bytes(cp)
    try:
        key = serialization.load_der_public_key(base64.b64decode(public_key_b64))
        signature = base64.b64decode(cp["signature"])
        alg = cp.get("alg")
        if alg == ALG_ED25519 and isinstance(key, ed25519.Ed25519PublicKey):
            key.verify(signature, message)
        elif (alg == ALG_ECDSA_P256 and isinstance(key, ec.EllipticCurvePublicKey)
              and isinstance(key.curve, ec.SECP256R1)):
            key.verify(signature, message, ec.ECDSA(hashes.SHA256()))
        else:
            raise CheckpointError("algorithm %r does not match the key type" % (alg,))
    except CheckpointError:
        raise
    except InvalidSignature:
        raise CheckpointError("signature does not match the checkpoint contents")
    except (ValueError, TypeError, KeyError) as exc:
        raise CheckpointError("unverifiable checkpoint: %s" % exc)


def load_keys(source: str) -> dict:
    """Load ``key_id -> {alg, public_key}`` from a file path or an https URL
    (the well-known endpoint). Accepts ``{"keys": {...}}`` or a bare mapping."""
    if source.startswith(("http://", "https://")):
        if source.startswith("http://") and not source.startswith(("http://localhost", "http://127.0.0.1")):
            raise CheckpointError("refusing to fetch signing keys over plain http")
        with urllib.request.urlopen(source, timeout=_FETCH_TIMEOUT) as resp:  # noqa: S310 (scheme checked)
            raw = resp.read(_FETCH_MAX_BYTES + 1)
        if len(raw) > _FETCH_MAX_BYTES:
            raise CheckpointError("signing key response too large")
        data = json.loads(raw)
    else:
        with open(source, encoding="utf-8") as fh:
            data = json.load(fh)
    keys = data.get("keys", data) if isinstance(data, dict) else None
    if not isinstance(keys, dict):
        raise CheckpointError("unrecognised key document")
    return keys


def load_bundle(path: str) -> tuple:
    """``(checkpoint, keys)`` from a JSON file: an export trailer, a feed page
    (``checkpoint`` + ``audit_keys``) or ``{checkpoint, keys}``."""
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict) or not isinstance(data.get("checkpoint"), dict):
        raise CheckpointError("no checkpoint in %s" % path)
    return data["checkpoint"], data.get("keys") or data.get("audit_keys") or {}


def check(cp: dict, keys: dict, *, by_hash: dict, first_pos, last_pos) -> dict:
    """Verify the signature, then that the export reaches the checkpoint head.

    ``by_hash``: entry_hash -> chain position (or None when unknown) for every chained
    row in the export; ``first_pos``/``last_pos``: positions of its first/last
    chained row (None when unknown). Returns ``{status, reason}``; status is
    ``valid`` or ``not_covered`` (checkpoint predates the export) on success.
    """
    entry = keys.get(cp.get("key_id"))
    if not isinstance(entry, dict):
        raise CheckpointError("checkpoint signed by unknown key %r" % (cp.get("key_id"),), status="unknown_key")
    if entry.get("alg") != cp.get("alg"):
        raise CheckpointError("checkpoint algorithm differs from the published key's algorithm")
    verify_signature(cp, entry.get("public_key", ""))
    count = int(cp["row_count"])
    head = cp["head_entry_hash"]
    if head in by_hash:
        pos = by_hash[head]
        if pos is not None and pos != count:
            raise CheckpointError("checkpoint pins row_count %d but its head sits at chain position %d" % (count, pos),
                                  status="mismatch")
        return {"status": "valid", "reason": None}
    if last_pos is not None and count > last_pos:
        raise CheckpointError(
            "export ends before the checkpoint head: it reaches chain position %d, the signed "
            "checkpoint pins %d rows (tail of the chain truncated)" % (last_pos, count), status="truncated")
    if first_pos is not None and count < first_pos:
        return {"status": "not_covered",
                "reason": "checkpoint (row %d) predates this export, which starts at position %d" % (count, first_pos)}
    if last_pos is None:
        raise CheckpointError("export has no chain positions, so it cannot be compared with the checkpoint; "
                              "re-export without filters from the start of the chain", status="unverifiable")
    raise CheckpointError("checkpoint head hash is not in the export (row removed or replaced)", status="truncated")
