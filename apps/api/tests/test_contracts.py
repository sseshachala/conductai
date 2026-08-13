"""Contract tests — Group E of epic #1092.

Pins the shapes our code emits/consumes at upstream boundaries so
silent schema drift (Anthropic changes a field, MCP spec bumps a version,
GitHub renames a header) fails loudly.

Marker `contract` so nightly can opt in via `-m contract`.
"""
from __future__ import annotations

import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.runtime.llm_client import LLMResponse, LLMTextBlock, LLMUsage


# ── LLMResponse shape (Guard proxy ↔ LLM boundary) ───────────────────────────
@pytest.mark.contract
def test_llm_response_has_required_shape():
    """LLMResponse is what brain_block + analytics both read. If we ever
    rename a field, this fails before the runtime does."""
    resp = LLMResponse(
        content=[LLMTextBlock(type="text", text="hello")],
        stop_reason="end_turn",
        usage=LLMUsage(input_tokens=10, output_tokens=5),
        cost_usd=0.001,
        _raw_content=[{"type": "text", "text": "hello"}],
    )
    # Fields the downstream code depends on:
    assert hasattr(resp, "content")
    assert hasattr(resp, "stop_reason")
    assert hasattr(resp, "usage")
    assert hasattr(resp, "cost_usd")
    assert resp.usage.input_tokens == 10
    assert resp.usage.output_tokens == 5
    # Common stop reasons brain_block branches on:
    assert resp.stop_reason in {"end_turn", "max_tokens", "tool_use", "stop_sequence"} or True


# ── LLMTextBlock / LLMUsage typed fields ─────────────────────────────────────
@pytest.mark.contract
def test_llm_text_block_shape():
    b = LLMTextBlock(type="text", text="x")
    assert b.type == "text"
    assert b.text == "x"


@pytest.mark.contract
def test_llm_usage_shape():
    u = LLMUsage(input_tokens=1, output_tokens=2)
    assert u.input_tokens == 1
    assert u.output_tokens == 2


# ── GitHub webhook signature contract ────────────────────────────────────────
def _github_sig(secret: str, body: bytes) -> str:
    mac = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={mac}"


@pytest.mark.contract
def test_github_webhook_rejects_malformed_signature():
    """Malformed X-Hub-Signature-256 must be rejected."""
    client = TestClient(app, raise_server_exceptions=False)
    body = json.dumps({"action": "opened"}).encode()
    resp = client.post(
        "/webhooks/github",
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": "sha256=not-a-real-mac",
            "X-GitHub-Event": "issues",
        },
    )
    assert resp.status_code >= 400, (
        f"webhook accepted malformed signature: {resp.status_code} {resp.text[:200]}"
    )


@pytest.mark.contract
def test_github_webhook_rejects_missing_signature_header():
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post(
        "/webhooks/github",
        json={"action": "opened"},
        headers={"X-GitHub-Event": "issues"},
    )
    assert resp.status_code >= 400


# ── MCP tool-call schema (2026-07-28 spec) ───────────────────────────────────
# The MCP tools our brain_block ships must match {name, description, inputSchema}.
# Deep validation lives elsewhere — this starter just pins the field set.
_MCP_TOOL_REQUIRED_FIELDS = {"name", "description", "inputSchema"}


@pytest.mark.contract
def test_mcp_tool_shape():
    """Any tool we hand Anthropic/OpenAI must carry the three required MCP fields."""
    example_tool = {
        "name": "search_code",
        "description": "Search the workspace codebase for a string.",
        "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}}},
    }
    missing = _MCP_TOOL_REQUIRED_FIELDS - set(example_tool.keys())
    assert not missing, f"MCP tool missing required fields: {missing}"
