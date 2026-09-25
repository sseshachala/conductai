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

    started = time.monotonic()

    # 1. Extract member token from whichever auth header the SDK sent
    raw = request.headers.get(auth_header_in, "")
    token = _extract_member_token(raw, bearer=bearer)
    if not token and auth_header_fallback:
        raw = request.headers.get(auth_header_fallback, "")
        token = _extract_member_token(
            raw,
            bearer=auth_header_fallback.lower() == "authorization",
        )

    # Internal server-to-server bypass (brain block / runtime calling its own proxy).
    # The runtime sends a per-run cond_run_* token OR the workspace's
    # cond_agt_* Agent Identity token via x-conductai-internal.
    _internal_key = request.headers.get("x-conductai-internal", "")
    _is_internal = False  # flips to True only after run/agent token validation
    _needs_run_token_validation = bool(_internal_key and _internal_key.startswith("cond_run_"))
    _needs_agent_validation = bool(_internal_key and _internal_key.startswith("cond_agt_"))
    _agent_identity_id: str | None = None
    _agent_risk_tier: str | None = None

    if not token and not _is_internal and not _needs_agent_validation and not _needs_run_token_validation:
        return _fail_closed(401, "Missing or malformed Conduct member token — run `conduct login`")

    # PR 2 (#2056) admission state — kill switch: ADMISSION_ENABLED.
    _admission_ticket = None
    _admission_streamed = False

    # 2. Resolve workspace + user — auth logic extracted to gateway_helpers
    # so admission (PR 2b) can wrap the whole post-auth body cleanly.
    try:
        # PR 6b — auth cache check before hitting the DB. Member-token
        # (Clerk) path only — run tokens and agent tokens have
        # per-request side effects (headers, first_used_at) that make
        # them cache-unfriendly. On cache hit we skip the threadpool
        # + DB roundtrip entirely.
        _cached_auth = None
        if token and not _needs_run_token_validation and not _needs_agent_validation:
            from app.core.auth_cache import get_auth_cache as _get_auth_cache
            _ac = _get_auth_cache()
            if _ac is not None:
                _cached_auth = await _ac.resolve(token)

        if _cached_auth is not None:
            workspace_id = _cached_auth.workspace_id
            clerk_user_id = _cached_auth.clerk_user_id or "system"
            _is_internal = _cached_auth.is_internal
            _agent_identity_id = _cached_auth.agent_identity_id
            _agent_risk_tier = _cached_auth.agent_risk_tier
        else:
            # PR 3 — no persistent DB session on the handler. Every helper
            # opens+uses+closes its own session inside a threadpool worker.
            # Auth runs first and returns plain values.
            _auth_result = await run_in_threadpool(
                _resolve_gateway_auth,
                request,
                token=token,
                internal_key=_internal_key,
                needs_run_token_validation=_needs_run_token_validation,
                needs_agent_validation=_needs_agent_validation,
            )
            if isinstance(_auth_result, JSONResponse):
                return _auth_result
            workspace_id = _auth_result.workspace_id
            clerk_user_id = _auth_result.clerk_user_id
            _is_internal = _auth_result.is_internal
            _agent_identity_id = _auth_result.agent_identity_id
            _agent_risk_tier = _auth_result.agent_risk_tier
        # Admission acquire — immediately after auth, before any further
        # DB work. Overload rejected fast without checking out a
        # connection.
        from app.core.admission import AdmissionRefused as _AdmRefused
        from app.core.admission import _acquire as _admission_acquire
        try:
            _admission_ticket = await _admission_acquire("gateway", workspace_id)
        except _AdmRefused as _adm_e:
            return JSONResponse(
                status_code=_adm_e.http_status,
                content={
                    "error": {
                        "type": "conduct_gateway_admission_refused",
                        "message": f"Gateway overloaded ({_adm_e.scope} slot full)",
                        "scope": _adm_e.scope,
                    }
                },
                headers={"Retry-After": str(int(_adm_e.retry_after_seconds))},
            )

        # 3. Parse request body
        try:
            body = await request.json()
        except Exception:
            return _fail_closed(400, "Body must be valid JSON")

        # #2004 Phase 1 — v2 execution wire-in. We're INSIDE the request
        # lifecycle here: Guard policy hasn't run yet, durable audit
        # hasn't opened, response gate hasn't attached. The v2 fork
        # deliberately does NOT short-circuit any of those; it only
        # replaces the ``transport.forward`` step further down. Every
        # v1 gate below (policy eval, rate limit, redaction, guidance
        # injection, durable audit open/close, response gate) runs
        # identically for a v2-routed request.
        #
        # Resolution + credential pre-fetch happen in this DB block; the
        # coordinator call happens later, outside the DB block, using
        # a resolver closure over the pre-fetched keys. Flag stays OFF
        # by default; a missing binding falls through to v1 rather
        # than fail-closed, so a partial rollout never surprises a
        # workspace that hasn't published a v2 profile yet.

        # PR 2 Commit 3 — tier resolution touches DB via model_router; offload.
        model, _routing_meta = await run_in_threadpool(
            _apply_tier_resolution_owned, workspace_id, provider, body,
        )
        # Keep the wire operation for audit normalization even without a
        # v2 profile. The generic "inference" label cannot distinguish
        # Chat Completions from Responses usage.
        _routing_meta = {**(_routing_meta or {}), "operation": upstream_path}
        if operation != "inference":
            _routing_meta = {
                **(_routing_meta or {}),
                "operation": operation,
                "billable": False,
            }

        # #2159 PR 2 — record tools offered by the caller AND tool
        # results the caller supplied (multi-turn continuation). Kept
        # here (pre-dispatch) so audit lands the fields even when the
        # response gate blocks or the coordinator returns an error.
        # ``tool_calls_generated`` lands later after the response gate
        # sees what the model actually returned.
        from app.modules.guard.tools_validator import (
            extract_tool_names_supplied as _extract_tool_names_supplied,
            extract_tool_results_supplied as _extract_tool_results_supplied,
            extract_tools_offered as _extract_tools_offered,
        )
        _tools_offered = _extract_tools_offered(body)
        _tool_results_supplied = _extract_tool_results_supplied(body)
        # Reviewer P2 #3 (2026-09-20): supplied-tool NAMES are the
        # policy-relevant signal (rule fires on "bank_transfer", not on
        # "call_abc"). IDs stay on routing_meta for the correlation
        # trail; names go into PolicyContext.tool_names_supplied.
        _tool_names_supplied = _extract_tool_names_supplied(body)
        if _tools_offered:
            _routing_meta = {**(_routing_meta or {}), "tools_offered": _tools_offered}
        if _tool_results_supplied:
            _routing_meta = {
                **(_routing_meta or {}),
                "tool_results_supplied": _tool_results_supplied,
            }
        if _tool_names_supplied:
            _routing_meta = {
                **(_routing_meta or {}),
                "tool_names_supplied": _tool_names_supplied,
            }

        # #2004 Phase 1 — v2 lookup + credential pre-fetch. Runs while
        # the DB session is still open; if a binding matches, we hand
        # the coordinator a pre-resolved credential map so the forward
        # step doesn't need to reach back into the DB. A None plan means
        # v1 handles this request as before.
        # v3 schema (#2007 follow-up): resolve by cond_code parsed out
        # of the client-sent ``model:`` field. Environment binding is
        # gone; the vault ref inside the target's credential_ref
        # carries the env. Format expected: ``cond-<8chars>-<alias>``.
        # Cond-prefixed identifier detection runs REGARDLESS of the flag.
        # A client that sent `cond-<code>-<alias>` explicitly asked for
        # a v2 profile; silently routing them via v1 when the flag is
        # off would misrepresent which profile served the traffic.
        #
        # PR 3 canary: the flag is now per-workspace via
        # ``gateway_profile_v2_enabled_for(workspace_id)`` — allowlist +
        # pct bucketing on top of the global kill switch. Deterministic
        # bucketing means a workspace never oscillates between v1 and v2
        # mid-session for a given rollout pct.
        _v2_plan = None
        _v2_enabled = settings.gateway_profile_v2_enabled_for(workspace_id)
        _cond_code = _extract_cond_code(body.get("model"))
        if _cond_code is not None and not _v2_enabled:
            from fastapi import HTTPException as _HTTPException
            raise _HTTPException(
                status_code=501,
                detail=(
                    f"Gateway Profile v2 (cond_code {_cond_code!r}) is not "
                    "enabled for this workspace. Use a v1 model name or "
                    "ask ops to enable v2."
                ),
            )
        if _v2_enabled:
            if _cond_code is not None:
                # P1 review fix — v2 plan build (profile + credential
                # resolution) offloaded to threadpool with its own session.
                # Was the primary latency bottleneck on the v2 path.
                _v2_plan = await run_in_threadpool(
                    _build_v2_plan_owned,
                    workspace_id=workspace_id,
                    cond_code=_cond_code,
                    provider=provider,
                    upstream_path=upstream_path,
                    body=body,
                )
                if _v2_plan is not None:
                    _routing_meta = {
                        **(_routing_meta or {}),
                        "gateway_version": "v2",
                        "cond_code": _cond_code,
                        "revision_id": str(_v2_plan.resolved.revision_id),
                        "v2_operation": _v2_plan.operation,
                    }
        if _routing_meta:
            log.info(
                "proxy.tier_resolved",
                workspace_id=workspace_id,
                provider=provider,
                tier_form=_routing_meta.get("tier_form"),
                resolved_model=model,
                reason=_routing_meta.get("reason"),
            )
        ai_tool = request.headers.get("x-conduct-ai-tool") or _infer_ai_tool(request)

        # 4a. Resolve user email for audit rows — offloaded to threadpool
        # with an own-session helper (P1 review fix, replaces sync
        # ``db.query`` on the event loop that used the shared session).
        from app.modules.guard.gateway_helpers import _lookup_user_email as _lookup_user_email_fn
        _user_email = await run_in_threadpool(
            _lookup_user_email_fn, workspace_id, clerk_user_id,
        )

        # 4b. Run context from brain block headers (workflow runs only)
        _run_id = request.headers.get("x-conductai-run-id") or None
        _workflow = request.headers.get("x-conductai-workflow") or None
        _workflow_id = request.headers.get("x-conductai-workflow-id") or None
        _environment_id = request.headers.get("x-conductai-environment-id") or None
        # #1959 Phase 0 note: Flight Recorder session correlation currently
        # requires clients to send X-Conduct-Session-Id. Codex Desktop's
        # config.toml does not populate it today. Without this header the
        # audit row lands with hook_session_id=NULL; do NOT synthesize one
        # from timestamps or client IP — attribution has to be honest.
        # Follow-up: signed session claims via Agent Identity (tracked
        # alongside #1968) will make this observable per-request.
        _hook_session_id = request.headers.get("x-conduct-session-id") or None

        # #1712 Track 1 — trial-plan lookup before policy eval so a BLOCK
        # response can carry an anonymous receipt URL. Cheap indexed read;
        # any failure falls back to workspace-only receipt.
        #
        # `is_trial` is TRUE only when the workspace is on the seed trial
        # plan AND has no owner attached — i.e. the anonymous curl-install
        # flow. Trials with an email/owner (Option A install, existing Try
        # page signup) get the workspace URL because the owner has a real
        # account to view it under, and we don't want block prompts to
        # default to a publicly-shareable link.
        from app.modules.guard.trial_seed import TRIAL_PLAN as _TRIAL_PLAN
        from app.modules.guard.gateway_helpers import _lookup_workspace_trial as _lookup_workspace_trial_fn
        _is_trial = False
        # P1 review fix — trial lookup offloaded to threadpool with an
        # own-session helper. Was a sync db.execute on the event loop.
        try:
            _ws_plan, _ws_owner = await run_in_threadpool(
                _lookup_workspace_trial_fn, workspace_id,
            )
            _row = (
                type("_Row", (), {"plan": _ws_plan, "owner_id": _ws_owner})()
                if _ws_plan is not None else None
            )
            if _row is not None:
                _is_trial = (_row.plan == _TRIAL_PLAN and _row.owner_id is None)
        except Exception:
            pass

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
            )

        if _pd.needs_approval:
            from app.modules.guard.routers._proxy_helpers import render_approval as _render_approval
            return _render_approval(
                _pd, background, workspace_id, clerk_user_id, ai_tool, provider,
                model, body, prompt_summary, _user_email, _run_id, _workflow,
                _workflow_id, _hook_session_id, started, _record_audit,
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

        # 4d. Per-key RPM/TPM rate limiting (#980, #1587 E1). Fires for
        # vault-key + trial-key + platform-key traffic — enforcement is
        # opt-in per workspace via guard_rate_limits rows. If no row
        # exists, check_rate_limit is a cheap no-op (early return in the
        # module). Redis outage fails open by design.
        # PR 3 fix — rate limit runs off the event loop with its own
        # session. Redis-primary but the config lookup + fail-closed
        # decision path can still hit DB and block the loop.
        from app.modules.guard.rate_limit import check_rate_limit as _check_rate_limit
        def _rate_check_owned():
            from app.core.database import SessionLocal as _SL
            from app.core.workspace_context import set_workspace_rls
            _db_local = _SL()
            try:
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
        if _rate.limited:
            log.info(
                "guard.proxy.rate_limited",
                workspace_id=workspace_id,
                scope=_rate.scope,
                metric=_rate.metric,
                limit=_rate.limit,
                current=_rate.current,
            )
            _record_failure(429, _rate.reason, rule_id="rate-limit")
            return _fail_closed(429, _rate.reason)

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
        )
        if _durable.fail_response is not None:
            return _durable.fail_response
        _durable_row_id = _durable.row_id
        # R5 fix (reviewer P1): the reservation row and the drawer query
        # correlate via the audit row's request_id (not its row_id).
        # Fall back to row_id if durable audit is off (no request_id
        # generated) so the reservation still has a stable key.
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
                        _v2_upstream_body_bytes = (
                            _response.body if hasattr(_response, "body") else None
                        )
                    except Exception:
                        _v2_upstream_body_bytes = None
            else:
                # ── PR-A2b: dispatch boundary (legacy path) ──
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
                and settings.guard_gateway_tools_stream_enabled
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
                    _wrap_tool_stream_gate(
                        _response.body_iterator,
                        outcome=_tool_stream_outcome,
                        policy_check=_stream_policy_check,
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
                    on_close=(_admission_ticket.release if _admission_ticket is not None else None),
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
                        on_close=(_admission_ticket.release if _admission_ticket is not None else None),
                        durable=_durable,
                        row_id=_durable_row_id,
                        workspace_id=workspace_id,
                        provider=provider,
                        model=model,
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
                        model=model,
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
                        on_close=(_admission_ticket.release if _admission_ticket is not None else None),
                        background=background,
                        workspace_id=workspace_id,
                        clerk_user_id=clerk_user_id,
                        ai_tool=ai_tool,
                        provider=provider,
                        model=model,
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
                        workspace_id, clerk_user_id, ai_tool, provider, model,
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
                        agent_identity_id=(
                            str(_agent_identity_id) if _agent_identity_id else None
                        ),
                        route=request.url.path,
                    )
        except BaseException as _forward_exc:  # noqa: BLE001 — need CancelledError too
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
                        model=model,
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
                        workspace_id, clerk_user_id, ai_tool, provider, model,
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
            if _dispatched and _response is not None and not isinstance(_response, StreamingResponse):
                _snapshot = locals().get("_v2_upstream_body_bytes")
                if isinstance(_snapshot, (bytes, bytearray)) and _snapshot:
                    _resp_bytes = bytes(_snapshot)
                elif _response is not None and hasattr(_response, "body"):
                    try:
                        _resp_bytes = _response.body
                    except Exception:
                        _resp_bytes = None
                if _resp_bytes is not None and (_routing_meta or {}).get("billable", True) is not False:
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
                        model=model,
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

        # Streaming lifecycle: transfer admission ticket ownership so the
        # outer finally does not release before ASGI drains the response.
        # v1 wrap already fires on_close in its iterator's finally; v2
        # wrappers received the same hook in this PR.
        if _admission_ticket is not None and isinstance(_response, StreamingResponse):
            _admission_streamed = True
            _admission_ticket.defer()
        return _response
    finally:
        # Outer admission cleanup — fires on every exit path (early return
        # in DB block, gap failure between DB and upstream try, exception,
        # normal fall-through). Idempotent: safe if a streaming on_close
        # already released. Skipped when the ticket was handed to the
        # stream lifecycle above.
        if _admission_ticket is not None and not _admission_streamed:
            try:
                if not _admission_ticket.released:
                    await _admission_ticket.release()
            except Exception:
                pass


