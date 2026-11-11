"""Signed audit chain-head checkpoints (#2524 item 2). PostgreSQL, isolated schema."""
from __future__ import annotations

import base64
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.schema import CreateSchema, DropSchema

from app.core.config import settings
from app.modules.guard import audit_export as ax
from app.modules.guard import audit_signing as sg
from app.modules.guard.audit_retention import verify_audit_history
from app.modules.guard.models import (
    GuardAuditCheckpoint, GuardAuditEvent, GuardAuditSigningKey, chain_begin, chain_seal,
)


@pytest.fixture
def chain_db():
    url = settings.sqlalchemy_database_url
    if not url.startswith("postgresql"):
        pytest.skip("needs PostgreSQL")
    import app.main  # noqa: F401 — register ORM relationships
    schema = "ckpt_" + uuid4().hex[:12]
    admin = create_engine(url)
    try:
        with admin.begin() as conn:
            conn.execute(CreateSchema(schema))
            conn.execute(text(f'CREATE TABLE "{schema}".workspaces (id uuid PRIMARY KEY)'))
            conn.execute(text(f'CREATE TABLE "{schema}".guard_audit_events '
                              "(LIKE public.guard_audit_events INCLUDING DEFAULTS)"))
    except Exception as exc:  # noqa: BLE001
        admin.dispose()
        pytest.skip(f"PostgreSQL unavailable: {exc}")
    engine = create_engine(url, pool_size=4, connect_args={"options": f"-csearch_path={schema},public"})
    with engine.begin() as conn:
        GuardAuditCheckpoint.__table__.create(conn)
        GuardAuditSigningKey.__table__.create(conn)
    factory = sessionmaker(bind=engine)
    ws = uuid4()
    with factory() as db:
        db.execute(text("INSERT INTO workspaces VALUES (:w)"), {"w": ws})
        db.commit()
    try:
        yield factory, ws
    finally:
        engine.dispose()
        with admin.begin() as conn:
            conn.execute(DropSchema(schema, cascade=True))
        admin.dispose()


def _append(factory, ws, n=1):
    for _ in range(n):
        with factory() as db:
            ts, prev = chain_begin(db, ws)
            db.add(chain_seal(GuardAuditEvent(id=uuid4(), workspace_id=ws, ai_tool="claude_code",
                                              source="hook", tool_call="bash", decision="allowed",
                                              ts=ts, previous_hash=prev)))
            db.commit()


def _signer():
    return sg.LocalEd25519Signer(ed25519.Ed25519PrivateKey.generate())


class FakeKms:
    """Stand-in for boto3's KMS client. Never touches AWS."""

    def __init__(self, spec="ECC_NIST_EDWARDS25519"):
        self.spec = spec
        self.calls = []
        if spec == "ECC_NIST_EDWARDS25519":
            self._key = ed25519.Ed25519PrivateKey.generate()
            pub = self._key.public_key()
        else:
            self._key = ec.generate_private_key(ec.SECP256R1())
            pub = self._key.public_key()
        self._der = pub.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)

    def get_public_key(self, KeyId):
        return {"PublicKey": self._der, "KeySpec": self.spec, "KeyUsage": "SIGN_VERIFY"}

    def sign(self, KeyId, Message, MessageType, SigningAlgorithm):
        self.calls.append((KeyId, MessageType, SigningAlgorithm))
        assert MessageType == "RAW"
        if self.spec == "ECC_NIST_EDWARDS25519":
            assert SigningAlgorithm == "ED25519_SHA_512"
            return {"Signature": self._key.sign(Message)}
        assert SigningAlgorithm == "ECDSA_SHA_256"
        return {"Signature": self._key.sign(Message, ec.ECDSA(hashes.SHA256()))}


def _keys(factory):
    with factory() as db:
        return sg.published_keys(db)


def test_no_rows_no_checkpoint(chain_db):
    factory, ws = chain_db
    assert sg.take_checkpoint(ws, _signer(), session_factory=factory) is None


def test_checkpoint_created_verifies_and_skips_without_new_rows(chain_db):
    factory, ws = chain_db
    signer = _signer()
    _append(factory, ws, 3)
    cp = sg.take_checkpoint(ws, signer, session_factory=factory)
    assert cp and cp["row_count"] == 3 and cp["alg"] == "Ed25519" and cp["hash_version"] == 2
    sg.verify_checkpoint(cp, _keys(factory))
    assert sg.take_checkpoint(ws, signer, session_factory=factory) is None  # no new rows
    _append(factory, ws, 1)
    cp2 = sg.take_checkpoint(ws, signer, session_factory=factory)
    assert cp2["row_count"] == 4 and cp2["head_entry_hash"] != cp["head_entry_hash"]
    with factory() as db:
        assert db.query(GuardAuditCheckpoint).count() == 2
        assert sg.latest_checkpoint(db, ws)["row_count"] == 4


