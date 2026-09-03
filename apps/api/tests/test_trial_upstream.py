"""Trial upstream resolver self-check (epic #1567 PR 2)."""
from __future__ import annotations

import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

HERE = Path(__file__).resolve()
APPS_API = HERE.parent.parent
if str(APPS_API) not in sys.path:
    sys.path.insert(0, str(APPS_API))


def _db_is_reachable() -> bool:
    try:
        import sqlalchemy
        from app.core.config import settings
        engine = sqlalchemy.create_engine(
            settings.sqlalchemy_database_url,
            connect_args={"connect_timeout": 3},
        )
        with engine.connect():
            pass
        return True
    except Exception:
        return False


if not _db_is_reachable():
    pytest.skip("Postgres unreachable", allow_module_level=True)


from sqlalchemy import text  # noqa: E402
from app.core.database import SessionLocal  # noqa: E402
from app.modules.guard.trial_seed import (  # noqa: E402
    TRIAL_IDENTITY_NAME,
    seed_trial,
)
from app.modules.guard.trial_upstream import (  # noqa: E402
    GUARD_TRIAL_ANTHROPIC_KEY_ENV,
    TRIAL_DAILY_CAP,
    resolve_trial_key,
)

# Not a real Anthropic key format — kept generic so the credential-leak rule
# doesn't fire on this test file.
_KEY = "TRIAL-KEY-PLACEHOLDER-" + uuid.uuid4().hex


@pytest.fixture()
def seeded_ws(monkeypatch):
    """Fresh workspace + seeded trial identity. Yields (ws_id, trial_id, db)."""
    monkeypatch.setenv(GUARD_TRIAL_ANTHROPIC_KEY_ENV, _KEY)
    db = SessionLocal()
    ws_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    db.execute(
        text(
            "INSERT INTO workspaces (id, name, owner_id, plan, is_approved, created_at, updated_at) "
            "VALUES (:id, :name, :owner, 'free', true, :now, :now)"
        ),
        {"id": ws_id, "name": f"trial-up-{ws_id[:8]}", "owner": f"test-{ws_id[:8]}", "now": now},
    )
    db.commit()
    seed_trial(db, ws_id)
    db.commit()
    trial_id = db.execute(
        text("SELECT id FROM agent_identities WHERE workspace_id = :ws AND name = :name"),
        {"ws": ws_id, "name": TRIAL_IDENTITY_NAME},
    ).scalar()
    try:
        yield ws_id, str(trial_id), db
    finally:
        db.rollback()
        db.execute(text("DELETE FROM workspaces WHERE id = :id"), {"id": ws_id})
        db.commit()
        db.close()


def test_returns_key_when_all_gates_pass(seeded_ws):
    ws_id, trial_id, db = seeded_ws
    key, status = resolve_trial_key(db, ws_id, "anthropic", trial_id)
    assert status == "active"
    assert key == _KEY


def test_wrong_provider_is_ineligible(seeded_ws):
    ws_id, trial_id, db = seeded_ws
    key, status = resolve_trial_key(db, ws_id, "openai", trial_id)
    assert status == "ineligible"
    assert key is None


def test_missing_env_var_is_ineligible(seeded_ws, monkeypatch):
    ws_id, trial_id, db = seeded_ws
    monkeypatch.delenv(GUARD_TRIAL_ANTHROPIC_KEY_ENV, raising=False)
    key, status = resolve_trial_key(db, ws_id, "anthropic", trial_id)
    assert status == "ineligible"
    assert key is None


def test_non_trial_plan_is_ineligible(seeded_ws):
    ws_id, trial_id, db = seeded_ws
    db.execute(text("UPDATE workspaces SET plan = 'free' WHERE id = :ws"), {"ws": ws_id})
    db.commit()
    key, status = resolve_trial_key(db, ws_id, "anthropic", trial_id)
    assert status == "ineligible"
    assert key is None


def test_expired_identity_returns_expired(seeded_ws):
    ws_id, trial_id, db = seeded_ws
    past = datetime.now(timezone.utc) - timedelta(days=1)
    db.execute(
        text("UPDATE agent_identities SET expires_at = :past WHERE id = :aid"),
        {"past": past, "aid": trial_id},
    )
    db.commit()
    key, status = resolve_trial_key(db, ws_id, "anthropic", trial_id)
    assert status == "expired"
    assert key is None


def test_daily_cap_returns_exceeded(seeded_ws):
    ws_id, trial_id, db = seeded_ws
    now = datetime.now(timezone.utc)
    for _ in range(TRIAL_DAILY_CAP):
        db.execute(
            text(
                "INSERT INTO guard_audit_events (id, workspace_id, agent_identity_id, ts, source, provider, decision, ai_tool) "
                "VALUES (gen_random_uuid(), :ws, :aid, :ts, 'proxy', 'anthropic', 'allowed', 'cli')"
            ),
            {"ws": ws_id, "aid": trial_id, "ts": now},
        )
    db.commit()
    key, status = resolve_trial_key(db, ws_id, "anthropic", trial_id)
    assert status == "exceeded"
    assert key is None


def test_no_agent_identity_is_ineligible(seeded_ws):
    ws_id, _trial_id, db = seeded_ws
    key, status = resolve_trial_key(db, ws_id, "anthropic", None)
    assert status == "ineligible"
    assert key is None
