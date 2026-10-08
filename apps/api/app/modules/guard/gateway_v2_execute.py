"""Gateway v2 forward step — ``_execute_v2``, the non-wrapped stream response,
the streaming tool-policy check, and routing-meta / finalize-arg helpers.

Split out of ``gateway_handler.py``; re-exported there."""
from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from fastapi.responses import JSONResponse, StreamingResponse

if TYPE_CHECKING:
    from app.modules.guard.gateway_v2_plan import _V2Plan


log = structlog.get_logger("app.modules.guard.gateway_handler")


async def _execute_v2(
    *,
    plan: _V2Plan,
    body: dict,
    stream: bool = False,
    policy_check=None,
    client_headers: dict[str, str] | None = None,
):
    """Run the coordinator + shape its result into a JSONResponse or
    ``StreamingResponse`` depending on the request's ``stream`` flag.

    Attempt records land on ``plan.last_meta`` so the caller can merge
    them into ``routing_meta`` for the durable audit row.

    PR 2.5 — streaming: when the coordinator returns a
    ``StreamingUpstream`` (from the native_http transport with
    ``stream=True``), we wrap its ``aiter_bytes()`` in a
    ``StreamingResponse`` and close the underlying httpx response when
    the client disconnects or the generator exhausts. Retry-after-headers
    is enforced by the coordinator (any success return locks the target).
    """
    from app.runtime.attempt_coordinator import (
        AllAttemptsFailed as _AllAttemptsFailed,
    )
    import json
    from app.runtime.gateway_transports import get_coordinator
    from app.runtime.gateway_v2_bridge import coerce_response_body
    from app.runtime.native_http_transport import StreamingUpstream as _StreamingUpstream
    from fastapi import HTTPException as _HTTPException

    if stream and plan.operation == "anthropic_count_tokens":
        raise _HTTPException(
            status_code=400, detail="Token counting does not support streaming.",
        )
    if plan.needs_anthropic_conversion:
        from app.modules.guard.tools_anthropic_converter import (
            canonical_to_anthropic as _canonical_to_anthropic,
        )
        body = _canonical_to_anthropic(body)

    # X5 — worker-lifetime singleton, NOT a per-request instance. The
    # transports inside share one httpx.AsyncClient pool across every
    # request handled by this worker, so ``max_connections=100`` is a
    # real worker-wide bound (was previously per-request → unbounded).
    coordinator = await get_coordinator()
    try:
        plan.dispatched = True
        result = await coordinator.execute(
            resolved=plan.resolved,
            operation=plan.operation,
            payload=body,
            credential_resolver=plan.credential_resolver,
            vendor_credential_resolver=plan.vendor_credential_resolver,
            stream=stream,
            policy_check=policy_check,
            client_headers=client_headers,
        )
    except _AllAttemptsFailed as exc:
        plan.last_meta = {
            "winning_target_id": None,
            "attempt_count": len(exc.attempts),
            # Session 6J reviewer #5: same operation preservation as the
            # success path.
            "operation": plan.operation,
            "attempts": [
                {
                    "target_id": a.target_id,
                    "transport": a.transport,
                    "provider_or_integration": a.provider_or_integration,
                    "succeeded": a.succeeded,
                    "error_class": a.error_class,
                    # #2209 Session 6D — carries the failed-attempt provider
                    # response body (base64) so per-attempt accounting can
                    # normalize + price it. Absent on success; the winner's
                    # bytes live in the handler-owned upstream snapshot.
                    "response_bytes_b64": a.response_bytes_b64,
                    # Session 6F reviewer #3 — per-attempt model attribution.
                    "model": getattr(a, "model", None),
                    "operation": plan.operation,
                }
                for a in exc.attempts
            ],
        }
        # X1 — if every attempt failed with a PolicyBlock, surface as
        # a 451 (unavailable-for-legal-reasons) rather than 502
        # (upstream unreachable). The two states are semantically
        # distinct: 502 means "your model is fine, our infra failed";
        # 451 means "your model is refused by policy" — retrying won't
        # help. The last PolicyBlock's error_summary carries the rule
        # id so the client sees which rule fired.
        if exc.attempts and all(a.error_class == "PolicyBlock" for a in exc.attempts):
            last = exc.attempts[-1]
            raise _HTTPException(
                status_code=451,
                detail=(
                    f"All Gateway v2 targets refused by policy: "
                    f"{last.error_summary or 'no matching target permitted'}"
                ),
            ) from exc
        # The provider answered with a 4xx: surface it instead of a blanket 502
        # (SDKs auto-retry 502s, and the client can't fix what it can't see).
        last = exc.attempts[-1] if exc.attempts else None
        upstream = last.upstream_status if last is not None else None
        if last is not None and upstream is not None and 400 <= upstream < 500:
            where = (
                f"target '{last.target_id}' on Gateway profile '{plan.resolved.profile.name}' "
                f"(HTTP {upstream})"
            )
            if upstream in (401, 403):
                # Dead/rotated profile credential: operator config problem → 424.
                # Provider text omitted on purpose — auth errors can echo key fragments.
                raise _HTTPException(
                    status_code=424,
                    detail=(
                        f"Provider {last.provider_or_integration} rejected the credential for "
                        f"{where}. Rotate that provider credential in Conduct."
                    ),
                ) from exc
            from app.runtime.attempt_coordinator import provider_error_message
            reason = provider_error_message(last.response_bytes_b64)
            raise _HTTPException(
                status_code=upstream,
                detail=(
                    f"Provider {last.provider_or_integration} rejected the request for {where}"
                    + (f": {reason}" if reason else ".")
                ),
            ) from exc
        raise _HTTPException(
            status_code=502,
            detail=(
                f"All Gateway v2 targets failed for revision "
                f"{plan.resolved.revision_id}: {exc}"
            ),
        ) from exc

    plan.last_meta = {
        "winning_target_id": result.winning_target_id,
        "attempt_count": len(result.attempts),
        # #2209 Session 6J reviewer #5 (#2221 review at bbcb5388): the
        # reconciler needs the original operation to pick the right
        # normalizer family (OpenAI Chat vs Responses). Carrying it in
        # routing_meta means the audit row already has what the
        # reconciler needs; no schema change required.
        "operation": plan.operation,
        "attempts": [
            {
                "target_id": a.target_id,
                "transport": a.transport,
                "provider_or_integration": a.provider_or_integration,
                "succeeded": a.succeeded,
                "error_class": a.error_class,
                # #2209 Session 6F reviewer #2 (#2221 review at 1219d734):
                # the failure list already carries response_bytes_b64 for
                # AllAttemptsFailed; the success list must too. When
                # attempt A fails and B succeeds, A's captured error
                # envelope is real usage that per-attempt accounting
                # needs to price. Prior code dropped it here.
                "response_bytes_b64": a.response_bytes_b64,
                # Session 6F reviewer #3: per-attempt model attribution.
                # AttemptRecord gains ``model`` so a mixed-target profile
                # can price each receipt against its actual model rates.
                "model": getattr(a, "model", None),
                "operation": plan.operation,
            }
            for a in result.attempts
        ],
    }

    if isinstance(result.response, _StreamingUpstream):
        response = _build_v2_stream_response(result.response, capture=plan.upstream_body)
        if plan.needs_anthropic_conversion:
            from app.modules.guard.tools_anthropic_converter import anthropic_stream_to_canonical
            response.body_iterator = anthropic_stream_to_canonical(response.body_iterator)
        return response
    if stream:
        raise _HTTPException(
            status_code=502, detail="Upstream did not return a streaming response.",
        )
    _resp_body = coerce_response_body(result.response)
    plan.upstream_body.extend(json.dumps(_resp_body).encode())
    if plan.needs_anthropic_conversion and isinstance(_resp_body, dict):
        from app.modules.guard.tools_anthropic_converter import (
            anthropic_to_canonical as _anthropic_to_canonical,
        )
        _resp_body = _anthropic_to_canonical(_resp_body)
    return JSONResponse(content=_resp_body)


