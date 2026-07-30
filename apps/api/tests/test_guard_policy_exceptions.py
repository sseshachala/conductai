import inspect
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi import BackgroundTasks, HTTPException

from app.modules.guard.models import GuardRuleOverride
from app.modules.guard.routers.policies import (
    PolicyPatch,
    _pack_rule_to_out,
    _find_pack_rule,
    _resolve_workspace_pack,
    _validate_exception_metadata,
    patch_policy,
)


def test_future_exception_metadata_is_accepted():
    expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

    reason, result_expiry = _validate_exception_metadata(
        relaxing=True,
        fields_touched=True,
        reason="  Vendor maintenance  ",
        expires_at=expires_at,
    )

    assert reason == "Vendor maintenance"
    assert result_expiry == expires_at


@pytest.mark.parametrize(
    ("reason", "expires_at"),
    [
        (None, datetime.now(timezone.utc) + timedelta(hours=1)),
        ("", datetime.now(timezone.utc) + timedelta(hours=1)),
        ("Needed", None),
        ("Needed", datetime.now(timezone.utc) - timedelta(seconds=1)),
        ("Needed", datetime.now() + timedelta(hours=1)),
    ],
)
def test_invalid_exception_metadata_is_rejected(reason, expires_at):
    with pytest.raises(HTTPException) as exc_info:
        _validate_exception_metadata(
            relaxing=True,
            fields_touched=True,
            reason=reason,
            expires_at=expires_at,
        )

    assert exc_info.value.status_code == 422


def test_non_relaxing_change_needs_no_exception_metadata():
    assert _validate_exception_metadata(
        relaxing=False,
        fields_touched=True,
        reason=None,
        expires_at=None,
    ) == (None, None)


def test_message_only_override_is_indefinite_customization():
    override = GuardRuleOverride(
        disabled=False,
        action=None,
        custom_message="Use the approved workflow",
        reason=None,
        expires_at=None,
    )

    result = _pack_rule_to_out(
        {"id": "r1", "action": "block", "message": "Base"},
        "conduct-base",
        datetime.now(timezone.utc),
        MagicMock(),
        override,
    )

    assert result.action == "block"
    assert result.message == "Use the approved workflow"
    assert result.exception_active is False
    assert result.exception_expired is False


def test_expired_exception_is_visible_but_not_effective():
    expired_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    override = GuardRuleOverride(
        disabled=True,
        action="warn",
        custom_message=None,
        reason="Temporary maintenance",
        expires_at=expired_at,
    )

    result = _pack_rule_to_out(
        {"id": "r1", "action": "block"},
        "conduct-base",
        datetime.now(timezone.utc),
        MagicMock(),
        override,
    )

    assert result.enabled is True
    assert result.action == "block"
    assert result.exception_reason == "Temporary maintenance"
    assert result.exception_expires_at == expired_at
    assert result.exception_active is False
    assert result.exception_expired is True


def test_patch_rejects_unknown_action():
    with pytest.raises(HTTPException) as exc_info:
        patch_policy(
            "r1",
            PolicyPatch(action="permit"),
            BackgroundTasks(),
            db=MagicMock(),
            workspace_id="00000000-0000-0000-0000-000000000001",
            user_id="user_1",
            _="admin",
        )

    assert exc_info.value.status_code == 422
    assert "Invalid action" in exc_info.value.detail


def test_patch_rejects_internal_allow_action():
    with pytest.raises(HTTPException) as exc_info:
        patch_policy(
            "r1",
            PolicyPatch(action="allow"),
            BackgroundTasks(),
            db=MagicMock(),
            workspace_id="00000000-0000-0000-0000-000000000001",
            user_id="user_1",
            _="admin",
        )

    assert exc_info.value.status_code == 422
    assert "Invalid action" in exc_info.value.detail


def test_find_pack_rule_honors_pinned_version():
    db = MagicMock()
    workspace_pack = MagicMock(
        pack_slug="conduct-base",
        pinned_version="2.9.0",
    )
    pinned_pack = MagicMock(
        rules=[{"id": "r1", "action": "warn"}],
    )
    db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [
        workspace_pack
    ]
    db.get.return_value = pinned_pack

    result = _find_pack_rule(
        db,
        __import__("uuid").UUID("00000000-0000-0000-0000-000000000001"),
        "r1",
    )

    assert result == (pinned_pack.rules[0], workspace_pack)
    db.get.assert_called_once()


