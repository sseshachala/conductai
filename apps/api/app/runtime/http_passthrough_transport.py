"""HTTP passthrough transport for v2 targets that hit an external gateway.

Same shape as ``NativeHTTPTransport`` (see ``native_http_transport.py``)
but the endpoint + auth-header shape is picked per-integration rather
than per-provider. The client's request body is proxied verbatim except
for the ``model`` field, which is swapped for the target's own model id.

Launch set (PR 5): **OpenRouter** as the reference integration. Other
integrations register into ``_INTEGRATION_ENDPOINTS`` below plus a
matching entry in ``capability_catalog._HTTP_PASSTHROUGH_CERTIFIED``.

Adding a new integration is a two-step change:

1. Add an ``IntegrationConfig`` entry here with the endpoint + auth
   header shape (and per-operation URL path map).
2. Certify the (integration, operation) tuples in the capability
   catalog.

Publish rejects any (integration, operation) not in both tables.

Coordinator retries are Conduct-owned. This transport does zero retries
on its own — same contract the LiteLLM + native_http transports follow.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import httpx
import structlog

from app.modules.guard.gateway_config import (
    HTTPPassthroughTarget,
    Integration,
    Operation,
)


log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class IntegrationConfig:
    """Endpoint + auth shape for one supported passthrough integration.

    - ``base_url``: without trailing slash. A ``HTTPPassthroughTarget``
      can override via its ``endpoint`` field only when
      ``allows_endpoint_override=True`` (currently reserved for
      integration='custom').
    - ``auth_header``: header name for the API key.
    - ``bearer_prefix``: True if the value should be ``"Bearer <key>"``.
    - ``extra_headers``: static headers this integration requires
      (e.g. ``anthropic-version`` for Helicone-anthropic).
    - ``operation_paths``: per-Operation URL path map. Absence = the
      integration doesn't (yet) certify that operation; publish
      rejects the combo before it can reach here.
    - ``allows_endpoint_override``: whether ``target.endpoint`` may
      replace ``base_url`` at request time. Only ``custom`` should
      flip this on today — the other integrations pin their URL so
      an admin publishing a Portkey target can't accidentally route
      through the wrong host.
    - ``vendor_auth_header`` / ``vendor_bearer_prefix`` /
      ``vendor_key_names``: two-key integrations (Helicone) authenticate
      the observability layer via ``auth_header`` AND the upstream
      vendor via ``vendor_auth_header``. Both keys live in the SAME
      vault entry — ``vendor_key_names`` lists the credential-dict
      names to try when the transport asks the vendor resolver for
      the upstream key. Empty tuple = one-key integration.
    """
    base_url: str
    auth_header: str
    bearer_prefix: bool
    operation_paths: dict[Operation, str]
    extra_headers: dict[str, str] = field(default_factory=dict)
    allows_endpoint_override: bool = False
    vendor_auth_header: str | None = None
    vendor_bearer_prefix: bool = False
    vendor_key_names: tuple[str, ...] = ()


# One entry per supported integration. Adding one here requires a
# matching entry in ``capability_catalog._HTTP_PASSTHROUGH_CERTIFIED``.
#
# OpenRouter is OpenAI-compatible on ``/api/v1/chat/completions``.
# Auth is ``Authorization: Bearer <openrouter_key>``. ``HTTP-Referer``
# + ``X-Title`` are OpenRouter's recommended attribution headers —
# without them Conduct traffic lands in the "unknown" bucket in
# OpenRouter's analytics + rate-limit dashboards.
_INTEGRATION_ENDPOINTS: dict[Integration, IntegrationConfig] = {
    "openrouter": IntegrationConfig(
        base_url="https://openrouter.ai/api/v1",
        auth_header="authorization",
        bearer_prefix=True,
        operation_paths={
            "openai_chat_completions": "/chat/completions",
        },
        extra_headers={
            # Hardcoded to Conduct's marketing URL. OpenRouter treats
            # HTTP-Referer as coarse attribution, not per-tenant
            # routing, so a per-workspace value would be misleading.
            # Follow-up: expose as ``target.provider_options`` (via a
            # schema addition on HTTPPassthroughTarget) if a customer
            # needs per-workspace attribution.
            "HTTP-Referer": "https://conductai.ai",
            "X-Title": "Conduct AI Gateway",
        },
    ),
    # PR 4 — Portkey. OpenAI-compat on ``/v1/chat/completions``. Auth
    # uses a raw key in ``x-portkey-api-key`` (NOT ``Authorization:
    # Bearer``). ``provider_options`` supplies the upstream selector
    # (virtual_key / provider / config) — transport injects the
    # matching ``x-portkey-*`` header at request time.
    "portkey": IntegrationConfig(
        base_url="https://api.portkey.ai/v1",
        auth_header="x-portkey-api-key",
        bearer_prefix=False,
        operation_paths={
            "openai_chat_completions": "/chat/completions",
        },
    ),
    # PR 5 — Helicone observability proxy for OpenAI. Two-key auth:
    # ``Helicone-Auth: Bearer <helicone-key>`` for the observability
    # layer PLUS ``Authorization: Bearer <openai-key>`` for the upstream
    # vendor. Both keys live in the same vault handle
    # (HELICONE_API_KEY + OPENAI_API_KEY inside one credential blob).
    "helicone_openai": IntegrationConfig(
        base_url="https://oai.helicone.ai/v1",
        auth_header="Helicone-Auth",
        bearer_prefix=True,
        operation_paths={
            "openai_chat_completions": "/chat/completions",
        },
        vendor_auth_header="authorization",
        vendor_bearer_prefix=True,
        vendor_key_names=("OPENAI_API_KEY", "openai_api_key", "api_key"),
    ),
    # PR 5 — Helicone observability proxy for Anthropic. Same
    # two-key pattern; vendor uses ``x-api-key`` (no Bearer prefix)
    # plus the mandatory ``anthropic-version`` static header.
    "helicone_anthropic": IntegrationConfig(
        base_url="https://anthropic.helicone.ai/v1",
        auth_header="Helicone-Auth",
        bearer_prefix=True,
        operation_paths={
            "anthropic_messages": "/messages",
        },
        extra_headers={
            # Anthropic REST requires an explicit API-version pin. The
            # Anthropic native transport sends this too — Helicone just
            # forwards it through to Anthropic.
            "anthropic-version": "2023-06-01",
        },
        vendor_auth_header="x-api-key",
        vendor_bearer_prefix=False,
        vendor_key_names=("ANTHROPIC_API_KEY", "anthropic_api_key", "api_key"),
    ),
}


class UnsupportedPassthroughIntegration(Exception):
    """Raised when a target's integration has no registered endpoint.

    The publish-time capability catalog gates this in ~every practical
    case; this exception is belt-and-braces for the "bad publish
    slipped past validation" corner and surfaces the missing
    integration name clearly."""


class HTTPPassthroughTransport:
    """Executes a http_passthrough target against a registered external gateway.

    One instance per worker process; state per attempt lives on the
    ``execute`` call frame. Uses a lazily-initialised shared httpx
    ``AsyncClient`` with a bounded connection pool so v2 traffic
    doesn't spin up a client per request.
    """

    name = "http_passthrough"

    def __init__(self, *, timeout_seconds: float = 60.0) -> None:
        self._timeout_seconds = timeout_seconds
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self._timeout_seconds, connect=10.0),
                limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
            )
        return self._client

    async def execute(
        self,
        *,
        target: HTTPPassthroughTarget,
        operation: Operation,
        payload: dict[str, Any],
        credential_resolver,
        stream: bool = False,
        client_headers: dict[str, str] | None = None,
        vendor_credential_resolver=None,
    ) -> Any:
        """Forward the payload to the integration's endpoint.

        Non-streaming: returns the parsed JSON body (dict).
        Streaming: raises ``NotImplementedError``. Streaming through
        passthrough integrations is a follow-up PR — the launch set is
        request/response only. Callers must publish a native_http
        target ahead of a passthrough target for streaming to work.

        X7 — ``client_headers`` is the allowlisted subset of the
        original request's vendor headers (``openai-organization``,
        ``anthropic-beta``, etc.). Merged into the outgoing headers
        AFTER the integration's own auth + static headers.

        Two-key integrations (Helicone): ``vendor_credential_resolver``
        must resolve the upstream vendor key from the SAME vault entry
        as ``credential_resolver``. Missing when required = fail-closed
        ValueError before the wire.
        """
        if stream:
            raise NotImplementedError(
                "HTTPPassthroughTransport streaming is a follow-up PR. "
                "Put a native_http target ahead of this passthrough "
                "target in the profile so streaming requests hit the "
                "native path first."
            )

        config = _INTEGRATION_ENDPOINTS.get(target.integration)
        if config is None:
            raise UnsupportedPassthroughIntegration(
                f"http_passthrough target {target.id!r} uses integration "
                f"{target.integration!r} which has no endpoint registered "
                f"in HTTPPassthroughTransport. Extend `_INTEGRATION_ENDPOINTS` "
                f"and the capability catalog together, or drop the target."
            )

        upstream_path = config.operation_paths.get(operation)
        if upstream_path is None:
            raise ValueError(
                f"http_passthrough target {target.id!r} advertises operation "
                f"{operation!r} which has no upstream URL path for "
                f"integration {target.integration!r}. The capability "
                f"catalog should have caught this at publish."
            )

        base_url = self._resolve_base_url(target, config)

        api_key = credential_resolver(target.credential_ref)
        if not api_key:
            raise ValueError(
                f"credential_resolver returned empty for "
                f"{target.credential_ref!r}"
            )

        request_body = dict(payload)
        request_body["model"] = target.model

        headers = {
            "content-type": "application/json",
            config.auth_header: (
                f"Bearer {api_key}" if config.bearer_prefix else api_key
            ),
            **config.extra_headers,
            **(client_headers or {}),
        }
        # content-type + auth stay under transport control regardless of
        # what the client sent.
        headers["content-type"] = "application/json"
        headers[config.auth_header] = (
            f"Bearer {api_key}" if config.bearer_prefix else api_key
        )

        # PR 4 — Portkey routing headers. Per Portkey docs the gateway
        # key alone doesn't select an upstream; one of
        # ``x-portkey-virtual-key`` / ``x-portkey-provider`` /
        # ``x-portkey-config`` MUST accompany the auth key. Admin
        # supplies via ``provider_options``.
        if target.integration == "portkey":
            opts = getattr(target, "provider_options", None) or {}
            if virtual_key := opts.get("virtual_key"):
                headers["x-portkey-virtual-key"] = str(virtual_key)
            if provider := opts.get("provider"):
                headers["x-portkey-provider"] = str(provider)
            if config_id := opts.get("config"):
                headers["x-portkey-config"] = str(config_id)
            if not any(k in headers for k in ("x-portkey-virtual-key", "x-portkey-provider", "x-portkey-config")):
                raise ValueError(
                    f"portkey target {target.id!r} needs one of "
                    f"``virtual_key`` / ``provider`` / ``config`` in "
                    f"provider_options — Portkey's gateway key does "
                    f"not select an upstream on its own. See "
                    f"https://portkey.ai/docs/product/ai-gateway/"
                    f"configs for the routing options."
                )

        # PR 5 — Two-key integrations (Helicone) also send an upstream
        # vendor auth header. The vendor key lives in the SAME vault
        # entry as the integration key — the bridge pre-resolved both.
        if config.vendor_auth_header:
            if vendor_credential_resolver is None:
                raise ValueError(
                    f"integration {target.integration!r} requires a "
                    f"vendor_credential_resolver but none was supplied "
                    f"to HTTPPassthroughTransport.execute — the bridge "
                    f"must pre-resolve the vendor key from the same "
                    f"vault entry as the integration key."
                )
            vendor_key = vendor_credential_resolver(target.credential_ref)
            if not vendor_key:
                raise ValueError(
                    f"vendor_credential_resolver returned empty for "
                    f"{target.credential_ref!r} on integration "
                    f"{target.integration!r} — the vault entry must hold "
                    f"the upstream vendor key alongside the integration key."
                )
            headers[config.vendor_auth_header] = (
                f"Bearer {vendor_key}" if config.vendor_bearer_prefix else vendor_key
            )

        client = await self._get_client()
        try:
            response = await client.post(
                base_url + upstream_path,
                headers=headers,
                content=json.dumps(request_body).encode("utf-8"),
            )
        except httpx.HTTPError as exc:
            log.warning(
                "gateway.v2.http_passthrough.transport_error",
                target_id=target.id,
                integration=target.integration,
                operation=operation,
                err_class=type(exc).__name__,
            )
            raise

        if response.status_code >= 400:
            log.info(
                "gateway.v2.http_passthrough.upstream_error",
                target_id=target.id,
                integration=target.integration,
                operation=operation,
                status_code=response.status_code,
            )
            response.raise_for_status()

        try:
            return response.json()
        except Exception as exc:
            log.warning(
                "gateway.v2.http_passthrough.response_parse_error",
                target_id=target.id,
                err=str(exc),
            )
            raise

    @staticmethod
    def _resolve_base_url(
        target: HTTPPassthroughTarget,
        config: IntegrationConfig,
    ) -> str:
        """Pick the base URL for this attempt.

        Integrations that don't allow overrides pin ``config.base_url``.
        ``integration='custom'`` (allows_endpoint_override=True) uses
        ``target.endpoint`` verbatim — it's the whole point of the
        custom integration.

        Warns loudly if a pinned integration carries a non-null
        ``target.endpoint``: silently ignoring it would leave the
        admin thinking they'd changed the route when the request
        actually went to the vendor-registered URL.
        """
        if config.allows_endpoint_override and target.endpoint:
            return target.endpoint.rstrip("/")
        if target.endpoint:
            log.warning(
                "gateway.v2.http_passthrough.endpoint_override_ignored",
                target_id=target.id,
                integration=target.integration,
                pinned_base_url=config.base_url,
                ignored_endpoint=target.endpoint,
                note=(
                    "target.endpoint is only honored for "
                    "integration='custom'. Remove endpoint from this "
                    "target or switch to integration='custom' if the "
                    "override was intentional."
                ),
            )
        return config.base_url


def integration_certifies_operation(
    integration: Integration, operation: Operation,
) -> bool:
    """Belt-and-braces helper for the capability catalog.

    Returns True iff this integration is registered here AND has a
    URL path for ``operation``. Publish uses this to double-check the
    capability catalog against the runtime map so the two never drift.
    """
    config = _INTEGRATION_ENDPOINTS.get(integration)
    if config is None:
        return False
    return operation in config.operation_paths


__all__ = [
    "HTTPPassthroughTransport",
    "UnsupportedPassthroughIntegration",
    "integration_certifies_operation",
]
