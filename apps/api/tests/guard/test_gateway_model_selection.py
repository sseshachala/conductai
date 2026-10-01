from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.modules.guard.gateway_model_selection import select_model, select_model_owned


def published(code="abcdefgh", model="gpt-test", alias="coding", provider="openai", accepts=None):
    return (SimpleNamespace(cond_code=code), SimpleNamespace(id=uuid4(), snapshot={
        "name": "test", "model_alias": alias,
        "accepts": accepts or ["openai_responses"],
        "targets": [{"id": "primary", "transport": "native_http", "provider": provider,
                     "model": model, "credential_ref": "vault://11111111-1111-4111-8111-111111111111/test-key"}],
    }))


def database(rows):
    db = MagicMock()
    query = db.query.return_value
    query.join.return_value = query
    query.filter.return_value = query
    query.all.return_value = rows
    return db, query


@pytest.mark.parametrize("selection", ["gpt-test", "coding"])
def test_explicit_selection_pins_revision_and_does_not_read_primitives(monkeypatch, selection):
    row = published()
    db, query = database([row])
    resolver = MagicMock(side_effect=AssertionError("Explicit choices must not use defaults"))
    monkeypatch.setattr("app.runtime.model_router.resolve_for_workspace", resolver)
    selected = select_model(db, "workspace-a", selection, "openai_responses")
    assert selected.model_id == "cond-abcdefgh-coding"
    assert selected.resolved.revision_id == row[1].id
    assert selected.metadata["requested_model"] == selection
    assert "workspace_id" in str(query.filter.call_args.args[0])
    assert query.filter.call_args.args[0].right.value == "workspace-a"
    join = str(query.join.call_args.args[1])
    assert "active_revision_id" in join and "profile_id" in join
    assert "schema_version" in str(query.filter.call_args.args[1])


@pytest.mark.parametrize("choice,expected_provider", [("balanced", None), ("openai/smart", "openai")])
def test_tier_uses_workspace_primitives_but_requires_published_profile(monkeypatch, choice, expected_provider):
    resolver = MagicMock(return_value=("openai", "gpt-test", "workspace map"))
    monkeypatch.setattr("app.runtime.model_router.resolve_for_workspace", resolver)
    db, _ = database([published()])
    selected = select_model(db, "workspace-a", choice, "openai_responses")
    assert selected.metadata["resolved_model"] == "gpt-test"
    assert resolver.call_args.kwargs["explicit_provider"] == expected_provider
    db, _ = database([])
    with pytest.raises(HTTPException) as error:
        select_model(db, "workspace-b", choice, "openai_responses")
    assert error.value.status_code == 404


@pytest.mark.parametrize("requested,status", [(None, 400), ({}, 400), ("", 400), ("copilot/balanced", 400), ("not-published", 404)])
def test_invalid_or_unknown_selection_fails_closed(requested, status):
    db, _ = database([published()])
    with pytest.raises(HTTPException) as error:
        select_model(db, "workspace", requested, "openai_responses")
    assert error.value.status_code == status


def test_ambiguous_profiles_require_full_id():
    db, _ = database([published(), published("ijklmnop")])
    with pytest.raises(HTTPException) as error:
        select_model(db, "workspace", "gpt-test", "openai_responses")
    assert error.value.status_code == 409


def test_incompatible_responses_does_not_convert_to_anthropic(monkeypatch):
    monkeypatch.setattr("app.runtime.model_router.resolve_for_workspace",
                        lambda *a, **kw: ("anthropic", "claude-test", "preferred provider"))
    db, _ = database([published(model="claude-test", provider="anthropic", accepts=["anthropic_messages"])])
    with pytest.raises(HTTPException) as error:
        select_model(db, "workspace", "balanced", "openai_responses")
    assert error.value.status_code == 400
    assert "openai_responses" in error.value.detail
    assert select_model(db, "workspace", "balanced", "anthropic_messages").model_id == "cond-abcdefgh-coding"


def test_mixed_model_profile_requires_explicit_profile_selection():
    row = published()
    row[1].snapshot["targets"].append({**row[1].snapshot["targets"][0], "id": "fallback", "model": "different-model"})
    db, _ = database([row])
    with pytest.raises(HTTPException) as error:
        select_model(db, "workspace", "gpt-test", "openai_responses")
    assert error.value.status_code == 404
    assert select_model(db, "workspace", "coding", "openai_responses").cond_code == "abcdefgh"


def test_working_copy_and_invalid_snapshot_cannot_authorize():
    row = published()
    row[0].working_copy = row[1].snapshot
    row[1].snapshot = {}
    db, _ = database([row])
    with pytest.raises(HTTPException) as error:
        select_model(db, "workspace", "coding", "openai_responses")
    assert error.value.status_code == 404


def test_owned_lookup_sets_authenticated_workspace_rls(monkeypatch):
    db, _ = database([published()])
    session = MagicMock()
    session.__enter__.return_value = db
    monkeypatch.setattr("app.core.database.SessionLocal", lambda: session)
    rls = MagicMock()
    monkeypatch.setattr("app.core.workspace_context.set_workspace_rls", rls)
    assert select_model_owned("workspace-a", "coding", "openai", "/v1/responses").cond_code == "abcdefgh"
    rls.assert_called_once_with(db, "workspace-a")
    session.__exit__.assert_called_once()


def test_plan_reuses_pinned_selection_and_preserves_streaming_tools(monkeypatch):
    from app.modules.guard.gateway_handler import _build_v2_plan
    db, _ = database([published()])
    selection = select_model(db, "workspace", "coding", "openai_responses")
    monkeypatch.setattr("app.modules.guard.gateway_runtime.resolve_v2",
                        MagicMock(side_effect=AssertionError("Do not reread the active pointer")))
    for name in ("build_credential_resolver", "build_vendor_credential_resolver"):
        monkeypatch.setattr("app.runtime.gateway_v2_bridge." + name, lambda *a, **kw: lambda *a: "test-only")
    body = {"model": selection.model_id, "stream": True,
            "input": [{"type": "function_call_output", "call_id": "call-1", "output": "ok"}],
            "tools": [{"type": "function", "name": "lookup", "parameters": {"type": "object"}}]}
    before = dict(body)
    plan = _build_v2_plan(db=db, workspace_id="workspace", cond_code=selection.cond_code,
                          provider="openai", upstream_path="/v1/responses", body=body,
                          resolved=selection.resolved)
    assert plan.resolved is selection.resolved
    assert plan.operation == "openai_responses"
    assert body == before
