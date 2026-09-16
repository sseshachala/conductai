"""Regression tests for the v2 wiring inside ``gateway_handler``.

These tests exercise the paths that the earlier suite missed because
``guard_gateway_profile_v2`` stays False by default in the wider fixture
harness. They lock:

- ``_build_v2_plan`` uses the correct import path (regression for the
  ``app.modules.guard.gateway_v2_bridge`` mistype).
- ``_execute_v2`` accepts the arguments the caller actually passes
  (regression for the stale ``routing_meta_ref`` positional).
- Explicit v2 requests (client sent a cond-prefixed identifier) that
  can't be served fail loudly instead of silently degrading to v1.
"""
from __future__ import annotations

import pytest


def test_build_v2_plan_imports_bridge_from_runtime():
    """Importing gateway_handler must not carry a bad module reference
    into _build_v2_plan's own import block."""
    from app.modules.guard import gateway_handler  # noqa: F401
    # The import block is inside the function body; force it to run by
    # invoking the function. All rejection paths below drive it.


def test_build_v2_plan_no_longer_rejects_streaming_at_plan_time(monkeypatch):
    """PR 2.5 — streaming lands. Regression test asserts plan-build no
    longer 501s for stream=true; the 501 branch belonged in Phase 1 and
    is gone. The plan proceeds to resolve_v2, which we stub to return
    None so the test asserts we got PAST the streaming pre-check and
    into the normal resolution path (404 not 501)."""
    from app.modules.guard import gateway_handler
    from fastapi import HTTPException

    monkeypatch.setattr(
        "app.modules.guard.gateway_runtime.resolve_v2",
        lambda db, *, workspace_id, cond_code: None,
    )

    with pytest.raises(HTTPException) as excinfo:
        gateway_handler._build_v2_plan(
            db=None,
            workspace_id="ws",
            cond_code="abc12345",
            provider="anthropic",
            upstream_path="/v1/messages",
            body={"stream": True, "model": "cond-abc12345-coding"},
        )
    # NOT 501 (streaming refusal) — 404 (unknown cond_code), meaning we
    # got past the streaming pre-check into normal resolution.
    assert excinfo.value.status_code == 404
    assert "abc12345" in str(excinfo.value.detail)


def test_build_v2_plan_unmapped_url_fails_explicit():
    """Client sent cond-<code>-<alias> on a URL the v2 capability map
    doesn't cover. Explicit refusal, not silent fallback."""
    from app.modules.guard.gateway_handler import _build_v2_plan
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as excinfo:
        _build_v2_plan(
            db=None,
            workspace_id="ws",
            cond_code="abc12345",
            provider="cohere",   # not in the launch matrix
            upstream_path="/v1/chat/completions",
            body={"model": "cond-abc12345-x"},
        )
    assert excinfo.value.status_code == 501
    assert "cohere" in str(excinfo.value.detail).lower() or "does not serve" in str(excinfo.value.detail).lower()


def test_build_v2_plan_unknown_cond_code_fails_explicit(monkeypatch):
    """Client explicitly asked for a v2 profile that doesn't exist.
    Silently routing to v1 with unrelated config would be a lie —
    return 404."""
    from app.modules.guard import gateway_handler
    from fastapi import HTTPException

    # Stub out resolve_v2 to return None (profile not found).
    def _fake_resolve_v2(db, *, workspace_id, cond_code):
        return None
    monkeypatch.setattr(
        "app.modules.guard.gateway_runtime.resolve_v2",
        _fake_resolve_v2,
    )

    with pytest.raises(HTTPException) as excinfo:
        gateway_handler._build_v2_plan(
            db=None,
            workspace_id="ws",
            cond_code="notreal0",
            provider="anthropic",
            upstream_path="/v1/messages",
            body={"model": "cond-notreal0-coding"},
        )
    assert excinfo.value.status_code == 404
    assert "notreal0" in str(excinfo.value.detail)


def test_execute_v2_signature_matches_caller():
    """Regression for the stale ``routing_meta_ref`` positional. The
    caller passes only ``plan`` and ``body`` (and PR 2.5 adds ``stream``
    as an optional kwarg). Ensure required kwargs still match caller."""
    import inspect
    from app.modules.guard.gateway_handler import _execute_v2
    sig = inspect.signature(_execute_v2)
    required = {
        name for name, p in sig.parameters.items()
        if p.default is inspect.Parameter.empty
    }
    assert required == {"plan", "body"}, (
        f"_execute_v2 kwargs drifted from caller ({required})"
    )
    # PR 2.5 — ``stream`` is an optional keyword with default False.
    assert "stream" in sig.parameters
    assert sig.parameters["stream"].default is False


# ─── Response-gate block: preserve upstream body + use gate's rule id ─


