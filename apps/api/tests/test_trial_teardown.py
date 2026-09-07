"""Trial teardown self-check (epic #1587 Round C).

Mirrors the fixture pattern in test_trial_seed.py — skip module when
Postgres is unreachable, workspace cascade-deletes seeded rows on teardown.
"""
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
from app.modules.guard.trial_seed import TRIAL_IDENTITY_NAME, seed_trial  # noqa: E402
from app.modules.guard.trial_teardown import teardown_trial  # noqa: E402


@pytest.fixture()
def ws():
    db = SessionLocal()
    ws_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    db.execute(
        text(
            "INSERT INTO workspaces (id, name, owner_id, plan, is_approved, created_at, updated_at) "
            "VALUES (:id, :name, :owner, 'free', true, :now, :now)"
        ),
        {"id": ws_id, "name": f"trial-tear-{ws_id[:8]}", "owner": f"test-{ws_id[:8]}", "now": now},
    )
    db.commit()
    try:
        yield ws_id, db
    finally:
        db.execute(text("DELETE FROM workspaces WHERE id = :id"), {"id": ws_id})
        db.commit()
        db.close()


def _count(db, sql: str, params: dict) -> int:
    return db.execute(text(sql), params).scalar() or 0


def test_teardown_removes_all_trial_artifacts(ws):
    ws_id, db = ws
    seed_trial(db, ws_id)
    db.commit()

    changed = teardown_trial(db, ws_id)
    db.commit()
    assert changed is True

    plan = db.execute(text("SELECT plan FROM workspaces WHERE id = :ws"), {"ws": ws_id}).scalar()
    assert plan == "free"

    lifecycle = db.execute(
        text("SELECT lifecycle_state FROM agent_identities WHERE workspace_id = :ws AND name = :name"),
        {"ws": ws_id, "name": TRIAL_IDENTITY_NAME},
    ).scalar()
    assert lifecycle == "expired"

    assert _count(db, "SELECT COUNT(*) FROM guard_rate_limits WHERE workspace_id = :ws AND agent_identity_id IS NULL", {"ws": ws_id}) == 0
    assert _count(db, "SELECT COUNT(*) FROM guard_spend_budgets WHERE workspace_id = :ws AND clerk_user_id IS NULL", {"ws": ws_id}) == 0


def test_teardown_is_idempotent(ws):
    ws_id, db = ws
    seed_trial(db, ws_id)
    db.commit()

    assert teardown_trial(db, ws_id) is True
    db.commit()
    assert teardown_trial(db, ws_id) is False
    db.commit()


def test_teardown_noop_when_no_trial(ws):
    """Workspace never had a trial — teardown returns False, nothing changes."""
    ws_id, db = ws
    plan_before = db.execute(text("SELECT plan FROM workspaces WHERE id = :ws"), {"ws": ws_id}).scalar()
    assert teardown_trial(db, ws_id) is False
    db.commit()
    plan_after = db.execute(text("SELECT plan FROM workspaces WHERE id = :ws"), {"ws": ws_id}).scalar()
    assert plan_before == plan_after == "free"


from app.modules.guard.trial_teardown import sweep_expired_trials  # noqa: E402


def test_sweep_tears_down_only_expired_trials(ws):
    """Workspace-scoped assertions — the sweeper is global, but other tests may
    have left unrelated trial rows in this shared test DB, so we can't assert
    the sweep count. What matters: this workspace's fresh trial is untouched
    before its expires_at, and torn down after."""
    ws_id, db = ws
    seed_trial(db, ws_id)
    db.commit()

    # Fresh trial has expires_at 7d out — this workspace should survive a sweep.
    sweep_expired_trials(db)
    plan = db.execute(text("SELECT plan FROM workspaces WHERE id = :ws"), {"ws": ws_id}).scalar()
    assert plan == "free_trial"
    lifecycle = db.execute(
        text("SELECT lifecycle_state FROM agent_identities WHERE workspace_id = :ws AND name = :name"),
        {"ws": ws_id, "name": TRIAL_IDENTITY_NAME},
    ).scalar()
    assert lifecycle == "active"

    # Force this trial's identity into the past.
    db.execute(
        text(
            "UPDATE agent_identities SET expires_at = :past "
            "WHERE workspace_id = :ws AND name = :name"
        ),
        {
            "past": datetime.now(timezone.utc) - timedelta(minutes=1),
            "ws": ws_id,
            "name": TRIAL_IDENTITY_NAME,
        },
    )
    db.commit()

    # Now sweep — this workspace should be torn down.
    sweep_expired_trials(db)
    plan = db.execute(text("SELECT plan FROM workspaces WHERE id = :ws"), {"ws": ws_id}).scalar()
    assert plan == "free"
    lifecycle = db.execute(
        text("SELECT lifecycle_state FROM agent_identities WHERE workspace_id = :ws AND name = :name"),
        {"ws": ws_id, "name": TRIAL_IDENTITY_NAME},
    ).scalar()
    assert lifecycle == "expired"
