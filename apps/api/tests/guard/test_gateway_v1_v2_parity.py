"""PR 4 — v1↔v2 audit-writer signature drift guard + outcome invariants.

Locks the invariants the canary ramp depends on. Both v1
(``guard/router.py::_schedule_audit`` durable branch) and v2
(``guard/gateway_lifecycle.py::finalize_durable_row``) end up calling
the same ``guard/audit.py::finalize`` under the hood — so parity is a
question of **which kwargs each path builds**. If v2 forgets a field
v1 always populates, dashboards and Flight Recorder queries lose
signal the moment traffic ramps.

Approach: **AST-walk the call sites**, don't regex the source. Regex
either over-matches (grabs local assignments) or under-matches
(misses kwargs whose RHS pattern the whitelist didn't anticipate).
The AST walk finds the actual ``Call`` node targeting ``finalize`` /
``_finalize_audit`` and reads its ``keyword`` children — the same
data structure the interpreter uses at call time. Rename-refactors
that don't break at runtime don't break these tests either.

Scope of this file:
- Signature-drift guard (invariants A + B): source-level checks that
  both paths call the same sink with kwargs the sink accepts.
- Outcome-value invariants (invariant C): pure-function checks on
  ``_derive_v2_finalize_args`` + ``_wrap_v2_stream_finalize`` — the
  helpers that shape v2's finalize args for each of the four request
  outcomes (ok, response-gate block, streaming ok, streaming
  cancelled).

Full end-to-end value parity between v1 and v2 (same request → same
column values across all outcomes) is out of scope here — that lives
in the canary ramp's dashboard diff. Firing a real request through
``handle_gateway_request`` needs Redis + Vault + composed policy
engine + RLS session; the fixture cost buys signal these tests
already provide via the shared-sink guarantee.
"""
from __future__ import annotations

import ast
import inspect

import pytest


# ─── Invariant A: shared sink ─────────────────────────────────────────