# ─── #2004 v2 execution bridge ────────────────────────────────────────


class _V2Plan:
    """Everything the forward step needs to serve a v2 request.

    Built while the DB session is still open; the coordinator + LiteLLM
    call use only the pre-resolved fields on this object, so the
    session can be closed before the network call fires. ``last_meta``
    is filled in by ``_execute_v2`` after the coordinator returns so
    the handler can merge attempt records into ``routing_meta`` for the
    durable audit row.
    """

    __slots__ = (
        "resolved", "operation", "credential_resolver",
        # PR 5 — two-key integrations (Helicone) resolve the upstream
        # vendor key from the same vault entry as the integration key;
        # None for one-key integrations + native/litellm paths.
        "vendor_credential_resolver",
        "last_meta",
        # #2157 wire-in — set True when the caller sent OpenAI-shape
        # canonical body but the profile targets Anthropic. Signals
        # _execute_v2 to run canonical_to_anthropic pre-dispatch and
        # anthropic_to_canonical post-dispatch so the response gate +
        # client both see canonical shape regardless of upstream.
        "needs_anthropic_conversion",
    )

    def __init__(self, resolved, operation, credential_resolver, needs_anthropic_conversion: bool = False, vendor_credential_resolver=None):
        self.resolved = resolved
        self.operation = operation
        self.credential_resolver = credential_resolver
        self.vendor_credential_resolver = vendor_credential_resolver
        self.last_meta: dict = {}
        self.needs_anthropic_conversion = needs_anthropic_conversion


