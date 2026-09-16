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


def test_build_v2_plan_streaming_fails_explicit():
    """Client sent a cond-<code>-<alias> identifier AND stream=true.
    Silent v1 fallback would misrepresent which profile served the
    request; return 501 instead."""
    from app.modules.guard.gateway_handler import _build_v2_plan
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as excinfo:
        _build_v2_plan(
            db=None,   # never touched — early rejection
            workspace_id="ws",
            cond_code="abc12345",
            provider="anthropic",
            upstream_path="/v1/messages",
            body={"stream": True, "model": "cond-abc12345-coding"},
        )
    assert excinfo.value.status_code == 501
    assert "streaming" in str(excinfo.value.detail).lower()


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
    caller passes only ``plan`` and ``body``; ensure the signature
    accepts that shape."""
    import inspect
    from app.modules.guard.gateway_handler import _execute_v2
    sig = inspect.signature(_execute_v2)
    # Only plan + body are required keyword args.
    required = {
        name for name, p in sig.parameters.items()
        if p.default is inspect.Parameter.empty
    }
    assert required == {"plan", "body"}, (
        f"_execute_v2 kwargs drifted from caller ({required})"
    )


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