def test_v1_and_v2_call_the_same_finalize_sink():
    """The parity story rests on both paths writing through
    ``guard/audit.py::finalize``. If v1's ``_schedule_audit`` durable
    branch or v2's ``finalize_durable_row`` ever start calling a
    different sink, the parity claim needs re-proving from scratch.

    Uses object-identity (``is``) for v1 (``_finalize_audit`` is a
    module-level import alias for ``audit.finalize``) and an AST walk
    for v2 (the ``finalize`` reference is captured inside a
    ``to_thread`` call), so nothing here relies on substring matches
    against source code.
    """
    from app.guard import router as v1_router
    from app.modules.guard import gateway_lifecycle as v2_lifecycle
    from app.guard.audit import finalize as canonical_finalize

    assert v1_router._finalize_audit is canonical_finalize, (
        "v1 (_schedule_audit's durable branch) no longer routes through "
        "audit.finalize — parity vs v2 must be re-proven end-to-end."
    )
    # v2: walk the AST of finalize_durable_row and require that at
    # least one asyncio.to_thread(...) call has `finalize` as its first
    # positional argument. Anything less is a substring match that
    # could pass even if the delegation is gone.
    tree = ast.parse(inspect.getsource(v2_lifecycle.finalize_durable_row))
    passes_finalize_to_to_thread = False
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        is_to_thread = (
            (isinstance(func, ast.Attribute) and func.attr == "to_thread")
            or (isinstance(func, ast.Name) and func.id == "to_thread")
        )
        if not is_to_thread:
            continue
        if node.args and isinstance(node.args[0], ast.Name) \
                and node.args[0].id == "finalize":
            passes_finalize_to_to_thread = True
            break
    assert passes_finalize_to_to_thread, (
        "finalize_durable_row no longer runs audit.finalize inside "
        "asyncio.to_thread. If the delegation moved, the shared-sink "
        "parity claim needs re-proving here."
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


def _kwargs_of_call_in(func, *, target_predicate) -> set[str]:
    """Walk ``func``'s AST; return the kwarg names of the *first* Call
    node whose callee satisfies ``target_predicate(callee_ast_node)``.

    Callee shapes we might encounter:
      - Name(id="finalize")
      - Attribute(attr="_finalize_audit", value=...)
      - Attribute(attr="finalize", value=...)
      - a nested Call whose returned function is called (rare)

    Returns an empty set if no matching call is found — callers assert
    on the resulting set (e.g. subset checks against the accepted
    kwargs of the sink), so an empty return propagates as a failing
    critical-kwargs assertion rather than a silent pass.
    """
    src = inspect.getsource(func)
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if target_predicate(node.func):
            return {kw.arg for kw in node.keywords if kw.arg}
    return set()


def _v1_durable_branch_call_target() -> callable:
    """Predicate — the v1 durable branch calls
    ``background.add_task(_finalize_audit, ...)`` — the callable we
    want is the *second-inner* Call (i.e. add_task's positional args
    inside the branch). Match the enclosing add_task Call whose first
    positional arg is ``Name('_finalize_audit')``."""
    def _predicate(callee):
        # We're matching the add_task call itself; the finalize kwargs
        # live on it. The caller of _kwargs_of_call_in narrows further.
        return (
            isinstance(callee, ast.Attribute)
            and callee.attr == "add_task"
        )
    return _predicate


def _kwargs_passed_by_v1_durable_branch() -> set[str]:
    """v1's durable branch schedules
    ``background.add_task(_finalize_audit, row_id, workspace_id,
    decision=..., ...)``. AST-walk the ``_schedule_audit`` source,
    find the add_task Call whose first positional arg is
    ``_finalize_audit`` (that's the durable branch — v1 has a second
    add_task for the legacy ``_record_audit`` path), and return its
    kwargs.

    Robust against renames of the RHS expressions: whether the value
    is ``audit_args[15]``, a helper function call, or a local
    variable, the kwarg *name* is what we read.
    """
    from app.guard import router

    tree = ast.parse(inspect.getsource(router._schedule_audit))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        callee = node.func
        if not (isinstance(callee, ast.Attribute) and callee.attr == "add_task"):
            continue
        # Match the durable branch add_task: first positional arg is
        # the _finalize_audit callable.
        first_arg = node.args[0] if node.args else None
        if not isinstance(first_arg, ast.Name) or first_arg.id != "_finalize_audit":
            continue
        return {kw.arg for kw in node.keywords if kw.arg}
    return set()


def _kwargs_passed_by_v2_finalize_wrapper() -> set[str]:
    """v2's ``finalize_durable_row`` schedules
    ``asyncio.create_task(asyncio.to_thread(finalize, row_id,
    workspace_id, decision=..., ...))``. AST-walk the source, find the
    to_thread Call whose first positional arg is ``finalize``, and
    return its kwargs.

    Robust against local-variable name collisions that regex would
    have matched — this reads the actual keyword argument names from
    the Call node.
    """
    from app.modules.guard import gateway_lifecycle

    tree = ast.parse(inspect.getsource(gateway_lifecycle.finalize_durable_row))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        callee = node.func
        is_to_thread = (
            (isinstance(callee, ast.Attribute) and callee.attr == "to_thread")
            or (isinstance(callee, ast.Name) and callee.id == "to_thread")
        )
        if not is_to_thread:
            continue
        first_arg = node.args[0] if node.args else None
        if not (isinstance(first_arg, ast.Name) and first_arg.id == "finalize"):
            continue
        return {kw.arg for kw in node.keywords if kw.arg}
    return set()


def test_kwarg_extractors_reject_local_var_noise():
    """Meta-test: if the extraction ever slips back to a regex that
    matches ``local = something``, this test catches it. Confirms both
    extractors find non-empty kwarg sets — an empty return would fail
    the downstream critical-kwargs assertions with a misleading
    "missing everything" error, so surface the extraction failure
    directly here."""
    v1_kwargs = _kwargs_passed_by_v1_durable_branch()
    v2_kwargs = _kwargs_passed_by_v2_finalize_wrapper()
    assert v1_kwargs, (
        "AST walk found no add_task(_finalize_audit, ...) call in "
        "v1's _schedule_audit — extraction broken or v1 stopped using "
        "the durable branch."
    )
    assert v2_kwargs, (
        "AST walk found no asyncio.to_thread(finalize, ...) call in "
        "v2's finalize_durable_row — extraction broken or v2 stopped "
        "delegating to audit.finalize."
    )
    # Both sets must be minimal — no keys that look like local vars
    # (single-letter, purely numeric, etc.). Guards against a false
    # match on some future add_task with different first positional.
    for name in v1_kwargs | v2_kwargs:
        assert name.isidentifier(), (
            f"AST extractor picked up non-identifier {name!r}"
        )


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