def test_derive_finalize_success_uses_ingress_rule_and_response_body():
    """Ok path — no gate block. Finalize params should carry the
    ingress decision + rule and the response body (matches the
    upstream in the no-transformation case)."""
    from app.modules.guard.gateway_handler import _derive_v2_finalize_args

    class _Resp:
        status_code = 200
        body = b'{"usage":{"input_tokens":10,"output_tokens":5}}'

    out = _derive_v2_finalize_args(
        post_gate_response=_Resp(),
        pre_gate_upstream_body=b'{"upstream":true}',
        ingress_decision="allowed",
        ingress_rule_id="ingress-rule",
    )
    assert out["decision"] == "allowed"
    assert out["execution_status"] == "ok"
    assert out["rule_id"] == "ingress-rule"
    # response body used verbatim; upstream body only kicks in for blocks
    assert out["response_bytes"] == _Resp.body


def test_derive_finalize_block_uses_gate_rule_and_upstream_body():
    """The critical fix: a response-gate block wrote the ingress rule
    id + the 451 body onto the audit row. Now: the block rule id from
    the 451 envelope AND the pre-gate upstream body are recorded so
    token accounting is preserved even for a blocked response."""
    from app.modules.guard.gateway_handler import _derive_v2_finalize_args

    class _BlockedResp:
        status_code = 451
        body = (
            b'{"error":{'
            b'"type":"conduct_guard_response_block",'
            b'"message":"redacted",'
            b'"rule_id":"gate-rule-response-block",'
            b'"gate":"response"'
            b'}}'
        )

    pre_gate_upstream = b'{"content":"secret","usage":{"input_tokens":80,"output_tokens":40}}'

    out = _derive_v2_finalize_args(
        post_gate_response=_BlockedResp(),
        pre_gate_upstream_body=pre_gate_upstream,
        ingress_decision="allowed",
        ingress_rule_id="ingress-rule",
    )
    assert out["decision"] == "blocked"
    assert out["execution_status"] == "blocked"
    # gate's rule id — NOT the ingress one
    assert out["rule_id"] == "gate-rule-response-block"
    # upstream body preserved so token usage stays in the row
    assert out["response_bytes"] == pre_gate_upstream


# ─── PR 2.5 — streaming through _execute_v2 ───────────────────────────


@pytest.mark.anyio("asyncio")
async def test_execute_v2_streaming_returns_streaming_response(monkeypatch):
    """When the coordinator returns a StreamingUpstream (native_http +
    stream=True), _execute_v2 wraps it in a StreamingResponse and does
    NOT wrap it in a JSONResponse. Tests the isinstance branch."""
    from fastapi.responses import StreamingResponse

    from app.modules.guard.gateway_handler import _execute_v2, _V2Plan
    from app.runtime.attempt_coordinator import (
        AttemptRecord,
        CoordinatorResult,
    )
    from app.runtime.native_http_transport import StreamingUpstream

    class _FakeHTTPXResp:
        headers = {"content-type": "text/event-stream"}
        async def aiter_bytes(self):
            for chunk in [b"data: {\"x\":1}\n\n", b"data: [DONE]\n\n"]:
                yield chunk
        async def aclose(self):
            pass

    upstream = StreamingUpstream(
        status_code=200,
        headers=dict(_FakeHTTPXResp.headers),
        response=_FakeHTTPXResp(),
        provider="anthropic",
    )

    class _FakeCoordinator:
        async def execute(self, *, resolved, operation, payload, credential_resolver, stream, **_kw):
            assert stream is True
            return CoordinatorResult(
                response=upstream,
                revision_id=resolved.revision_id if resolved is not None else None,
                attempts=[AttemptRecord(
                    target_id="primary",
                    transport="native_http",
                    provider_or_integration="anthropic",
                    started_at_monotonic=0.0,
                    completed_at_monotonic=0.1,
                    succeeded=True,
                    error_class=None,
                    error_summary=None,
                )],
                winning_target_id="primary",
            )

    # X5 — _execute_v2 now goes through gateway_transports.get_coordinator
    # (worker-lifetime singleton). Patch that async function so the test
    # gets our fake coordinator without triggering the real transport
    # init path (which would try to build httpx clients etc.).
    async def _fake_get_coordinator():
        return _FakeCoordinator()
    monkeypatch.setattr(
        "app.runtime.gateway_transports.get_coordinator",
        _fake_get_coordinator,
    )

    # A tiny stub plan — resolved.revision_id + resolved.profile.accepts
    # are the only fields _execute_v2 reads directly; other fields go
    # through the coordinator we've stubbed.
    from types import SimpleNamespace
    plan = _V2Plan(
        resolved=SimpleNamespace(
            revision_id="rev-1",
            profile=SimpleNamespace(accepts=["anthropic_messages"]),
        ),
        operation="anthropic_messages",
        credential_resolver=lambda ref: "sk-fake",
    )

    response = await _execute_v2(plan=plan, body={"stream": True}, stream=True)
    assert isinstance(response, StreamingResponse), (
        f"streaming request should return StreamingResponse, got {type(response).__name__}"
    )
    assert response.status_code == 200
    assert response.media_type == "text/event-stream"


