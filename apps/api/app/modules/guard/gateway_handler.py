"""Canonical Gateway request entry point.

Owns the full Gateway request lifecycle: authenticate the caller (member
token, agent identity, or run token), evaluate Guard policies, open a
durable-audit row via ``gateway_lifecycle``, forward to the vendor, apply
the response gate, and close the audit row. Legacy ``/proxy/*`` route
decorators in ``routers/proxy.py`` delegate here — no new Gateway behavior
is allowed to grow on that legacy surface.
"""
from __future__ import annotations

import time
import uuid

import structlog
from fastapi import BackgroundTasks, Request
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import text

from app.core.config import settings


log = structlog.get_logger(__name__)


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
    # Lazy import: routers.proxy still owns the helpers (redaction, tier
    # resolution, upstream/vault lookup, response gate) plus the re-exports
    # for auth/session/audit. Function-body import breaks the circular dep
    # with routers/proxy.py, and lets test patches on ``routers.proxy.X``
    # intercept each call (the module attribute is re-read on every entry
    # because the ``from ... import`` compiles to a runtime lookup).
    from app.modules.guard.routers.proxy import (
        _apply_tier_resolution,
        _flatten_prompt,
        _estimate_input_tokens,
        _infer_ai_tool,
        _upstream_url,
        _upstream_api_key,
        _vault_key,
        _redact_body,
        _inject_guidance,
        _apply_response_gate,
        _wrap_streaming_response,
        _extract_member_token,
        SessionLocal,
        resolve_agent_token,
        token_is_expired,
        set_workspace_rls,
        _record_audit,
        _fail_closed,
        _forward,
        get_provider_transport_registry,
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

    # 2. Resolve workspace + user
    db = SessionLocal()
    try:
        if _needs_run_token_validation and not _is_internal:
            import hashlib as _rt_hashlib
            from app.modules.agent_identity.run_token_model import AgentRunToken as _AgentRunToken
            from datetime import datetime, timezone
            _hdr_ws = request.headers.get("x-conductai-workspace-id", "")
            if not _hdr_ws:
                return _fail_closed(400, "X-Conductai-Workspace-Id required for run token calls")
            _token_hash = _rt_hashlib.sha256(_internal_key.encode()).hexdigest()
            _now_rt = datetime.now(timezone.utc)
            # Audit S04 — expires_at check. An abandoned or leaked run token
            # can't authenticate past its bounded lifetime even if the run
            # itself never got a chance to set invalidated_at.
            _rt = db.query(_AgentRunToken).filter(
                _AgentRunToken.token_hash == _token_hash,
                _AgentRunToken.workspace_id == uuid.UUID(_hdr_ws),
                _AgentRunToken.invalidated_at == None,  # noqa: E711
                _AgentRunToken.expires_at > _now_rt,
            ).first()
            if not _rt:
                return _fail_closed(401, "Run token not found, expired, or already invalidated")
            _is_internal = True
            if not _rt.first_used_at:
                _rt.first_used_at = _now_rt
                db.commit()

        if _needs_agent_validation and not _is_internal:
            # Audit S04 — was an inline decrypt loop over every AgentIdentity
            # in the workspace, missing the lifecycle_state and token_type
            # checks that _resolve_agent_token already applies. Now shares
            # one code path so deactivated / expired / external identities
            # are rejected here just like they are at the member-token door.
            _hdr_ws = request.headers.get("x-conductai-workspace-id", "")
            if not _hdr_ws:
                return _fail_closed(400, "X-Conductai-Workspace-Id required for agent identity calls")
            from app.core.auth import _resolve_agent_token as _resolve_ai
            from fastapi import HTTPException as _HTTPException
            try:
                _ai, _ = _resolve_ai(_internal_key, db)
            except _HTTPException as _exc:
                return _fail_closed(int(_exc.status_code), str(_exc.detail or "Agent Identity token not recognized"))
            if str(_ai.workspace_id) != _hdr_ws:
                return _fail_closed(401, "Agent Identity token does not belong to the requested workspace")
            _is_internal = True
            _agent_identity_id = _ai.id
            _agent_risk_tier = getattr(_ai, "risk_tier", None)

        if _is_internal:
            workspace_id = request.headers.get("x-conductai-workspace-id", "")
            if not workspace_id:
                return _fail_closed(400, "X-Conductai-Workspace-Id required for internal proxy calls")
            set_workspace_rls(db, workspace_id)
            _internal_email = request.headers.get("x-conductai-user-email") or None
            clerk_user_id = _internal_email or "system"
            if _agent_identity_id:
                from app.modules.agent_identity.models import AgentIdentity as _AgentIdentity
                from datetime import datetime, timezone as _tz
                _id_row = db.query(_AgentIdentity).filter(_AgentIdentity.id == _agent_identity_id).first()
                if _id_row:
                    _id_row.last_used_at = datetime.now(_tz.utc)
                    db.commit()
        else:
            ident = resolve_agent_token(token, db)
            if not ident:
                if token_is_expired(token, db):
                    return _fail_closed(401, "Conduct session expired — run `conduct login`")
                return _fail_closed(401, "Conduct member token not recognized — run `conduct login`")
            workspace_id, clerk_user_id = ident
            set_workspace_rls(db, workspace_id)
            # Best-effort risk_tier lookup for tier-gated policies. Legacy
            # guard-mt-* member tokens have no identity row → None.
            try:
                from app.core.auth import resolve_agent_identity_row as _rair
                _proxy_ai_row = _rair(token, db)
                if _proxy_ai_row:
                    _agent_risk_tier = getattr(_proxy_ai_row, "risk_tier", None)
                    # Phase 0 of #1959 — this branch previously read risk_tier
                    # off the identity row but never propagated the id. Every
                    # external-token audit row therefore had agent_identity_id
                    # NULL even though a matching identity was resolved.
                    _agent_identity_id = getattr(_proxy_ai_row, "id", None) or _agent_identity_id
            except Exception:
                pass

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

        model, _routing_meta = _apply_tier_resolution(db, workspace_id, provider, body)
        if operation != "inference":
            _routing_meta = {
                **(_routing_meta or {}),
                "operation": operation,
                "billable": False,
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
                _v2_plan = _build_v2_plan(
                    db=db,
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

        # 4a. Resolve user email for audit rows
        _user_email: str | None = None
        if not _user_email:
            try:
                from app.models.user import User as _User
                _u = db.query(_User).filter(_User.clerk_id == clerk_user_id).first()
                if _u:
                    _user_email = _u.email
            except Exception:
                pass

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
        _is_trial = False
        try:
            _row = db.execute(
                text("SELECT plan, owner_id FROM workspaces WHERE id = :ws"),
                {"ws": workspace_id},
            ).fetchone()
            if _row is not None:
                _is_trial = (_row.plan == _TRIAL_PLAN and _row.owner_id is None)
        except Exception:
            pass

        # 4c. Pre-call Guard policy evaluation — composed engine (#1225 Phase 4)
        prompt_summary = _flatten_prompt(body)[:200]
        from app.guard.policy import evaluate_composed as _eval_composed
        from app.guard.policy_types import PolicyContext as _PolicyContext
        _ctx = _PolicyContext(
            workspace_id=workspace_id,
            clerk_user_id=clerk_user_id,
            agent_identity_id=str(_agent_identity_id) if _agent_identity_id else None,
            provider=provider,
            model=model,
            body=body,
            input_tokens=_estimate_input_tokens(body),
            db=db,
            gate="prompt",  # #1733: outbound LLM proxy egress
            risk_tier=_agent_risk_tier,
            # ai_tool was resolved earlier via header or UA sniff (line 458);
            # threading it into policy eval scopes SpendCapPolicySource
            # lookups per-tool. "unknown" flows through and SpendCap treats
            # it as absence (workspace + user caps still apply).
            ai_tool=ai_tool or None,
        )
        _pd = _eval_composed(_ctx)
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
        from app.modules.guard.rate_limit import check_rate_limit as _check_rate_limit
        _rate = _check_rate_limit(
            db,
            workspace_id=workspace_id,
            agent_identity_id=str(_agent_identity_id) if _agent_identity_id else None,
            input_tokens=_estimate_input_tokens(body),
            # Production Gateway is fail-closed; local/test environments keep
            # the historical fail-open behavior when Redis is intentionally
            # absent.
            fail_closed=canonical_profile and settings.environment == "production",
        )
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
        upstream = _upstream_url(db, workspace_id, provider, _environment_id)
        _upstream_key = _upstream_api_key(db, workspace_id, _environment_id)
        _vault_key_val = _vault_key(db, workspace_id, provider, _environment_id)
        transport = get_provider_transport_registry().for_provider(provider)
        if canonical_profile:
            from app.modules.guard.gateway_runtime import TransportResolver

            profile_runtime = TransportResolver().resolve(
                db, workspace_id, provider, _environment_id,
            )
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
            from app.modules.guard.trial_upstream import resolve_trial_key
            _trial_key, _trial_status = resolve_trial_key(
                db, workspace_id, provider, str(_agent_identity_id) if _agent_identity_id else None,
            )
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
    finally:
        db.close()

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
            _response = await _execute_v2(
                plan=_v2_plan, body=body, stream=is_stream,
                policy_check=_policy_check,
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
        # #1733 PR 4: response gate (non-streaming).
        if (
            operation == "inference"
            and not is_stream
            and isinstance(_response, JSONResponse)
            and _response.status_code < 400
        ):
            _response = _apply_response_gate(
                _response, workspace_id=workspace_id, provider=provider, model=model,
                clerk_user_id=clerk_user_id, agent_identity_id=_agent_identity_id,
                agent_risk_tier=_agent_risk_tier,
                ai_tool=ai_tool,
            )
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
        if _v2_plan is not None and _durable_row_id:
            if isinstance(_response, StreamingResponse):
                _response = _wrap_v2_stream_finalize(
                    _response,
                    row_id=_durable_row_id,
                    workspace_id=workspace_id,
                    provider=provider,
                    model=model,
                    body=body,
                    ingress_decision=_audit_decision,
                    ingress_rule_id=_audit_rule_id,
                    routing_meta=_routing_meta,
                    clerk_user_id=clerk_user_id,
                    ai_tool=ai_tool,
                    user_email=_user_email,
                    started_monotonic=started,
                )
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
    except BaseException as _forward_exc:  # noqa: BLE001 — need CancelledError too
        # Best-effort finalize so the row lands terminated immediately
        # instead of waiting on the reconciler's lease sweep. WHERE
        # lifecycle_state = 'accepted' in audit.finalize means this is
        # a no-op if the transport / _stream_chunks already finalized
        # (e.g. an error partway through streaming).
        if _durable_row_id:
            _is_cancel = isinstance(_forward_exc, _asyncio.CancelledError)
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
                    execution_status="interrupted" if _is_cancel else "error",
                    result_summary=(
                        "Request cancelled during upstream forward"
                        if _is_cancel
                        else f"forward/gate exception: {type(_forward_exc).__name__}: {str(_forward_exc)[:400]}"
                    ),
                    clerk_user_id=clerk_user_id,
                    ai_tool=ai_tool,
                    user_email=_user_email,
                )
            except Exception:
                log.exception("guard.gateway.error_finalize_failed", row_id=_durable_row_id)
        raise
    finally:
        # Cancel the whole-request renewal task owned by gateway_lifecycle.
        # For streaming, _stream_chunks starts its own renewal for the
        # stream lifetime. For non-streaming this marks the deadline.
        # Idempotent — safe on every exit path including exceptions.
        await _close_durable(_durable)

    return _response


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

    __slots__ = ("resolved", "operation", "credential_resolver", "last_meta")

    def __init__(self, resolved, operation, credential_resolver):
        self.resolved = resolved
        self.operation = operation
        self.credential_resolver = credential_resolver
        self.last_meta: dict = {}


_COND_CODE_RE = None


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

    if operation not in resolved.profile.accepts:
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
    except CredentialsUnavailable as exc:
        raise _HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc

    return _V2Plan(resolved=resolved, operation=operation, credential_resolver=resolver)


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
    from app.modules.guard.routers.proxy import (
        SessionLocal,
        _estimate_input_tokens,
        set_workspace_rls,
    )
    from app.runtime.attempt_coordinator import PolicyBlock

    def _check(target) -> PolicyBlock | None:
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
            ctx = _PolicyContext(
                workspace_id=workspace_id,
                clerk_user_id=clerk_user_id,
                agent_identity_id=agent_identity_id,
                provider=target_provider,
                model=target_model,   # <-- key: re-eval against target model
                body=body,
                input_tokens=_estimate_input_tokens(body),
                db=_db,
                gate="prompt",
                risk_tier=risk_tier,
                ai_tool=ai_tool or None,
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

    return _check


async def _execute_v2(
    *,
    plan: _V2Plan,
    body: dict,
    stream: bool = False,
    policy_check=None,
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
        AttemptCoordinator as _AttemptCoordinator,
    )
    from app.runtime.gateway_v2_bridge import coerce_response_body
    from app.runtime.native_http_transport import StreamingUpstream as _StreamingUpstream
    from fastapi import HTTPException as _HTTPException

    coordinator = _AttemptCoordinator()
    try:
        result = await coordinator.execute(
            resolved=plan.resolved,
            operation=plan.operation,
            payload=body,
            credential_resolver=plan.credential_resolver,
            stream=stream,
            policy_check=policy_check,
        )
    except _AllAttemptsFailed as exc:
        plan.last_meta = {
            "winning_target_id": None,
            "attempt_count": len(exc.attempts),
            "attempts": [
                {
                    "target_id": a.target_id,
                    "transport": a.transport,
                    "provider_or_integration": a.provider_or_integration,
                    "succeeded": a.succeeded,
                    "error_class": a.error_class,
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
        "attempts": [
            {
                "target_id": a.target_id,
                "transport": a.transport,
                "provider_or_integration": a.provider_or_integration,
                "succeeded": a.succeeded,
                "error_class": a.error_class,
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
    return JSONResponse(content=coerce_response_body(result.response))


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


def _wrap_v2_stream_finalize(
    response: StreamingResponse,
    *,
    row_id,
    workspace_id: str,
    provider: str,
    model: str,
    body: dict,
    ingress_decision: str,
    ingress_rule_id: str | None,
    routing_meta: dict | None,
    clerk_user_id: str | None,
    ai_tool: str | None,
    user_email: str | None,
    started_monotonic: float,
) -> StreamingResponse:
    """Fire durable-audit finalize when the streaming response closes.

    Collects bytes as they pass through so the audit row records the full
    upstream body for cost + token accounting. Non-streaming v2 does its
    finalize synchronously in ``handle_gateway_request``; for streaming
    the finalize *has to* wait until the stream drains, which is why
    this wrapper exists.

    ponytail: response gate for streaming is a post-hoc buffered scan
    (see ``_wrap_streaming_response``) and never modifies bytes, so we
    can safely treat what we see == what the vendor emitted. If a
    future gate rewrites stream chunks, revisit the ``response_bytes``
    argument passed to finalize below.
    """
    original = response.body_iterator

    async def _wrapped():
        collected = bytearray()
        stream_exc: BaseException | None = None
        try:
            async for chunk in original:
                if isinstance(chunk, str):
                    chunk_bytes = chunk.encode("utf-8")
                else:
                    chunk_bytes = chunk
                collected.extend(chunk_bytes)
                yield chunk_bytes
        except BaseException as exc:  # noqa: BLE001 — need CancelledError too
            stream_exc = exc
            raise
        finally:
            from app.modules.guard.gateway_lifecycle import (
                finalize_durable_row as _finalize_durable_row,
            )
            _is_cancel = isinstance(stream_exc, __import__("asyncio").CancelledError)
            _decision = ingress_decision if stream_exc is None else "error"
            _execution_status = (
                "ok" if stream_exc is None
                else ("interrupted" if _is_cancel else "error")
            )
            _result_summary = (
                None
                if stream_exc is None
                else (
                    "Stream cancelled by client" if _is_cancel
                    else f"stream aborted: {type(stream_exc).__name__}: {str(stream_exc)[:400]}"
                )
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
                    rule_id=ingress_rule_id,
                    routing_meta=routing_meta,
                    execution_status=_execution_status,
                    result_summary=_result_summary,
                    clerk_user_id=clerk_user_id,
                    ai_tool=ai_tool,
                    user_email=user_email,
                )
            except Exception:
                log.exception(
                    "guard.gateway.v2.stream_finalize_failed",
                    row_id=row_id,
                )

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
