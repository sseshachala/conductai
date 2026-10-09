"""Gateway lifecycle phase 4: v1 upstream credentials → outbound request (#2399).

Extracted verbatim from ``handle_gateway_request``: legacy (v1-only)
vault/credential resolution with the trial-key fallback, then secret
redaction, guidance injection, stream flag, vendor header passthrough
and the client ``X-Request-Id`` merge into ``routing_meta``.
"""
from __future__ import annotations

import structlog
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from app.modules.guard.gateway_phase_policy import record_failure
from app.modules.guard.gateway_request_state import GatewayCall

log = structlog.get_logger(__name__)


async def resolve_upstream_credentials(st: GatewayCall) -> JSONResponse | None:
    """Step 5 — vault lookup. For BYO gateways: upstream_key authenticates with
    the gateway, vault_key is the real vendor key the gateway forwards to.

    X3 — legacy credential resolution is v1-only. v2 targets carry their
    own ``credential_ref`` pointing at Vault; the resolver was built with
    the v2 plan. Running this block for v2 traffic was dead weight AND
    broke v2-only workspaces (the 503 below fired before ``_execute_v2``
    ever ran). Skip the whole block when ``_v2_plan`` is in play.
    """
    from app.guard.router import fail_closed as _fail_closed
    from app.runtime.provider_transport import get_provider_transport_registry

    workspace_id, provider = st.workspace_id, st.provider
    _environment_id, _v2_plan = st.environment_id, st.v2_plan
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
        if st.canonical_profile:
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
            _aid = st.agent_identity_str
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
                record_failure(st, 401, "trial_expired", rule_id="trial-expired")
                return _fail_closed(
                    401,
                    "trial_expired: 7-day trial ended. Add your own key in Settings → Environments.",
                )
            if _trial_status == "exceeded":
                record_failure(st, 429, "trial_exceeded", rule_id="trial-quota")
                return _fail_closed(
                    429,
                    "trial_exceeded: daily trial quota hit. Add your own key in Settings → Environments.",
                )
            real_key = _trial_key
        if not real_key:
            record_failure(st, 503, f"No {provider} API key configured", rule_id="credential-missing")
            return _fail_closed(
                503,
                f"No API key configured — add {provider.upper()}_API_KEY in Settings → Environments, "
                f"or set LLM_UPSTREAM_API_KEY in Settings → Proxy.",
            )
    st.upstream, st.upstream_key, st.vault_key_val = upstream, _upstream_key, _vault_key_val
    st.transport, st.real_key = transport, real_key
    return None


def prepare_outbound_request(st: GatewayCall) -> None:
    """Steps 5.5–6 — redact, inject guidance, stream flag, vendor headers."""
    from app.modules.guard.gateway_helpers import _inject_guidance, _redact_body

    request, operation, workspace_id = st.request, st.operation, st.workspace_id
    body = st.body
    # 5.5 Redact secrets from body before forwarding — runs after policy eval so
    # credential-leak rules still fire first and can block.
    if operation == "inference":
        body, _redacted = _redact_body(body)
        st.body = body
        if _redacted:
            log.info("guard.proxy.redacted", types=_redacted, workspace_id=workspace_id)

    # 5.6 Inject guidance to model when rule has inject_guidance=true (#1141).
    # Fires for warn/audit/allow paths — block path is handled above via response body.
    if st.guidance_text and operation == "inference":
        body = st.body = _inject_guidance(body, st.guidance_text, st.provider)
        log.info("guard.proxy.guidance_injected",
                 rule_id=st.decision.get("rule_id"), workspace_id=workspace_id)

    # 6. Forward + stream back. Use a fresh DB session inside the background task.
    st.is_stream = bool(body.get("stream"))
    # Pass through all vendor-specific headers the SDK sends (anthropic-beta,
    # openai-organization, openai-project, etc.) minus the ones we own.
    _skip = {
        st.auth_header_in,
        st.auth_header_fallback,
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
    st.extra_headers = {
        k.lower(): v for k, v in request.headers.items()
        if k.lower() not in _skip and not k.lower().startswith("x-conduct")
    }
    # P2: merge the client's X-Request-Id into routing_meta *at the
    # caller* so the enriched dict is what flows through open + audit
    # + downstream finalize. Prior split (writer enriched, caller kept
    # original) meant audit.finalize's ``routing_meta = CAST(:routing
    # AS jsonb)`` UPDATE clobbered client_request_id back out on the
    # finalized row.
    _client_request_id = st.client_request_id = request.headers.get("x-request-id") or None
    if _client_request_id:
        st.routing_meta = {**(st.routing_meta or {}), "client_request_id": _client_request_id}
