"""PR 4 self-checks — new-engine settlement cutover (Option A).

The settlement flip is the atomic behavior change that retires legacy
accounting. Tests cover:

- ``compute_settlement_micros`` (single-attempt math + completeness gates)
- ``settle_micros_for_attempts`` (per-attempt aggregation + fail-to-pending)
- gateway_handler + wrapper source-pins so refactors cannot silently drop
  the new-engine call sites
- The four P1 scenarios that gated Option A: recovery-vs-live drift,
  fallback-ignores-attempts, partial-usage-becomes-final, streaming
  responses uses chat normalizer
"""

from __future__ import annotations

import base64

from app.runtime.accounting.settlement import (
    compute_settlement_micros,
    settle_micros_for_attempts,
)


# ─── compute_settlement_micros — same math as shadow_write ─────────────


def test_returns_none_when_no_response_bytes():
    """Nothing to normalize ⇒ nothing to price. Caller records the
    settlement as PENDING_RECONCILER."""
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
    ⇒ no calculation ⇒ caller marks PENDING_RECONCILER."""
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


# ─── gateway_handler wiring pin ────────────────────────────────────────


def test_gateway_handler_calls_settle_micros_for_attempts_unconditionally():
    """Pin the wiring: source-string check so a future refactor cannot
    silently drop the new-engine settlement call from gateway_handler.

    Cutover invariant (Option A): no flag, no
    ``new_engine_settles_for_workspace`` branch. The handler always
    routes settlement through the new engine, and it sums per-attempt
    (not winner-only) so preceding failed attempts are counted.
    """
    import inspect
    from app.modules.guard import gateway_handler

    src = inspect.getsource(gateway_handler)
    # P1-2: per-attempt aggregation, not winner-only.
    assert "settle_micros_for_attempts" in src
    # No flag machinery — this is the whole point of Option A.
    assert "new_engine_settles_for_workspace" not in src
    assert "guard_accounting_new_engine_settles" not in src


def test_settlement_helper_and_writer_use_same_pricing_service():
    """Both call the same normalizer + pricing service, so a settled
    request must produce the same number as its receipt's
    calculated_cost_microdollars. This is what makes the cutover safe:
    settlement and audit both read from one source of truth."""
    import inspect
    from app.runtime.accounting import settlement, shadow_writer

    settle_src = inspect.getsource(settlement)
    writer_src = inspect.getsource(shadow_writer)
    assert "default_pricing_service()" in settle_src
    assert "default_pricing_service()" in writer_src


# ─── P1-3 — partial usage + incomplete pricing become PENDING, not
# a final charge ──────────────────────────────────────────────────────


def test_partial_stream_settles_pending_not_lower_bound():
    """Interrupted Anthropic stream (only message_start, no message_stop)
    → PARTIAL usage → return None (PENDING_RECONCILER). The buggy
    pre-fix behavior charged for the partial output."""
    partial_sse = (
        b"event: message_start\n"
        b'data: {"type":"message_start","message":{"usage":{"input_tokens":100,"output_tokens":1}}}\n\n'
        b"event: content_block_delta\n"
        b'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"hi"}}\n\n'
        # NO message_delta with final usage, NO message_stop — stream cut.
    )
    result = compute_settlement_micros(
        provider="anthropic",
        model="claude-sonnet-4-6",
        operation="messages.create",
        response_bytes=partial_sse,
    )
    assert result is None, (
        "PARTIAL usage must return None so settlement waits for the "
        "reconciler; charging on a lower bound is unsafe."
    )


def test_unknown_cache_write_tier_settles_pending_not_lower_bound():
    """Anthropic response with ephemeral_30d cache-write tier that isn't
    in the rate card → INCOMPLETE pricing (unknown tier dropped from
    total) → return None. The buggy pre-fix behavior settled the
    remaining priced tokens as a definite charge."""
    # 100 input + 50 output — those price to 1_050 μUSD. But the
    # 200 cache-write tokens live in an unknown tier that strict pricing
    # cannot honor, so the whole result must be PENDING, not 1_050.
    payload = (
        b'{"usage":{"input_tokens":100,"output_tokens":50,'
        b'"cache_creation_input_tokens":200,'
        b'"cache_creation":{"ephemeral_30d_input_tokens":200}}}'
    )
    result = compute_settlement_micros(
        provider="anthropic",
        model="claude-sonnet-4-6",
        operation="messages.create",
        response_bytes=payload,
    )
    assert result is None, (
        "INCOMPLETE pricing (unknown cache tier) must return None; "
        "silently dropping unpriced tokens understates spend."
    )


# ─── P1-2 — settlement sums across every attempt, not winner-only ──────


def test_settle_micros_for_attempts_sums_per_attempt():
    """A failed attempt on Anthropic (rate-limited after 100/50 tokens)
    followed by a winning attempt on OpenAI (200/100 tokens) → the
    settlement charge is the SUM, not just the winner's."""
    failed_anthropic_bytes = b'{"usage":{"input_tokens":100,"output_tokens":50}}'
    winner_openai_bytes = b'{"usage":{"prompt_tokens":200,"completion_tokens":100}}'
    attempts_meta = [
        {
            "provider_or_integration": "anthropic",
            "model": "claude-sonnet-4-6",
            "succeeded": False,
            "response_bytes_b64": base64.b64encode(failed_anthropic_bytes).decode(),
        },
        {
            "provider_or_integration": "openai",
            "model": "gpt-4.1",
            "succeeded": True,
        },
    ]
    total = settle_micros_for_attempts(
        attempts_meta=attempts_meta,
        request_provider="openai",  # request-level model — the winner
        request_model="gpt-4.1",
        operation="chat.completions",
        winner_response_bytes=winner_openai_bytes,
    )
    # Anthropic 100 in + 50 out at sonnet-4-6 rates: 100*3 + 50*15 = 1_050
    # OpenAI 200 in + 100 out at gpt-4.1: 200*2 + 100*8 = 1_200
    # Total: 2_250. Winner-only would have missed the 1_050.
    assert total == 2_250