_COND_CODE_RE = None


# X7 — vendor-header allowlist for v2 targets.
#
# v1 forwards every header the SDK sends (minus a hop-header skip set)
# because it's a "trusted upstream" proxy. v2 is stricter: only pass
# through headers the vendor documents as legitimate client controls.
# Anything else is silently dropped, matching the principle that a
# compromised client MUST NOT be able to inject arbitrary headers into
# an upstream request via the Gateway.
#
# Header names are lowercased at collection time (see the caller in
# ``handle_gateway_request``), so the allowlist keys are lowercase.
_V2_HEADER_ALLOWLIST: frozenset[str] = frozenset({
    # Anthropic
    "anthropic-beta",         # feature-flag opt-ins
    "anthropic-version",      # API version pin (transport sets default; allow client override)
    # OpenAI
    "openai-organization",    # org selector
    "openai-project",         # project selector
    "openai-beta",            # beta features (e.g. Assistants v2)
    # OpenRouter passthrough — attribution is handled server-side but
    # some clients pass their own; harmless to allow.
    "openrouter-referer",
})


def _v2_allowlisted_headers(headers: dict[str, str] | None) -> dict[str, str]:
    """Filter a header dict down to the v2 vendor allowlist.

    Returns an empty dict if ``headers`` is None or empty. Case-
    insensitive matching (input is expected lowercase — handler
    lowercases at collection time).
    """
    if not headers:
        return {}
    return {
        k: v
        for k, v in headers.items()
        if k.lower() in _V2_HEADER_ALLOWLIST
    }


