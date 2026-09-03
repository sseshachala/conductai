"""Trial session endpoint self-check (epic #1567 PR 3)."""
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
from app.modules.guard.routers.trial import get_trial_session  # noqa: E402
from app.modules.guard.trial_seed import TRIAL_IDENTITY_NAME, TRIAL_PLAN  # noqa: E402
from app.modules.guard.trial_upstream import TRIAL_DAILY_CAP  # noqa: E402


@pytest.fixture()
def empty_ws():
    """Fresh workspace with plan='free' and no trial identity."""
    db = SessionLocal()
    ws_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    db.execute(
        text(
            "INSERT INTO workspaces (id, name, owner_id, plan, is_approved, created_at, updated_at) "
            "VALUES (:id, :name, :owner, 'free', true, :now, :now)"
        ),
        {"id": ws_id, "name": f"trial-sess-{ws_id[:8]}", "owner": f"test-{ws_id[:8]}", "now": now},
    )
    db.commit()
    try:
        yield ws_id, db
    finally:
        db.rollback()
        # integrations doesn't cascade, so wipe it explicitly. Other trial-owned
        # tables (agent_identities, guard_rate_limits, guard_spend_budgets,
        # guard_audit_events) do cascade off workspaces.id.
        db.execute(text("DELETE FROM integrations WHERE workspace_id = :id"), {"id": ws_id})
        db.execute(text("DELETE FROM workspaces WHERE id = :id"), {"id": ws_id})
        db.commit()
        db.close()


def _call(ws_id: str, db):
    return get_trial_session(workspace_id=ws_id, _perm="admin", db=db)


def test_on_demand_seed_when_no_trial_identity(empty_ws):
    ws_id, db = empty_ws

    out = _call(ws_id, db)

    assert out.plan == TRIAL_PLAN
    assert out.expired is False
    assert out.token and out.token.startswith("cond_agt_")
    assert 6 <= out.days_remaining <= 7
    assert out.cap_used == 0
    assert out.cap_max == TRIAL_DAILY_CAP
    assert out.gateway_url  # non-empty

    plan_now = db.execute(
        text("SELECT plan FROM workspaces WHERE id = :ws"), {"ws": ws_id},
    ).scalar()
    assert plan_now == TRIAL_PLAN


def test_repeat_visit_re_reveals_same_token(empty_ws):
    ws_id, db = empty_ws

    first = _call(ws_id, db)
    second = _call(ws_id, db)

    assert first.token == second.token
    assert first.days_remaining == second.days_remaining

    count = db.execute(
        text(
            "SELECT COUNT(*) FROM agent_identities "
            "WHERE workspace_id = :ws AND name = :name"
        ),
        {"ws": ws_id, "name": TRIAL_IDENTITY_NAME},
    ).scalar()
    assert count == 1


def test_expired_identity_returns_expired_true(empty_ws):
    ws_id, db = empty_ws

    _call(ws_id, db)
    past = datetime.now(timezone.utc) - timedelta(days=1)
    db.execute(
        text(
            "UPDATE agent_identities SET expires_at = :past "
            "WHERE workspace_id = :ws AND name = :name"
        ),
        {"past": past, "ws": ws_id, "name": TRIAL_IDENTITY_NAME},
    )
    db.commit()

    out = _call(ws_id, db)
    assert out.expired is True
    assert out.token is None
    assert out.days_remaining == 0


def test_cap_used_reflects_recent_audit_rows(empty_ws):
    ws_id, db = empty_ws

    first = _call(ws_id, db)
    trial_id = db.execute(
        text("SELECT id FROM agent_identities WHERE workspace_id = :ws AND name = :name"),
        {"ws": ws_id, "name": TRIAL_IDENTITY_NAME},
    ).scalar()

    now = datetime.now(timezone.utc)
    for _ in range(3):
        db.execute(
            text(
                "INSERT INTO guard_audit_events (id, workspace_id, agent_identity_id, ts, source, provider, decision, ai_tool) "
                "VALUES (gen_random_uuid(), :ws, :aid, :ts, 'proxy', 'anthropic', 'allowed', 'cli')"
            ),
            {"ws": ws_id, "aid": str(trial_id), "ts": now},
        )
    db.commit()

    second = _call(ws_id, db)
    assert second.cap_used == 3
    assert second.token == first.token


def test_paid_empty_workspace_plan_not_overwritten(empty_ws):
    """PR 5: a paid workspace with no runs/keys must keep its plan when the
    Try-It endpoint on-demand-seeds. seed_trial only flips `free`, and the
    endpoint must re-fetch instead of assuming the flip happened."""
    ws_id, db = empty_ws

    db.execute(text("UPDATE workspaces SET plan = 'pro' WHERE id = :ws"), {"ws": ws_id})
    db.commit()

    out = _call(ws_id, db)
    assert out.plan == "pro"
    assert out.token and out.token.startswith("cond_agt_")

    plan_now = db.execute(
        text("SELECT plan FROM workspaces WHERE id = :ws"), {"ws": ws_id},
    ).scalar()
    assert plan_now == "pro"


def test_active_workspace_with_integration_is_ineligible(empty_ws):
    """PR 4 B: workspace already has a vault key → refuse to seed a trial identity."""
    ws_id, db = empty_ws

    db.execute(
        text(
            "INSERT INTO integrations (id, workspace_id, service, auth_method, handle, created_at) "
            "VALUES (gen_random_uuid(), :ws, 'anthropic', 'api_key', 'anthropic', NOW())"
        ),
        {"ws": ws_id},
    )
    db.commit()

    out = _call(ws_id, db)
    assert out.ineligible is True
    assert out.reason == "active_workspace"
    assert out.token is None
    assert out.days_remaining == 0

    n = db.execute(
        text(
            "SELECT COUNT(*) FROM agent_identities "
            "WHERE workspace_id = :ws AND name = :name"
        ),
        {"ws": ws_id, "name": TRIAL_IDENTITY_NAME},
    ).scalar()
    assert n == 0, "no trial identity should be minted for active workspaces"