def test_settle_micros_for_attempts_uses_per_attempt_pricing_identity():
    """Failed attempt was cheap model, winner was expensive — settlement
    must price each with its OWN provider/model."""
    cheap_failed = b'{"usage":{"input_tokens":1000,"output_tokens":0}}'
    expensive_winner = b'{"usage":{"input_tokens":100,"output_tokens":50}}'
    attempts_meta = [
        {
            "provider_or_integration": "anthropic",
            "model": "claude-haiku-4-5-20251001",  # $1/1M input
            "succeeded": False,
            "response_bytes_b64": base64.b64encode(cheap_failed).decode(),
        },
        {
            "provider_or_integration": "anthropic",
            "model": "claude-opus-4-7",  # $15/1M input, $75/1M output
            "succeeded": True,
        },
    ]
    total = settle_micros_for_attempts(
        attempts_meta=attempts_meta,
        request_provider="anthropic",
        request_model="claude-opus-4-7",
        operation="messages.create",
        winner_response_bytes=expensive_winner,
    )
    # haiku: 1000 * 1 = 1_000. Opus: 100*15 + 50*75 = 1_500 + 3_750 = 5_250.
    # If we (wrongly) priced everything at opus rates it would be
    # 1000*15 + 5_250 = 20_250 — nearly 4× overcharge.
    assert total == 6_250


def test_settle_micros_for_attempts_returns_none_when_failed_attempt_missing_bytes():
    """Failed attempt with no captured response bytes — provider may
    have billed anyway. Force PENDING_RECONCILER, do not settle."""
    winner_bytes = b'{"usage":{"input_tokens":100,"output_tokens":50}}'
    attempts_meta = [
        {
            "provider_or_integration": "anthropic",
            "model": "claude-sonnet-4-6",
            "succeeded": False,
            # No response_bytes_b64 — coordinator saw the connection error
            # but didn't capture the upstream response body.
        },
        {
            "provider_or_integration": "anthropic",
            "model": "claude-sonnet-4-6",
            "succeeded": True,
        },
    ]
    result = settle_micros_for_attempts(
        attempts_meta=attempts_meta,
        request_provider="anthropic",
        request_model="claude-sonnet-4-6",
        operation="messages.create",
        winner_response_bytes=winner_bytes,
    )
    assert result is None