def _extract_cond_code(model: object) -> str | None:
    """Parse ``cond-<8chars>-<alias>`` out of the client's ``model:``
    field. Returns None on any mismatch — caller falls through to v1.

    Kept deliberately strict: exact 8-char alphanumeric code, hyphen
    separators, ``cond-`` prefix. A near-miss silently routing to v1
    is better than a permissive parse that misfires on a v1 model name
    that happens to look similar.
    """
    global _COND_CODE_RE
    if _COND_CODE_RE is None:
        import re
        _COND_CODE_RE = re.compile(r"^cond-([a-z0-9]{8})-([a-z0-9._\-]+)$")
    if not isinstance(model, str):
        return None
    match = _COND_CODE_RE.match(model)
    return match.group(1) if match else None


def _build_v2_plan_owned(
    *,
    workspace_id: str,
    cond_code: str,
    provider: str,
    upstream_path: str,
    body: dict,
) -> "_V2Plan | None":
    """Session-per-thread wrapper. Opens SessionLocal(), sets RLS,
    delegates to ``_build_v2_plan``, closes on exit regardless of path.
    Caller invokes via ``run_in_threadpool`` so v2 profile + credential
    resolution runs off the event loop (P1 review fix — this is the
    v2-path latency bottleneck)."""
    from app.core.database import SessionLocal as _SessionLocal
    from app.core.workspace_context import set_workspace_rls
    db = _SessionLocal()
    try:
        set_workspace_rls(db, workspace_id)
        return _build_v2_plan(
            db=db,
            workspace_id=workspace_id,
            cond_code=cond_code,
            provider=provider,
            upstream_path=upstream_path,
            body=body,
        )
    finally:
        db.close()


def _build_v2_plan(
    *,
    db,
    workspace_id: str,
    cond_code: str,
    provider: str,
    upstream_path: str,
    body: dict,
) -> _V2Plan | None:
    """Return a v2 execution plan or None (fall through to v1).

    Returns None on any of:
      - unknown cond_code in this workspace (no active revision).
      - the URL surface isn't in the v2 operation map yet.
      - stream=true (Phase 1 non-streaming only — streaming lands in a
        follow-up commit tracked on #2004).

    Raises via HTTPException on credentials being partially resolvable —
    that's a config error, not a silent degrade. The caller sees a 503
    with the specific target id so ops can fix it in Vault.
    """
    from app.runtime.gateway_v2_bridge import (
        CredentialsUnavailable,
        build_credential_resolver,
        build_vendor_credential_resolver,
        map_operation,
    )
    from app.modules.guard.gateway_runtime import resolve_v2
    from fastapi import HTTPException as _HTTPException

    # A client that sent a cond-prefixed identifier is explicitly asking
    # for v2 routing. Any failure below must be loud — silently routing a
    # `cond-<code>-<alias>` request through v1 with unrelated config
    # would lie about the profile working.
    #
    # PR 2.5: streaming is now supported end-to-end for the launch set
    # (Anthropic Messages, OpenAI Chat + Responses) via NativeHTTPTransport
    # + StreamingResponse. The pre-check that used to raise 501 here is
    # gone; ``_execute_v2`` threads ``stream`` down through the coordinator.

    operation = map_operation(provider, upstream_path)
    if operation is None:
        raise _HTTPException(
            status_code=501,
            detail=(
                f"Gateway Profile v2 does not serve {provider!r} on "
                f"{upstream_path!r}. Publish the profile against a URL "
                f"the v2 capability catalog certifies."
            ),
        )

    resolved = resolve_v2(
        db,
        workspace_id=workspace_id,
        cond_code=cond_code,
    )
    if resolved is None:
        raise _HTTPException(
            status_code=404,
            detail=(
                f"Gateway Profile with cond_code {cond_code!r} not found "
                f"in this workspace, or the profile has no active revision "
                f"(never published, or rolled back to none)."
            ),
        )

    needs_anthropic_conversion = False
    if operation not in resolved.profile.accepts:
        # #2157 wire-in — canonical /gateway/v1/completions always sends
        # operation=openai_chat_completions. If profile advertises
        # anthropic_messages instead and ALL targets are Anthropic,
        # convert on the way in + normalize on the way out.
        _can_convert_to_anthropic = (
            operation == "openai_chat_completions"
            and "anthropic_messages" in resolved.profile.accepts
            and all(
                getattr(t, "provider", None) == "anthropic"
                for t in resolved.profile.targets
            )
        )
        if _can_convert_to_anthropic:
            operation = "anthropic_messages"
            needs_anthropic_conversion = True
        else:
            raise _HTTPException(
                status_code=400,
                detail=(
                    f"Gateway Profile v2 {cond_code!r} does not accept "
                    f"operation {operation!r}. Advertised: "
                    f"{list(resolved.profile.accepts)!r}. Republish with "
                    f"{operation!r} in ``accepts`` or route this URL to a "
                    f"different profile."
                ),
            )

    try:
        resolver = build_credential_resolver(
            db,
            workspace_id=workspace_id,
            environment_id=None,   # v3: env lives inside each credential_ref
            provider=provider,
            profile=resolved.profile,
        )
        vendor_resolver = build_vendor_credential_resolver(
            db,
            workspace_id=workspace_id,
            environment_id=None,
            profile=resolved.profile,
        )
    except CredentialsUnavailable as exc:
        raise _HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc

    return _V2Plan(
        resolved=resolved, operation=operation, credential_resolver=resolver,
        vendor_credential_resolver=vendor_resolver,
        needs_anthropic_conversion=needs_anthropic_conversion,
    )