# hop-by-hop headers httpx already handles or Starlette re-emits — never
# forward these back to the client verbatim, or the chunked framing
# breaks and the client sees Content-Length mismatch errors.
_STREAM_HOP_HEADERS: frozenset[str] = frozenset({
    "content-length",
    "content-encoding",
    "transfer-encoding",
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "upgrade",
})


def _build_v2_stream_response(upstream, *, capture=None) -> StreamingResponse:
    """Wrap a ``StreamingUpstream`` in a Starlette ``StreamingResponse``.

    Generator yields raw bytes as they arrive and closes the httpx
    response in ``finally`` so a dropped client connection doesn't leak
    a pooled slot. Vendor content-type is preserved (SSE for Anthropic /
    OpenAI) so downstream SDKs consume the stream unchanged.
    """
    async def _gen():
        try:
            async for chunk in upstream.response.aiter_bytes():
                if capture is not None:
                    capture.extend(chunk)
                yield chunk
        finally:
            try:
                await upstream.response.aclose()
            except Exception:
                log.warning(
                    "gateway.v2.native_http.stream_close_failed",
                    provider=upstream.provider,
                )

    forwarded_headers = {
        k: v
        for k, v in upstream.headers.items()
        if k.lower() not in _STREAM_HOP_HEADERS
    }
    return StreamingResponse(
        _gen(),
        status_code=upstream.status_code,
        headers=forwarded_headers,
        media_type=upstream.headers.get("content-type"),
    )


