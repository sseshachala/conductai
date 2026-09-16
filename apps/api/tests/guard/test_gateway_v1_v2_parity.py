"""PR 4 — v1↔v2 audit parity contract.

Locks the parity invariants the canary ramp depends on. Both v1
(``guard/router.py::_schedule_audit`` durable branch) and v2
(``guard/gateway_lifecycle.py::finalize_durable_row``) end up calling
the same ``guard/audit.py::finalize`` under the hood — so parity is a
question of **which kwargs each path builds**. If v2 forgets a field
v1 always populates, dashboards and Flight Recorder queries lose
signal the moment traffic ramps.

These are contract tests, not full request-lifecycle integration.
Firing a real request through ``handle_gateway_request`` requires
Redis + Vault + composed policy engine + RLS session — none of which
add signal to the specific parity question here. The signature checks
below catch the class of regression that matters: field drift between
the two paths.

Full end-to-end value parity across all scenarios (200 OK, response
gate block, streaming success, streaming cancellation, all-attempts-
failed) is deferred to the canary ramp's dashboard diff — those
scenarios each have their own dedicated tests in the v2 suite; the
parity guarantee is that v1 wrote the same column values for the
same inputs *before* Phase 2 durable audit landed, and continues to
via the shared ``finalize`` sink.
"""
from __future__ import annotations

import inspect

import pytest


# ─── Invariant A: shared sink ─────────────────────────────────────────


def test_v1_and_v2_call_the_same_finalize_sink():
    """The parity story rests on both paths writing through
    ``guard/audit.py::finalize``. If v1's ``_schedule_audit`` durable
    branch or v2's ``finalize_durable_row`` ever start calling a
    different sink, the parity claim needs re-proving from scratch."""
    from app.guard import router as v1_router
    from app.modules.guard import gateway_lifecycle as v2_lifecycle
    from app.guard.audit import finalize as canonical_finalize

    assert v1_router._finalize_audit is canonical_finalize, (
        "v1 (_schedule_audit's durable branch) no longer routes through "
        "audit.finalize — parity vs v2 must be re-proven end-to-end."
    )
    # v2's supervised wrapper calls audit.finalize inside a to_thread. The
    # import lives inside the function body so we grab it via the
    # module's own namespace at import time.
    src = inspect.getsource(v2_lifecycle.finalize_durable_row)
    assert "finalize," in src or "finalize(" in src, (
        "finalize_durable_row no longer delegates to audit.finalize. "
        "The shared-sink parity claim needs re-proving."
    )


# ─── Invariant B: same kwarg surface at the sink ──────────────────────


def _finalize_kwargs() -> set[str]:
    """Return the kwarg names ``audit.finalize`` accepts (excluding
    positionals). The parity claim is that every kwarg v1 and v2 pass
    is in this set — and both paths pass overlapping subsets on the
    fields that matter."""
    from app.guard.audit import finalize
    sig = inspect.signature(finalize)
    return {
        name for name, p in sig.parameters.items()
        if p.kind in (
            inspect.Parameter.KEYWORD_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        )
    }


def _kwargs_passed_by_v1_durable_branch() -> set[str]:
    """Extract the kwarg names v1's ``_schedule_audit`` durable branch
    passes. Read from source (rather than executing) because the
    function body invokes ``background.add_task`` with a payload we
    would otherwise have to schedule to inspect."""
    from app.guard import router
    src = inspect.getsource(router._schedule_audit)
    # The durable branch is bounded by the ``if _durable_row_id:``
    # block and its ``return``. Grab that slice, then pull kwargs.
    start = src.index("if _durable_row_id:")
    end = src.index("return", start)
    slice_ = src[start:end]
    # kwarg names are the identifiers preceding '=' inside the call.
    import re
    return set(re.findall(r"(\w+)\s*=\s*audit_args", slice_)) | \
           set(re.findall(r"(\w+)\s*=\s*int\(", slice_)) | \
           set(re.findall(r"(\w+)\s*=\s*response_bytes", slice_)) | \
           set(re.findall(r"(\w+)\s*=\s*execution_status", slice_)) | \
           set(re.findall(r"(\w+)\s*=\s*result_summary", slice_))


