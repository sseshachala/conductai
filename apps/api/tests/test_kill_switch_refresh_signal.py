"""Refresh tells the CLI when an admin deactivated the identity (kill switch)."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.modules.auth import cli_token


def _identity(state):
    return SimpleNamespace(
        id="33333333-3333-4333-8333-333333333333",
        workspace_id="11111111-1111-4111-8111-111111111111",
        refresh_token_expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        token_type="cli",
        lifecycle_state=state,
    )


def _legacy_db(identity):
    db = MagicMock()
    db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = identity
    return db


def _session_db(identity):
    db = MagicMock()
    session = SimpleNamespace(agent_identity_id=identity.id,
                              refresh_token_expires_at=datetime.now(timezone.utc) + timedelta(days=1))
    db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = session
    db.query.return_value.filter.return_value.first.return_value = identity
    return db


@pytest.mark.parametrize("token,make_db", [
    ("cond_ref_legacy", _legacy_db),
    ("cond_ref_s1_session", _session_db),
])
@pytest.mark.parametrize("state,expected", [("deactivated", "deactivated"), ("expired", None)])
def test_only_deactivation_carries_the_signal(token, make_db, state, expected):
    with pytest.raises(HTTPException) as exc:
        cli_token.rotate_identity_by_refresh(token, make_db(_identity(state)))
    assert exc.value.status_code == 401
    assert exc.value.detail == "Agent identity is inactive"
    assert (exc.value.headers or {}).get(cli_token.IDENTITY_STATE_HEADER) == expected


def test_lens_deactivate_drops_cached_auth(monkeypatch):
    from app.modules.glens.actor.registrations import deactivate_agent_identity as mod
    import app.core.auth_events as auth_events

    agent = SimpleNamespace(id="33333333-3333-4333-8333-333333333333", lifecycle_state="active", deactivated_at=None)
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = agent
    published = []
    monkeypatch.setattr(auth_events, "publish_identity_disabled", published.append)
    ctx = SimpleNamespace(db=db, workspace_id="11111111-1111-4111-8111-111111111111")

    mod._execute_deactivate(ctx, {"agent_id": agent.id, "agent_name": "a"})

    assert agent.lifecycle_state == "deactivated"
    assert published == [agent.id]
