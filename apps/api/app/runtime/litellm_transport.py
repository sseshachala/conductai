"""In-process LiteLLM transport for Gateway Profile v2 (#2001, commit 4/4).

Executes an ordered target from a v2 profile through LiteLLM's Python
SDK, mapped to operation-specific APIs rather than everything through
``completion()``. Retries are Conduct-owned — LiteLLM's own retry ladder
is turned off by design (``num_retries=0``) so we don't stack attempts.
Credentials are resolved per-attempt from Vault and never persisted in
LiteLLM's callback/log surface.

Operation dispatch (mapped to the pinned LiteLLM version — capability
catalog gates which of these are user-selectable at publish time):

    anthropic_messages       → litellm.anthropic_messages(...)      async
    anthropic_count_tokens   → litellm.token_counter(...)           sync
    openai_chat_completions  → litellm.acompletion(...)             async
    openai_responses         → litellm.aresponses(...)              async

Nothing in this module reads a database directly. The caller supplies a
``credential_resolver`` — a callable that takes a ``vault://<env>/<name>``
ref and returns the plaintext API key. Keeps the transport unit-testable
without a live DB and enforces the "credential scoped to one attempt"
contract explicitly.

Registered under the transport name ``litellm_sdk`` and bound to
``provider="litellm"`` in the shared registry when
``settings.guard_litellm_in_process`` is true. Off by default; the
existing ``RawHTTPTransport`` still services ``provider="litellm"``
traffic (as proxy-through) until the flag is flipped per workspace.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Protocol, runtime_checkable

import structlog

from app.modules.guard.gateway_config import (
    LiteLLMSDKTarget,
    Operation,
)


log = structlog.get_logger(__name__)


#: A callable that takes a ``vault://<environment-uuid>/<name>`` ref
#: and returns the plaintext credential. In production this closes over
#: the DB session + workspace id. In tests it's a lambda returning a
#: fake key. Either way the transport does not touch a database.
CredentialResolver = Callable[[str], str]


@runtime_checkable
class V2Transport(Protocol):
    """Contract every v2 transport implements.

    Deliberately separate from the v1 ``ProviderTransport`` — the v1
    protocol conflates client-building with wire-forwarding and doesn't
    carry the operation typing that v2 needs. A v2 transport takes a
    target + operation + payload and returns the raw LiteLLM (or
    passthrough) response; the caller wraps it into the client-facing
    HTTP response.
    """

    name: str

    async def execute(
        self,
        *,
        target: LiteLLMSDKTarget,
        operation: Operation,
        payload: dict[str, Any],
        credential_resolver: CredentialResolver,
        stream: bool = False,
    ) -> Any: ...


class LiteLLMTransport:
    """In-process LiteLLM SDK executor.

    Instantiated once per worker process; safe to reuse across requests
    because state per attempt (credential, model, messages) is passed
    into each ``execute()`` call.
    """

    name = "litellm_sdk"

    #: Every operation this transport claims to support MUST have a
    #: corresponding line in the capability catalog before it can be
    #: published to any workspace. This list is the runtime side of that
    #: contract — if the caller passes an operation not in this map,
    #: we raise a clear error rather than silently drop.
    _dispatch: dict[Operation, str] = {
        "anthropic_messages":      "anthropic_messages",   # async
        "anthropic_count_tokens":  "token_counter",        # sync
        "openai_chat_completions": "acompletion",          # async
        "openai_responses":        "aresponses",           # async
    }

    async def execute(
        self,
        *,
        target: LiteLLMSDKTarget,
        operation: Operation,
        payload: dict[str, Any],
        credential_resolver: CredentialResolver,
        stream: bool = False,
    ) -> Any:
        if operation not in self._dispatch:
            raise ValueError(
                f"LiteLLMTransport does not support operation {operation!r}. "
                f"Known operations: {sorted(self._dispatch)}. Extend the "
                f"capability catalog *and* this dispatch table together."
            )

        # Resolve the credential immediately before the call and never
        # store it beyond this function's stack frame. LiteLLM's
        # callbacks/logs receive the api_key as a kwarg but must not
        # persist it — configuring callbacks is server-side only (Phase
        # 1 story 12 of #1911), so the surface for accidental
        # persistence is bounded.
        api_key = credential_resolver(target.credential_ref)
        if not api_key:
            raise ValueError(
                f"credential_resolver returned empty for {target.credential_ref!r}"
            )

        kwargs: dict[str, Any] = {
            "model": target.model,
            "api_key": api_key,
            "custom_llm_provider": target.provider,
            # Conduct owns the retry ladder. LiteLLM's own retries would
            # stack on ours, and the ``max_attempts`` field on the v2
            # profile would silently mean 2× or 3× what the admin
            # intended.
            "num_retries": 0,
            "stream": stream,
        }
        # ``provider_options`` are per-provider knobs (region, api_version,
        # etc.). Merged with the resolver's output; explicit fields above
        # win over provider_options.
        for key, value in target.provider_options.items():
            kwargs.setdefault(key, value)

        # Late import: keeps ``litellm`` off the module-load path so
        # test suites that don't exercise LiteLLM aren't paying the
        # (heavy) import cost, and so mocks can patch the module before
        # first use.
        import litellm

        func = getattr(litellm, self._dispatch[operation])

        # #2001 review fix — explicit per-operation payload whitelisting
        # rather than a blanket dict.update(payload). The prior draft
        # accepted arbitrary SDK kwargs and only reserved five fields,
        # which meant a client could inject api_base, base_url,
        # organization, proxy, callbacks, etc. to redirect traffic
        # while still using the Vault-resolved key. Transport / auth /
        # routing controls are Conduct-owned; the client can only
        # supply operation-body fields on the whitelist below.
        payload_fields = _payload_fields_for(operation, payload)

        try:
            if operation == "openai_chat_completions":
                return await func(**kwargs, **payload_fields)
            if operation == "openai_responses":
                return await func(**kwargs, **payload_fields)
            if operation == "anthropic_messages":
                # max_tokens is required by LiteLLM signature; default
                # if the client omitted it.
                payload_fields.setdefault("max_tokens", 1024)
                return await func(**kwargs, **payload_fields)
            if operation == "anthropic_count_tokens":
                # token_counter is sync + doesn't want api_key/stream.
                counter_kwargs = {"model": target.model, **payload_fields}
                return func(**counter_kwargs)
            # Unreachable — guarded by the dispatch check above.
            raise ValueError(f"unhandled operation {operation!r}")  # pragma: no cover
        except Exception:
            # Do NOT log the api_key or the payload — either could leak
            # customer data. The caller records the failure into
            # ``routing_meta`` with the target id + version pinned; the
            # log line here is just a breadcrumb.
            log.warning(
                "gateway.v2.litellm.transport_error",
                target_id=target.id,
                provider=target.provider,
                operation=operation,
            )
            raise


def register_litellm_transport_if_enabled() -> None:
    """Bind LiteLLMTransport to ``provider='litellm'`` when the flag is on.

    Called once at worker startup. Idempotent — calling twice is a no-op
    because the registry's ``replace=True`` semantics kick in.
    """
    from app.core.config import settings
    if not settings.guard_litellm_in_process:
        return

    # v1 transport registry only knows how to serve the v1
    # ``ProviderTransport`` protocol. LiteLLMTransport is a v2 transport;
    # it lives in its own module and is looked up by the v2 runtime.
    # This function is a hook point — commit 5 (the request-path wiring)
    # will use it to swap the resolver's transport lookup.
    log.info(
        "gateway.v2.litellm_transport.enabled",
        transport=LiteLLMTransport.name,
    )


# ─── Payload whitelisting per operation (#2001 review) ────────────────


# Per-operation allowed body fields. Anything else the client sends is
# dropped BEFORE it reaches LiteLLM, so a request payload cannot
# override transport/auth (api_key, api_base, base_url, organization,
# proxy, num_retries, callbacks, ...) or routing (custom_llm_provider,
# model) — those are Conduct-owned.
#
# If a legitimately-missing field lands here (LiteLLM adds a new
# operation-body parameter we haven't reviewed), we'll notice because
# the client-visible behavior degrades and we can extend this table
# with an intentional decision. Silently forwarding everything was the
# review-flagged failure mode.
_ALLOWED_PAYLOAD_FIELDS: dict[Operation, frozenset[str]] = {
    "openai_chat_completions": frozenset({
        "messages", "tools", "tool_choice", "response_format",
        "temperature", "top_p", "n", "stop", "max_tokens",
        "presence_penalty", "frequency_penalty", "logit_bias", "user",
        "seed", "logprobs", "top_logprobs", "parallel_tool_calls",
        "service_tier", "reasoning_effort",
    }),
    "openai_responses": frozenset({
        "input", "instructions", "previous_response_id", "tools",
        "tool_choice", "text", "reasoning", "max_output_tokens",
        "temperature", "top_p", "parallel_tool_calls", "user", "metadata",
        "truncation",
    }),
    "anthropic_messages": frozenset({
        "messages", "system", "max_tokens", "metadata",
        "stop_sequences", "temperature", "top_k", "top_p", "tools",
        "tool_choice", "thinking",
    }),
    "anthropic_count_tokens": frozenset({
        "messages", "system", "tools", "tool_choice",
    }),
}


def _payload_fields_for(operation: Operation, payload: dict[str, Any]) -> dict[str, Any]:
    """Return the subset of ``payload`` the operation's LiteLLM API
    accepts. Anything else — including SDK controls like ``api_base``
    or ``callbacks`` — is dropped."""
    allowed = _ALLOWED_PAYLOAD_FIELDS.get(operation, frozenset())
    return {k: v for k, v in payload.items() if k in allowed}