def _kwargs_passed_by_v2_finalize_wrapper() -> set[str]:
    """Extract the kwarg names v2's ``finalize_durable_row`` passes to
    ``audit.finalize``. Same source-scan approach as v1."""
    from app.modules.guard import gateway_lifecycle
    src = inspect.getsource(gateway_lifecycle.finalize_durable_row)
    start = src.index("finalize,")   # start of the to_thread call
    end = src.index(")\n", start)
    slice_ = src[start:end]
    import re
    return set(re.findall(r"(\w+)\s*=\s*\w+", slice_))


def test_v1_durable_branch_only_passes_kwargs_finalize_accepts():
    """v1 (_schedule_audit) MUST NOT pass a kwarg finalize doesn't know.
    A typo here would raise TypeError at request time — the durable
    lifecycle would silently orphan the row."""
    accepted = _finalize_kwargs()
    v1_kwargs = _kwargs_passed_by_v1_durable_branch()
    unknown = v1_kwargs - accepted
    assert not unknown, (
        f"v1 _schedule_audit passes kwargs finalize() does not accept: "
        f"{sorted(unknown)}. Rename the kwarg or extend finalize's "
        f"signature — do not swallow the mismatch."
    )


def test_v2_wrapper_only_passes_kwargs_finalize_accepts():
    """Symmetric assertion for v2's supervised wrapper."""
    accepted = _finalize_kwargs()
    v2_kwargs = _kwargs_passed_by_v2_finalize_wrapper()
    unknown = v2_kwargs - accepted
    assert not unknown, (
        f"finalize_durable_row passes kwargs finalize() does not accept: "
        f"{sorted(unknown)}. Rename or extend finalize's signature — "
        f"do not swallow the mismatch."
    )


def test_v1_and_v2_pass_the_same_critical_kwargs():
    """The set of kwargs both paths pass must overlap on the fields
    dashboards actually query: decision, rule_id, execution_status,
    routing_meta, duration_ms, response_bytes, workspace_id (implicit),
    provider, model, ai_tool, clerk_user_id, user_email, body.

    If v2 stops passing one that v1 does, the audit row loses a column
    the moment v2 traffic ramps."""
    critical = {
        "decision", "rule_id", "execution_status", "routing_meta",
        "duration_ms", "response_bytes", "provider", "model",
        "ai_tool", "clerk_user_id", "user_email", "body",
        "result_summary",
    }
    v1_kwargs = _kwargs_passed_by_v1_durable_branch()
    v2_kwargs = _kwargs_passed_by_v2_finalize_wrapper()

    missing_from_v1 = critical - v1_kwargs
    missing_from_v2 = critical - v2_kwargs
    assert not missing_from_v1, (
        f"v1 no longer passes critical kwargs: {sorted(missing_from_v1)}. "
        f"Dashboards depend on these — regression before canary ramp."
    )
    assert not missing_from_v2, (
        f"v2 does not pass critical kwargs: {sorted(missing_from_v2)}. "
        f"Rows would land with these columns empty; dashboards lose "
        f"signal the moment traffic ramps."
    )


# ─── Invariant C: value-parity for the four outcome buckets ───────────
#
# The four outcomes a request can land in — ok, blocked-by-response-gate,
# streaming-ok, streaming-cancelled — must produce identical column
# values on the audit row regardless of which path served the request.
# Rather than fire a full request through both paths (fixture-heavy),
# we exercise the pure-function helpers that derive the final finalize
# args for each outcome, and lock the values they compute.


def test_ok_outcome_decision_and_execution_status():
    """Ok path — decision carries the ingress action, execution_status
    is 'ok'. If v2 ever writes execution_status='success' (v1's older
    value), dashboards will fork on that field."""
    from app.modules.guard.gateway_handler import _derive_v2_finalize_args

    class _Resp:
        status_code = 200
        body = b'{"content":"hello"}'

    out = _derive_v2_finalize_args(
        post_gate_response=_Resp(),
        pre_gate_upstream_body=b'{"content":"hello"}',
        ingress_decision="allowed",
        ingress_rule_id=None,
    )
    assert out["decision"] == "allowed"
    assert out["execution_status"] == "ok"
    assert out["response_bytes"] == b'{"content":"hello"}'
    assert out["rule_id"] is None


