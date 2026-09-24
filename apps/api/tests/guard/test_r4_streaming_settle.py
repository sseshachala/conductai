"""R4 (reviewer P1) — streaming settle in stream wrappers.

Pre-fix the handler's inline settle ran BEFORE ASGI drained the stream,
so ``actual_cents`` was None and reservations stayed open forever (the
reconciler would eventually mark them ``left_open`` / released, but
Redis capacity was held for the interim). Plus non-streaming response-
gate blocks read the *replacement* body when computing cost, not the
preserved upstream snapshot — so gated responses undercounted spend.

Post-fix:

1. ``_wrap_v2_stream_finalize`` accepts a ``reservations`` list. On
   stream close / client cancel / body-timeout, it extracts token
   counts from the drained bytes, computes cost, and calls
   ``settle_reservations`` inside a threadpool (R3 pattern) so the
   ASGI drain path stays responsive.
2. The handler's inline settle SKIPS streaming responses — the
   wrapper owns them.
3. Non-streaming settle prefers ``_v2_upstream_body_bytes`` (the
   pre-gate snapshot) over ``_response.body`` so a response-gate
   block still bills the caller for the tokens the provider
   actually served.

Structural tests only. Live-DB streaming coverage lives in the epic's
chaos suite.
"""
from __future__ import annotations

import inspect


def test_wrap_v2_stream_finalize_accepts_reservations():
    from app.modules.guard.gateway_handler import _wrap_v2_stream_finalize

    sig = inspect.signature(_wrap_v2_stream_finalize)
    assert "reservations" in sig.parameters, (
        "R4 regressed: _wrap_v2_stream_finalize must accept reservations "
        "so the wrapper owns settlement after stream drain."
    )
    param = sig.parameters["reservations"]
    assert param.default is None, (
        "reservations param must default to None so non-flagged callers "
        "still work (no reservations to settle)."
    )


def test_wrap_v2_stream_finalize_calls_settle_reservations():
    """Grep-guard: the wrapper body must call settle_reservations
    (via the run_in_threadpool pattern from R3)."""
    from app.modules.guard.gateway_handler import _wrap_v2_stream_finalize

    src = inspect.getsource(_wrap_v2_stream_finalize)
    assert "settle_reservations" in src, (
        "wrapper does not call settle_reservations — reservations will "
        "stay open until reconciler picks them up. See R4."
    )
    assert "run_in_threadpool" in src or "_rin_threadpool" in src, (
        "wrapper settle must offload to threadpool (R3 pattern). "
        "Otherwise the ASGI drain path blocks on sync DB+Redis."
    )


def test_wrap_v2_stream_finalize_computes_actual_cents_from_body():
    """The wrapper must derive actual_cents from the drained body, not
    pass None (which would mark PENDING_RECONCILER for every stream)."""
    from app.modules.guard.gateway_handler import _wrap_v2_stream_finalize

    src = inspect.getsource(_wrap_v2_stream_finalize)
    # #2209 PR 4 (cutover): settlement math now runs through
    # ``settle_micros_for_attempts`` — sums per-attempt priced micros
    # from the routing_meta so preceding failed attempts are counted.
    assert "settle_micros_for_attempts" in src, (
        "wrapper must call settle_micros_for_attempts so failed "
        "attempts before the winner are settled too."
    )
    assert "_actual_cents_stream" in src, (
        "wrapper must compute an actual_cents value to pass to "
        "settle_reservations."
    )


def test_handler_skips_inline_settle_for_streaming_responses():
    """Handler must NOT settle inline when the response is streaming —
    the wrapper owns it. Settling twice would double-commit or double-
    release."""
    import app.modules.guard.gateway_handler as gh

    src = inspect.getsource(gh)
    assert "_reservations and not isinstance(_response, StreamingResponse)" in src, (
        "R4 regressed: handler settles inline for streaming responses. "
        "The wrapper owns settlement post-drain."
    )


def test_non_streaming_settle_prefers_upstream_snapshot():
    """Response-gate replaces _response.body with an error envelope.
    Settle must read _v2_upstream_body_bytes so token counts reflect
    what the provider actually served."""
    import app.modules.guard.gateway_handler as gh

    src = inspect.getsource(gh)
    assert '_snapshot = locals().get("_v2_upstream_body_bytes")' in src, (
        "R4 regressed: non-streaming settle no longer reads "
        "_v2_upstream_body_bytes. Gated responses will undercount."
    )
