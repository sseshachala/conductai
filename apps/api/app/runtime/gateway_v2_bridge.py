"""Bridge between Gateway request lifecycle and v2 execution (#2004).

Splits three concerns out of ``gateway_handler.py`` so the v2 hook-in
stays a thin, testable fork of the v1 path:

- **Operation mapping** — provider + upstream URL → capability-catalog
  ``Operation`` string. Kept as a static dict because the launch matrix
  is intentionally narrow; expanding requires a matching entry in the
  capability catalog and a test.
- **Credential pre-resolution** — every target's Vault key gets resolved
  while the request-scoped DB session is still open, then handed to the
  coordinator as a plain callable. Keeps the coordinator + transport
  unit-testable and cleanly separates DB IO from network IO.
- **Response coercion** — LiteLLM SDK returns Pydantic objects; the v1
  gateway historically forwards raw JSON. Normalize to a JSON-safe dict
  so the downstream response gate and audit lifecycle don't have to
  branch on transport type.

Streaming lands via ``NativeHTTPTransport`` — see
``gateway_handler._execute_v2`` for the ``stream=true`` path.
LiteLLM SDK streaming isn't wired yet: a stream request that wins
against a LiteLLM target returns 501 (see the guard in
``_execute_v2``) rather than crashing inside ``coerce_response_body``.
"""
from __future__ import annotations

from typing import Any, Callable

from sqlalchemy.orm import Session

from app.modules.guard.gateway_config import (
    GatewayProfileV2,
    HTTPPassthroughTarget,
    LiteLLMSDKTarget,
    NativeHTTPTarget,
    Operation,
)
from app.modules.guard.gateway_credentials import (
    resolve_gateway_key,
    resolve_vendor_key,
)


# Integrations whose targets need a second (upstream vendor) API key
# pulled from the same vault entry as the primary integration key.
# Kept next to the bridge because the bridge is the boundary that
# converts DB reads into pure closures the coordinator can call
# without touching Postgres. Values must match
# ``IntegrationConfig.vendor_key_names`` in
# ``app/runtime/http_passthrough_transport.py``.
_VENDOR_KEY_NAMES_BY_INTEGRATION: dict[str, tuple[str, ...]] = {
    "helicone_openai":    ("OPENAI_API_KEY", "openai_api_key", "api_key"),
    "helicone_anthropic": ("ANTHROPIC_API_KEY", "anthropic_api_key", "api_key"),
}


# (provider, upstream_path) → capability-catalog Operation.
#
# Launch set matches ``_LITELLM_SDK_CERTIFIED`` in the capability
# catalog exactly. Extending BOTH tables is the checklist for adding a
# new operation — one without the other means a request hits a route
# with no coordinator dispatch, or a published profile with no way to
# route to it.
_ROUTE_TO_OPERATION: dict[tuple[str, str], Operation] = {
    ("anthropic", "/v1/messages"):                 "anthropic_messages",
    ("anthropic", "/v1/messages/count_tokens"):    "anthropic_count_tokens",
    ("openai",    "/v1/chat/completions"):         "openai_chat_completions",
    ("openai",    "/v1/responses"):                "openai_responses",
    # Legacy /chat/completions path (some SDKs strip the /v1/ prefix).
    ("openai",    "/chat/completions"):            "openai_chat_completions",
}


def map_operation(provider: str, upstream_path: str) -> Operation | None:
    """Return the ``Operation`` for a (provider, upstream_path) pair.

    ``None`` means the URL surface isn't served by v2 — the caller
    should fall through to the v1 path rather than fail closed. Adding
    a new operation is a two-step change (this table + the capability
    catalog) so a partial rollout can't route to something the
    coordinator refuses.
    """
    return _ROUTE_TO_OPERATION.get((provider, upstream_path))


class CredentialsUnavailable(RuntimeError):
    """Raised when a target's Vault credential can't be resolved.

    Fail-closed by design — a missing credential is a config error,
    not a transient failure, and letting the coordinator's retry loop
    burn attempts against the same missing key just delays the eventual
    error to the client. The gateway_handler catches this and returns
    503 with the specific target id so ops can find the fix in one
    click.
    """

    def __init__(self, target_id: str, credential_ref: str) -> None:
        self.target_id = target_id
        self.credential_ref = credential_ref
        super().__init__(
            f"credential for target {target_id!r} at {credential_ref!r} "
            f"is not available in Vault. Fix by adding the credential to "
            f"the environment referenced by the ref, then republish."
        )


