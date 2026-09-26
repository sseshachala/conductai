from datetime import timedelta
from uuid import uuid4
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import text

from app.modules.glens.entry_context import LensEntryContext, resolve_entry_context
from app.modules.glens.platform_evidence import PlatformEvidenceQuery, read_platform_evidence
from app.modules.glens.evidence_explanation import answer_from_result
from app.modules.glens.executor import Executor
from tests.glens.test_trial_evidence import data, WS, OTHER, NOW  # noqa: F401
from tests.glens.test_trial_accounting import accounting, BOB  # noqa: F401
from tests.glens.test_platform_evidence import platform  # noqa: F401


def context(kind, resource_id=None, **kwargs):
    return LensEntryContext(kind=kind, resource_id=resource_id, workspace_id=WS, **kwargs)


@pytest.mark.parametrize("args", [
    {"kind": "event"}, {"kind": "run", "resource_id": "bad"},
    {"kind": "trial", "resource_id": str(uuid4())},
    {"kind": "event", "resource_id": str(uuid4()), "block_id": "a"},
    {"kind": "trial", "user_id": "admin"},
])
def test_invalid_or_authority_bearing_context_rejected(args):
    with pytest.raises(ValidationError):
        LensEntryContext(workspace_id=WS, **args)


def test_workspace_mismatch_does_not_query():
    db = MagicMock()
    with pytest.raises(HTTPException) as exc:
        resolve_entry_context(db, OTHER, "alice", context("trial"))
    assert exc.value.status_code == 409
    db.execute.assert_not_called()


def test_selected_old_event_is_exact_and_preserves_receipts(platform):
    db, activity, receipt, _ = platform
    row = activity(when=NOW - timedelta(days=90))
    receipt(row)
    activity()
    query = resolve_entry_context(db, WS, "alice", context("event", row["id"]))
    result = read_platform_evidence(db, WS, "alice", query)
    assert [r.source_id for r in result.records] == [row["id"]]
    assert result.accounting_totals.input_tokens.value == 100
    _, saved = answer_from_result(result.model_dump_json(), str(WS), "get_platform_evidence")
    assert saved["exact_resource"] is True and saved["event_ids"] == [str(row["id"])]


@pytest.mark.parametrize("foreign", [False, True])
def test_other_user_or_workspace_event_denied(platform, foreign):
    db, activity, _, _ = platform
    row = activity(identity=BOB, user="bob", workspace=OTHER if foreign else WS)
    with pytest.raises(HTTPException) as exc:
        resolve_entry_context(db, WS, "alice", context("event", row["id"]))
    assert exc.value.status_code == 404


def test_admin_can_investigate_other_user_without_broadening(platform):
    db, activity, _, _ = platform
    row = activity(identity=BOB, user="bob")
    query = resolve_entry_context(db, WS, "admin", context("event", row["id"]))
    assert query.scope == "workspace" and query.event_ids == [row["id"]]


def test_run_and_step_handoff_uses_recorded_step_ids(platform):
    db, _, _, run = platform
    rid = run()
    query = resolve_entry_context(db, WS, "alice", context("run", rid, block_id="ship"))
    result = read_platform_evidence(db, WS, "alice", query)
    assert result.runs[0].source_id == rid
    assert all(step.block_id == "ship" for step in result.runs[0].steps)
    answer, _ = answer_from_result(result.model_dump_json(), str(WS), "get_platform_evidence")
    assert "run-wide, not step-specific" in answer
    with pytest.raises(HTTPException) as exc:
        resolve_entry_context(db, WS, "alice", context("run", rid, block_id="invented"))
    assert exc.value.status_code == 404


def test_missing_run_or_revoked_permission_never_falls_back(platform):
    db, _, _, run = platform
    with pytest.raises(HTTPException):
        resolve_entry_context(db, WS, "alice", context("run", uuid4()))
    rid = run()
    db.execute(text("DELETE FROM role_permissions WHERE permission_id=5"))
    with pytest.raises(HTTPException) as exc:
        resolve_entry_context(db, WS, "alice", context("run", rid))
    assert exc.value.status_code == 403


def test_exact_scope_requires_resource():
    with pytest.raises(ValidationError):
        PlatformEvidenceQuery(exact_resource=True)
    with pytest.raises(ValidationError):
        PlatformEvidenceQuery(block_id="ship")


def test_context_dispatch_uses_registry_without_llm_selection(platform, monkeypatch):
    from app.modules.glens.routers import chat
    from app.mcp import lens_adapter
    db, activity, _, _ = platform
    row = activity()
    query = resolve_entry_context(db, WS, "alice", context("event", row["id"]))
    executor = Executor(db, str(WS), clerk_user_id="alice")
    executor.entry_query = query.model_dump(mode="json")
    dispatch = MagicMock(return_value=read_platform_evidence(db, WS, "alice", query).model_dump_json())
    monkeypatch.setattr(lens_adapter, "dispatch", dispatch)
    config = MagicMock(side_effect=AssertionError("Must not call model selection"))
    monkeypatch.setattr(chat, "_llm_config", config)
    _, answer, calls = chat._resolve_tools([], "", executor)
    assert calls[0][0] == "get_platform_evidence"
    assert dispatch.call_args.args[2].clerk_user_id == "alice"
    assert str(row["id"]) in answer
    config.assert_not_called()