def _build_stream_tool_policy_check(
    *,
    workspace_id: str,
    clerk_user_id: str | None,
    agent_identity_id: str | None,
    agent_risk_tier: str | None,
    ai_tool: str | None,
    provider: str,
    model: str,
    body: dict,
    routing_meta: dict | None,
):
    """#2173 P1 — closure invoked by ``tools_stream_gate`` on assembled tool_calls.

    Runs the same composed-engine gate that ``_apply_response_gate``
    runs on the non-streaming path — the callback signature keeps this
    module out of ``tools_stream_gate.py`` (which stays pure). Returns
    ``(allow, block_reason)`` — the wrapper emits an in-band error
    frame + marks the outcome as ``POLICY_BLOCK`` when ``allow=False``.

    Called once per choice at flush time (finish_reason=tool_calls),
    after the argument redactor has run. Sees the redacted tool_calls
    only — same view as the client would have seen.
    """
    from fastapi.concurrency import run_in_threadpool
    from app.core.database import SessionLocal as _SL
    from app.core.workspace_context import set_workspace_rls
    from app.runtime.accounting.estimator import estimate_tokens as _estimate_tokens
    from app.guard.policy import evaluate_composed as _eval_composed
    from app.guard.policy_types import PolicyAction as _PA, PolicyContext as _PolicyContext

    _tool_names_offered_snapshot = (routing_meta or {}).get("tools_offered") or None
    _tool_names_supplied_snapshot = (
        (routing_meta or {}).get("tool_names_supplied")
        or (routing_meta or {}).get("tool_results_supplied")
        or None
    )

    async def _check(assembled_calls: list[dict]) -> tuple[bool, str | None]:
        # Names of tools the model actually generated in THIS response.
        # Feeds match_tool_name_generated selectors.
        gen_names = [
            (tc.get("function") or {}).get("name", "")
            for tc in assembled_calls
            if isinstance(tc, dict)
        ]
        gen_names = [n for n in gen_names if n] or None

        # Synthesize a response body shape so composed rules that read
        # response-side context (choices[].message.tool_calls[]) can
        # match. Kept minimal — we don't fake usage.
        synthetic_response_body = {
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": assembled_calls,
                },
            }],
        }

        def _eval_owned() -> tuple[bool, str | None]:
            _db_local = _SL()
            try:
                set_workspace_rls(_db_local, workspace_id)
                _ctx = _PolicyContext(
                    workspace_id=workspace_id,
                    clerk_user_id=clerk_user_id,
                    agent_identity_id=agent_identity_id,
                    provider=provider,
                    model=model,
                    body=body,
                    input_tokens=_estimate_tokens(body).input_tokens,
                    db=_db_local,
                    gate="response",
                    risk_tier=agent_risk_tier,
                    ai_tool=ai_tool or None,
                    tool_names_offered=_tool_names_offered_snapshot,
                    tool_names_generated=gen_names,
                    tool_names_supplied=_tool_names_supplied_snapshot,
                    response_body=synthetic_response_body,
                )
                pd = _eval_composed(_ctx)
            finally:
                _db_local.close()
            if pd.action == _PA.BLOCK:
                return False, pd.reason or pd.rule_id or "response_policy_block"
            return True, None

        try:
            return await run_in_threadpool(_eval_owned)
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "guard.gateway.stream_tool_policy_check_failed",
                workspace_id=workspace_id, provider=provider, model=model,
                err=str(exc),
            )
            # Fail closed on eval error — same posture as non-streaming.
            return False, f"policy_eval_error: {type(exc).__name__}"

    return _check