def test_resolve_workspace_pack_uses_latest_when_unpinned():
    db = MagicMock()
    workspace_pack = MagicMock(
        pack_slug="conduct-base",
        pinned_version=None,
    )
    older_pack = MagicMock(version="2.9.0")
    latest_pack = MagicMock(version="2.10.0")
    pack_query = db.query.return_value.filter.return_value
    pack_query.all.return_value = [older_pack, latest_pack]

    result = _resolve_workspace_pack(db, workspace_pack)

    assert result is latest_pack
    pack_query.all.assert_called_once()


def _call_pack_patch(body: PolicyPatch, base_action: str):
    db = MagicMock()
    db.get.side_effect = [None, None]
    workspace_pack = MagicMock(
        pack_slug="conduct-base",
        installed_at=datetime.now(timezone.utc),
    )
    override = GuardRuleOverride(
        disabled=not body.enabled if body.enabled is not None else False,
        action=body.action,
        custom_message=body.message,
        reason=body.reason,
        expires_at=body.expires_at,
    )
    with patch(
        "app.modules.guard.routers.policies._find_pack_rule",
        return_value=({"id": "r1", "action": base_action}, workspace_pack),
    ), patch(
        "app.modules.guard.routers.policies._upsert_override",
        return_value=override,
    ) as upsert, patch(
        "app.modules.guard.routers.policies.invalidate_policy_cache",
    ), patch(
        "app.modules.guard.routers.policies._write_audit",
    ):
        result = patch_policy(
            "r1",
            body,
            BackgroundTasks(),
            db=db,
            workspace_id="00000000-0000-0000-0000-000000000001",
            user_id="user_1",
            _="admin",
        )
    return result, upsert


def test_patch_accepts_future_relaxing_exception():
    expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

    result, upsert = _call_pack_patch(
        PolicyPatch(
            action="warn",
            reason="Incident response maintenance",
            expires_at=expires_at,
        ),
        base_action="block",
    )

    assert result.action == "warn"
    assert result.exception_active is True
    assert upsert.call_args.kwargs["reason"] == "Incident response maintenance"
    assert upsert.call_args.kwargs["expires_at"] == expires_at


def test_patch_accepts_stronger_action_without_expiry():
    result, upsert = _call_pack_patch(
        PolicyPatch(action="block"),
        base_action="warn",
    )

    assert result.action == "block"
    assert result.exception_active is False
    assert upsert.call_args.kwargs["clear_exception"] is True


def test_patch_accepts_message_only_customization_without_expiry():
    result, upsert = _call_pack_patch(
        PolicyPatch(message="Use the approved workflow"),
        base_action="block",
    )

    assert result.message == "Use the approved workflow"
    assert result.exception_active is False
    assert upsert.call_args.kwargs["clear_exception"] is True


def test_patch_can_revoke_active_exception_before_expiry():
    db = MagicMock()
    expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    existing = GuardRuleOverride(
        disabled=True,
        action=None,
        reason="Temporary maintenance",
        expires_at=expires_at,
    )
    db.get.side_effect = [None, existing, existing]
    workspace_pack = MagicMock(
        pack_slug="conduct-base",
        installed_at=datetime.now(timezone.utc),
    )

    with patch(
        "app.modules.guard.routers.policies._find_pack_rule",
        return_value=({"id": "r1", "action": "block"}, workspace_pack),
    ), patch(
        "app.modules.guard.routers.policies.invalidate_policy_cache",
    ), patch(
        "app.modules.guard.routers.policies._write_audit",
    ):
        result = patch_policy(
            "r1",
            PolicyPatch(enabled=True),
            BackgroundTasks(),
            db=db,
            workspace_id="00000000-0000-0000-0000-000000000001",
            user_id="user_1",
            _="admin",
        )

    assert result.enabled is True
    assert result.exception_active is False
    assert existing.disabled is False
    assert existing.reason is None
    assert existing.expires_at is None


def test_patch_endpoint_keeps_existing_permission_gate():
    source = inspect.getsource(patch_policy)
    assert 'require_permission("guard.policies.edit")' in source
