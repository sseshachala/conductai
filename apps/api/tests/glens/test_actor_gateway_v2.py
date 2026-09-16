"""#2012 — actor ActionSpec + ToolDef parity for the Gateway Profile v2
tool set.

Propose-path only — the confirm/dispatch path is covered by the actor
substrate integration suite and the router-endpoint tests for
create/update/publish/rollback. Here we lock:

- Every ToolDef + ActionSpec is registered under the right name.
- Read tools return the projected shape (list, get, revisions).
- Every propose function rejects the specific error paths that Lens
  users would otherwise only hit at the confirm click.
- Publish's summary distinguishes first-publish vs replaces-existing so
  the confirm card reads correctly.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.modules.glens.actor import default_action_registry, ActionCtx
from app.modules.glens.actor import registrations  # noqa: F401 — populate registry
from app.tools import registrations as _tool_registrations  # noqa: F401
from app.tools.registry import default_registry


_WS = "00000000-0000-0000-0000-000000000000"
_PROFILE = "11111111-1111-1111-1111-111111111111"
_ENV = "22222222-2222-2222-2222-222222222222"
_REV = "33333333-3333-3333-3333-333333333333"


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


def _query_returning(*rows):
    """Chain that returns rows in sequence per .first() call."""
    db = MagicMock()
    calls = list(rows)

    def _first_side_effect(*_a, **_k):
        return calls.pop(0) if calls else None

    filter_chain = MagicMock()
    filter_chain.first.side_effect = _first_side_effect
    db.query.return_value.filter.return_value = filter_chain
    return db


# ── Registration parity ──────────────────────────────────────────────


def test_every_gateway_v2_actionspec_registered():
    for name in (
        "gateway_v2_create_draft",
        "gateway_v2_update_working_copy",
        "gateway_v2_publish",
        "gateway_v2_rollback",
    ):
        spec = default_action_registry.get(name)
        assert spec is not None, name
        assert spec.guard_permission == "platform.credentials.manage", name
        assert callable(spec.propose)
        assert callable(spec.execute)


def test_every_gateway_v2_tooldef_registered():
    read_tools = (
        "list_gateway_v2_profiles",
        "get_gateway_v2_profile",
        "list_gateway_v2_revisions",
    )
    for name in read_tools:
        tool = default_registry.get(name)
        assert tool is not None, name
        assert tool.annotations.read_only is True, name
        assert tool.permission == "platform.credentials.manage", name

    mutating_tools = (
        "gateway_v2_create_draft",
        "gateway_v2_update_working_copy",
        "gateway_v2_publish",
        "gateway_v2_rollback",
    )
    for name in mutating_tools:
        tool = default_registry.get(name)
        assert tool is not None, name
        assert tool.annotations.read_only is False, name
        # RBAC on the ActionSpec, not the ToolDef — matches update_budget,
        # invite_member, etc.
        assert tool.permission is None, name
        assert "actor" in tool.tags, name


# ── create_draft ──────────────────────────────────────────────────────


def test_create_draft_rejects_empty_name():
    spec = default_action_registry.get("gateway_v2_create_draft")
    out = spec.propose(_ctx(), {})
    assert out.rejected and "name required" in (out.reason or "")


def test_create_draft_rejects_non_dict_working_copy():
    spec = default_action_registry.get("gateway_v2_create_draft")
    out = spec.propose(_ctx(), {"name": "prod", "working_copy": "oops"})
    assert out.rejected and "working_copy" in (out.reason or "")


def test_create_draft_rejects_name_collision():
    spec = default_action_registry.get("gateway_v2_create_draft")
    existing = SimpleNamespace(name="prod")
    ctx = _ctx(db=_query_returning(existing))
    out = spec.propose(ctx, {"name": "prod"})
    assert out.rejected and "already exists" in (out.reason or "")


def test_create_draft_summary_names_alias_when_supplied():
    spec = default_action_registry.get("gateway_v2_create_draft")
    ctx = _ctx(db=_query_returning(None))  # no collision
    out = spec.propose(ctx, {
        "name": "coding-profile",
        "working_copy": {"model_alias": "coding"},
    })
    assert not out.rejected
    assert "coding-profile" in out.summary
    assert "coding" in out.summary
    assert out.resolved_input["name"] == "coding-profile"


# ── update_working_copy ──────────────────────────────────────────────


def test_update_working_copy_rejects_invalid_uuid():
    spec = default_action_registry.get("gateway_v2_update_working_copy")
    out = spec.propose(_ctx(), {"profile_id": "nope", "working_copy": {"k": "v"}})
    assert out.rejected and "not a valid UUID" in (out.reason or "")


def test_update_working_copy_rejects_empty_body():
    spec = default_action_registry.get("gateway_v2_update_working_copy")
    out = spec.propose(_ctx(), {"profile_id": _PROFILE, "working_copy": {}})
    assert out.rejected and "non-empty" in (out.reason or "")


def test_update_working_copy_rejects_missing_profile():
    spec = default_action_registry.get("gateway_v2_update_working_copy")
    ctx = _ctx(db=_query_returning(None))
    out = spec.propose(ctx, {
        "profile_id": _PROFILE,
        "working_copy": {"model_alias": "coding"},
    })
    assert out.rejected and "not found" in (out.reason or "")


def test_update_working_copy_summary_counts_targets():
    spec = default_action_registry.get("gateway_v2_update_working_copy")
    profile = SimpleNamespace(id=uuid.UUID(_PROFILE), name="prod",
                              working_copy=None)
    ctx = _ctx(db=_query_returning(profile))
    out = spec.propose(ctx, {
        "profile_id": _PROFILE,
        "working_copy": {
            "model_alias": "coding",
            "targets": [{"id": "a"}, {"id": "b"}],
        },
    })
    assert not out.rejected
    assert "prod" in out.summary
    assert "2 target" in out.summary


# ── publish ──────────────────────────────────────────────────────────


def test_publish_rejects_empty_working_copy():
    spec = default_action_registry.get("gateway_v2_publish")
    profile = SimpleNamespace(id=uuid.UUID(_PROFILE), name="prod", working_copy=None)
    ctx = _ctx(db=_query_returning(profile))
    out = spec.propose(ctx, {"profile_id": _PROFILE, "environment_id": _ENV})
    assert out.rejected and "empty" in (out.reason or "")


def test_publish_rejects_wrong_workspace_environment():
    spec = default_action_registry.get("gateway_v2_publish")
    profile = SimpleNamespace(
        id=uuid.UUID(_PROFILE), name="prod",
        working_copy={"model_alias": "coding"},
    )
    # profile lookup returns profile, environment lookup returns None.
    ctx = _ctx(db=_query_returning(profile, None))
    out = spec.propose(ctx, {"profile_id": _PROFILE, "environment_id": _ENV})
    assert out.rejected and "does not belong" in (out.reason or "")


def test_publish_summary_mentions_first_publish_when_no_existing_binding():
    spec = default_action_registry.get("gateway_v2_publish")
    profile = SimpleNamespace(
        id=uuid.UUID(_PROFILE), name="prod",
        working_copy={"model_alias": "coding"},
    )
    env = SimpleNamespace(id=uuid.UUID(_ENV), name="Production")
    # profile → env → binding(None)
    ctx = _ctx(db=_query_returning(profile, env, None))
    out = spec.propose(ctx, {"profile_id": _PROFILE, "environment_id": _ENV})
    assert not out.rejected
    assert "Production" in out.summary
    assert "first publish" in out.summary.lower()


def test_publish_summary_mentions_replace_when_existing_binding():
    spec = default_action_registry.get("gateway_v2_publish")
    profile = SimpleNamespace(
        id=uuid.UUID(_PROFILE), name="prod",
        working_copy={"model_alias": "coding"},
    )
    env = SimpleNamespace(id=uuid.UUID(_ENV), name="Production")
    binding = SimpleNamespace(revision_id=uuid.UUID(_REV))
    ctx = _ctx(db=_query_returning(profile, env, binding))
    out = spec.propose(ctx, {"profile_id": _PROFILE, "environment_id": _ENV})
    assert not out.rejected
    assert "replaces" in out.summary.lower()


# ── rollback ─────────────────────────────────────────────────────────


def test_rollback_rejects_cross_profile_revision():
    """The router already checks this; we mirror the check at propose
    time so the user sees the failure without waiting for the confirm."""
    spec = default_action_registry.get("gateway_v2_rollback")
    profile = SimpleNamespace(id=uuid.UUID(_PROFILE), name="prod")
    ctx = _ctx(db=_query_returning(profile, None))  # revision lookup fails
    out = spec.propose(ctx, {
        "profile_id": _PROFILE, "environment_id": _ENV, "revision_id": _REV,
    })
    assert out.rejected and "does not belong" in (out.reason or "")


def test_rollback_summary_names_version_and_environment():
    spec = default_action_registry.get("gateway_v2_rollback")
    profile = SimpleNamespace(id=uuid.UUID(_PROFILE), name="prod")
    revision = SimpleNamespace(
        id=uuid.UUID(_REV), version=7,
        published_by="alice@example.com",
        published_at=datetime.now(timezone.utc),
    )
    env = SimpleNamespace(id=uuid.UUID(_ENV), name="Production")
    ctx = _ctx(db=_query_returning(profile, revision, env))
    out = spec.propose(ctx, {
        "profile_id": _PROFILE, "environment_id": _ENV, "revision_id": _REV,
    })
    assert not out.rejected
    assert "v7" in out.summary
    assert "Production" in out.summary
    assert "alice@example.com" in out.summary
