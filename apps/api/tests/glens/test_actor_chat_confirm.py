"""P0 #1465 — confirm_pending_action + cancel_pending_action Lens tools.

Registration parity + happy-path + ownership + session-id + already-decided
tests. Direct impl calls (no HTTP) with mocked `dispatch_confirm` /
`dispatch_cancel` so the tool-side plumbing is exercised in isolation.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from app.mcp.server import MCPContext
from app.modules.glens.actor.helpers import ConfirmError
from app.tools import registrations as _tool_registrations  # noqa: F401 — populate registry
from app.tools.registry import default_registry


_CTX = MCPContext(
    workspace_id="00000000-0000-0000-0000-000000000000",
    clerk_user_id="user_abc",
    user_email="user@example.com",
    session_id="sess-xyz",
    surface="lens",
)


# ── Registration parity ────────────────────────────────────────────────────

def test_confirm_pending_action_registered():
    tool = default_registry.get("confirm_pending_action")
    assert tool is not None
    assert "lens" in tool.tags
    assert "actor" in tool.tags
    assert tool.annotations.read_only is False


def test_cancel_pending_action_registered():
    tool = default_registry.get("cancel_pending_action")
    assert tool is not None
    assert "lens" in tool.tags
    assert "actor" in tool.tags
    assert tool.annotations.read_only is False


# ── Confirm impl ───────────────────────────────────────────────────────────

def test_confirm_happy_path_returns_execute_result():
    from app.tools.registrations.lens.actor import _confirm_pending_action_impl

    fake_payload = {
        "executed": True, "cached": False,
        "action_id": "a1", "tool_name": "run_workflow",
        "status": "approved",
        "result": {"run_id": "r1", "status": "pending"},
    }
    with patch("app.core.database.SessionLocal", return_value=SimpleNamespace(close=lambda: None)), \
         patch("app.modules.glens.actor.helpers.dispatch_confirm", return_value=fake_payload) as mock_dispatch:
        out = _confirm_pending_action_impl(_CTX, "a1")

    mock_dispatch.assert_called_once()
    call_kwargs = mock_dispatch.call_args.kwargs
    assert call_kwargs["action_id"] == "a1"
    assert call_kwargs["workspace_id"] == _CTX.workspace_id
    assert call_kwargs["clerk_user_id"] == _CTX.clerk_user_id
    # Session id is forwarded so dispatch can enforce match against the row.
    assert call_kwargs["session_id"] == _CTX.session_id
    assert out["executed"] is True
    assert out["result"]["run_id"] == "r1"


def test_confirm_returns_error_dict_on_confirm_error():
    from app.tools.registrations.lens.actor import _confirm_pending_action_impl

    with patch("app.core.database.SessionLocal", return_value=SimpleNamespace(close=lambda: None)), \
         patch("app.modules.glens.actor.helpers.dispatch_confirm",
               side_effect=ConfirmError(403, "action belongs to a different chat session")):
        out = _confirm_pending_action_impl(_CTX, "a1")

    assert out == {"error": "action belongs to a different chat session", "status_code": 403}


def test_confirm_on_already_executed_returns_cached_result():
    """dispatch_confirm's idempotent path returns cached=True; tool passes it through."""
    from app.tools.registrations.lens.actor import _confirm_pending_action_impl

    fake_payload = {
        "executed": True, "cached": True,
        "action_id": "a1", "tool_name": "run_workflow",
        "status": "approved",
        "result": {"run_id": "r1"},
    }
    with patch("app.core.database.SessionLocal", return_value=SimpleNamespace(close=lambda: None)), \
         patch("app.modules.glens.actor.helpers.dispatch_confirm", return_value=fake_payload):
        out = _confirm_pending_action_impl(_CTX, "a1")

    assert out["cached"] is True
    assert out["result"]["run_id"] == "r1"


# ── Cancel impl ────────────────────────────────────────────────────────────