def test_response_gate_block_decision_and_upstream_preservation():
    """Response-gate block — decision='blocked', execution_status='blocked',
    rule_id names the GATE's rule (not the ingress rule), response_bytes
    preserves the upstream body so cost accounting still lands on the
    row."""
    from app.modules.guard.gateway_handler import _derive_v2_finalize_args

    class _BlockedResp:
        status_code = 451
        body = b'{"error":{"rule_id":"gate-rule","gate":"response"}}'

    upstream = b'{"content":"leaked-key","usage":{"input_tokens":40,"output_tokens":10}}'

    out = _derive_v2_finalize_args(
        post_gate_response=_BlockedResp(),
        pre_gate_upstream_body=upstream,
        ingress_decision="allowed",
        ingress_rule_id="ingress-rule",
    )
    assert out["decision"] == "blocked"
    assert out["execution_status"] == "blocked"
    assert out["rule_id"] == "gate-rule"
    assert out["response_bytes"] == upstream


# ─── Invariant D: streaming ok/interrupted mapping ────────────────────


@pytest.mark.anyio("asyncio")
async def test_streaming_ok_execution_status(monkeypatch):
    """Streaming happy path — the wrap's ``finally`` block MUST call
    finalize with execution_status='ok' and the collected bytes.
    Symmetric with v1's _stream_chunks execution_status='success' →
    'ok' translation (post-Phase-2 they use the same string)."""
    from fastapi.responses import StreamingResponse
    from app.modules.guard.gateway_handler import _wrap_v2_stream_finalize

    captured: dict = {}

    async def _fake_finalize(*, row_id, workspace_id, decision, provider,
                             model, body, response_bytes, duration_ms,
                             rule_id, routing_meta, execution_status,
                             result_summary, clerk_user_id, ai_tool,
                             user_email):
        captured.update(
            decision=decision, execution_status=execution_status,
            response_bytes=response_bytes,
        )

    monkeypatch.setattr(
        "app.modules.guard.gateway_lifecycle.finalize_durable_row",
        _fake_finalize,
    )

    async def _upstream():
        yield b"data: hi\n\n"
        yield b"data: [DONE]\n\n"

    inner = StreamingResponse(_upstream(), media_type="text/event-stream")
    wrapped = _wrap_v2_stream_finalize(
        inner,
        row_id="row-1",
        workspace_id="ws",
        provider="anthropic",
        model="claude",
        body={},
        ingress_decision="allowed",
        ingress_rule_id=None,
        routing_meta={},
        clerk_user_id="u",
        ai_tool="tool",
        user_email=None,
        started_monotonic=0.0,
    )

    async for _ in wrapped.body_iterator:
        pass

    assert captured["decision"] == "allowed"
    assert captured["execution_status"] == "ok"
    assert b"[DONE]" in captured["response_bytes"]


@pytest.mark.anyio("asyncio")
async def test_streaming_cancelled_execution_status(monkeypatch):
    """Streaming cancellation — MUST land with
    execution_status='interrupted' (v1's _stream_chunks value on
    CancelledError). If v2 writes 'error' or 'success' on cancel,
    the reconciler dashboard can't tell an aborted stream from a
    genuine upstream failure."""
    import asyncio

    from fastapi.responses import StreamingResponse
    from app.modules.guard.gateway_handler import _wrap_v2_stream_finalize

    captured: dict = {}

    async def _fake_finalize(*, execution_status, decision, **_kw):
        captured.update(decision=decision, execution_status=execution_status)

    monkeypatch.setattr(
        "app.modules.guard.gateway_lifecycle.finalize_durable_row",
        _fake_finalize,
    )

    async def _hanging():
        yield b"data: hi\n\n"
        raise asyncio.CancelledError()

    inner = StreamingResponse(_hanging(), media_type="text/event-stream")
    wrapped = _wrap_v2_stream_finalize(
        inner,
        row_id="row-2",
        workspace_id="ws",
        provider="anthropic",
        model="claude",
        body={},
        ingress_decision="allowed",
        ingress_rule_id=None,
        routing_meta={},
        clerk_user_id="u",
        ai_tool="tool",
        user_email=None,
        started_monotonic=0.0,
    )

    with pytest.raises(asyncio.CancelledError):
        async for _ in wrapped.body_iterator:
            pass

    assert captured["decision"] == "error"
    assert captured["execution_status"] == "interrupted"