def build_credential_resolver(
    db: Session,
    *,
    workspace_id: str,
    environment_id: str | None,
    provider: str,
    profile: GatewayProfileV2,
) -> Callable[[str], str]:
    """Pre-resolve every target's credential while the DB session is
    open. Return a pure callable the coordinator can use per attempt.

    Rationale: the request-scoped ``db`` session is closed before the
    coordinator runs (the DB block finishes before the forward). If we
    handed the coordinator a resolver that reached back into the DB,
    every attempt would either need its own short-lived session or leak
    the request session across the forward boundary. Neither is worth
    the complexity; the number of targets per profile is bounded (list
    length is capped by publish-time validation), and pre-resolving is
    O(targets) — the same or fewer DB reads than a lazy resolver would
    do in the fallback case.

    A target with an unresolvable credential is raised as
    ``CredentialsUnavailable`` — that maps cleanly to a 503 at the
    handler level. Callers should NOT try to route the request without
    every target's key ready, because a partial resolution means a
    fallback attempt could silently degrade to an unavailable route.
    """
    resolved: dict[str, str] = {}
    for target in profile.targets:
        if not isinstance(
            target,
            (NativeHTTPTarget, LiteLLMSDKTarget, HTTPPassthroughTarget),
        ):  # pragma: no cover - future safety
            continue

        # PR 5 — passthrough targets carry their own credentials
        # (OpenRouter key, Portkey key, Helicone key). Pre-resolve them
        # the same way as native + LiteLLM so the coordinator's
        # resolver stays a pure callable. The credential lookup uses
        # ``target.integration`` as the provider hint since passthrough
        # targets don't carry a ``provider`` field.
        provider_hint = (
            getattr(target, "provider", None)
            or getattr(target, "integration", None)
            or provider
        )
        key = resolve_gateway_key(
            db,
            workspace_id,
            target.credential_ref,
            provider_hint,
            environment_id,
        )
        if not key:
            raise CredentialsUnavailable(target.id, target.credential_ref)
        resolved[target.credential_ref] = key

    def _resolver(credential_ref: str) -> str:
        key = resolved.get(credential_ref)
        if not key:
            # Should never fire in practice — build_credential_resolver
            # already refused to return if any target's key was missing.
            # Belt-and-braces so a coordinator bug can't surface as a
            # silent empty api_key to LiteLLM.
            raise CredentialsUnavailable("<unknown>", credential_ref)
        return key

    return _resolver


def build_vendor_credential_resolver(
    db: Session,
    *,
    workspace_id: str,
    environment_id: str | None,
    profile: GatewayProfileV2,
) -> Callable[[str], str] | None:
    """Pre-resolve vendor keys for Helicone-style two-key integrations.

    Returns ``None`` if no target in the profile needs a vendor key —
    keeps the coordinator's per-attempt hot path free of extra
    indirection when only one-key integrations are in play.

    Fail-closed: any Helicone target that can't produce a vendor key
    from its vault entry raises ``CredentialsUnavailable`` so publish-
    time validation + resolve-time errors match — an admin can never
    reach the transport with half-configured Helicone credentials.
    """
    resolved: dict[str, str] = {}
    needs_vendor = False
    for target in profile.targets:
        if not isinstance(target, HTTPPassthroughTarget):
            continue
        vendor_names = _VENDOR_KEY_NAMES_BY_INTEGRATION.get(target.integration)
        if not vendor_names:
            continue
        needs_vendor = True
        vendor_key = resolve_vendor_key(
            db,
            workspace_id,
            target.credential_ref,
            vendor_names,
            environment_id,
        )
        if not vendor_key:
            raise CredentialsUnavailable(target.id, target.credential_ref)
        resolved[target.credential_ref] = vendor_key

    if not needs_vendor:
        return None

    def _vendor_resolver(credential_ref: str) -> str:
        key = resolved.get(credential_ref)
        if not key:
            raise CredentialsUnavailable("<unknown>", credential_ref)
        return key

    return _vendor_resolver


def coerce_response_body(response: Any) -> Any:
    """Normalize a LiteLLM SDK response into a JSON-safe dict.

    LiteLLM returns Pydantic v2 model instances for most operations
    (``ModelResponse``, ``ResponsesAPIResponse``, ...). FastAPI's
    ``JSONResponse`` doesn't know how to serialize those directly, and
    hard-coding ``.model_dump()`` would break for ``anthropic_messages``
    which already returns a dict. Prefer duck-typing over isinstance
    checks so the LiteLLM version bump doesn't shift the API here.
    """
    if hasattr(response, "model_dump"):
        return response.model_dump()
    if hasattr(response, "dict") and callable(response.dict):
        # Pydantic v1 compat, if some path in LiteLLM still returns one.
        return response.dict()
    return response


__all__ = [
    "CredentialsUnavailable",
    "build_credential_resolver",
    "build_vendor_credential_resolver",
    "coerce_response_body",
    "map_operation",
]