def test_settle_micros_for_attempts_returns_none_if_any_attempt_is_partial():
    """One PARTIAL attempt (interrupted stream captured on failure)
    poisons the whole aggregate — cannot definitively charge."""
    partial_failed = (
        b"event: message_start\n"
        b'data: {"type":"message_start","message":{"usage":{"input_tokens":100,"output_tokens":1}}}\n\n'
    )
    winner = b'{"usage":{"input_tokens":50,"output_tokens":25}}'
    attempts_meta = [
        {
            "provider_or_integration": "anthropic",
            "model": "claude-sonnet-4-6",
            "succeeded": False,
            "response_bytes_b64": base64.b64encode(partial_failed).decode(),
        },
        {
            "provider_or_integration": "anthropic",
            "model": "claude-sonnet-4-6",
            "succeeded": True,
        },
    ]
    result = settle_micros_for_attempts(
        attempts_meta=attempts_meta,
        request_provider="anthropic",
        request_model="claude-sonnet-4-6",
        operation="messages.create",
        winner_response_bytes=winner,
    )
    assert result is None


def test_settle_micros_for_attempts_empty_falls_back_to_winner_only():
    """No attempts_meta (legacy single-dispatch path) → winner-only
    settlement, same result as compute_settlement_micros directly."""
    winner = b'{"usage":{"input_tokens":100,"output_tokens":50}}'
    result = settle_micros_for_attempts(
        attempts_meta=None,
        request_provider="anthropic",
        request_model="claude-sonnet-4-6",
        operation="messages.create",
        winner_response_bytes=winner,
    )
    assert result == 1_050


# ─── P1-4 — streaming Responses uses OPENAI_RESPONSES normalizer ──────


def test_handler_passes_request_url_path_as_operation_to_stream_wrapper():
    """P1-4 pin: handler must pass ``operation=request.url.path`` when
    invoking ``_wrap_v2_stream_finalize`` so the normalizer picks the
    right family (Responses vs Chat). The wrapper has a default for
    legacy test scaffolding — this test locks the production wiring."""
    import inspect
    from app.modules.guard import gateway_handler

    src = inspect.getsource(gateway_handler)
    assert "operation=request.url.path" in src, (
        "P1-4 regressed: handler no longer threads request.url.path into "
        "_wrap_v2_stream_finalize. Responses-shape usage will be parsed "
        "under the Chat normalizer and settle to None."
    )


def test_settlement_picks_responses_family_when_operation_contains_responses():
    """Streaming wrapper threads the actual request path (e.g.
    /gateway/v1/openai/v1/responses) — settlement family follows.
    Pre-fix the wrapper hardcoded 'chat.completions.stream' and
    responses-shape usage was parsed under the Chat normalizer."""
    responses_shape_bytes = (
        b'{"usage":{"input_tokens":100,"output_tokens":50}}'
    )
    # As Chat family, this JSON has no prompt_tokens/completion_tokens
    # so extraction would be UNAVAILABLE → None. As Responses family,
    # input_tokens/output_tokens are the correct fields → priced.
    responses_result = compute_settlement_micros(
        provider="openai",
        model="gpt-4.1",
        operation="/gateway/v1/openai/v1/responses",
        response_bytes=responses_shape_bytes,
    )
    chat_result = compute_settlement_micros(
        provider="openai",
        model="gpt-4.1",
        operation="chat.completions.stream",
        response_bytes=responses_shape_bytes,
    )
    assert responses_result == 600  # 100*2 + 50*8 = 600
    assert chat_result is None      # different field names — not extractable


# ─── P1-1 — recovery reads from receipts (authoritative) not audit ────


def test_reconciler_reads_committed_from_llm_attempt_receipts_not_audit():
    """budget_ledger.reconcile() must sum from
    ``LlmAttemptReceipt.calculated_cost_microdollars`` post-cutover.
    Pre-fix it summed ``GuardAuditEvent.cost_usd_after`` — legacy
    audit-side math without cache breakout — so a Redis rebuild
    restored a DIFFERENT total than the live counter."""
    import inspect
    from app.core import budget_ledger

    reconcile_src = inspect.getsource(budget_ledger.BudgetLedger.reconcile)
    assert "LlmAttemptReceipt" in reconcile_src
    assert "calculated_cost_microdollars" in reconcile_src
    # P1-C: the reconciler MAY read audit rows as a pre-cutover fallback,
    # but ONLY under a NOT EXISTS predicate that excludes any request
    # already represented by a settleable receipt. Assert the completeness
    # gate is present so partial receipts never contribute to the sum.
    assert "usage_completeness" in reconcile_src
    assert "pricing_completeness" in reconcile_src
