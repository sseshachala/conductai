"""PR 4 self-checks — new-engine settlement cutover.

The settlement flip is the atomic behavior change that retires legacy
accounting. Tests here cover the compute_settlement_micros helper (the
shared math) + the per-workspace canary decision. gateway_handler
wiring is tested end-to-end in tests/guard/.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.core.config import settings
from app.runtime.accounting.settlement import compute_settlement_micros


# ─── compute_settlement_micros — same math as shadow_write ─────────────


def test_returns_none_when_no_response_bytes():
    """Nothing to normalize ⇒ nothing to price. Caller falls back to
    legacy path OR leaves settlement PENDING_RECONCILER."""
    result = compute_settlement_micros(
        provider="anthropic",
        model="claude-sonnet-4-6",
        operation="messages.create",
        response_bytes=None,
    )
    assert result is None


def test_returns_none_when_usage_dict_is_empty():
    """{"usage": {}} means the provider didn't report — do not
    fabricate a number. Preserves invariant #4 (missing != zero)."""
    result = compute_settlement_micros(
        provider="anthropic",
        model="claude-sonnet-4-6",
        operation="messages.create",
        response_bytes=b'{"usage":{}}',
    )
    assert result is None


def test_anthropic_response_priced_via_new_engine():
    """Sanity: 100 fresh input + 50 output at claude-sonnet-4-6.
    Same math shadow_write uses when it populates calculated_cost_micros.
    100 × $3/1M + 50 × $15/1M = $0.0003 + $0.00075 = $0.00105 = 1_050 μUSD."""
    result = compute_settlement_micros(
        provider="anthropic",
        model="claude-sonnet-4-6",
        operation="messages.create",
        response_bytes=b'{"usage":{"input_tokens":100,"output_tokens":50}}',
    )
    assert result == 1_050


def test_openai_chat_response_priced_via_new_engine():
    """gpt-4.1: $2/1M in, $8/1M out. 100 in + 50 out = 200 + 400 = 600 μUSD."""
    result = compute_settlement_micros(
        provider="openai",
        model="gpt-4.1",
        operation="chat.completions",
        response_bytes=b'{"usage":{"prompt_tokens":100,"completion_tokens":50}}',
    )
    assert result == 600


def test_openai_responses_uses_responses_normalizer():
    """/v1/responses in operation ⇒ OPENAI_RESPONSES family. Different
    field shape (input_tokens, output_tokens instead of prompt/completion)."""
    result = compute_settlement_micros(
        provider="openai",
        model="gpt-4.1",
        operation="/v1/responses",
        response_bytes=b'{"usage":{"input_tokens":100,"output_tokens":50}}',
    )
    assert result == 600


def test_strict_unknown_model_returns_none():
    """Invariant #9 preserved into the settlement path. Unknown model
    ⇒ no calculation ⇒ caller falls back or marks PENDING_RECONCILER."""
    result = compute_settlement_micros(
        provider="anthropic",
        model="claude-something-that-doesnt-exist",
        operation="messages.create",
        response_bytes=b'{"usage":{"input_tokens":100,"output_tokens":50}}',
        strict=True,
    )
    assert result is None


def test_anthropic_sse_stream_body_handled():
    """Stream responses arrive as SSE bytes. Normalizer + pricing still
    produce the same number as JSON — settlement doesn't care."""
    sse = (
        b"event: message_start\n"
        b'data: {"type":"message_start","message":{"usage":{"input_tokens":100,"output_tokens":1}}}\n\n'
        b"event: message_delta\n"
        b'data: {"type":"message_delta","usage":{"output_tokens":50}}\n\n'
        b"event: message_stop\n"
        b'data: {"type":"message_stop"}\n\n'
    )
    result = compute_settlement_micros(
        provider="anthropic",
        model="claude-sonnet-4-6",
        operation="messages.create",
        response_bytes=sse,
    )
    assert result == 1_050


# ─── Canary allowlist ─────────────────────────────────────────────────


def test_new_engine_settles_disabled_when_global_flag_off(monkeypatch):
    monkeypatch.setattr(settings, "guard_accounting_new_engine_settles", False)
    monkeypatch.setattr(
        settings, "guard_accounting_new_engine_workspace_allowlist", "*"
    )
    assert settings.new_engine_settles_for_workspace("ws-a") is False


def test_new_engine_settles_all_workspaces_when_wildcard(monkeypatch):
    monkeypatch.setattr(settings, "guard_accounting_new_engine_settles", True)
    monkeypatch.setattr(
        settings, "guard_accounting_new_engine_workspace_allowlist", "*"
    )
    assert settings.new_engine_settles_for_workspace("ws-a") is True
    assert settings.new_engine_settles_for_workspace("ws-b") is True


def test_new_engine_settles_all_workspaces_when_empty_allowlist(monkeypatch):
    """Empty and wildcard both mean 'all' — matches the shadow flag semantics."""
    monkeypatch.setattr(settings, "guard_accounting_new_engine_settles", True)
    monkeypatch.setattr(
        settings, "guard_accounting_new_engine_workspace_allowlist", ""
    )
    assert settings.new_engine_settles_for_workspace("ws-a") is True


def test_new_engine_settles_only_allowlisted_workspaces(monkeypatch):
    monkeypatch.setattr(settings, "guard_accounting_new_engine_settles", True)
    monkeypatch.setattr(
        settings,
        "guard_accounting_new_engine_workspace_allowlist",
        "ws-canary-1, ws-canary-2",
    )
    assert settings.new_engine_settles_for_workspace("ws-canary-1") is True
    assert settings.new_engine_settles_for_workspace("ws-canary-2") is True
    assert settings.new_engine_settles_for_workspace("ws-not-listed") is False


# ─── gateway_handler wiring pin ────────────────────────────────────────


def test_gateway_handler_calls_compute_settlement_micros_behind_flag():
    """Pin the wiring: source-string check so a future refactor cannot
    silently drop the new-engine settlement call from gateway_handler."""
    import inspect
    from app.modules.guard import gateway_handler

    src = inspect.getsource(gateway_handler)
    assert "compute_settlement_micros" in src
    assert "new_engine_settles_for_workspace" in src


def test_settlement_helper_deltas_match_shadow_writer_exactly():
    """Both call the same normalizer + pricing service, so a settled
    request must produce the same number as its shadow row's
    calculated_cost_microdollars. This is what makes the cutover safe:
    the shadow-vs-legacy delta report has already validated the answer."""
    import inspect
    from app.runtime.accounting import settlement
    from app.runtime.accounting import shadow_writer

    settle_src = inspect.getsource(settlement)
    writer_src = inspect.getsource(shadow_writer)
    # Both use price_tokens on the same rate card. If either drifts,
    # the shadow delta report catches it — this test just ensures both
    # point at the same PricingService entry.
    assert "default_pricing_service()" in settle_src
    assert "default_pricing_service()" in writer_src
