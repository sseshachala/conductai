"""Trial seed self-check (epic #1567 PR 1).

conftest.py sets DATABASE_URL and ENCRYPTION_KEY defaults before this file
imports, so the test just skips the module if Postgres is unreachable.
"""
from __future__ import annotations

import sys
import uuid
from datetime import datetime, timezone
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
    TRIAL_HARD_USD,
    TRIAL_IDENTITY_NAME,
    TRIAL_MONTHLY_USD,
    TRIAL_PLAN,
    TRIAL_RPM,
    TRIAL_TPM,
    seed_trial,
)


@pytest.fixture()
def ws():
    """Create a bare workspace, yield (id, db), delete on teardown (cascade removes seeded rows)."""
    db = SessionLocal()
    ws_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    db.execute(
        text(
            "INSERT INTO workspaces (id, name, owner_id, plan, is_approved, created_at, updated_at) "
            "VALUES (:id, :name, :owner, 'free', true, :now, :now)"
        ),
        {"id": ws_id, "name": f"trial-seed-{ws_id[:8]}", "owner": f"test-{ws_id[:8]}", "now": now},
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


def test_seed_trial_inserts_expected_rows(ws):
    ws_id, db = ws

    plaintext = seed_trial(db, ws_id)
    db.commit()

    assert plaintext and plaintext.startswith("cond_agt_")

    plan = db.execute(
        text("SELECT plan FROM workspaces WHERE id = :ws"), {"ws": ws_id},
    ).scalar()
    assert plan == TRIAL_PLAN

    rl = db.execute(
        text(
            "SELECT rpm, tpm FROM guard_rate_limits "
            "WHERE workspace_id = :ws AND agent_identity_id IS NULL"
        ),
        {"ws": ws_id},
    ).fetchone()
    assert rl is not None
    assert rl.rpm == TRIAL_RPM
    assert rl.tpm == TRIAL_TPM

    bg = db.execute(
        text(
            "SELECT monthly_limit_usd, hard_limit_usd FROM guard_spend_budgets "
            "WHERE workspace_id = :ws AND clerk_user_id IS NULL"
        ),
        {"ws": ws_id},
    ).fetchone()
    assert bg is not None
    assert float(bg.monthly_limit_usd) == TRIAL_MONTHLY_USD
    assert float(bg.hard_limit_usd) == TRIAL_HARD_USD

    ai = db.execute(
        text(
            "SELECT expires_at, lifecycle_state FROM agent_identities "
            "WHERE workspace_id = :ws AND name = :name"
        ),
        {"ws": ws_id, "name": TRIAL_IDENTITY_NAME},
    ).fetchone()
    assert ai is not None
    assert ai.lifecycle_state == "active"
    delta_days = (ai.expires_at - datetime.now(timezone.utc)).days
    assert 6 <= delta_days <= 7


def test_seed_trial_is_idempotent(ws):
    ws_id, db = ws

    first = seed_trial(db, ws_id)
    db.commit()
    assert first is not None

    second = seed_trial(db, ws_id)
    db.commit()
    assert second is None

    for table, filt in [
        ("guard_rate_limits", "workspace_id = :ws AND agent_identity_id IS NULL"),
        ("guard_spend_budgets", "workspace_id = :ws AND clerk_user_id IS NULL"),
        ("agent_identities", "workspace_id = :ws AND name = :name"),
    ]:
        params = {"ws": ws_id}
        if "name" in filt:
            params["name"] = TRIAL_IDENTITY_NAME
        n = _count(db, f"SELECT COUNT(*) FROM {table} WHERE {filt}", params)
        assert n == 1, f"{table}: expected 1 row, got {n}"