def _build_policy_check(
    *,
    workspace_id: str,
    clerk_user_id: str | None,
    agent_identity_id: str | None,
    fallback_provider: str,
    body: dict,
    risk_tier: str | None,
    ai_tool: str | None,
):
    """Build the per-target policy re-eval closure (X1).

    Called by the coordinator right before each attempt with the target
    that would be dispatched. Returns ``PolicyBlock`` if a rule fires
    against the target's real model — coordinator then skips this
    target and tries the next one. Returns None to allow dispatch.

    The closure opens a short-lived DB session per call because the
    request-scoped ``db`` has already been closed by the time the
    coordinator runs. Cost: one indexed query against the composed
    policy engine per target attempt.
    """
    from app.core.database import SessionLocal
    from app.core.workspace_context import set_workspace_rls
    from app.runtime.accounting.estimator import estimate_tokens as _estimate_tokens
    from app.runtime.attempt_coordinator import PolicyBlock

    def _check_sync(target) -> PolicyBlock | None:
        # Passthrough targets don't carry a ``provider`` field; fall
        # back to the request's provider surface (or the target's
        # integration if we can read one) so the policy eval sees
        # *some* provider context.
        target_provider = (
            getattr(target, "provider", None)
            or getattr(target, "integration", None)
            or fallback_provider
        )
        target_model = getattr(target, "model", "") or ""

        from app.guard.policy import evaluate_composed as _eval_composed
        from app.guard.policy_types import PolicyContext as _PolicyContext

        _db = SessionLocal()
        try:
            set_workspace_rls(_db, workspace_id)
            # #2159 PR 2 (#2156) — extract tool-name signals from the
            # request body so per-target policy re-check can select on
            # tool identity. Called per-target so extraction is cheap.
            from app.modules.guard.tools_validator import (
                extract_tool_names_supplied as _extract_tool_names_supplied_t,
                extract_tools_offered as _extract_tools_offered_t,
            )
            _t_offered = _extract_tools_offered_t(body) or None
            # Reviewer P2 #3 — supplied field is names, not ids.
            _t_supplied = _extract_tool_names_supplied_t(body) or None
            ctx = _PolicyContext(
                workspace_id=workspace_id,
                clerk_user_id=clerk_user_id,
                agent_identity_id=agent_identity_id,
                provider=target_provider,
                model=target_model,   # <-- key: re-eval against target model
                body=body,
                input_tokens=_estimate_tokens(body).input_tokens,
                db=_db,
                gate="prompt",
                risk_tier=risk_tier,
                ai_tool=ai_tool or None,
                tool_names_offered=_t_offered,
                tool_names_supplied=_t_supplied,
            )
            pd = _eval_composed(ctx)
        finally:
            _db.close()

        # Y1 — refuse dispatch on BOTH block-action AND approval-action.
        # The ingress eval handled approval via ``render_approval`` (queues
        # the request for a human), but that ran against the cond-alias.
        # A rule keyed on the target model (``approval when model=gpt-4o``)
        # would still be bypassed by the alias if we only checked
        # ``pd.blocks`` here — approval-gated models would silently
        # dispatch. Treat needs_approval as a refuse-and-fall-through so
        # the coordinator skips this target and tries the next; if every
        # target is refused, the 451 renders with the last refuse-reason
        # in its detail.
        if pd.blocks or pd.needs_approval:
            reason_kind = "policy-block" if pd.blocks else "policy-approval-required"
            return PolicyBlock(
                rule_id=pd.rule_id or reason_kind,
                message=pd.reason or (
                    "target model blocked by policy"
                    if pd.blocks
                    else "target model requires human approval; alias "
                         "cannot bypass approval by resolving to it"
                ),
                matched_rules=list(pd.matched_rules or []),
            )
        return None

    async def _check(target) -> PolicyBlock | None:
        # PR 3 fix — per-target policy re-eval runs off the event loop.
        # The sync closure ``_check_sync`` opens its own DB session,
        # sets workspace RLS, evaluates the composed policy engine, and
        # closes. Under high v2 concurrency this was the last remaining
        # sync-DB-on-the-event-loop path; wrapping in run_in_threadpool
        # keeps the loop responsive to /health and other requests.
        from starlette.concurrency import run_in_threadpool
        return await run_in_threadpool(_check_sync, target)

    return _check


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
    from app.runtime.gateway_transports import get_coordinator
    from app.runtime.gateway_v2_bridge import coerce_response_body
    from app.runtime.native_http_transport import StreamingUpstream as _StreamingUpstream
    from fastapi import HTTPException as _HTTPException

    # Pre-dispatch capability gate (#2152 reviewer P1). Streaming
    # works only through ``native_http`` today; the post-hoc 501 below
    # fired AFTER the coordinator picked a winning target, meaning
    # upstream bytes were already in flight. Refuse before touch when
    # the plan has no eligible target.
    if stream and not any(
        getattr(t, "transport", None) == "native_http"
        for t in plan.resolved.profile.targets
    ):
        _transports = sorted({
            getattr(t, "transport", None) or "unknown"
            for t in plan.resolved.profile.targets
        })
        raise _HTTPException(
            status_code=501,
            detail=(
                "Gateway Profile v2 streaming requires a native_http "
                f"target. Revision {plan.resolved.revision_id} "
                f"advertises transports: {_transports}. Add a "
                "native_http target ahead of others, or send stream=false."
            ),
        )

    # #2157 wire-in — SSE-to-SSE Anthropic→OpenAI translation is a
    # separate follow-up (#2155). Reject streaming when conversion is
    # needed; non-streaming Anthropic works end-to-end.
    if plan.needs_anthropic_conversion and stream:
        raise _HTTPException(
            status_code=501,
            detail=(
                "Streaming to an Anthropic-target profile via the "
                "canonical /gateway/v1/completions is not supported "
                "yet — SSE-to-SSE format translation is deferred to a "
                "follow-up. Send stream=false or route to an "
                "OpenAI-target profile."
            ),
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
            }
            for a in result.attempts
        ],
    }

    if isinstance(result.response, _StreamingUpstream):
        return _build_v2_stream_response(result.response)
    if stream:
        # Non-native transports (LiteLLM SDK, http_passthrough) don't
        # produce a StreamingUpstream. Rather than crash inside
        # coerce_response_body on an async iterator, raise a clean 501
        # naming the transport that won the coordinator race.
        raise _HTTPException(
            status_code=501,
            detail=(
                f"Gateway Profile v2 streaming supports transport="
                f"native_http only in this launch. Winning target "
                f"{result.winning_target_id!r} used a different "
                "transport; add a native_http target ahead of it or "
                "request stream=false."
            ),
        )
    _resp_body = coerce_response_body(result.response)
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


def _build_v2_stream_response(upstream) -> StreamingResponse:
    """Wrap a ``StreamingUpstream`` in a Starlette ``StreamingResponse``.

    Generator yields raw bytes as they arrive and closes the httpx
    response in ``finally`` so a dropped client connection doesn't leak
    a pooled slot. Vendor content-type is preserved (SSE for Anthropic /
    OpenAI) so downstream SDKs consume the stream unchanged.
    """
    async def _gen():
        try:
            async for chunk in upstream.response.aiter_bytes():
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