@pytest.mark.anyio("asyncio")
async def test_execute_v2_streaming_501_for_non_native_transport(monkeypatch):
    """If the coordinator wins with a non-native transport (LiteLLM SDK,
    which returns a generator, or passthrough), streaming through
    _execute_v2 raises 501 rather than crashing inside coerce_response_body.
    Names the winning target so the operator knows which one to swap."""
    from fastapi import HTTPException

    from app.modules.guard.gateway_handler import _execute_v2, _V2Plan
    from app.runtime.attempt_coordinator import (
        AttemptRecord,
        CoordinatorResult,
    )

    class _FakeCoordinator:
        async def execute(self, *, resolved, operation, payload, credential_resolver, stream, **_kw):
            # A LiteLLM stream would return an async generator, not a
            # StreamingUpstream. Simulate that with a MagicMock().
            from unittest.mock import MagicMock
            return CoordinatorResult(
                response=MagicMock(),
                revision_id=resolved.revision_id if resolved is not None else None,
                attempts=[AttemptRecord(
                    target_id="litellm-primary",
                    transport="litellm_sdk",
                    provider_or_integration="anthropic",
                    started_at_monotonic=0.0,
                    completed_at_monotonic=0.1,
                    succeeded=True,
                    error_class=None,
                    error_summary=None,
                )],
                winning_target_id="litellm-primary",
            )

    # X5 — _execute_v2 now goes through gateway_transports.get_coordinator
    # (worker-lifetime singleton). Patch that async function so the test
    # gets our fake coordinator without triggering the real transport
    # init path (which would try to build httpx clients etc.).
    async def _fake_get_coordinator():
        return _FakeCoordinator()
    monkeypatch.setattr(
        "app.runtime.gateway_transports.get_coordinator",
        _fake_get_coordinator,
    )

    from types import SimpleNamespace
    plan = _V2Plan(
        resolved=SimpleNamespace(
            revision_id="rev-1",
            profile=SimpleNamespace(accepts=["anthropic_messages"]),
        ),
        operation="anthropic_messages",
        credential_resolver=lambda ref: "sk-fake",
    )

    with pytest.raises(HTTPException) as excinfo:
        await _execute_v2(plan=plan, body={"stream": True}, stream=True)
    assert excinfo.value.status_code == 501
    assert "native_http" in str(excinfo.value.detail)
    assert "litellm-primary" in str(excinfo.value.detail)


# ─── PR 3 canary flip — gateway_handler consults per-workspace resolver ─


def test_gateway_handler_uses_per_workspace_v2_resolver_not_global_flag():
    """PR 3 wiring regression. Before this PR the handler read
    ``settings.guard_gateway_profile_v2`` — the global flag — meaning
    it was on for every workspace or none. Now it must consult
    ``settings.gateway_profile_v2_enabled_for(workspace_id)`` so an
    allowlist entry (or non-zero rollout pct) can dark-launch v2 for
    specific customers first.

    Guarded by source-scan rather than a full request test because the
    handler's request path pulls in Redis, RLS, Vault, and the composed
    policy engine — none of which this wiring change touches.
    """
    from pathlib import Path
    handler_src = (
        Path(__file__).resolve().parents[2]
        / "app" / "modules" / "guard" / "gateway_handler.py"
    ).read_text(encoding="utf-8")

    # Every read of the global-boolean flag inside the handler is a bug —
    # the handler must go through the per-workspace resolver so canary
    # bucketing kicks in. The only ok reference to the global attribute
    # lives on ``Settings`` itself, not in this handler.
    assert "settings.guard_gateway_profile_v2" not in handler_src, (
        "gateway_handler.py still reads the global v2 flag directly. "
        "Use settings.gateway_profile_v2_enabled_for(workspace_id) so "
        "the allowlist + rollout_pct canary knobs actually take effect."
    )
    assert "settings.gateway_profile_v2_enabled_for(workspace_id)" in handler_src, (
        "gateway_handler.py must call the per-workspace resolver for "
        "canary bucketing. Import path: from app.core.config import "
        "settings; settings.gateway_profile_v2_enabled_for(...)."
    )


def test_derive_finalize_block_with_malformed_envelope_falls_back_to_ingress():
    """If the block body isn't the expected 451-envelope shape (edge
    case: gate handler fails, upstream returns 4xx directly, etc.),
    finalize should still record blocked-execution with the ingress
    rule id rather than losing all attribution."""
    from app.modules.guard.gateway_handler import _derive_v2_finalize_args

    class _Weird:
        status_code = 500
        body = b'not-json-at-all'

    out = _derive_v2_finalize_args(
        post_gate_response=_Weird(),
        pre_gate_upstream_body=b'{"upstream":true}',
        ingress_decision="allowed",
        ingress_rule_id="ingress-rule",
    )
    assert out["decision"] == "blocked"
    assert out["execution_status"] == "blocked"
    assert out["rule_id"] == "ingress-rule"
