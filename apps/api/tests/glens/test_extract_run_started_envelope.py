"""#1480 PR 13 — the SSE 'done' event must surface a run_started envelope
so the frontend renders <RunBubble> instead of the LLM's prose.

_extract_run_started_envelope scans final_msgs for the first tool result
whose JSON body carries executed=True + result.run_id — that's the shape
`confirm_pending_action` returns after natural-language "yes"."""
from __future__ import annotations

import json

from app.modules.glens.routers.chat import _extract_run_started_envelope


CONFIRMED = {
    "executed": True,
    "cached": False,
    "action_id": "act_abc",
    "tool_name": "run_workflow",
    "status": "approved",
    "result": {
        "run_id": "31def331-49d1-49c0-90eb-a00b88c47ea0",
        "workflow_name": "self_driving_network_approval_demo",
        "status": "pending",
    },
}


def test_matches_openai_shape_tool_role() -> None:
    msgs = [
        {"role": "user", "content": "run it"},
        {"role": "assistant", "content": "calling tool"},
        {"role": "tool", "content": json.dumps(CONFIRMED)},
    ]
    envelope = _extract_run_started_envelope(msgs)
    assert envelope == {
        "run_id": "31def331-49d1-49c0-90eb-a00b88c47ea0",
        "workflow_name": "self_driving_network_approval_demo",
        "status": "pending",
    }


def test_matches_anthropic_shape_tool_result_in_user_message() -> None:
    msgs = [
        {"role": "user", "content": "run it"},
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "content": json.dumps(CONFIRMED)},
            ],
        },
    ]
    envelope = _extract_run_started_envelope(msgs)
    assert envelope is not None
    assert envelope["run_id"] == "31def331-49d1-49c0-90eb-a00b88c47ea0"


def test_returns_none_when_no_tool_result() -> None:
    msgs = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hi"}]
    assert _extract_run_started_envelope(msgs) is None


def test_returns_none_when_executed_false() -> None:
    """cancel_pending_action returns executed=False; must not fire RunBubble."""
    payload = {"cancelled": True, "action_id": "x", "tool_name": "run_workflow"}
    msgs = [{"role": "tool", "content": json.dumps(payload)}]
    assert _extract_run_started_envelope(msgs) is None


def test_returns_none_when_no_run_id_in_result() -> None:
    """Non-run tools (e.g. rules mutations) return executed=True but no
    run_id — RunBubble must not fire for those."""
    payload = {
        "executed": True,
        "action_id": "x",
        "tool_name": "apply_policy",
        "status": "approved",
        "result": {"policy_id": "pol_123"},
    }
    msgs = [{"role": "tool", "content": json.dumps(payload)}]
    assert _extract_run_started_envelope(msgs) is None


def test_falls_back_to_tool_name_when_workflow_name_missing() -> None:
    payload = {
        "executed": True,
        "action_id": "x",
        "tool_name": "run_workflow",
        "status": "approved",
        "result": {"run_id": "r1"},
    }
    msgs = [{"role": "tool", "content": json.dumps(payload)}]
    envelope = _extract_run_started_envelope(msgs)
    assert envelope == {
        "run_id": "r1",
        "workflow_name": "run_workflow",
        "status": "pending",
    }


def test_skips_unparseable_content() -> None:
    msgs = [
        {"role": "tool", "content": "not-json"},
        {"role": "tool", "content": json.dumps(CONFIRMED)},
    ]
    envelope = _extract_run_started_envelope(msgs)
    assert envelope is not None
    assert envelope["run_id"] == "31def331-49d1-49c0-90eb-a00b88c47ea0"