@pytest.mark.parametrize("field,value", [("row_count", 99), ("head_entry_hash", "0" * 64),
                                         ("ts", "2020-01-01T00:00:00.000000Z"), ("alg", "ECDSA-P256-SHA256")])
def test_tampered_checkpoint_fails(chain_db, field, value):
    factory, ws = chain_db
    _append(factory, ws, 2)
    cp = sg.take_checkpoint(ws, _signer(), session_factory=factory)
    with pytest.raises(sg.CheckpointError):
        sg.verify_checkpoint({**cp, field: value}, _keys(factory))


def test_unknown_key_and_swapped_public_key_fail(chain_db):
    factory, ws = chain_db
    _append(factory, ws, 1)
    cp = sg.take_checkpoint(ws, _signer(), session_factory=factory)
    with pytest.raises(sg.CheckpointError) as exc:
        sg.verify_checkpoint(cp, {})
    assert exc.value.status == "unknown_key"
    other = _signer()
    forged = {cp["key_id"]: {"alg": "Ed25519", "public_key": other.public_key_b64}}
    with pytest.raises(sg.CheckpointError):
        sg.verify_checkpoint(cp, forged)


def test_tail_truncation_detected_server_side(chain_db):
    factory, ws = chain_db
    _append(factory, ws, 5)
    sg.take_checkpoint(ws, _signer(), session_factory=factory)
    with factory() as db:
        ok = verify_audit_history(db, ws)
        assert ok["valid"] and ok["checkpoint"]["status"] == "valid"
        # Delete the newest two rows: every remaining hash is still valid.
        rows = (db.query(GuardAuditEvent).filter(GuardAuditEvent.workspace_id == ws)
                .order_by(GuardAuditEvent.ts.desc(), GuardAuditEvent.id.desc()).limit(2).all())
        for row in rows:
            db.delete(row)
        db.commit()
        res = verify_audit_history(db, ws)
    assert res["valid"] is False and res["broken_at"] == "checkpoint_truncated"
    assert res["checkpoint"]["status"] == "truncated" and res["checkpoint"]["current_row_count"] == 3


def test_key_rotation_old_checkpoint_still_verifies(chain_db):
    factory, ws = chain_db
    old, new = _signer(), _signer()
    _append(factory, ws, 2)
    cp_old = sg.take_checkpoint(ws, old, session_factory=factory)
    _append(factory, ws, 1)
    cp_new = sg.take_checkpoint(ws, new, session_factory=factory)
    keys = _keys(factory)
    assert set(keys) == {old.key_id, new.key_id} and old.key_id != new.key_id
    sg.verify_checkpoint(cp_old, keys)
    sg.verify_checkpoint(cp_new, keys)
    with factory() as db:
        assert verify_audit_history(db, ws)["checkpoint"]["key_id"] == new.key_id
    # Public material only.
    assert all(set(v) == {"alg", "public_key", "created_at"} for v in keys.values())


@pytest.mark.parametrize("spec,alg", [("ECC_NIST_EDWARDS25519", "Ed25519"), ("ECC_NIST_P256", "ECDSA-P256-SHA256")])
def test_kms_backend_mocked(chain_db, spec, alg):
    factory, ws = chain_db
    kms = FakeKms(spec)
    cfg = SimpleNamespace(guard_audit_checkpoint_backend="kms",
                          guard_audit_checkpoint_kms_key_id="arn:aws:kms:us-east-1:1:key/secret-arn",
                          guard_audit_checkpoint_kms_region="us-east-1",
                          guard_audit_checkpoint_ed25519_private_key=None)
    signer = sg.get_signer(cfg, kms_client=kms)
    assert signer.alg == alg and "secret-arn" not in signer.key_id
    _append(factory, ws, 2)
    cp = sg.take_checkpoint(ws, signer, session_factory=factory)
    assert cp["alg"] == alg and kms.calls
    sg.verify_checkpoint(cp, _keys(factory))
    with pytest.raises(sg.CheckpointError):
        sg.verify_checkpoint({**cp, "row_count": 3}, _keys(factory))


