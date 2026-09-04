"""Trial spend alert self-check (epic #1587 A3)."""
from __future__ import annotations

import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

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
from app.modules.guard.observability.trial_spend_alert import (  # noqa: E402
    _reset_dedup_for_tests,
    check_and_alert_trial_spend,
)
from app.modules.guard.trial_seed import TRIAL_IDENTITY_NAME, seed_trial  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_dedup():
    _reset_dedup_for_tests()
    yield
    _reset_dedup_for_tests()


@pytest.fixture()
def spend_ws():
    """Trial workspace with $5 of audit rows in the last hour."""
    db = SessionLocal()
    ws_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    db.execute(
        text(
            "INSERT INTO workspaces (id, name, owner_id, plan, is_approved, created_at, updated_at) "
            "VALUES (:id, :name, :owner, 'free', true, :now, :now)"
        ),
        {"id": ws_id, "name": f"spend-alert-{ws_id[:8]}", "owner": f"test-{ws_id[:8]}", "now": now},
    )
    db.commit()
    seed_trial(db, ws_id)
    db.commit()
    aid = str(db.execute(
        text("SELECT id FROM agent_identities WHERE workspace_id = :ws AND name = :name"),
        {"ws": ws_id, "name": TRIAL_IDENTITY_NAME},
    ).scalar())
    for _ in range(5):
        db.execute(
            text(
                "INSERT INTO guard_audit_events "
                "(id, workspace_id, agent_identity_id, ts, source, provider, decision, ai_tool, cost_usd_after) "
                "VALUES (gen_random_uuid(), :ws, :aid, :ts, 'proxy', 'anthropic', 'allowed', 'cli', 1.0)"
            ),
            {"ws": ws_id, "aid": aid, "ts": now},
        )
    db.commit()
    try:
        yield ws_id, db
    finally:
        db.rollback()
        db.execute(text("DELETE FROM integrations WHERE workspace_id = :id"), {"id": ws_id})
        db.execute(text("DELETE FROM workspaces WHERE id = :id"), {"id": ws_id})
        db.commit()
        db.close()


def test_noops_when_webhook_env_missing(spend_ws, monkeypatch):
    _ws, db = spend_ws
    monkeypatch.delenv("CONDUCT_INTERNAL_ALERT_SLACK_CHANNEL", raising=False)
    monkeypatch.setenv("GUARD_TRIAL_DAILY_ALERT_USD", "2.0")

    with patch("httpx.post") as mock_post:
        check_and_alert_trial_spend(db)
    mock_post.assert_not_called()


def test_noops_when_threshold_env_missing(spend_ws, monkeypatch):
    _ws, db = spend_ws
    monkeypatch.setenv("CONDUCT_INTERNAL_ALERT_SLACK_CHANNEL", "conduct-alerts")
    monkeypatch.delenv("GUARD_TRIAL_DAILY_ALERT_USD", raising=False)

    with patch("httpx.post") as mock_post:
        check_and_alert_trial_spend(db)
    mock_post.assert_not_called()


def test_noops_when_below_threshold(spend_ws, monkeypatch):
    _ws, db = spend_ws
    monkeypatch.setenv("CONDUCT_INTERNAL_ALERT_SLACK_CHANNEL", "conduct-alerts")
    monkeypatch.setenv("GUARD_TRIAL_DAILY_ALERT_USD", "100.0")  # $5 in DB, threshold $100

    with patch("httpx.post") as mock_post:
        check_and_alert_trial_spend(db)
    mock_post.assert_not_called()


def test_posts_when_over_threshold(spend_ws, monkeypatch):
    ws_id, db = spend_ws
    monkeypatch.setenv("CONDUCT_INTERNAL_ALERT_SLACK_CHANNEL", "conduct-alerts")
    monkeypatch.setenv("GUARD_TRIAL_DAILY_ALERT_USD", "2.0")  # $5 in DB, threshold $2

    with patch("httpx.post") as mock_post:
        check_and_alert_trial_spend(db)
    assert mock_post.call_count == 1
    text_body = mock_post.call_args.kwargs["json"]["text"]
    assert "Trial spend crossed threshold" in text_body
    assert "$5.00" in text_body
    # PR 4 A3 v2: alert now includes the workspace name of the top spender
    # and the request count against the daily cap. Workspace name from the
    # fixture is `spend-alert-<8char>`.
    assert "Top spender" in text_body
    assert "spend-alert-" in text_body
    assert "5 of 200 calls" in text_body  # 5 seeded rows, cap 200


def test_second_call_within_rate_limit_is_deduped(spend_ws, monkeypatch):
    _ws, db = spend_ws
    monkeypatch.setenv("CONDUCT_INTERNAL_ALERT_SLACK_CHANNEL", "conduct-alerts")
    monkeypatch.setenv("GUARD_TRIAL_DAILY_ALERT_USD", "2.0")

    with patch("httpx.post") as mock_post:
        check_and_alert_trial_spend(db)
        check_and_alert_trial_spend(db)
    assert mock_post.call_count == 1


def test_bad_threshold_env_noops(spend_ws, monkeypatch):
    _ws, db = spend_ws
    monkeypatch.setenv("CONDUCT_INTERNAL_ALERT_SLACK_CHANNEL", "conduct-alerts")
    monkeypatch.setenv("GUARD_TRIAL_DAILY_ALERT_USD", "not-a-number")

    with patch("httpx.post") as mock_post:
        check_and_alert_trial_spend(db)
    mock_post.assert_not_called()