def _wrap_v2_stream_finalize(
    response: StreamingResponse,
    *,
    on_close=None,
    durable=None,
    row_id,
    workspace_id: str,
    provider: str,
    model: str,
    # P1-4: real request path (e.g. /gateway/v1/openai/v1/responses) — the
    # production caller (``handle_gateway_request``) always passes
    # ``request.url.path`` so the normalizer picks the right family
    # (Responses vs Chat). Default is only for legacy test scaffolding;
    # a source-string pin in tests/runtime/accounting/test_pr4_settlement_cutover
    # asserts the handler passes an explicit operation on both call sites.
    operation: str = "chat.completions.stream",
    body: dict,
    ingress_decision: str,
    ingress_rule_id: str | None,
    routing_meta: dict | None,
    clerk_user_id: str | None,
    ai_tool: str | None,
    user_email: str | None,
    started_monotonic: float,
    stream_deadline_seconds: float | None = None,
    # #2209 Session 6D — for accounting shadow write attribution.
    conductai_run_id: str | None = None,
    # R4 fix (reviewer P1): reservation ownership transferred from the
    # handler. Wrapper computes actual_cents from the drained body then
    # calls settle_reservations on stream close / cancel / timeout.
    reservations: list | None = None,
    _routing_meta: dict | None = None,
    # #2173 P1 — stream-gate outcome. Wrapper reads this after the
    # stream drains to decide the audit decision + execution_status.
    # None = tool-gate was not applied; finalize uses upstream signals only.
    tool_stream_outcome=None,
) -> StreamingResponse:
    """Fire durable-audit finalize when the streaming response closes.

    Collects bytes as they pass through so the audit row records the full
    upstream body for cost + token accounting. Non-streaming v2 does its
    finalize synchronously in ``handle_gateway_request``; for streaming
    the finalize *has to* wait until the stream drains, which is why
    this wrapper exists.

    X4 — stream lifetime:

    - ``durable``: the ``DurableRow`` from ``open_durable_row()``, whose
      renewal task keeps the audit row's lease alive. The handler stops
      cancelling it in its own ``finally``; this wrapper cancels it
      here AFTER finalize completes so the row stays leased for the
      full stream body, not just the header-arrival window.
    - ``stream_deadline_seconds``: wall-clock cap from the profile's
      ``timeout_seconds``. The coordinator's ``wait_for`` only guarded
      header arrival; without a body-side deadline a stalled vendor
      stream could hold the connection open indefinitely. If exceeded,
      raise ``asyncio.TimeoutError`` — the outer ``finally`` records
      it as ``execution_status='error'`` and cancels renewal.

    ponytail: response gate for streaming is a post-hoc buffered scan
    (see ``_wrap_streaming_response``) and never modifies bytes, so we
    can safely treat what we see == what the vendor emitted. If a
    future gate rewrites stream chunks, revisit the ``response_bytes``
    argument passed to finalize below.
    """
    import asyncio as _a

    original = response.body_iterator

    async def _wrapped():
        collected = bytearray()
        stream_exc: BaseException | None = None
        # Y3 — the original ``async for chunk in original`` implicitly
        # awaits ``__anext__``. That await has no timeout of its own,
        # so a stalled upstream (headers arrived, then no chunk ever
        # sent) blocks here indefinitely — the profile's
        # ``timeout_seconds`` is only checked BEFORE each chunk yields.
        # Reviewer's reproducer: a mock body_iterator whose
        # ``__anext__`` sleeps past the deadline never trips the check.
        #
        # Fix: drive the iteration by hand, ``wait_for(anext)`` with
        # the remaining budget as the timeout. TimeoutError from
        # wait_for lands in the outer except and finalize records
        # ``execution_status='timeout'``.
        iterator = original.__aiter__() if hasattr(original, "__aiter__") else original
        try:
            while True:
                if stream_deadline_seconds is not None:
                    remaining = stream_deadline_seconds - (
                        time.monotonic() - started_monotonic
                    )
                    if remaining <= 0:
                        raise _a.TimeoutError(
                            f"stream body exceeded profile "
                            f"timeout_seconds={stream_deadline_seconds}"
                        )
                    try:
                        chunk = await _a.wait_for(
                            iterator.__anext__(), timeout=remaining,
                        )
                    except _a.TimeoutError:
                        # Re-raise with our message so the finalize
                        # branch below distinguishes stalled-upstream
                        # timeout from other timeouts.
                        raise _a.TimeoutError(
                            f"stream body exceeded profile "
                            f"timeout_seconds={stream_deadline_seconds}"
                            f" (stalled upstream)"
                        )
                else:
                    try:
                        chunk = await iterator.__anext__()
                    except StopAsyncIteration:
                        break
                if isinstance(chunk, str):
                    chunk_bytes = chunk.encode("utf-8")
                else:
                    chunk_bytes = chunk
                collected.extend(chunk_bytes)
                yield chunk_bytes
        except StopAsyncIteration:
            pass
        except BaseException as exc:  # noqa: BLE001 — need CancelledError too
            stream_exc = exc
            raise
        finally:
            from app.modules.guard.gateway_lifecycle import (
                close_durable_row as _close_durable,
                finalize_durable_row as _finalize_durable_row,
            )
            _is_cancel = isinstance(stream_exc, _a.CancelledError)
            _is_timeout = isinstance(stream_exc, _a.TimeoutError)
            _decision = ingress_decision if stream_exc is None else "error"
            if stream_exc is None:
                _execution_status = "ok"
            elif _is_cancel:
                _execution_status = "interrupted"
            elif _is_timeout:
                _execution_status = "timeout"
            else:
                _execution_status = "error"
            _result_summary = (
                None
                if stream_exc is None
                else (
                    "Stream cancelled by client" if _is_cancel
                    else (
                        f"Stream body exceeded {stream_deadline_seconds}s "
                        f"wall-clock deadline" if _is_timeout
                        else f"stream aborted: {type(stream_exc).__name__}: {str(stream_exc)[:400]}"
                    )
                )
            )
            # #2173 P1 — stream-gate outcome takes precedence over the
            # "no exception raised = ok" default. A synthetic error
            # frame from tools_stream_gate does NOT raise (the stream
            # completed normally from the ASGI side), so without this
            # override the audit row landed as decision=allowed
            # execution_status=ok despite the client seeing an error.
            _final_routing_meta = routing_meta
            _final_rule_id = ingress_rule_id
            _final_result_summary = _result_summary
            if stream_exc is None and tool_stream_outcome is not None:
                try:
                    from app.modules.guard.tools_stream_gate import (
                        StreamGateStatus as _SGS,
                    )
                    from app.modules.guard.tools_validator import (
                        ResponseGateReason as _RGR,
                    )
                    _st = tool_stream_outcome.status
                    if _st != _SGS.OK:
                        # Any non-OK stream-gate verdict → blocked row.
                        _decision = "blocked"
                        _execution_status = "error"
                        _final_result_summary = (
                            tool_stream_outcome.reason or _st.value
                        )
                        # Map to the same response_gate_reason taxonomy
                        # as non-streaming so audit UI can label alike.
                        if _st == _SGS.POLICY_BLOCK:
                            _reason_val = _RGR.POLICY_BLOCK
                            _final_rule_id = (
                                tool_stream_outcome.reason
                                or "guard.stream.policy_block"
                            )
                        else:
                            _reason_val = _RGR.VALIDATION_FAILURE
                            _final_rule_id = (
                                f"guard.stream.{_st.value}"
                            )
                        _final_routing_meta = {
                            **(routing_meta or {}),
                            "response_gate_reason": _reason_val,
                            "stream_gate_status": _st.value,
                        }
                    if tool_stream_outcome.correlation_ids:
                        _final_routing_meta = {
                            **(_final_routing_meta or {}),
                            "tool_call_correlation_ids": (
                                tool_stream_outcome.correlation_ids
                            ),
                        }
                except Exception:
                    log.exception(
                        "guard.gateway.stream_outcome_merge_failed",
                        row_id=row_id,
                    )
            try:
                await _finalize_durable_row(
                    row_id=row_id,
                    workspace_id=workspace_id,
                    decision=_decision,
                    provider=provider,
                    model=model,
                    body=body,
                    response_bytes=bytes(collected) or None,
                    duration_ms=int((time.monotonic() - started_monotonic) * 1000),
                    rule_id=_final_rule_id,
                    routing_meta=_final_routing_meta,
                    execution_status=_execution_status,
                    result_summary=_final_result_summary,
                    clerk_user_id=clerk_user_id,
                    ai_tool=ai_tool,
                    user_email=user_email,
                )
            except Exception:
                log.exception(
                    "guard.gateway.v2.stream_finalize_failed",
                    row_id=row_id,
                )
            # R4 fix (reviewer P1): settle reservations from the
            # drained upstream body. Runs on success, cancel, and
            # timeout — same finally as finalize.
            _stream_resp_bytes = bytes(collected) if collected else None
            _stream_new_engine_micros: int | None = None
            if (
                _stream_resp_bytes is not None
                and (_routing_meta or {}).get("billable", True) is not False
            ):
                try:
                    from app.runtime.accounting.settlement import (
                        settle_micros_for_attempts,
                    )
                    _stream_attempts_for_settle = (
                        _routing_meta.get("attempts")
                        if isinstance(_routing_meta, dict)
                        else None
                    )
                    _stream_new_engine_micros = settle_micros_for_attempts(
                        attempts_meta=_stream_attempts_for_settle,
                        request_provider=provider,
                        request_model=model,
                        operation=operation,  # P1-4: real path picks the right family
                        winner_response_bytes=_stream_resp_bytes,
                        strict=True,
                    )
                except Exception:
                    log.exception(
                        "guard.gateway.v2.stream_settle_compute_failed",
                        row_id=row_id,
                        provider=provider,
                        model=model,
                    )
            # P1-D (post-review): persist per-attempt receipts BEFORE
            # settling reservations. Same ordering invariant as the
            # non-streaming path. Failure to persist any expected receipt
            # ⇒ skip settle; recovery sweep reconstructs from whatever
            # eventually lands.
            _stream_receipts_durable = False
            _stream_meta = _routing_meta if isinstance(_routing_meta, dict) else {}
            _stream_attempts_meta = _stream_meta.get("attempts")
            _stream_expected_receipts = (
                len(_stream_attempts_meta) if _stream_attempts_meta else 1
            )
            try:
                from app.runtime.accounting.shadow_writer import (
                    write_receipts_for_attempts as _write_shadow_attempts,
                )
                from starlette.concurrency import (
                    run_in_threadpool as _rin_threadpool_shadow,
                )
                _reserved_micros: int | None = None
                if reservations:
                    try:
                        _reserved_micros = sum(
                            int(getattr(r, "estimated_micros", 0) or 0)
                            for r in reservations
                        ) or None
                    except Exception:
                        _reserved_micros = None
                # #2209 Session 6D — workflow attribution.
                _stream_wf_run_uuid = None
                if conductai_run_id:
                    try:
                        import uuid as _uuid_wf_stream
                        _stream_wf_run_uuid = _uuid_wf_stream.UUID(
                            str(conductai_run_id)
                        )
                    except (ValueError, TypeError):
                        _stream_wf_run_uuid = None
                _stream_receipt_ids = await _rin_threadpool_shadow(
                    _write_shadow_attempts,
                    workspace_id=workspace_id,
                    request_id=(
                        (durable.request_id if durable is not None else None)
                        or row_id
                    ),
                    provider=provider,
                    model=model,
                    operation=operation,  # P1-4: real op flows to receipt normalizer too
                    dispatched=True,
                    response_bytes=_stream_resp_bytes,
                    reserved_microdollars=_reserved_micros,
                    developer_external_id=clerk_user_id,
                    source="gateway",
                    client_tool=ai_tool,
                    attempts_meta=_stream_attempts_meta,
                    workflow_run_id=_stream_wf_run_uuid,
                )
                _stream_receipts_durable = (
                    _stream_receipt_ids is not None
                    and len(_stream_receipt_ids) >= _stream_expected_receipts
                )
                if not _stream_receipts_durable:
                    log.warning(
                        "guard.gateway.v2.stream_receipts_partial_skip_settle",
                        row_id=row_id,
                        written=(
                            len(_stream_receipt_ids)
                            if _stream_receipt_ids else 0
                        ),
                        expected=_stream_expected_receipts,
                    )
            except Exception:
                log.exception(
                    "guard.gateway.v2.stream_receipts_write_failed",
                    row_id=row_id,
                )
                _stream_receipts_durable = False

            if reservations and _stream_receipts_durable:
                try:
                    from app.modules.guard.gateway_lifecycle import (
                        settle_reservations as _settle_reservations,
                    )
                    from app.core.database import SessionLocal
                    _dispatched_stream = True
                    _actual_cents_stream: int | None = None
                    _actual_micros_stream: int | None = None
                    if _stream_new_engine_micros is not None:
                        _actual_micros_stream = _stream_new_engine_micros
                        _actual_cents_stream = int(round(_stream_new_engine_micros / 10_000))
                    # R3 pattern: offload the sync settle to a threadpool
                    # so the ASGI drain path stays responsive.
                    def _settle_stream_owned():
                        _db = SessionLocal()
                        try:
                            _settle_reservations(
                                db=_db,
                                reservations=reservations,
                                dispatched=_dispatched_stream,
                                actual_cents=_actual_cents_stream,
                                actual_micros=_actual_micros_stream,
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
                    from starlette.concurrency import (
                        run_in_threadpool as _rin_threadpool,
                    )
                    await _rin_threadpool(_settle_stream_owned)
                except Exception:
                    log.exception(
                        "guard.gateway.v2.stream_settle_failed",
                        row_id=row_id,
                        reservation_count=len(reservations) if reservations else 0,
                    )

            # X4 — cancel the renewal task last, AFTER finalize. If we
            # cancelled first, the row would show up as expired to the
            # reconciler in the seconds between cancellation and
            # finalize completion.
            if durable is not None:
                try:
                    await _close_durable(durable)
                except Exception:
                    log.exception(
                        "guard.gateway.v2.stream_close_durable_failed",
                        row_id=row_id,
                    )
            if on_close is not None:
                try:
                    if asyncio.iscoroutinefunction(on_close):
                        await on_close()
                    else:
                        on_close()
                except Exception:
                    log.warning("guard.gateway.v2.stream_on_close_failed")

    return StreamingResponse(
        _wrapped(),
        media_type=response.media_type,
        headers=dict(response.headers),
        status_code=response.status_code,
    )


def _wrap_v2_stream_record_legacy(
    response: StreamingResponse,
    *,
    on_close=None,
    background,
    workspace_id: str,
    clerk_user_id: str | None,
    ai_tool: str | None,
    provider: str,
    model: str,
    body: dict,
    prompt_summary: str,
    user_email: str | None,
    conductai_run_id,
    conductai_workflow,
    conductai_workflow_id,
    hook_session_id,
    routing_meta: dict | None,
    agent_identity_id: str | None,
    route: str,
    ingress_decision: str,
    ingress_rule_id: str | None,
    started_monotonic: float,
    record_audit_fn,
    stream_deadline_seconds: float | None = None,
) -> StreamingResponse:
    """X2 fallback wrapper — mirrors ``_wrap_v2_stream_finalize`` but
    schedules ``_record_audit`` (v1's single-phase writer) instead of
    ``_finalize_durable_row``. Used when v2 executes but the
    durable-audit canary is off for this workspace.

    Same shape guarantees: collects bytes as they pass, fires the
    audit call on stream close (or cancellation), never swallows the
    stream on writer failure.

    Z2 — deadline enforcement is now independent of the audit flag.
    ``stream_deadline_seconds`` uses the same ``asyncio.wait_for``
    per-chunk pattern as ``_wrap_v2_stream_finalize`` (Y3 fix), so a
    stalled upstream trips the profile timeout whether durable-audit
    is on or off. Prior state: only the durable-on wrapper enforced
    the deadline → stalled streams under durable-off held the
    connection open indefinitely.
    """
    import asyncio as _a

    original = response.body_iterator

    async def _wrapped():
        collected = bytearray()
        stream_exc: BaseException | None = None
        iterator = (
            original.__aiter__() if hasattr(original, "__aiter__") else original
        )
        try:
            # Z2 — same per-chunk wait_for pattern as Y3 uses in the
            # durable-on wrapper. Refactoring both wrappers to share
            # the loop would be nicer, but keeping them side-by-side
            # for review clarity: the shape MUST match so a future
            # fix to one is easy to mirror.
            while True:
                if stream_deadline_seconds is not None:
                    remaining = stream_deadline_seconds - (
                        time.monotonic() - started_monotonic
                    )
                    if remaining <= 0:
                        raise _a.TimeoutError(
                            f"stream body exceeded profile "
                            f"timeout_seconds={stream_deadline_seconds}"
                        )
                    try:
                        chunk = await _a.wait_for(
                            iterator.__anext__(), timeout=remaining,
                        )
                    except _a.TimeoutError:
                        raise _a.TimeoutError(
                            f"stream body exceeded profile "
                            f"timeout_seconds={stream_deadline_seconds}"
                            f" (stalled upstream)"
                        )
                else:
                    try:
                        chunk = await iterator.__anext__()
                    except StopAsyncIteration:
                        break
                if isinstance(chunk, str):
                    chunk_bytes = chunk.encode("utf-8")
                else:
                    chunk_bytes = chunk
                collected.extend(chunk_bytes)
                yield chunk_bytes
        except StopAsyncIteration:
            pass
        except BaseException as exc:  # noqa: BLE001
            stream_exc = exc
            raise
        finally:
            _is_cancel = isinstance(stream_exc, _a.CancelledError)
            _is_timeout = isinstance(stream_exc, _a.TimeoutError)
            _decision = ingress_decision if stream_exc is None else "error"
            if stream_exc is None:
                _execution_status = "success"
            elif _is_cancel:
                _execution_status = "interrupted"
            elif _is_timeout:
                _execution_status = "timeout"
            else:
                _execution_status = "error"
            try:
                # Z1 note — same failure mode as the non-streaming
                # exception path: background.add_task never runs if
                # the response was aborted. Streaming's "response
                # already sent" state means ASGI does drain queued
                # tasks in the happy path; on error, this may or may
                # not fire depending on ASGI server timing. Not
                # worth switching to asyncio.to_thread here because
                # the stream completed the send BEFORE this finally
                # (bytes were yielded successfully); the writer
                # timing is a best-effort observability signal, not
                # a correctness gate.
                background.add_task(
                    record_audit_fn,
                    workspace_id, clerk_user_id, ai_tool, provider, model,
                    _decision,
                    ingress_rule_id,
                    int((time.monotonic() - started_monotonic) * 1000),
                    body=body,
                    response_bytes=bytes(collected) or None,
                    prompt_summary=prompt_summary,
                    user_email=user_email,
                    conductai_run_id=conductai_run_id,
                    conductai_workflow=conductai_workflow,
                    conductai_workflow_id=conductai_workflow_id,
                    hook_session_id=hook_session_id,
                    routing_meta=routing_meta,
                    execution_status=_execution_status,
                    agent_identity_id=agent_identity_id,
                    route=route,
                )
            except Exception:
                log.exception(
                    "guard.gateway.v2.stream_record_legacy_failed",
                    workspace_id=workspace_id,
                )
            if on_close is not None:
                try:
                    if asyncio.iscoroutinefunction(on_close):
                        await on_close()
                    else:
                        on_close()
                except Exception:
                    log.warning("guard.gateway.v2.stream_on_close_failed")

    return StreamingResponse(
        _wrapped(),
        media_type=response.media_type,
        headers=dict(response.headers),
        status_code=response.status_code,
    )


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
