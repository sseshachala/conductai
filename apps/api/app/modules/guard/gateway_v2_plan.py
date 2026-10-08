"""Gateway v2 request planning — ``_V2Plan``, vendor-header allowlist, and
the policy-check builder used by ``handle_gateway_request``.

Split out of ``gateway_handler.py``; re-exported there."""
from __future__ import annotations


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
        "upstream_body",
        "dispatched",
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
        self.upstream_body = bytearray()
        self.dispatched = False
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
    resolved=None,
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
            resolved=resolved,
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
    resolved=None,
) -> _V2Plan | None:
    """Build a pinned v2 plan, rejecting unsupported operations or credentials.

    ``resolved`` is an internal selection from the same authenticated workspace,
    never client input. Reuse its revision rather than re-reading a publish pointer.
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

    if resolved is None:
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
                or getattr(t, "transport", None) == "litellm_sdk" and getattr(t, "provider", None) == "openai"
                or getattr(t, "transport", None) == "http_passthrough" and (
                    getattr(t, "integration", None) == "helicone_anthropic"
                    or getattr(t, "integration", None) == "custom" and t.provider_options.get("protocol") == "anthropic"
                )
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
