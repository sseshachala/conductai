"""
Integration tests for brain_block config-parity — one test per persisted field the
runtime MUST honor. Prevents the "silent-drop" class of bug where the loader/UI
stores a field but the runtime never reads it.

See project_session_july27_runtime_bugs.md for the history: `data["prompt"]` was
half-shipped for 7 weeks (loader stored, runtime ignored) and `mcp_server_ids`
UI toggle was cosmetic. Each field below has ONE assertion that fails loudly if
the runtime ever stops reading what the UI/loader stores.

Rule: any time a new persisted field is added to a brain-block config panel,
add one test here. Field with no test = field the runtime is free to drop.
"""
from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

from app.runtime.llm_client import LLMResponse, LLMTextBlock, LLMUsage
from app.runtime.blocks.brain_block import _execute_brain, _load_workspace_mcp_tools


RUN_ID = "run-config-parity"
BLOCK_ID = "brain-1"


def _fake_response(text: str = "ok") -> LLMResponse:
    return LLMResponse(
        content=[LLMTextBlock(type="text", text=text)],
        stop_reason="end_turn",
        usage=LLMUsage(input_tokens=1, output_tokens=1),
        cost_usd=0.0,
        _raw_content=[{"type": "text", "text": text}],
    )


def _run_with_capture(block: dict, state: dict) -> str:
    """Execute a single-turn brain block and return the user_message sent to the LLM."""
    captured: list = []
    mock_llm = MagicMock()

    def _capture_create(**kwargs):
        captured.append(kwargs.get("messages"))
        return _fake_response()

    mock_llm.create.side_effect = _capture_create

    redis_mock = MagicMock()
    redis_mock.get.return_value = None

    artifacts = {BLOCK_ID: {"system_prompt": block["data"].get("description", ""), "is_agentic": False}}

    with (
        patch("app.runtime.blocks.brain_block.AnthropicClient", return_value=mock_llm),
        patch("app.runtime.blocks.brain_block._get_redis", return_value=redis_mock),
    ):
        _execute_brain(
            block=block, state=state, compiled_artifacts=artifacts,
            run_id=RUN_ID, block_id=BLOCK_ID,
        )

    assert captured, "LLM was never called — brain_block returned before create()"
    return captured[0][0]["content"]


# ── data["prompt"] — user-message template ────────────────────────────────────

def test_prompt_field_is_used_as_user_message():
    """If block.data['prompt'] is set, its rendered text IS the user_message."""
    block = {
        "id": BLOCK_ID, "type": "brain",
        "data": {
            "isAgentic": False,
            "description": "sys",
            "prompt": "Repo is {{plan.repo}}, ticket {{plan.ticket}}. Act now.",
        },
    }
    msg = _run_with_capture(block, {"plan": {"repo": "acme/widgets", "ticket": 42}})
    assert "Repo is acme/widgets" in msg
    assert "ticket 42" in msg
    assert "Workflow context so far" not in msg  # fallback must NOT trigger


def test_prompt_field_absent_falls_back_to_context_dump():
    """No prompt: field → runtime keeps historical fallback behaviour."""
    block = {
        "id": BLOCK_ID, "type": "brain",
        "data": {"isAgentic": False, "description": "sys"},
    }
    msg = _run_with_capture(block, {"plan": {"repo": "acme/widgets"}})
    assert "Workflow context so far" in msg
    assert "Execute your task" in msg


def test_prompt_field_empty_string_falls_back():
    """Empty prompt: '' is treated the same as absent."""
    block = {
        "id": BLOCK_ID, "type": "brain",
        "data": {"isAgentic": False, "description": "sys", "prompt": "   "},
    }
    msg = _run_with_capture(block, {"plan": {"repo": "x"}})
    assert "Workflow context so far" in msg


# ── Safety: private state keys, PII redaction, size cap ──────────────────────

def test_prompt_field_hides_private_state_keys():
    """Templates cannot reach `__`-prefixed state keys (tokens, internal URLs)."""
    block = {
        "id": BLOCK_ID, "type": "brain",
        "data": {
            "isAgentic": False, "description": "sys",
            "prompt": "token={{__conduct_run_token__}}, url={{__cred_api_url__}}",
        },
    }
    msg = _run_with_capture(block, {
        "__conduct_run_token__": "cond_run_supersecret",
        "__cred_api_url__": "https://api.internal/",
    })
    assert "cond_run_supersecret" not in msg
    assert "api.internal" not in msg
    # Unresolved refs stay as-is — visible signal to the author that they used
    # a private key rather than a silent leak
    assert "{{__conduct_run_token__}}" in msg