def test_kms_unsupported_key_spec_rejected():
    class Rsa(FakeKms):
        def get_public_key(self, KeyId):
            return {"PublicKey": b"x", "KeySpec": "RSA_2048", "KeyUsage": "SIGN_VERIFY"}
    with pytest.raises(sg.CheckpointError):
        sg.KmsSigner("k", Rsa())


def test_local_backend_config_and_no_key_echo():
    seed = base64.b64encode(ed25519.Ed25519PrivateKey.generate().private_bytes(
        serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())).decode()
    from pydantic import SecretStr
    cfg = SimpleNamespace(guard_audit_checkpoint_backend="local",
                          guard_audit_checkpoint_ed25519_private_key=SecretStr(seed))
    signer = sg.get_signer(cfg)
    assert signer.alg == "Ed25519" and seed not in repr(vars(signer)) and seed not in signer.public_key_b64
    bad = SimpleNamespace(guard_audit_checkpoint_backend="local",
                          guard_audit_checkpoint_ed25519_private_key=SecretStr("not-a-key-SECRETVALUE"))
    with pytest.raises(sg.CheckpointError) as exc:
        sg.get_signer(bad)
    assert "SECRETVALUE" not in str(exc.value)
    assert sg.get_signer(SimpleNamespace(guard_audit_checkpoint_backend="off")) is None


def test_cleanup_keeps_newest_per_workspace(chain_db):
    factory, ws = chain_db
    signer = _signer()
    now = datetime.now(timezone.utc)
    _append(factory, ws, 1)
    sg.take_checkpoint(ws, signer, session_factory=factory, now=now - timedelta(days=500))
    _append(factory, ws, 1)
    sg.take_checkpoint(ws, signer, session_factory=factory, now=now - timedelta(days=400))
    assert sg.cleanup_expired(session_factory=factory, retention_days=365, now=now) == 1
    with factory() as db:
        assert [c.row_count for c in db.query(GuardAuditCheckpoint).all()] == [2]
    # The newest is kept even when older than the window.
    assert sg.cleanup_expired(session_factory=factory, retention_days=30, now=now) == 0


def test_feed_page_and_export_trailer_carry_checkpoint(chain_db, monkeypatch):
    factory, ws = chain_db
    signer = _signer()
    _append(factory, ws, 3)
    cp = sg.take_checkpoint(ws, signer, session_factory=factory)
    now = datetime.now(timezone.utc) + timedelta(minutes=5)
    with factory() as db:
        page = ax.feed_page(db, ws, since=now - timedelta(days=1), now=now)
    assert page["checkpoint"] == cp and signer.key_id in page["audit_keys"]
    sg.verify_checkpoint(page["checkpoint"], page["audit_keys"])

    monkeypatch.setattr(ax, "SessionLocal", factory)
    since, until = now - timedelta(days=1), now
    lines = "".join(ax.stream_export(ws, since, until, [], None, "ndjson")).splitlines()
    trailer = json.loads(lines[-1])
    assert trailer["kind"] == "audit_checkpoint" and trailer["checkpoint"] == cp and len(lines) == 4
    assert "audit_checkpoint" not in "".join(ax.stream_export(ws, since, until, ["block"], None, "ndjson"))
    assert "audit_checkpoint" not in "".join(ax.stream_export(ws, since, until, [], None, "ndjson", cap=3))


def test_run_checkpoints_once(chain_db):
    factory, ws = chain_db
    _append(factory, ws, 1)
    cfg = SimpleNamespace(guard_audit_checkpoint_retention_days=365)
    res = sg.run_checkpoints_once(session_factory=factory, settings_obj=cfg, signer=_signer())
    assert res["created"] == 1 and res["errors"] == 0
    res = sg.run_checkpoints_once(session_factory=factory, settings_obj=cfg, signer=_signer())
    assert res["errors"] == 0  # second run with a different signer still has no new rows
    assert res["created"] == 0


def test_cli_fixture_checkpoint_verifies_with_api():
    """The CLI fixtures were signed by this module; the API verifier must accept them."""
    from pathlib import Path
    fix = Path(__file__).resolve().parents[4] / "packages/conduct-cli/tests/fixtures"
    for name in ("audit_checkpoint_bundle.json", "audit_checkpoint_bundle_row3.json"):
        bundle = json.loads((fix / name).read_text())
        sg.verify_checkpoint(bundle["checkpoint"], bundle["keys"])
