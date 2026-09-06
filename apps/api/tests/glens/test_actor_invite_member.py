"""#1301 — actor ActionSpec + ToolDef parity for invite_member.

Propose-path only; live-DB confirm+dispatch is covered by the actor
substrate integration suite.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.modules.glens.actor import default_action_registry, ActionCtx
from app.modules.glens.actor import registrations  # noqa: F401 — populate registry
from app.tools import registrations as _tool_registrations  # noqa: F401
from app.tools.registry import default_registry


_WS = "00000000-0000-0000-0000-000000000000"


def _ctx(**over):
    base = dict(
        db=MagicMock(),
        workspace_id=_WS,
        clerk_user_id="user_abc",
        user_email="user@example.com",
        session_id=None,
        agent_identity_id=None,
        surface="lens",
    )
    base.update(over)
    return ActionCtx(**base)


def _no_existing_member_or_invite(ctx):
    """Wire ctx.db so both existence checks return None."""
    ctx.db.execute.return_value.fetchone.return_value = None


def test_invite_member_actionspec_registered():
    spec = default_action_registry.get("invite_member")
    assert spec is not None
    assert spec.guard_permission == "platform.members.manage"
    assert callable(spec.propose)
    assert callable(spec.execute)


def test_invite_member_tooldef_registered():
    tool = default_registry.get("invite_member")
    assert tool is not None
    assert "lens" in tool.tags
    assert "actor" in tool.tags
    assert tool.annotations.read_only is False


def test_propose_rejects_empty_email():
    spec = default_action_registry.get("invite_member")
    out = spec.propose(_ctx(), {"email": "", "role": "viewer"})
    assert out.rejected
    assert "email required" in (out.reason or "")


def test_propose_rejects_malformed_email():
    spec = default_action_registry.get("invite_member")
    out = spec.propose(_ctx(), {"email": "not-an-email", "role": "viewer"})
    assert out.rejected
    assert "email required" in (out.reason or "")


def test_propose_rejects_empty_role():
    spec = default_action_registry.get("invite_member")
    out = spec.propose(_ctx(), {"email": "new@example.com", "role": ""})
    assert out.rejected
    assert "role required" in (out.reason or "")


def test_propose_rejects_invalid_role():
    spec = default_action_registry.get("invite_member")
    ctx = _ctx()
    with patch("app.core.auth.get_valid_roles",
               return_value={"admin", "developer", "viewer"}):
        out = spec.propose(ctx, {"email": "new@example.com", "role": "wizard"})
    assert out.rejected
    assert "Invalid role 'wizard'" in (out.reason or "")


def test_propose_rejects_already_a_member():
    spec = default_action_registry.get("invite_member")
    ctx = _ctx()
    ctx.db.execute.return_value.fetchone.return_value = SimpleNamespace()
    with patch("app.core.auth.get_valid_roles",
               return_value={"admin", "viewer"}), \
         patch("app.core.auth.find_clerk_user_id_by_email",
               return_value="user_existing"):
        out = spec.propose(ctx, {"email": "existing@example.com", "role": "viewer"})
    assert out.rejected
    assert "already a member" in (out.reason or "")


def test_propose_rejects_pending_invite():
    spec = default_action_registry.get("invite_member")
    ctx = _ctx()
    # find_clerk_user_id_by_email → None skips membership check;
    # pending invite check is the only execute()
    ctx.db.execute.return_value.fetchone.return_value = SimpleNamespace()
    with patch("app.core.auth.get_valid_roles",
               return_value={"admin", "viewer"}), \
         patch("app.core.auth.find_clerk_user_id_by_email",
               return_value=None):
        out = spec.propose(ctx, {"email": "pending@example.com", "role": "viewer"})
    assert out.rejected
    assert "already pending" in (out.reason or "")


def test_propose_success_shape():
    spec = default_action_registry.get("invite_member")
    ctx = _ctx()
    _no_existing_member_or_invite(ctx)
    with patch("app.core.auth.get_valid_roles",
               return_value={"admin", "developer", "viewer"}), \
         patch("app.core.auth.find_clerk_user_id_by_email",
               return_value=None):
        out = spec.propose(ctx, {"email": "New@Example.com", "role": "developer"})
    assert not out.rejected
    assert out.summary == "Invite 'new@example.com' as developer"
    assert out.resolved_input == {"email": "new@example.com", "role": "developer"}
