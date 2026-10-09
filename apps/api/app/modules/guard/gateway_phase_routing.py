"""Gateway lifecycle phase 2: body → model routing → request context (#2399).

Extracted verbatim from ``handle_gateway_request``: parse the JSON body,
resolve the model (canonical-profile selection or v1 tier resolution),
build ``routing_meta`` (operation, federation provenance, tool signals),
build the v2 plan when the request names a ``cond-*`` profile, then load
the audit context (user email, run headers, trial plan).
"""
from __future__ import annotations

from typing import Callable

import structlog
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.modules.guard.gateway_request_state import GatewayCall
from app.modules.guard.gateway_v2_plan import _extract_cond_code

log = structlog.get_logger(__name__)


async def parse_and_route(
    st: GatewayCall, *, build_v2_plan_owned: Callable,
) -> JSONResponse | None:
    """Step 3 — parse body, resolve model + routing_meta, build the v2 plan.

    ``build_v2_plan_owned`` is passed in by the handler so the lookup stays
    ``gateway_handler._build_v2_plan_owned`` (the patch point tests use).
    """
    from app.guard.router import fail_closed as _fail_closed
    from app.modules.guard.gateway_helpers import _apply_tier_resolution_owned, _infer_ai_tool

    request = st.request
    provider = st.provider
    upstream_path = st.upstream_path
    operation = st.operation
    workspace_id = st.workspace_id
    _federation = st.federation
    # 3. Parse request body
    try:
        body = await request.json()
    except Exception:
        return _fail_closed(400, "Body must be valid JSON")
    st.body = body

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

    _selection = None
    _v2_enabled = settings.gateway_profile_v2_enabled_for(workspace_id)
    if st.canonical_profile and _v2_enabled and _extract_cond_code(body.get("model")) is None:
        from app.modules.guard.gateway_model_selection import select_model_owned
        _selection = await run_in_threadpool(
            select_model_owned, workspace_id, body.get("model"), provider, upstream_path,
        )
        model = body["model"] = _selection.model_id
        _routing_meta = _selection.metadata
    else:
        model, _routing_meta = await run_in_threadpool(
            _apply_tier_resolution_owned, workspace_id, provider, body,
        )
    st.model = model
    # Keep the wire operation for audit normalization even without a
    # v2 profile. The generic "inference" label cannot distinguish
    # Chat Completions from Responses usage.
    _routing_meta = {**(_routing_meta or {}), "operation": upstream_path}
    if _federation:
        from app.modules.auth.federation.ingress import provenance
        _routing_meta["federation"] = provenance(_federation)
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
    _tools_offered = st.tools_offered = _extract_tools_offered(body)
    _tool_results_supplied = _extract_tool_results_supplied(body)
    # Reviewer P2 #3 (2026-09-20): supplied-tool NAMES are the
    # policy-relevant signal (rule fires on "bank_transfer", not on
    # "call_abc"). IDs stay on routing_meta for the correlation
    # trail; names go into PolicyContext.tool_names_supplied.
    _tool_names_supplied = st.tool_names_supplied = _extract_tool_names_supplied(body)
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
    st.routing_meta = _routing_meta

    # #2004 Phase 1 — v2 lookup + credential pre-fetch. A None plan means
    # v1 handles this request as before. Resolve by cond_code parsed out
    # of the client-sent ``model:`` field (``cond-<8chars>-<alias>``).
    # Cond-prefixed identifier detection runs REGARDLESS of the flag:
    # a client that sent `cond-<code>-<alias>` explicitly asked for a v2
    # profile; silently routing them via v1 when the flag is off would
    # misrepresent which profile served the traffic.
    #
    # PR 3 canary: the flag is per-workspace via
    # ``gateway_profile_v2_enabled_for(workspace_id)`` — allowlist + pct
    # bucketing on top of the global kill switch. Deterministic bucketing
    # means a workspace never oscillates between v1 and v2 mid-session.
    _cond_code = _selection.cond_code if _selection else _extract_cond_code(body.get("model"))
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
                build_v2_plan_owned,
                workspace_id=workspace_id,
                cond_code=_cond_code,
                provider=provider,
                upstream_path=upstream_path,
                body=body,
                **({"resolved": _selection.resolved} if _selection else {}),
            )
            st.v2_plan = _v2_plan
            if _v2_plan is not None:
                _routing_meta = st.routing_meta = {
                    **(_routing_meta or {}),
                    "gateway_version": "v2",
                    "cond_code": _cond_code,
                    "gateway_profile_id": str(_v2_plan.resolved.profile_id) if getattr(_v2_plan.resolved, "profile_id", None) else None,
                    "gateway_profile": model,
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
    st.ai_tool = request.headers.get("x-conduct-ai-tool") or _infer_ai_tool(request)
    return None


async def load_request_context(st: GatewayCall) -> None:
    """Steps 4a/4b — user email, workflow-run headers, trial-plan lookup."""
    request = st.request
    workspace_id = st.workspace_id
    # 4a. Resolve user email for audit rows — offloaded to threadpool
    # with an own-session helper (P1 review fix, replaces sync
    # ``db.query`` on the event loop that used the shared session).
    from app.modules.guard.gateway_helpers import _lookup_user_email as _lookup_user_email_fn
    st.user_email = await run_in_threadpool(
        _lookup_user_email_fn, workspace_id, st.clerk_user_id,
    )

    # 4b. Run context from brain block headers (workflow runs only)
    _run_id = request.headers.get("x-conductai-run-id") or None
    if st.federation and st.federation.run_id:
        _run_id = str(st.federation.run_id)
    st.run_id = _run_id
    st.workflow = request.headers.get("x-conductai-workflow") or None
    st.workflow_id = request.headers.get("x-conductai-workflow-id") or None
    st.environment_id = request.headers.get("x-conductai-environment-id") or None
    # #1959 Phase 0 note: Flight Recorder session correlation currently
    # requires clients to send X-Conduct-Session-Id. Codex Desktop's
    # config.toml does not populate it today. Without this header the
    # audit row lands with hook_session_id=NULL; do NOT synthesize one
    # from timestamps or client IP — attribution has to be honest.
    # Follow-up: signed session claims via Agent Identity (tracked
    # alongside #1968) will make this observable per-request.
    st.hook_session_id = request.headers.get("x-conduct-session-id") or None

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
    st.is_trial = False
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
            st.is_trial = (_row.plan == _TRIAL_PLAN and _row.owner_id is None)
    except Exception:
        pass
