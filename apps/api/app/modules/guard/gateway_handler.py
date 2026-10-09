"""Canonical Gateway request entry point.

Owns the full Gateway request lifecycle: authenticate the caller (member
token, agent identity, or run token), evaluate Guard policies, open a
durable-audit row via ``gateway_lifecycle``, forward to the vendor, apply
the response gate, and close the audit row. Legacy ``/proxy/*`` route
decorators in ``routers/proxy.py`` delegate here — no new Gateway behavior
is allowed to grow on that legacy surface.
"""
from __future__ import annotations

import asyncio
import time

from starlette.concurrency import run_in_threadpool
import uuid

import structlog
from fastapi import BackgroundTasks, Request
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import text

from app.core.config import settings
from app.modules.auth.federation.resolver import FederationDenied
from app.modules.guard.gateway_request_state import GatewayCall
from app.modules.guard.gateway_v2_plan import (  # noqa: F401 — re-exports
    _V2_HEADER_ALLOWLIST,
    _V2Plan,
    _build_policy_check,
    _build_v2_plan,
    _build_v2_plan_owned,
    _extract_cond_code,
    _v2_allowlisted_headers,
)
from app.modules.guard.gateway_v2_execute import (  # noqa: F401 — re-exports
    _STREAM_HOP_HEADERS,
    _build_stream_tool_policy_check,
    _build_v2_stream_response,
    _derive_v2_finalize_args,
    _execute_v2,
    _merge_routing_meta,
)
from app.modules.guard.gateway_v2_stream import (  # noqa: F401 — re-exports
    _close_stream_iterator,
    _wrap_stream_receipts,
    _wrap_v2_stream_finalize,
    _wrap_v2_stream_record_legacy,
)


log = structlog.get_logger(__name__)


def apply_tool_call_gate(
    response: JSONResponse,
    routing_meta: dict | None,
    *,
    workspace_id: str,
    provider: str,
    model: str,
) -> tuple[JSONResponse, dict | None]:
    """#2159 PR 2 — tool-call scanner + reason marker.

    Contract:
      - Parses ``response.body`` as JSON.
      - Walks ``choices[].message.tool_calls[].function.arguments``,
        redacting string leaves via ``tools_validator.scan_response_tool_calls``.
      - On ``RedactionFailure``: returns (502 envelope, routing_meta with
        ``response_gate_reason=validation_failure`` and empty
        ``tool_calls_generated``). Upstream cost stays on the audit row
        because inference already happened; only the tool_call is refused.
      - Otherwise: returns (response with redacted body substituted,
        routing_meta with ``tool_calls_generated`` populated).

    Never raises. The existing composed-engine ``_apply_response_gate``
    runs AFTER this helper — a 502 here short-circuits the gate; a
    successful scan hands off the sanitised body to the gate for
    policy evaluation. The gate's own 451 result is marked separately
    in the caller so the two ``response_gate_reason`` values stay
    distinct.
    """
    import json as _json_tc
    from app.modules.guard.tools_validator import (
        ResponseGateReason,
        scan_response_tool_calls,
    )

    try:
        _resp_parsed = _json_tc.loads(response.body or b"{}")
    except Exception:
        _resp_parsed = {}
    scan = scan_response_tool_calls(_resp_parsed)
    if scan.error is not None:
        log.warning(
            "guard.response.tool_args_validation_failed",
            workspace_id=workspace_id, provider=provider, model=model,
            source=scan.error.source, reason=scan.error.reason,
        )
        routing_meta = {
            **(routing_meta or {}),
            "response_gate_reason": ResponseGateReason.VALIDATION_FAILURE,
            "tool_calls_generated": [],
        }
        response = JSONResponse(
            status_code=502,
            content={
                "error": {
                    "type": "conduct_gateway_tool_arguments_validation_failed",
                    "message": (
                        "Tool_call arguments failed validation and cannot "
                        "be safely delivered. Upstream inference completed "
                        "and is billed; the tool call is refused."
                    ),
                    "detail": scan.error.reason,
                    "source": scan.error.source,
                    "gate": "response",
                }
            },
        )
        return response, routing_meta

    correlation_ids: dict[str, str] = {}
    if scan.generated_calls:
        # #2158 — assign a correlation id per generated tool_call.
        # Runtime executor reads the X-Conduct-Tool-Correlation-Ids
        # response header and attaches it to its own Flight Recorder
        # entry so both sides can be joined. Stored alongside
        # tool_calls_generated in routing_meta for audit-side lookup.
        from app.modules.guard.tools_validator import (
            generate_tool_call_correlation_ids as _gen_corr,
        )
        correlation_ids = _gen_corr(scan.generated_calls)
        routing_meta = {
            **(routing_meta or {}),
            "tool_calls_generated": scan.generated_calls,
            "tool_call_correlation_ids": correlation_ids,
        }

    if scan.scanned_body is not None and scan.scanned_body is not _resp_parsed:
        response = JSONResponse(
            status_code=response.status_code,
            content=scan.scanned_body,
        )

    if correlation_ids:
        # Attach correlation header on the outgoing response. Existing
        # headers preserved by JSONResponse are all defaults (content
        # type + length), so setting one custom header is safe.
        from app.modules.guard.tools_validator import (
            encode_correlation_header as _enc_corr,
        )
        response.headers["X-Conduct-Tool-Correlation-Ids"] = _enc_corr(correlation_ids)

    return response, routing_meta


