"""#1475 — the SSE 'done' event must surface a confirm envelope from tool
results so the frontend renders ActionConfirmBubble instead of prose.

_extract_confirm_envelope scans final_msgs (LLM tool-turn list) for the
first tool result whose JSON body carries confirm_required=True +
approval_request_id. Non-tool roles are ignored; unparseable content is
skipped; the first match wins."""
from __future__ import annotations

import json

from app.modules.glens.routers.chat import _extract_confirm_envelope


ENVELOPE = {
    "confirm_required": True,
    "approval_request_id": "req_abc",
    "tool_name": "run_workflow",
    "summary": "Run self_driving_network_approval_demo?",
    "warnings": [],
    "expires_at": "2026-08-30T02:55:56+00:00",
    "surface": "lens",
}


def test_returns_first_matching_tool_result():
    msgs = [
        {"role": "user", "content": "run it"},
        {"role": "assistant", "content": "ok"},
        {"role": "tool", "content": json.dumps(ENVELOPE)},
    ]
    assert _extract_confirm_envelope(msgs) == ENVELOPE


def test_none_when_no_tool_results():
    assert _extract_confirm_envelope([{"role": "user", "content": "hi"}]) is None


def test_none_when_tool_result_lacks_confirm():
    msgs = [{"role": "tool", "content": json.dumps({"count": 5})}]
    assert _extract_confirm_envelope(msgs) is None


def test_skips_unparseable_tool_content_then_matches():
    msgs = [
        {"role": "tool", "content": "not json"},
        {"role": "tool", "content": json.dumps(ENVELOPE)},
    ]
    assert _extract_confirm_envelope(msgs) == ENVELOPE


def test_requires_both_flag_and_id():
    msgs = [{"role": "tool", "content": json.dumps({"confirm_required": True})}]
    assert _extract_confirm_envelope(msgs) is None


def test_anthropic_tool_result_shape():
    """Anthropic batches tool results as {role: user, content: [{type: tool_result, content: ...}]}."""
    msgs = [
        {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "t1", "content": json.dumps(ENVELOPE)},
        ]},
    ]
    assert _extract_confirm_envelope(msgs) == ENVELOPE