def test_cancel_happy_path():
    from app.tools.registrations.lens.actor import _cancel_pending_action_impl

    fake_payload = {"cancelled": True, "action_id": "a1", "tool_name": "run_workflow"}
    with patch("app.core.database.SessionLocal", return_value=SimpleNamespace(close=lambda: None)), \
         patch("app.modules.glens.actor.helpers.dispatch_cancel", return_value=fake_payload) as mock_dispatch:
        out = _cancel_pending_action_impl(_CTX, "a1", reason="user changed mind")

    call_kwargs = mock_dispatch.call_args.kwargs
    assert call_kwargs["reason"] == "user changed mind"
    assert call_kwargs["session_id"] == _CTX.session_id
    assert out["cancelled"] is True


def test_cancel_returns_error_dict_on_already_decided():
    from app.tools.registrations.lens.actor import _cancel_pending_action_impl

    with patch("app.core.database.SessionLocal", return_value=SimpleNamespace(close=lambda: None)), \
         patch("app.modules.glens.actor.helpers.dispatch_cancel",
               side_effect=ConfirmError(409, "action is approved")):
        out = _cancel_pending_action_impl(_CTX, "a1")

    assert out == {"error": "action is approved", "status_code": 409}


# ── Session-id enforcement in dispatch_confirm ─────────────────────────────

def test_dispatch_confirm_rejects_cross_session():
    """Row.session_id != ctx.session_id → 403. This is the core prompt-injection
    guard: a compromised LLM in session B can't confirm session A's actions."""
    from app.modules.glens.actor.helpers import _enforce_ownership

    row = SimpleNamespace(requester_user_id="user_abc", session_id="sess-xyz")
    # Same user, wrong session
    try:
        _enforce_ownership(row, clerk_user_id="user_abc", session_id="sess-other")
    except ConfirmError as e:
        assert e.status_code == 403
        assert "different chat session" in e.detail
    else:
        raise AssertionError("expected ConfirmError")


def test_dispatch_confirm_rejects_cross_user():
    from app.modules.glens.actor.helpers import _enforce_ownership

    row = SimpleNamespace(requester_user_id="user_abc", session_id="sess-xyz")
    try:
        _enforce_ownership(row, clerk_user_id="user_other", session_id="sess-xyz")
    except ConfirmError as e:
        assert e.status_code == 403
        assert "proposer" in e.detail
    else:
        raise AssertionError("expected ConfirmError")


def test_enforce_ownership_passes_when_both_match():
    from app.modules.glens.actor.helpers import _enforce_ownership

    row = SimpleNamespace(requester_user_id="user_abc", session_id="sess-xyz")
    # Should not raise
    _enforce_ownership(row, clerk_user_id="user_abc", session_id="sess-xyz")


def test_enforce_ownership_lenient_when_row_has_no_session():
    """Actions created via HTTP (no chat session) can be confirmed via HTTP
    without a session id. Row.session_id is None → skip check."""
    from app.modules.glens.actor.helpers import _enforce_ownership

    row = SimpleNamespace(requester_user_id="user_abc", session_id=None)
    _enforce_ownership(row, clerk_user_id="user_abc", session_id=None)


def test_agent_proposed_row_can_be_confirmed_by_any_human():
    """#1475 HITL: Lens session proposes as an agent identity, a real human
    clicks Confirm. Ownership check must NOT require user equality when
    the row was proposed by an agent."""
    from app.modules.glens.actor.helpers import _enforce_ownership

    row = SimpleNamespace(
        requester_user_id="system:lens",
        requester_agent_ident="ai_lens_session_1",
        session_id=None,
    )
    _enforce_ownership(row, clerk_user_id="user_real_human", session_id=None)


def test_agent_proposed_by_synthetic_user_id_also_lenient():
    """Belt-and-braces: even without requester_agent_ident, a 'system:*'
    requester_user_id marks the row as agent-proposed."""
    from app.modules.glens.actor.helpers import _enforce_ownership

    row = SimpleNamespace(
        requester_user_id="system:lens",
        requester_agent_ident=None,
        session_id=None,
    )
    _enforce_ownership(row, clerk_user_id="user_real_human", session_id=None)
