"""#1254 — streaming sibling of guarded_llm_call.

Unit tests for `guarded_llm_stream`. Mocks httpx.stream + evaluate_composed
+ record so the flow can be exercised without a live provider or DB.
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


class _FakeResponse:
    """Minimal fake for httpx.stream context manager response."""
    def __init__(self, status_code: int, lines: list[str], body: str = "") -> None:
        self.status_code = status_code
        self._lines = lines
        self._body = body

    def read(self) -> bytes:
        return self._body.encode()

    def iter_lines(self):
        return iter(self._lines)


class _FakeStreamCtx:
    def __init__(self, response: _FakeResponse) -> None:
        self._response = response

    def __enter__(self):
        return self._response

    def __exit__(self, *args):
        return False


def _fake_decision(action_name: str, rule_id: str | None = None):
    from app.guard.policy_types import PolicyAction
    return SimpleNamespace(
        action=PolicyAction[action_name],
        rule_id=rule_id,
        reason=None,
        matched_rules=[],
        defense_score=0,
        source="test",
    )


def _sse_lines(tokens: list[str]) -> list[str]:
    """Build a list of SSE lines that yield the given tokens."""
    lines = []
    for tok in tokens:
        lines.append(f'data: {json.dumps({"choices":[{"delta":{"content":tok}}]})}')
        lines.append("")
    lines.append("data: [DONE]")
    return lines


def test_allowed_stream_drives_callback_and_returns_full_text():
    from app.guard.gateway import guarded_llm_stream

    tokens_seen: list[str] = []
    fake_stream = _FakeStreamCtx(_FakeResponse(200, _sse_lines(["Hel", "lo", " ", "wo", "rld"])))

    with patch("httpx.stream", return_value=fake_stream), \
         patch("app.guard.policy.evaluate_composed", return_value=_fake_decision("ALLOW")), \
         patch("app.guard.audit.record") as rec:
        text = guarded_llm_stream(
            workspace_id="00000000-0000-0000-0000-000000000001",
            provider="openai", model="gpt-4o-mini",
            upstream_url="https://api.openai.com", api_key="sk-test",
            messages=[{"role": "user", "content": "hi"}], system="s",
            max_tokens=100,
            on_token=lambda t: tokens_seen.append(t),
        )

    assert text == "Hello world"
    assert tokens_seen == ["Hel", "lo", " ", "wo", "rld"]
    rec.assert_called_once()
    args, kwargs = rec.call_args
    assert args[2] == "lens"           # ai_tool
    assert args[1] == "system:lens"    # clerk_user_id (attribution)
    assert args[5] == "allowed"        # decision
    assert kwargs["response_bytes"]    # response_bytes captured (non-empty)


def test_blocked_stream_raises_and_records_blocked_row_without_upstream_call():
    from app.guard.gateway import guarded_llm_stream

    with patch("httpx.stream") as stream, \
         patch("app.guard.policy.evaluate_composed",
               return_value=_fake_decision("BLOCK", rule_id="R-lens")), \
         patch("app.guard.audit.record") as rec:
        with pytest.raises(Exception, match="Guard blocked lens call"):
            guarded_llm_stream(
                workspace_id="00000000-0000-0000-0000-000000000001",
                provider="openai", model="gpt-4o-mini",
                upstream_url="https://api.openai.com", api_key="sk-test",
                messages=[{"role": "user", "content": "hi"}], system="s",
                max_tokens=100,
                on_token=lambda t: None,
            )

    stream.assert_not_called()          # never hit provider
    rec.assert_called_once()
    args, _ = rec.call_args
    assert args[5] == "blocked"
    assert args[6] == "R-lens"


def test_upstream_5xx_raises_after_read():
    from app.guard.gateway import guarded_llm_stream

    fake_stream = _FakeStreamCtx(_FakeResponse(500, [], body="internal server error"))

    with patch("httpx.stream", return_value=fake_stream), \
         patch("app.guard.policy.evaluate_composed", return_value=_fake_decision("ALLOW")), \
         patch("app.guard.audit.record"):
        with pytest.raises(Exception, match="Upstream stream 500"):
            guarded_llm_stream(
                workspace_id="00000000-0000-0000-0000-000000000001",
                provider="openai", model="gpt-4o-mini",
                upstream_url="https://api.openai.com", api_key="sk-test",
                messages=[{"role": "user", "content": "hi"}], system="s",
                max_tokens=100,
                on_token=lambda t: None,
            )


def test_warn_decision_records_warned_but_still_streams():
    from app.guard.gateway import guarded_llm_stream

    tokens_seen: list[str] = []
    fake_stream = _FakeStreamCtx(_FakeResponse(200, _sse_lines(["ok"])))

    with patch("httpx.stream", return_value=fake_stream), \
         patch("app.guard.policy.evaluate_composed",
               return_value=_fake_decision("WARN", rule_id="R-warn")), \
         patch("app.guard.audit.record") as rec:
        text = guarded_llm_stream(
            workspace_id="00000000-0000-0000-0000-000000000001",
            provider="openai", model="gpt-4o-mini",
            upstream_url="https://api.openai.com", api_key="sk-test",
            messages=[{"role": "user", "content": "hi"}], system="s",
            max_tokens=100,
            on_token=lambda t: tokens_seen.append(t),
        )

    assert text == "ok"
    args, _ = rec.call_args
    assert args[5] == "warned"
    assert args[6] == "R-warn"
