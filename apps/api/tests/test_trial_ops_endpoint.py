"""Trial ops endpoint self-check (epic #1587 A1)."""
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
from app.modules.guard.routers.trial import get_trial_ops  # noqa: E402
from app.modules.guard.trial_seed import TRIAL_IDENTITY_NAME, seed_trial  # noqa: E402
from app.modules.guard.trial_upstream import TRIAL_DAILY_CAP  # noqa: E402


def _make_workspace(db, plan: str = "free_trial") -> str:
    ws_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    db.execute(
        text(
            "INSERT INTO workspaces (id, name, owner_id, plan, is_approved, created_at, updated_at) "
            "VALUES (:id, :name, :owner, :plan, true, :now, :now)"
        ),
        {"id": ws_id, "name": f"ops-{ws_id[:8]}", "owner": f"test-{ws_id[:8]}", "plan": plan, "now": now},
    )
    db.commit()
    return ws_id


def _seed_and_get_trial_id(db, ws_id: str) -> str:
    seed_trial(db, ws_id)
    db.commit()
    return str(db.execute(
        text("SELECT id FROM agent_identities WHERE workspace_id = :ws AND name = :name"),
        {"ws": ws_id, "name": TRIAL_IDENTITY_NAME},
    ).scalar())


def _insert_audit(db, ws_id: str, aid: str, cost: float, ts: datetime | None = None):
    ts = ts or datetime.now(timezone.utc)
    db.execute(
        text(
            "INSERT INTO guard_audit_events "
            "(id, workspace_id, agent_identity_id, ts, source, provider, decision, ai_tool, cost_usd_after) "
            "VALUES (gen_random_uuid(), :ws, :aid, :ts, 'proxy', 'anthropic', 'allowed', 'cli', :cost)"
        ),
        {"ws": ws_id, "aid": aid, "ts": ts, "cost": cost},
    )


@pytest.fixture()
def workspaces():
    """Create three trial workspaces with different burn levels; teardown wipes everything."""
    db = SessionLocal()
    created: list[str] = []
    try:
        ws1 = _make_workspace(db)
        ws2 = _make_workspace(db)
        ws3 = _make_workspace(db)
        created = [ws1, ws2, ws3]

        aid1 = _seed_and_get_trial_id(db, ws1)
        aid2 = _seed_and_get_trial_id(db, ws2)
        aid3 = _seed_and_get_trial_id(db, ws3)

        # ws1 = biggest spender ($0.50 total), 5 rows
        for _ in range(5):
            _insert_audit(db, ws1, aid1, 0.10)
        # ws2 = middle spender ($0.20 total), 2 rows
        for _ in range(2):
            _insert_audit(db, ws2, aid2, 0.10)
        # ws3 = at cap (TRIAL_DAILY_CAP rows, tiny cost each)
        for _ in range(TRIAL_DAILY_CAP):
            _insert_audit(db, ws3, aid3, 0.001)
        db.commit()

        yield {"ws1": (ws1, aid1), "ws2": (ws2, aid2), "ws3": (ws3, aid3), "db": db}
    finally:
        db.rollback()
        for ws in created:
            db.execute(text("DELETE FROM integrations WHERE workspace_id = :id"), {"id": ws})
            db.execute(text("DELETE FROM workspaces WHERE id = :id"), {"id": ws})
        db.commit()
        db.close()


def _call(db):
    return get_trial_ops(_perm="security", db=db)


def test_reports_active_workspaces_and_total_spend(workspaces):
    db = workspaces["db"]

    out = _call(db)

    assert out.trial_workspaces_active_24h >= 3
    # ws1=0.50 + ws2=0.20 + ws3=0.2 = ~0.90 minimum from our fixture
    assert out.spend_today_usd >= 0.89
    assert out.cap_max == TRIAL_DAILY_CAP


def test_top_10_ranks_by_spend_desc(workspaces):
    db = workspaces["db"]
    ws1, _ = workspaces["ws1"]

    out = _call(db)

    assert len(out.top_10_by_spend) >= 3
    spends = [r.spend_usd for r in out.top_10_by_spend]
    assert spends == sorted(spends, reverse=True)

    top = out.top_10_by_spend[0]
    assert top.workspace_id == ws1
    assert top.spend_usd >= 0.49  # ~$0.50, allow float slack


def test_workspaces_at_cap_counted(workspaces):
    db = workspaces["db"]
    ws3, _ = workspaces["ws3"]

    out = _call(db)

    assert out.workspaces_at_cap >= 1

    # ws3 landed in top 10 by cap_used (200 rows), verify its row shows at-cap
    ws3_row = next((r for r in out.top_10_by_spend if r.workspace_id == ws3), None)
    assert ws3_row is not None
    assert ws3_row.cap_used == TRIAL_DAILY_CAP


def test_stale_audit_rows_excluded_from_24h_window(workspaces):
    db = workspaces["db"]
    ws1, aid1 = workspaces["ws1"]

    # Insert a row 48h old — must not count
    old_ts = datetime.now(timezone.utc) - timedelta(hours=48)
    _insert_audit(db, ws1, aid1, 99.99, ts=old_ts)
    db.commit()

    out = _call(db)

    ws1_row = next(r for r in out.top_10_by_spend if r.workspace_id == ws1)
    assert ws1_row.spend_usd < 10.0, "48h-old $99.99 row should not appear in 24h window"