async def handle_gateway_request(
    request: Request,
    background: BackgroundTasks,
    *,
    provider: str,
    upstream_path: str,
    auth_header_in: str,
    auth_header_out: str,
    auth_header_fallback: str | None = None,
    bearer: bool = False,
    canonical_profile: bool = False,
    operation: str = "inference",
) -> StreamingResponse | JSONResponse:
    """One implementation, three providers — only the URL + auth header shape differs."""
    # Helpers live in gateway_helpers.py (extracted 2026-09-17). Re-exports
    # come from their real home modules. routers/proxy.py is legacy and this
    # handler no longer depends on it.
    from app.core.auth import resolve_agent_token, token_is_expired
    from app.core.database import SessionLocal
    from app.core.workspace_context import set_workspace_rls
    from app.runtime.provider_transport import get_provider_transport_registry
    from app.guard.audit import record as _record_audit
    from app.runtime.accounting.estimator import estimate_tokens as _estimate_tokens
    from app.guard.policy import flatten_prompt as _flatten_prompt
    from app.guard.router import fail_closed as _fail_closed, upstream as _forward
    from app.modules.guard.gateway_helpers import (
        _apply_response_gate,
        _apply_tier_resolution,
        _apply_tier_resolution_owned,
        _extract_member_token,
        _infer_ai_tool,
        _inject_guidance,
        _redact_body,
        _resolve_gateway_auth,
        _upstream_api_key,
        _upstream_url,
        _vault_key,
        _wrap_streaming_response,
    )
    from app.modules.guard.gateway_attempt_outcome import merge_attempts as _merge_attempts  # #2403
    from app.modules.guard.gateway_attempt_outcome import served_model as _served_model, wrap_stream_finally
    from app.modules.guard import gateway_phase_ingress as _ingress
    from app.modules.guard import gateway_phase_routing as _routing

    started = time.monotonic()

    st = GatewayCall(
        request=request, background=background, provider=provider,
        upstream_path=upstream_path, auth_header_in=auth_header_in,
        auth_header_out=auth_header_out, auth_header_fallback=auth_header_fallback,
        bearer=bearer, canonical_profile=canonical_profile, operation=operation,
        started=started,
    )

    # 1. Member token / internal key — 401 before any admission state.
    _early = _ingress.extract_token(st)
    if _early is not None:
        return _early

    # PR 2 (#2056) admission state — kill switch: ADMISSION_ENABLED.
    _admission_ticket = None
    _admission_streamed = False
    _profile_rate_admission = None
    _profile_rate_streamed = False
    _v2_plan = None

    try:
        # 2. Identity → federation → admission acquire (gateway_phase_ingress).
        if (_early := await _ingress.resolve_caller(st, operation=operation)) is not None:
            return _early
        workspace_id, clerk_user_id = st.workspace_id, st.clerk_user_id
        _agent_identity_id, _agent_risk_tier = st.agent_identity_id, st.agent_risk_tier
        _federation, _admission_ticket = st.federation, st.admission_ticket
        from app.modules.auth.federation.gateway import recheck_gateway, delegated_policy_check

        # 3. Body → model routing → v2 plan (gateway_phase_routing).
        _early = await _routing.parse_and_route(st, build_v2_plan_owned=_build_v2_plan_owned)
        _v2_plan = st.v2_plan
        if _early is not None:
            return _early
        body, model, _routing_meta, ai_tool = st.body, st.model, st.routing_meta, st.ai_tool
        _tools_offered, _tool_names_supplied = st.tools_offered, st.tool_names_supplied

        # 4a/4b. User email, workflow-run headers, trial plan.
        await _routing.load_request_context(st)
        _user_email, _run_id, _workflow, _workflow_id = st.user_email, st.run_id, st.workflow, st.workflow_id
        _environment_id, _hook_session_id, _is_trial = st.environment_id, st.hook_session_id, st.is_trial

        # 4c. Pre-call Guard policy evaluation — composed engine (#1225 Phase 4)
        # P1 review fix — offloaded to threadpool with an owned session
        # (was sync DB-heavy eval on the event loop).
        prompt_summary = _flatten_prompt(body)[:200]

        def _eval_prompt_policy_owned():
            from app.core.database import SessionLocal as _SL
            from app.core.workspace_context import set_workspace_rls
            from app.guard.policy import evaluate_composed as _eval_composed
            from app.guard.policy_types import PolicyContext as _PolicyContext
            _db_local = _SL()
            try:
                set_workspace_rls(_db_local, workspace_id)
                _ctx = _PolicyContext(
                    workspace_id=workspace_id,
                    clerk_user_id=clerk_user_id,
                    agent_identity_id=str(_agent_identity_id) if _agent_identity_id else None,
                    provider=provider,
                    model=model,
                    body=body,
                    input_tokens=_estimate_tokens(body).input_tokens,
                    db=_db_local,
                    gate="prompt",
                    risk_tier=_agent_risk_tier,
                    ai_tool=ai_tool or None,
                    # #2159 PR 2 (#2156) — tool-name signals populated on
                    # the request-gate side. Empty list stays semantically
                    # distinct from None (unset) so rules can distinguish.
                    tool_names_offered=_tools_offered or None,
                    tool_names_supplied=_tool_names_supplied or None,
                )
                return _eval_composed(_ctx)
            finally:
                _db_local.close()

        _pd = await run_in_threadpool(_eval_prompt_policy_owned)
        decision = _pd.extras.get("raw") or {
            "action": _pd.action.value,
            "rule_id": _pd.rule_id,
            "message": _pd.reason,
            "matched_rules": _pd.matched_rules,
            "defense_score": _pd.defense_score,
            "inject_guidance": _pd.inject_guidance,
            "guidance": _pd.guidance,
            "rule": _pd.extras.get("rule"),
        }
        _action = _pd.action.value
        _guidance_text = _pd.guidance if _pd.inject_guidance else None

        if _pd.blocks:
            from app.modules.guard.routers._proxy_helpers import render_block as _render_block
            return _render_block(
                _pd, background, workspace_id, clerk_user_id, ai_tool, provider,
                model, body, prompt_summary, _user_email, _run_id, _workflow,
                _workflow_id, _hook_session_id, started, _record_audit, _fail_closed,
                is_trial=_is_trial,
                routing_meta=_routing_meta, agent_identity_id=_agent_identity_id,
                route=request.url.path,
            )

        if _pd.needs_approval:
            from app.modules.guard.routers._proxy_helpers import render_approval as _render_approval
            return _render_approval(
                _pd, background, workspace_id, clerk_user_id, ai_tool, provider,
                model, body, prompt_summary, _user_email, _run_id, _workflow,
                _workflow_id, _hook_session_id, started, _record_audit,
                routing_meta=_routing_meta, agent_identity_id=_agent_identity_id,
                route=request.url.path,
            )

        # Map internal action to audit decision string
        _audit_decision = "warned" if _action == "WARN" else "allowed"
        _audit_rule_id  = decision["rule_id"] if _action == "WARN" else None

        def _record_failure(status: int, message: str, *, rule_id: str | None = None) -> None:
            background.add_task(
                _record_audit,
                workspace_id, clerk_user_id, ai_tool, provider, model,
                "blocked" if status in (403, 429) else _audit_decision,
                rule_id or _audit_rule_id,
                int((time.monotonic() - started) * 1000),
                body=body, response_bytes=None, prompt_summary=prompt_summary,
                user_email=_user_email, conductai_run_id=_run_id,
                conductai_workflow=_workflow, conductai_workflow_id=_workflow_id,
                hook_session_id=_hook_session_id, routing_meta=_routing_meta,
                execution_status="error", result_summary=f"HTTP {status}: {message}"[:500],
                agent_identity_id=str(_agent_identity_id) if _agent_identity_id else None,
                route=request.url.path,
            )

        # v2 checks shared profile and agent-wide quotas atomically.
        # Legacy traffic keeps its original workspace/agent limits.
        from app.modules.guard.rate_limit import check_rate_limit as _check_rate_limit
        def _rate_check_owned():
            from app.core.database import SessionLocal as _SL
            from app.core.workspace_context import set_workspace_rls
            _db_local = _SL()
            try:
                if _v2_plan is not None:
                    from app.modules.guard.gateway_profile_rate_limit import check_profile_rate_limit, reserved_profile_tokens
                    return check_profile_rate_limit(
                        _db_local, workspace_id=workspace_id,
                        profile_id=getattr(_v2_plan.resolved, "profile_id", None),
                        revision_id=_v2_plan.resolved.revision_id,
                        agent_identity_id=str(_agent_identity_id) if _agent_identity_id else None,
                        reserved_tokens=reserved_profile_tokens(body, _v2_plan.operation),
                    )
                set_workspace_rls(_db_local, workspace_id)
                return _check_rate_limit(
                    _db_local,
                    workspace_id=workspace_id,
                    agent_identity_id=str(_agent_identity_id) if _agent_identity_id else None,
                    input_tokens=_estimate_tokens(body).input_tokens,
                    fail_closed=canonical_profile and settings.environment == "production",
                )
            finally:
                _db_local.close()
        _rate = await run_in_threadpool(_rate_check_owned)
        _profile_rate_admission = getattr(_rate, "admission", None)
        if _rate.limited:
            log.info(
                "guard.proxy.rate_limited",
                workspace_id=workspace_id,
                scope=_rate.scope,
                metric=_rate.metric,
                limit=_rate.limit,
                current=_rate.current,
            )
            status = getattr(_rate, "status", 429)
            _record_failure(status, _rate.reason, rule_id="rate-limit")
            response = _fail_closed(status, _rate.reason)
            response.headers["Retry-After"] = str(getattr(_rate, "retry_after", 60))
            return response

        # 5. Vault lookup — for BYO gateways: upstream_key authenticates with the gateway,
        # vault_key is the real vendor key the gateway forwards to Anthropic/OpenAI.
        #
        # X3 — legacy credential resolution is v1-only. v2 targets
        # carry their own ``credential_ref`` pointing at Vault; the
        # resolver was built in step 4 (``_build_v2_plan``). Running
        # this block for v2 traffic was dead weight AND actively
        # broke v2-only workspaces: if a workspace never provisioned
        # a v1 ``ANTHROPIC_API_KEY`` / ``OPENAI_API_KEY`` but did
        # publish a v2 profile with valid Vault refs, the 503 below
        # fired before ``_execute_v2`` ever ran. Skip the whole block
        # when ``_v2_plan`` is in play.
        upstream = None
        _upstream_key = None
        _vault_key_val = None
        transport = None
        real_key = None
        if _v2_plan is None:
            # PR 2 Commit 3 — three sequential DB round-trips run off the
            # event loop in one bounded session.
            from app.modules.guard.gateway_helpers import _resolve_upstream_credentials
            upstream, _upstream_key, _vault_key_val = await run_in_threadpool(
                _resolve_upstream_credentials,
                workspace_id, provider, _environment_id,
            )
            transport = get_provider_transport_registry().for_provider(provider)
            if canonical_profile:
                # PR 3 fix — canonical-profile TransportResolver runs
                # off the event loop with its own session.
                from app.modules.guard.gateway_runtime import TransportResolver
                def _resolve_transport_owned():
                    from app.core.database import SessionLocal as _SL
                    from app.core.workspace_context import set_workspace_rls
                    _db_local = _SL()
                    try:
                        set_workspace_rls(_db_local, workspace_id)
                        return TransportResolver().resolve(
                            _db_local, workspace_id, provider, _environment_id,
                        )
                    finally:
                        _db_local.close()
                profile_runtime = await run_in_threadpool(_resolve_transport_owned)
                if profile_runtime:
                    upstream = profile_runtime.upstream_url or upstream
                    _upstream_key = profile_runtime.api_key or _upstream_key
                    transport = profile_runtime.transport
                    if profile_runtime.profile.provider == "litellm":
                        _vault_key_val = None
                    real_key = _upstream_key or _vault_key_val
                else:
                    real_key = _upstream_key or _vault_key_val
            else:
                real_key = _upstream_key or _vault_key_val
            if not real_key:
                # #1567 PR 2: trial workspaces with no BYO key fall through to a
                # platform-funded env key, fenced by plan + provider + identity + daily cap.
                # PR 3 fix — trial key resolution off event loop.
                from app.modules.guard.trial_upstream import resolve_trial_key
                _aid = str(_agent_identity_id) if _agent_identity_id else None
                def _resolve_trial_key_owned():
                    from app.core.database import SessionLocal as _SL
                    from app.core.workspace_context import set_workspace_rls
                    _db_local = _SL()
                    try:
                        set_workspace_rls(_db_local, workspace_id)
                        return resolve_trial_key(
                            _db_local, workspace_id, provider, _aid,
                        )
                    finally:
                        _db_local.close()
                _trial_key, _trial_status = await run_in_threadpool(_resolve_trial_key_owned)
                if _trial_status == "expired":
                    _record_failure(401, "trial_expired", rule_id="trial-expired")
                    return _fail_closed(
                        401,
                        "trial_expired: 7-day trial ended. Add your own key in Settings → Environments.",
                    )
                if _trial_status == "exceeded":
                    _record_failure(429, "trial_exceeded", rule_id="trial-quota")
                    return _fail_closed(
                        429,
                        "trial_exceeded: daily trial quota hit. Add your own key in Settings → Environments.",
                    )
                real_key = _trial_key
            if not real_key:
                _record_failure(503, f"No {provider} API key configured", rule_id="credential-missing")
                return _fail_closed(
                    503,
                    f"No API key configured — add {provider.upper()}_API_KEY in Settings → Environments, "
                    f"or set LLM_UPSTREAM_API_KEY in Settings → Proxy.",
                )
        # 5.5 Redact secrets from body before forwarding — runs after policy eval so
        # credential-leak rules still fire first and can block.
        if operation == "inference":
            body, _redacted = _redact_body(body)
            if _redacted:
                log.info("guard.proxy.redacted", types=_redacted, workspace_id=workspace_id)

        # 5.6 Inject guidance to model when rule has inject_guidance=true (#1141).
        # Fires for warn/audit/allow paths — block path is handled above via response body.
        if _guidance_text and operation == "inference":
            body = _inject_guidance(body, _guidance_text, provider)
            log.info("guard.proxy.guidance_injected",
                     rule_id=decision.get("rule_id"), workspace_id=workspace_id)

        # 6. Forward + stream back. Use a fresh DB session inside the background task.
        is_stream = bool(body.get("stream"))
        # Pass through all vendor-specific headers the SDK sends (anthropic-beta,
        # openai-organization, openai-project, etc.) minus the ones we own.
        _skip = {
            auth_header_in,
            auth_header_fallback,
            "host",
            "content-length",
            "transfer-encoding",
            "connection",
            "content-type",
            "accept",
            "user-agent",
            "conduct-subject-token",
            "conduct-federation-connection",
        }
        extra_headers = {
            k.lower(): v for k, v in request.headers.items()
            if k.lower() not in _skip and not k.lower().startswith("x-conduct")
        }
        # #1959 durable audit lifecycle. All logic (insert_accepted +
        # fail-closed decision + whole-request renewal) lives in
        # gateway_lifecycle so new Gateway behavior never grows in the
        # legacy proxy.py file. This handler just threads the resulting
        # row_id through the existing audit_args tuple at index 18.
        #
        # P2: merge the client's X-Request-Id into routing_meta *at the
        # caller* so the enriched dict is what flows through open + audit
        # + downstream finalize. Prior split (writer enriched, caller kept
        # original) meant audit.finalize's ``routing_meta = CAST(:routing
        # AS jsonb)`` UPDATE clobbered client_request_id back out on the
        # finalized row.
        _client_request_id = request.headers.get("x-request-id") or None
        if _client_request_id:
            _routing_meta = {**(_routing_meta or {}), "client_request_id": _client_request_id}

        from app.modules.guard.gateway_lifecycle import (
            open_durable_row as _open_durable,
            close_durable_row as _close_durable,
            finalize_durable_row as _finalize_durable_row,
        )
        _durable = await _open_durable(
            workspace_id=workspace_id,
            clerk_user_id=clerk_user_id,
            ai_tool=ai_tool,
            provider=provider,
            model=model,
            body=body,
            prompt_summary=prompt_summary,
            user_email=_user_email,
            agent_identity_id=str(_agent_identity_id) if _agent_identity_id else None,
            route=request.url.path,
            hook_session_id=_hook_session_id,
            routing_meta=_routing_meta,
            conductai_run_id=_run_id,
            conductai_workflow=_workflow,
            conductai_workflow_id=_workflow_id,
            request_correlation_id=None,  # already merged into _routing_meta above
            idempotency_key=_client_request_id,  # #2403 item 1
        )
        if _durable.fail_response is not None:
            return _durable.fail_response
        _durable_row_id = _durable.row_id
        # R5 fix (reviewer P1): the reservation row and the drawer query
        # correlate via the audit row's request_id (not its row_id).
        # The lifecycle mints request_id even when durable audit is off.
        # Keep the row-id fallback for older lifecycle integrations.
        _audit_request_id = _durable.request_id or _durable_row_id

        # ── PR-A2b: pre-flight budget reservation ─────────────────────
        # Reserve applicable hard-cap budgets before dispatch. The helper
        # itself checks ``BUDGET_LEDGER_ENABLED`` and returns DISABLED
        # when off, so zero behavior change until ops flips the flag on.
        # Fail-CLOSED: any non-ACCEPTED outcome closes the audit row and
        # returns a budget-block response (402/503, see helper).
        from app.modules.guard.gateway_lifecycle import (
            budget_block_response as _budget_block_response,
            estimate_budget_cents as _estimate_budget_cents,
            reserve_budgets_for_request as _reserve_budgets_for_request,
            ReserveOutcome as _ReserveOutcome,
            settle_reservations as _settle_reservations,
        )
        try:
            from app.modules.guard.gateway_lifecycle import (
                estimate_budget_micros as _estimate_budget_micros,
            )
        except ImportError:  # backward compat if module hasn't been redeployed
            _estimate_budget_micros = None
        _reservations: list = []
        _dispatched = False  # flipped to True right before any upstream call
        _actual_cents: int | None = None
        _actual_micros: int | None = None  # R9 (reviewer P1)
        # R3 fix (reviewer P1): reserve owns its own session lifecycle
        # inside a threadpool call. No shared session held across the
        # upstream await, no sync SQL/Redis on the event loop.
        def _reserve_sync_owned():
            _db = SessionLocal()
            try:
                return _reserve_budgets_for_request(
                    db=_db,
                    workspace_id=workspace_id,
                    agent_identity_id=(
                        str(_agent_identity_id) if _agent_identity_id else None
                    ),
                    transport="gateway",
                    client_tool=(ai_tool if ai_tool and ai_tool != "gateway" else None),
                    clerk_user_id=clerk_user_id,
                    estimated_cents=_estimate_budget_cents(body, provider, model, ai_tool),
                    # R9 (reviewer P1): microdollar precision so the ledger's
                    # Redis counter accumulates sub-cent requests correctly
                    # instead of rounding to zero.
                    estimated_micros=(
                        _estimate_budget_micros(body, provider, model, ai_tool)
                        if _estimate_budget_micros is not None
                        else None
                    ),
                    request_id=_audit_request_id,
                )
            finally:
                try:
                    _db.close()
                except Exception:
                    pass
        try:
            _reserve_result = await run_in_threadpool(_reserve_sync_owned)
        except Exception as _reserve_exc:  # noqa: BLE001
            log.warning("guard.gateway.reserve_wire_raised", err=str(_reserve_exc))
            # R7 fix (reviewer P1): the exception path used to leave
            # ``_reserve_result = None`` and fall through to dispatch —
            # a fail-OPEN branch that bypassed hard-cap enforcement
            # whenever the helper raised (bad SessionLocal, transient
            # DB blip, estimator error). Represent unexpected failures
            # as a synthetic DB_ERROR so the same rejection path fires
            # UNLESS the ledger is entirely disabled (flag off preserves
            # pre-PR-A behavior — no enforcement, no synthetic reject).
            from app.core.budget_ledger import enabled as _ledger_enabled
            if _ledger_enabled():
                from app.modules.guard.gateway_lifecycle import (
                    ReserveBudgetsResult as _RBR,
                )
                _reserve_result = _RBR(
                    outcome=_ReserveOutcome.DB_ERROR,
                    error=f"reserve raised: {type(_reserve_exc).__name__}",
                )
            else:
                _reserve_result = None
        # Reserve failed = fail-closed reject (any non-ACCEPTED outcome).
        if _reserve_result is not None and _reserve_result.outcome in (
            _ReserveOutcome.EXCEEDED,
            _ReserveOutcome.NOT_READY,
            _ReserveOutcome.REDIS_DOWN,
            _ReserveOutcome.DB_ERROR,
        ):
            # R6 fix (reviewer P1): finalize the audit row as blocked
            # BEFORE cancelling the renewal task. Previously the row
            # stayed in 'accepted' state until lease expiry; the
            # reconciler then reported 'orphaned' instead of the real
            # refusal outcome. Rule_id encodes the specific refusal
            # so Flight Recorder + drawer can label it correctly.
            _refusal_rule = {
                _ReserveOutcome.EXCEEDED:   "guard.budget_cap_exceeded",
                _ReserveOutcome.NOT_READY:  "guard.budget_ledger_not_ready",
                _ReserveOutcome.REDIS_DOWN: "guard.budget_ledger_unavailable",
                _ReserveOutcome.DB_ERROR:   "guard.budget_ledger_error",
            }[_reserve_result.outcome]
            if _durable_row_id:
                try:
                    await _finalize_durable_row(
                        row_id=_durable_row_id,
                        workspace_id=workspace_id,
                        decision="blocked",
                        provider=provider,
                        model=model,
                        body=body,
                        response_bytes=None,
                        duration_ms=int((time.monotonic() - started) * 1000),
                        rule_id=_refusal_rule,
                        routing_meta=_routing_meta,
                        execution_status="error",
                        result_summary=_reserve_result.error,
                        clerk_user_id=clerk_user_id,
                        ai_tool=ai_tool,
                        user_email=_user_email,
                    )
                except Exception:
                    log.exception(
                        "guard.gateway.refusal_finalize_failed",
                        row_id=_durable_row_id,
                        outcome=_reserve_result.outcome.value,
                    )
            await _close_durable(_durable)
            return _budget_block_response(_reserve_result)
        if _reserve_result is not None:
            _reservations = _reserve_result.reservations or []

        # P1: forward + response-gate must run under an exception-safe
        # lifecycle. Prior structure had close_durable_row *after* the
        # gate block, so any exception (or cancellation) between here and
        # the close call leaked the whole-request heartbeat: the renewal
        # task kept renew_lease-ing an abandoned row forever, preventing
        # the reconciler from ever flipping it. Guarantees now:
        #   - close_durable_row runs on every exit path (finally).
        #   - On exception, best-effort finalize with 'error' / 'interrupted'
        #     so the row lands terminated immediately instead of waiting on
        #     the reconciler's lease-expiry sweep.
        import asyncio as _asyncio
        # X4 — set before the try/finally so ``finally: _close_durable``
        # can read it even if an early raise skips the wrap.
        _v2_stream_wrapped = False
        _tool_stream_outcome = None  # set inside the streaming tool-gate branch
        # Same reason — the finally block down at ~line 1374 references
        # ``_response`` when computing actuals for settle. Any raise
        # inside the try (v2 502 from _execute_v2, v1 forwarder error,
        # etc.) leaves the assignment unbound and Python raises
        # UnboundLocalError from the finally, masking the real
        # HTTPException as a generic 500. Initialise here so the
        # finally can guard via ``if _response is not None``.
        _response = None
        _v2_upstream_body_bytes = None
        try:
            if _v2_plan is not None:
                # #2004 Phase 1 — v2 executes the coordinator + LiteLLM SDK
                # transport inside the same lifecycle as v1. Same audit row,
                # same response gate, same finalize path — only the actual
                # upstream call differs. Finalize is intentionally deferred
                # to AFTER the response gate below so a blocked response
                # doesn't land on top of a pre-gate "ok" row.
                #
                # PR 2.5 — streaming: pass ``stream`` down so the coordinator +
                # native_http transport can return a live StreamingResponse.
                # Non-streaming returns a JSONResponse (same shape as before).
                #
                # X1 — per-target policy re-eval. The ingress policy eval
                # (line ~339) runs against the cond-* alias; the transport
                # substitutes ``target.model`` before wire. Any rule keyed
                # on the real target model would be bypassed by the alias
                # otherwise. Build a closure the coordinator calls per
                # target; block → skip target (records PolicyBlock attempt);
                # all blocked → AllAttemptsFailed → 451 to the client.
                _policy_check = _build_policy_check(
                    workspace_id=workspace_id,
                    clerk_user_id=clerk_user_id,
                    agent_identity_id=(
                        str(_agent_identity_id) if _agent_identity_id else None
                    ),
                    fallback_provider=provider,
                    body=body,
                    risk_tier=_agent_risk_tier,
                    ai_tool=ai_tool,
                )
                # X7 — vendor-specific client headers (``anthropic-beta``,
                # ``openai-organization``, ...) reach v2 targets via a
                # v2-side allowlist (stricter than v1's blanket forward).
                _v2_client_headers = _v2_allowlisted_headers(extra_headers)
                _policy_check = delegated_policy_check(_policy_check, _federation)
                # ── PR-A2b: dispatch boundary ──
                # Flip BEFORE bytes fly. Any exception past this point
                # is treated as "may have dispatched" -> settle marks
                # PENDING_RECONCILER (never releases, reconciler owns
                # cleanup). This is intentionally over-conservative for
                # correctness: releasing after real spend would silently
                # drop billed cost.
                _dispatched = True
                _response = await _execute_v2(
                    plan=_v2_plan, body=body, stream=is_stream,
                    policy_check=_policy_check,
                    client_headers=_v2_client_headers,
                )
                # Reflect coordinator attempt records back into routing_meta
                # so the durable audit row lands with the full attempt list.
                _routing_meta = _merge_routing_meta(_routing_meta, _v2_plan.last_meta)
                # Snapshot the upstream body BEFORE the response gate runs.
                # If the gate blocks, `_response` will be replaced with a
                # 451 error envelope carrying no token usage. Finalize needs
                # the upstream bytes so cost + token accounting still work
                # even for a blocked response.
                #
                # For streaming: body isn't materialised until the stream
                # drains, so the pre-gate snapshot is unavailable here.
                # `_wrap_v2_stream_finalize` collects bytes as they pass
                # through and calls finalize on stream-close.
                if isinstance(_response, StreamingResponse):
                    _v2_upstream_body_bytes: bytes | None = None
                else:
                    try:
                        _v2_upstream_body_bytes = bytes(_v2_plan.upstream_body) or None
                    except Exception:
                        _v2_upstream_body_bytes = None
            else:
                # ── PR-A2b: dispatch boundary (legacy path) ──
                await run_in_threadpool(recheck_gateway, _federation)
                _dispatched = True
                _response = await transport.forward(
                    sender=_forward,
                    upstream=upstream,
                    path=upstream_path,
                    body=body,
                    real_key=real_key,
                    auth_header_out=auth_header_out,
                    bearer=bearer,
                    is_stream=is_stream,
                    extra_headers=extra_headers,
                    background=background,
                    audit_args=(
                        workspace_id,
                        clerk_user_id,
                        ai_tool,
                        provider,
                        model,
                        _audit_decision,
                        _audit_rule_id,
                        started,
                        body,
                        prompt_summary,
                        _user_email,
                        _run_id,
                        _workflow,
                        _workflow_id,
                        _hook_session_id,
                        _routing_meta,
                        # Phase 0 of #1959 — index 16 = resolved agent identity id. Read by
                        # router._schedule_audit and forwarded to audit.record so Gateway
                        # rows carry agent attribution end-to-end.
                        str(_agent_identity_id) if _agent_identity_id else None,
                        # Follow-up to #1971 — index 17 = FastAPI request path so
                        # /proxy/* vs /gateway/v1/* is queryable from audit rows.
                        request.url.path,
                        # Phase 2 of #1959 — index 18 = durable row id. When set,
                        # _schedule_audit dispatches to finalize() instead of record().
                        _durable_row_id,
                        _audit_request_id,
                    ),
                    upstream_api_key=_upstream_key,
                    vendor_key=_vault_key_val,
                    provider=provider,
                )
            # #2159 PR 2 — scan tool_call arguments BEFORE the existing
            # composed-engine gate. See ``apply_tool_call_gate`` for the
            # full contract (RedactionFailure → 502 terminal, redacted
            # body substituted otherwise, routing_meta updated with
            # generated_calls / response_gate_reason).
            if (
                operation == "inference"
                and not is_stream
                and isinstance(_response, JSONResponse)
                and _response.status_code < 400
            ):
                _response, _routing_meta = apply_tool_call_gate(
                    _response, _routing_meta,
                    workspace_id=workspace_id, provider=provider, model=model,
                )

            # #2155 — streaming tool_call gate. Same invariant as
            # non-streaming (no raw unsafe tool_call arguments reach the
            # client) but buffered across SSE deltas. Wraps the upstream
            # body_iterator so tool_call arg fragments are held until
            # ``finish_reason: "tool_calls"``, run through the same
            # validator + redactor as ``apply_tool_call_gate``, and
            # re-emitted as one synthetic frame. Text ``delta.content``
            # keeps streaming chunk-by-chunk unchanged.
            #
            # Runs BEFORE the buffered-text response gate wrap below so
            # that gate scans what the client will actually see (post-
            # rewriting). Gate is a no-op when body has no ``tools`` or
            # the flag is off — the shim'''s 400 rejection is the fallback.
            if (
                operation == "inference"
                and is_stream
                and isinstance(_response, StreamingResponse)
                and _response.status_code < 400
                and body.get("tools")
                and (settings.guard_gateway_tools_stream_enabled or _v2_plan is not None)
            ):
                from app.modules.guard.tools_stream_gate import (
                    wrap_tool_stream as _wrap_tool_stream_gate,
                    StreamGateOutcome as _StreamGateOutcome,
                )
                # #2173 P1 — shared outcome + composed-engine policy check.
                # Outcome mutates as the stream drains; _wrap_v2_stream_finalize
                # reads it below to set decision + execution_status and to
                # merge correlation_ids into routing_meta.
                _tool_stream_outcome = _StreamGateOutcome()
                _stream_operation = (
                    "openai_chat_completions" if _v2_plan and _v2_plan.needs_anthropic_conversion
                    else _v2_plan.operation if _v2_plan
                    else "openai_responses" if request.url.path.endswith("/responses")
                    else "anthropic_messages" if provider == "anthropic"
                    else "openai_chat_completions"
                )
                _stream_gate = _wrap_tool_stream_gate
                _stream_gate_args = {}
                if _stream_operation != "openai_chat_completions":
                    from app.modules.guard.tools_native_stream_gate import wrap_native_tool_stream
                    _stream_gate = wrap_native_tool_stream
                    _stream_gate_args = {"operation": _stream_operation}
                _stream_policy_check = _build_stream_tool_policy_check(
                    workspace_id=workspace_id,
                    clerk_user_id=clerk_user_id,
                    agent_identity_id=(
                        str(_agent_identity_id) if _agent_identity_id else None
                    ),
                    agent_risk_tier=_agent_risk_tier,
                    ai_tool=ai_tool,
                    provider=provider,
                    model=model,
                    body=body,
                    routing_meta=_routing_meta,
                )
                _response = StreamingResponse(
                    _stream_gate(
                        _response.body_iterator,
                        outcome=_tool_stream_outcome,
                        policy_check=_stream_policy_check,
                        **_stream_gate_args,
                    ),
                    media_type=_response.media_type,
                    headers=dict(_response.headers),
                    status_code=_response.status_code,
                )
                # `_tool_stream_outcome` stays in scope and gets passed
                # to `_wrap_v2_stream_finalize` below so the audit row's
                # decision / execution_status reflect the stream-gate
                # verdict instead of a false-positive "allowed / ok".

            # #1733 PR 4: response gate (non-streaming). Only runs when
            # the tool-call scanner above didn't already 502.
            if (
                operation == "inference"
                and not is_stream
                and isinstance(_response, JSONResponse)
                and _response.status_code < 400
            ):
                # PR 2 Commit 3 — response gate policy eval hits DB; offload.
                import functools as _ft
                # #2159 PR 2 (#2156) — thread tool-name signals from
                # routing_meta into the response-gate PolicyContext so
                # composed-engine rules can select on tool identity.
                _rm_now = _routing_meta or {}
                _tng_names = [
                    tc.get("name", "") for tc in (_rm_now.get("tool_calls_generated") or [])
                    if isinstance(tc, dict) and tc.get("name")
                ] or None
                _response = await run_in_threadpool(
                    _ft.partial(
                        _apply_response_gate,
                        _response,
                        workspace_id=workspace_id,
                        provider=provider,
                        model=model,
                        clerk_user_id=clerk_user_id,
                        agent_identity_id=_agent_identity_id,
                        agent_risk_tier=_agent_risk_tier,
                        ai_tool=ai_tool,
                        tool_names_offered=_rm_now.get("tools_offered") or None,
                        tool_names_generated=_tng_names,
                        tool_names_supplied=_rm_now.get("tool_names_supplied") or None,
                    )
                )
                # #2159 PR 2 — mark policy-block reason on audit when the
                # existing composed-engine gate 451'd. The scanner's
                # ``VALIDATION_FAILURE`` reason (above) is distinct from
                # this one so ops can tell the two apart.
                if _response.status_code == 451:
                    from app.modules.guard.tools_validator import (
                        ResponseGateReason as _RGR_block,
                    )
                    _routing_meta = {
                        **(_routing_meta or {}),
                        "response_gate_reason": _RGR_block.POLICY_BLOCK,
                    }
            # #1733 PR 5: response gate (streaming, buffered end-of-stream scan).
            elif (
                operation == "inference"
                and is_stream
                and isinstance(_response, StreamingResponse)
                and _response.status_code < 400
            ):
                _response = _wrap_streaming_response(
                    _response, workspace_id=workspace_id, provider=provider, model=model,
                    clerk_user_id=clerk_user_id, agent_identity_id=_agent_identity_id,
                    agent_risk_tier=_agent_risk_tier,
                    ai_tool=ai_tool,
                )
            # v2 finalize — deliberately AFTER the response gate so a
            # gate-blocked response doesn't land on top of a pre-gate "ok"
            # row. v1 gets its finalize inside transport.forward's
            # _schedule_audit path (which fires after the response is sent
            # in a BackgroundTask), so v1 isn't touched here.
            #
            # Streaming: finalize can't run synchronously — we haven't seen
            # the vendor bytes yet. Wrap the stream generator so finalize
            # fires when the stream drains (or client disconnects). Non-
            # streaming still finalizes inline.
            # X4 — streaming lifetime. When v2 wraps a stream, the response
            # generator (owned by ASGI) is what actually reads the vendor's
            # bytes AFTER this handler returns. Cancelling the renewal task
            # in the finally below would kill lease renewal before the body
            # is consumed — the reconciler would flip the row to orphaned
            # while it's still live. Transfer renewal ownership to the
            # stream wrapper: it inherits ``_durable``, keeps renewal
            # running while chunks flow, and cancels it after finalize
            # completes. ``_v2_stream_wrapped`` was initialised above the
            # try block; we only flip it True when a wrap actually happens.
            if _v2_plan is not None and _durable_row_id:
                if isinstance(_response, StreamingResponse):
                    _response = _wrap_v2_stream_finalize(
                        _response,
                        durable=_durable,
                        row_id=_durable_row_id,
                        workspace_id=workspace_id,
                        provider=provider,
                        model=_served_model(_routing_meta, model), model_alias=model,
                        operation=request.url.path,  # P1-4: real op for normalizer family
                        body=body,
                        ingress_decision=_audit_decision,
                        ingress_rule_id=_audit_rule_id,
                        routing_meta=_routing_meta,
                        clerk_user_id=clerk_user_id,
                        ai_tool=ai_tool,
                        user_email=_user_email,
                        started_monotonic=started,
                        # R4 fix (reviewer P1): transfer reservation
                        # ownership to the stream wrapper so settle
                        # fires after the stream drains (not when the
                        # handler returns and bytes still queued).
                        reservations=_reservations,
                        _routing_meta=_routing_meta,
                        # #2209 Session 6D — attribution.
                        conductai_run_id=_run_id,
                        hook_session_id=_hook_session_id,
                        agent_identity_id=_agent_identity_id,
                        # Wall-clock deadline for the stream body. The
                        # coordinator's ``wait_for`` only guarded header
                        # arrival; the stream body has no timeout of its
                        # own. Pull the profile's ``timeout_seconds`` as
                        # the total-request budget.
                        stream_deadline_seconds=(
                            _v2_plan.resolved.profile.timeout_seconds
                            if _v2_plan and _v2_plan.resolved else None
                        ),
                        tool_stream_outcome=_tool_stream_outcome,
                        upstream_capture=_v2_plan.upstream_body,
                    )
                    _v2_stream_wrapped = True
                else:
                    _v2_finalize = _derive_v2_finalize_args(
                        post_gate_response=_response,
                        pre_gate_upstream_body=_v2_upstream_body_bytes,
                        ingress_decision=_audit_decision,
                        ingress_rule_id=_audit_rule_id,
                    )
                    await _finalize_durable_row(
                        row_id=_durable_row_id,
                        workspace_id=workspace_id,
                        decision=_v2_finalize["decision"],
                        provider=provider,
                        model=_served_model(_routing_meta, model),
                        body=body,
                        response_bytes=_v2_finalize["response_bytes"],
                        duration_ms=int((time.monotonic() - started) * 1000),
                        rule_id=_v2_finalize["rule_id"],
                        routing_meta=_routing_meta,
                        execution_status=_v2_finalize["execution_status"],
                        result_summary=None,
                        clerk_user_id=clerk_user_id,
                        ai_tool=ai_tool,
                        user_email=_user_email,
                    )
            elif _v2_plan is not None:
                # X2 — v2 executed but durable-audit was off (v2 flag +
                # durable-audit flag are independent). Without this branch
                # every v2 request skipped audit entirely: durable-audit's
                # ``_open_durable`` short-circuited to an empty row, the
                # v2 finalize block above required ``_durable_row_id`` and
                # was skipped, and v1's ``_record_audit`` never ran because
                # the v2 branch took the request. Fall back to the legacy
                # single-phase ``_record_audit`` so v2 traffic always lands
                # a row while durable-audit stays optional per workspace.
                if isinstance(_response, StreamingResponse):
                    _response = _wrap_v2_stream_record_legacy(
                        _response,
                        background=background,
                        workspace_id=workspace_id,
                        clerk_user_id=clerk_user_id,
                        ai_tool=ai_tool,
                        provider=provider,
                        model=_served_model(_routing_meta, model),
                        body=body,
                        prompt_summary=prompt_summary,
                        user_email=_user_email,
                        conductai_run_id=_run_id,
                        conductai_workflow=_workflow,
                        conductai_workflow_id=_workflow_id,
                        hook_session_id=_hook_session_id,
                        routing_meta=_routing_meta,
                        agent_identity_id=(
                            str(_agent_identity_id) if _agent_identity_id else None
                        ),
                        route=request.url.path,
                        ingress_decision=_audit_decision,
                        ingress_rule_id=_audit_rule_id,
                        started_monotonic=started,
                        record_audit_fn=_record_audit,
                        tool_stream_outcome=_tool_stream_outcome,
                        upstream_capture=_v2_plan.upstream_body,
                        request_id=_audit_request_id,
                        # Z2 — deadline enforcement independent of audit
                        # flag. Same profile timeout the durable-on
                        # wrapper uses (Y3).
                        stream_deadline_seconds=(
                            _v2_plan.resolved.profile.timeout_seconds
                            if _v2_plan and _v2_plan.resolved else None
                        ),
                    )
                else:
                    _v2_finalize = _derive_v2_finalize_args(
                        post_gate_response=_response,
                        pre_gate_upstream_body=_v2_upstream_body_bytes,
                        ingress_decision=_audit_decision,
                        ingress_rule_id=_audit_rule_id,
                    )
                    background.add_task(
                        _record_audit,
                        workspace_id, clerk_user_id, ai_tool, provider, _served_model(_routing_meta, model),
                        _v2_finalize["decision"],
                        _v2_finalize["rule_id"],
                        int((time.monotonic() - started) * 1000),
                        body=body,
                        response_bytes=_v2_finalize["response_bytes"],
                        prompt_summary=prompt_summary,
                        user_email=_user_email,
                        conductai_run_id=_run_id,
                        conductai_workflow=_workflow,
                        conductai_workflow_id=_workflow_id,
                        hook_session_id=_hook_session_id,
                        routing_meta=_routing_meta,
                        execution_status=_v2_finalize["execution_status"],
                        request_id=_audit_request_id,
                        agent_identity_id=(
                            str(_agent_identity_id) if _agent_identity_id else None
                        ),
                        route=request.url.path,
                    )
        except BaseException as _forward_exc:  # noqa: BLE001 — need CancelledError too
            _routing_meta = _merge_attempts(_routing_meta, _v2_plan)  # #2403 item 4: all-failed attempts
            # Best-effort finalize so the row lands terminated immediately
            # instead of waiting on the reconciler's lease sweep. WHERE
            # lifecycle_state = 'accepted' in audit.finalize means this is
            # a no-op if the transport / _stream_chunks already finalized
            # (e.g. an error partway through streaming).
            _is_cancel = isinstance(_forward_exc, _asyncio.CancelledError)
            _exec_status = "interrupted" if _is_cancel else "error"
            _result_summary = (
                "Request cancelled during upstream forward"
                if _is_cancel
                else f"forward/gate exception: {type(_forward_exc).__name__}: {str(_forward_exc)[:400]}"
            )
            if _durable_row_id:
                try:
                    await _finalize_durable_row(
                        row_id=_durable_row_id,
                        workspace_id=workspace_id,
                        decision="error",
                        provider=provider,
                        model=_served_model(_routing_meta, model),
                        body=body,
                        response_bytes=None,
                        duration_ms=int((time.monotonic() - started) * 1000),
                        rule_id=None,
                        routing_meta=_routing_meta,
                        execution_status=_exec_status,
                        result_summary=_result_summary,
                        clerk_user_id=clerk_user_id,
                        ai_tool=ai_tool,
                        user_email=_user_email,
                    )
                except Exception:
                    log.exception("guard.gateway.error_finalize_failed", row_id=_durable_row_id)
            elif _v2_plan is not None:
                # Z1 fix — v2 executed with durable-audit OFF and the
                # request raised. Y2 originally used
                # ``background.add_task(_record_audit, ...)``, but FastAPI
                # only runs queued background tasks AFTER the response is
                # returned normally — a raise here propagates to FastAPI's
                # error handler, which returns a 5xx without draining the
                # queued task. Net effect: exception-path v2 requests with
                # durable-audit off wrote ZERO rows (reviewer's
                # ``recorded 0 times`` reproducer).
                #
                # Fix: run ``_record_audit`` synchronously in a thread
                # (``asyncio.to_thread``) BEFORE re-raising. Blocks the
                # exception path by the DB write duration, but that's
                # bounded by audit.record's own timeout and it's the only
                # way the row lands. Failure of the writer itself is
                # logged, never re-raised, so the original exception the
                # caller sees is preserved.
                try:
                    await _asyncio.to_thread(
                        _record_audit,
                        workspace_id, clerk_user_id, ai_tool, provider, _served_model(_routing_meta, model),
                        "error",
                        None,   # rule_id
                        int((time.monotonic() - started) * 1000),
                        body=body,
                        response_bytes=None,
                        prompt_summary=prompt_summary,
                        user_email=_user_email,
                        conductai_run_id=_run_id,
                        conductai_workflow=_workflow,
                        conductai_workflow_id=_workflow_id,
                        hook_session_id=_hook_session_id,
                        routing_meta=_routing_meta,
                        execution_status=_exec_status,
                        result_summary=_result_summary,
                        request_id=_audit_request_id,
                        agent_identity_id=(
                            str(_agent_identity_id) if _agent_identity_id else None
                        ),
                        route=request.url.path,
                    )
                except Exception:
                    log.exception("guard.gateway.v2.error_record_audit_failed")
            raise
        finally:
            # X4 — v2 streaming transfers renewal ownership to
            # ``_wrap_v2_stream_finalize``. Cancelling here would kill the
            # lease before ASGI consumes the body; the reconciler would
            # flip a live stream to orphaned. The wrapper's ``finally``
            # calls ``_close_durable`` after the stream drains.
            #
            # For every other exit path (non-streaming, error, cancel
            # before we ever wrapped), cancel here — idempotent.
            if not _v2_stream_wrapped:
                await _close_durable(_durable)

            # ── PR-A2b: settle reservations ────────────────────────
            # Idempotent + best-effort. Empty list is a NOOP (matches
            # ACCEPTED_NO_HARD_CAP / DISABLED). See helper docstring for
            # the dispatched x actual_cents truth table.
            # R4 fix (reviewer P1): for streaming responses the stream
            # wrapper (``_wrap_v2_stream_finalize``) owns settlement so
            # actual_cents reflects the drained body. Skip inline here
            # to avoid settling twice.
            # #2209 review #2 (#2221): compute cost OUTSIDE the reservation
            # gate so per-attempt receipts fire for every settled attempt,
            # not just reserved ones.
            _resp_bytes: bytes | None = None
            _new_engine_micros: int | None = None
            if _dispatched and not isinstance(_response, StreamingResponse):  # None = all attempts failed
                _snapshot = locals().get("_v2_upstream_body_bytes")
                if isinstance(_snapshot, (bytes, bytearray)) and _snapshot:
                    _resp_bytes = bytes(_snapshot)
                elif _response is not None and hasattr(_response, "body"):
                    try:
                        _resp_bytes = _response.body
                    except Exception:
                        _resp_bytes = None
                if (_resp_bytes is not None or (_routing_meta or {}).get("attempts")) and (_routing_meta or {}).get("billable", True) is not False:
                    try:
                        from app.runtime.accounting.settlement import (
                            settle_micros_for_attempts,
                        )
                        _attempts_for_settle = (
                            _routing_meta.get("attempts")
                            if isinstance(_routing_meta, dict)
                            else None
                        )
                        # P1-2: sum per-attempt priced micros using each
                        # attempt's actual provider/model + captured bytes.
                        # Falls back to winner-only when no attempts_meta.
                        _new_engine_micros = settle_micros_for_attempts(
                            attempts_meta=_attempts_for_settle,
                            request_provider=provider,
                            request_model=model,
                            operation=request.url.path,
                            winner_response_bytes=_resp_bytes,
                            strict=True,
                        )
                    except Exception:
                        log.exception(
                            "guard.gateway.settle_compute_failed",
                            workspace_id=str(workspace_id),
                            provider=provider,
                            model=model,
                        )

            # P1-D (post-review): persist per-attempt receipts BEFORE
            # settling reservations. Receipts are the durable, idempotent
            # authoritative record recovery reads (P1-1, P1-A). Settling
            # first and losing the write leaves committed spend with no
            # evidence to reconstruct from. Failure to persist any
            # expected receipt ⇒ skip settle; the reservation stays open
            # and the recovery sweep re-classifies from the receipt(s)
            # that eventually land.
            _receipts_durable = False
            _attempts_meta = (
                _routing_meta.get("attempts")
                if isinstance(_routing_meta, dict)
                else None
            )
            _expected_receipts = (
                len(_attempts_meta) if _attempts_meta else 1
            )
            if not isinstance(_response, StreamingResponse):
                try:
                    from app.runtime.accounting.shadow_writer import (
                        write_receipts_for_attempts as _write_shadow_attempts,
                    )
                    _reserved_micros: int | None = None
                    if _reservations:
                        try:
                            _reserved_micros = sum(
                                int(getattr(r, "estimated_micros", 0) or 0)
                                for r in _reservations
                            ) or None
                        except Exception:
                            _reserved_micros = None
                    # #2209 Session 6D — attribution: when this Gateway
                    # request originated from a workflow run (brain_block
                    # via gateway_profile adapter), the caller sent
                    # x-conductai-run-id — carry it onto the receipt so
                    # per-run cost aggregations JOIN cleanly.
                    _wf_run_uuid = None
                    if _run_id:
                        try:
                            import uuid as _uuid_wf
                            _wf_run_uuid = _uuid_wf.UUID(str(_run_id))
                        except (ValueError, TypeError):
                            _wf_run_uuid = None
                    _receipt_ids = await run_in_threadpool(
                        _write_shadow_attempts,
                        workspace_id=workspace_id,
                        request_id=_audit_request_id,
                        provider=provider,
                        model=_served_model(_routing_meta, model), model_alias=(model if _v2_plan is not None else None),
                        operation=request.url.path,
                        dispatched=_dispatched,
                        response_bytes=_resp_bytes,
                        reserved_microdollars=_reserved_micros,
                        developer_external_id=clerk_user_id,
                        agent_identity_id=_agent_identity_id,
                        source="gateway",
                        client_tool=ai_tool,
                        attempts_meta=_attempts_meta,
                        workflow_run_id=_wf_run_uuid,
                        hook_session_id=_hook_session_id,
                    )
                    _receipts_durable = (
                        _receipt_ids is not None
                        and len(_receipt_ids) >= _expected_receipts
                    )
                    if not _receipts_durable:
                        log.warning(
                            "guard.gateway.receipts_partial_skip_settle",
                            request_id=str(_audit_request_id),
                            written=len(_receipt_ids) if _receipt_ids else 0,
                            expected=_expected_receipts,
                        )
                except Exception:
                    log.exception(
                        "guard.gateway.receipts_write_failed",
                        request_id=str(_audit_request_id),
                    )
                    _receipts_durable = False

            # Reservation-gated settlement — actual cost from the new engine.
            # Gated on ``_receipts_durable`` (P1-D): if the receipts didn't
            # persist, leave the reservation open so the recovery sweep can
            # reconstruct authoritative cost from the receipt(s) that
            # eventually land. Never commit spend without durable evidence.
            if (
                _reservations
                and not isinstance(_response, StreamingResponse)
                and _receipts_durable
            ):
                try:
                    if _dispatched and _actual_cents is None and _new_engine_micros is not None:
                        _actual_micros = _new_engine_micros
                        _actual_cents = int(round(_new_engine_micros / 10_000))
                    # R3 fix (reviewer P1): settle owns its own session
                    # inside a threadpool call.
                    _reservations_snapshot = list(_reservations)
                    _dispatched_snapshot = _dispatched
                    _actual_cents_snapshot = _actual_cents
                    _actual_micros_snapshot = _actual_micros  # R9

                    def _settle_sync_owned():
                        _db = SessionLocal()
                        try:
                            _settle_reservations(
                                db=_db,
                                reservations=_reservations_snapshot,
                                dispatched=_dispatched_snapshot,
                                actual_cents=_actual_cents_snapshot,
                                actual_micros=_actual_micros_snapshot,  # R9
                            )
                            try:
                                _db.commit()
                            except Exception:
                                pass
                        finally:
                            try:
                                _db.close()
                            except Exception:
                                pass
                    await run_in_threadpool(_settle_sync_owned)
                except Exception:
                    log.exception(
                        "guard.gateway.settle_wire_failed",
                        reservation_count=len(_reservations),
                        dispatched=_dispatched,
                    )

        if isinstance(_response, StreamingResponse) and (_v2_plan is None or not _durable_row_id):
            _response = _wrap_stream_receipts(
                _response, upstream_capture=(_v2_plan.upstream_body if _v2_plan else None),
                workspace_id=workspace_id, request_id=_audit_request_id,
                provider=provider, model=_served_model(_routing_meta, model), model_alias=(model if _v2_plan else None), operation=request.url.path,
                developer_external_id=clerk_user_id, agent_identity_id=_agent_identity_id,
                source="gateway", client_tool=ai_tool, attempts_meta=(_routing_meta or {}).get("attempts"),
                workflow_run_id=_run_id, hook_session_id=_hook_session_id,
            )

        if _profile_rate_admission is not None and isinstance(_response, StreamingResponse):
            from app.modules.guard.gateway_profile_rate_limit import wrap_profile_rate_stream
            _response = wrap_profile_rate_stream(_response, _profile_rate_admission, _v2_plan)
            _profile_rate_streamed = True

        # Streaming lifecycle: the outermost wrapper is the single owner of
        # the admission slot and releases it exactly once when the body
        # ends (drained, disconnect, upstream error) (#2403 item 2).
        if _admission_ticket is not None and isinstance(_response, StreamingResponse):
            _response = wrap_stream_finally(_response, _admission_ticket.release)
            _admission_streamed = True
            _admission_ticket.defer()
        if _audit_request_id:
            _response.headers["X-Conduct-Request-Id"] = str(_audit_request_id)
        return _response
    except FederationDenied as error:
        from app.modules.auth.federation.gateway import error_response
        return error_response(error)
    finally:
        if _profile_rate_admission is not None and not _profile_rate_streamed:
            from app.modules.guard.gateway_profile_rate_limit import finish_profile_rate_limit
            await finish_profile_rate_limit(_profile_rate_admission, _v2_plan)
        # Outer admission cleanup on every non-streaming exit path. A
        # streamed ticket is released once by wrap_stream_finally above.
        if _admission_ticket is not None and not _admission_streamed:
            try:
                if not _admission_ticket.released:
                    await _admission_ticket.release()
            except Exception:
                pass