def _merge_routing_meta(current: dict | None, updates: dict) -> dict:
    """Return ``current`` merged with ``updates`` — never mutates in
    place. ``routing_meta`` gets threaded through the audit args tuple
    and downstream lifecycle finalize; a shared mutable reference would
    cross the request/audit boundary and could race the background
    finalize task."""
    return {**(current or {}), **updates}


def _derive_v2_finalize_args(
    *,
    post_gate_response,
    pre_gate_upstream_body,
    ingress_decision: str,
    ingress_rule_id: str | None,
) -> dict:
    """Pick the finalize params for a v2 request based on the post-gate
    response.

    Two knobs:

    1. Whether the response gate flipped the outcome to a block. Read
       from the response's ``status_code`` (>=400 = blocked).
    2. If blocked, the gate's ``rule_id`` from the 451 envelope wins
       over the ingress ``_audit_rule_id`` — otherwise the audit row
       would name the ingress rule for a response-gate block.

    Body bytes:
    - Blocked → use the pre-gate upstream body. The 451 envelope has
      no token usage; recording the block body drops cost accounting.
    - Ok → use the post-gate body (identical to upstream when no
      transformation ran).

    Kept pure so the block-branch is unit-testable without spinning up
    a Request / DB / gate.
    """
    status = getattr(post_gate_response, "status_code", 200)
    blocked = status >= 400

    if not blocked:
        try:
            body_bytes = (
                post_gate_response.body
                if hasattr(post_gate_response, "body") else None
            )
        except Exception:
            body_bytes = None
        return {
            "decision": ingress_decision,
            "execution_status": "ok",
            "rule_id": ingress_rule_id,
            "response_bytes": body_bytes,
        }

    # Blocked — extract the gate's rule_id from the 451 envelope shape
    # (``{"error": {"rule_id": ..., ...}}``). Any parse failure falls
    # back to the ingress rule id so the row still carries something.
    gate_rule_id = ingress_rule_id
    try:
        import json as _json
        gate_body = _json.loads(getattr(post_gate_response, "body", b"") or b"{}")
        candidate = gate_body.get("error", {}).get("rule_id")
        if candidate:
            gate_rule_id = candidate
    except Exception:
        pass

    return {
        "decision": "blocked",
        "execution_status": "blocked",
        "rule_id": gate_rule_id,
        "response_bytes": pre_gate_upstream_body,
    }