def test_prompt_field_pii_redacted_when_guard_enabled():
    """When Guard is on, PII in the rendered prompt is redacted before LLM call."""
    block = {
        "id": BLOCK_ID, "type": "brain",
        "data": {
            "isAgentic": False, "description": "sys",
            "prompt": "Reviewer: {{lead.email}}",
        },
    }
    msg = _run_with_capture(block, {
        "__guard_enabled": True,
        "lead": {"email": "jane.doe@example.com"},
    })
    assert "jane.doe@example.com" not in msg


def test_prompt_field_truncates_runaway_blob():
    """Rendered prompt above the cap is truncated with a marker — no unbounded tokens."""
    huge = "X" * 40000
    block = {
        "id": BLOCK_ID, "type": "brain",
        "data": {
            "isAgentic": False, "description": "sys",
            "prompt": "Data: {{ctx.blob}}",
        },
    }
    msg = _run_with_capture(block, {"ctx": {"blob": huge}})
    assert "[truncated at 32000 chars]" in msg
    # Everything before the credentials suffix should be within the cap window
    assert len(msg) < 40000


# ── data["mcp_server_ids"] — MCP server filter ────────────────────────────────

def _fake_server(sid: str, name: str) -> MagicMock:
    s = MagicMock()
    s.id = sid
    s.name = name
    s.encrypted_auth = None
    s.transport = "http"
    s.url = f"https://mcp.example/{name}"
    return s


def _fake_db_with_servers(servers: list[MagicMock]) -> MagicMock:
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = servers
    db.query.return_value.filter.return_value.filter.return_value.all.return_value = servers
    return db


def test_mcp_selection_none_returns_all_servers():
    servers = [_fake_server("s1", "gh"), _fake_server("s2", "slack")]
    db = _fake_db_with_servers(servers)
    with patch(
        "app.runtime.integrations.mcp_client.list_tools",
        return_value=([{"name": "t1", "description": "d"}], None),
    ):
        tools = _load_workspace_mcp_tools("ws-1", None, db, selected_ids=None)
    # Two servers × one tool each = 2 tools total
    assert len(tools) == 2
    assert {"gh::t1", "slack::t1"} == {t["name"] for t in tools}


def test_mcp_selection_all_sentinel_returns_all_servers():
    servers = [_fake_server("s1", "gh"), _fake_server("s2", "slack")]
    db = _fake_db_with_servers(servers)
    with patch(
        "app.runtime.integrations.mcp_client.list_tools",
        return_value=([{"name": "t1", "description": "d"}], None),
    ):
        tools = _load_workspace_mcp_tools("ws-1", None, db, selected_ids=["all"])
    assert {"gh::t1", "slack::t1"} == {t["name"] for t in tools}


def test_mcp_selection_empty_list_returns_all_servers():
    servers = [_fake_server("s1", "gh"), _fake_server("s2", "slack")]
    db = _fake_db_with_servers(servers)
    with patch(
        "app.runtime.integrations.mcp_client.list_tools",
        return_value=([{"name": "t1", "description": "d"}], None),
    ):
        tools = _load_workspace_mcp_tools("ws-1", None, db, selected_ids=[])
    assert {"gh::t1", "slack::t1"} == {t["name"] for t in tools}


def test_mcp_selection_specific_ids_filters_to_subset():
    servers = [
        _fake_server("s1", "gh"),
        _fake_server("s2", "slack"),
        _fake_server("s3", "linear"),
    ]
    db = _fake_db_with_servers(servers)
    with patch(
        "app.runtime.integrations.mcp_client.list_tools",
        return_value=([{"name": "t1", "description": "d"}], None),
    ):
        tools = _load_workspace_mcp_tools("ws-1", None, db, selected_ids=["s1", "s3"])
    # slack (s2) must be filtered out
    assert {"gh::t1", "linear::t1"} == {t["name"] for t in tools}
    assert not any(t["name"].startswith("slack::") for t in tools)
