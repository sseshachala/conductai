"""Gateway lifecycle phase 1: identity → admission (#2399).

Extracted verbatim from ``handle_gateway_request``. Same order, same
await points: member-token extraction, auth (cache, else threadpool DB
lookup), federation prepare, then the admission acquire immediately
after auth so overload is rejected before any further DB work.
"""
from __future__ import annotations

import structlog
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from app.modules.guard.gateway_request_state import GatewayCall

log = structlog.get_logger(__name__)


def extract_token(st: GatewayCall) -> JSONResponse | None:
    """Step 1 — member token / internal key. Returns the 401 when neither is present."""
    from app.guard.router import fail_closed as _fail_closed
    from app.modules.guard.gateway_helpers import _extract_member_token

    request = st.request
    # 1. Extract member token from whichever auth header the SDK sent
    raw = request.headers.get(st.auth_header_in, "")
    token = _extract_member_token(raw, bearer=st.bearer)
    if not token and st.auth_header_fallback:
        raw = request.headers.get(st.auth_header_fallback, "")
        token = _extract_member_token(
            raw,
            bearer=st.auth_header_fallback.lower() == "authorization",
        )
    st.token = token

    # Internal server-to-server bypass (brain block / runtime calling its own proxy).
    # The runtime sends a per-run cond_run_* token OR the workspace's
    # cond_agt_* Agent Identity token via x-conductai-internal.
    _internal_key = request.headers.get("x-conductai-internal", "")
    st.internal_key = _internal_key
    st.is_internal = False  # flips to True only after run/agent token validation
    st.needs_run_token_validation = bool(_internal_key and _internal_key.startswith("cond_run_"))
    st.needs_agent_validation = bool(_internal_key and _internal_key.startswith("cond_agt_"))

    if (
        not token and not st.is_internal
        and not st.needs_agent_validation and not st.needs_run_token_validation
    ):
        return _fail_closed(401, "Missing or malformed Conduct member token — run `conduct login`")
    return None


async def resolve_caller(st: GatewayCall, *, operation: str) -> JSONResponse | None:
    """Step 2 — resolve workspace + user, federation, then admission acquire."""
    from app.modules.guard.gateway_helpers import _resolve_gateway_auth

    request = st.request
    token = st.token
    _internal_key = st.internal_key
    _needs_run_token_validation = st.needs_run_token_validation
    _needs_agent_validation = st.needs_agent_validation
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
        st.workspace_id = workspace_id
        st.clerk_user_id = _cached_auth.clerk_user_id or "system"
        st.is_internal = _cached_auth.is_internal
        st.agent_identity_id = _cached_auth.agent_identity_id
        st.agent_risk_tier = _cached_auth.agent_risk_tier
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
        st.workspace_id = workspace_id
        st.clerk_user_id = _auth_result.clerk_user_id
        st.is_internal = _auth_result.is_internal
        st.agent_identity_id = _auth_result.agent_identity_id
        st.agent_risk_tier = _auth_result.agent_risk_tier
    from app.modules.auth.federation.gateway import prepare_gateway
    _federation = await run_in_threadpool(
        prepare_gateway, request, workspace_id, token, _internal_key, operation,
    )
    if isinstance(_federation, JSONResponse):
        return _federation
    st.federation = _federation
    if _federation and st.agent_identity_id is None:
        st.agent_identity_id = str(_federation.caller.agent_identity_id)
    # Admission acquire — immediately after auth, before any further
    # DB work. Overload rejected fast without checking out a
    # connection.
    from app.core.admission import AdmissionRefused as _AdmRefused
    from app.core.admission import _acquire as _admission_acquire
    try:
        st.admission_ticket = await _admission_acquire("gateway", workspace_id)
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
    return None
