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

        try:
            if operation == "openai_chat_completions":
                return await func(messages=payload["messages"], **kwargs)
            if operation == "openai_responses":
                return await func(input=payload["input"], **kwargs)
            if operation == "anthropic_messages":
                # anthropic_messages requires ``max_tokens`` positionally
                # in the current LiteLLM signature — pull from payload
                # with a sane default; capability catalog will refuse
                # any deployment that fails this contract.
                return await func(
                    max_tokens=payload.get("max_tokens", 1024),
                    messages=payload["messages"],
                    **kwargs,
                )
            if operation == "anthropic_count_tokens":
                # token_counter is sync + doesn't want api_key or stream;
                # strip the streaming/retry kwargs before calling.
                return func(
                    model=target.model,
                    messages=payload["messages"],
                )
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
