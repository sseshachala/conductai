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
    """
    base_url: str
    auth_header: str
    bearer_prefix: bool
    operation_paths: dict[Operation, str]
    extra_headers: dict[str, str] = field(default_factory=dict)
    allows_endpoint_override: bool = False
    # PR 6 — per-tenant integrations (Azure OpenAI). A path containing
    # ``{model}`` gets substituted with ``target.model`` at request
    # time so the URL carries the deployment name inline. Names listed
    # in ``query_params_from_options`` are pulled from
    # ``target.provider_options`` and added as URL query parameters
    # (underscore → dash conversion: ``api_version`` → ``api-version``).
    query_params_from_options: tuple[str, ...] = field(default_factory=tuple)


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
    # PR 6 — Azure OpenAI. Per-tenant URL, so
    # ``allows_endpoint_override=True`` and the admin supplies the
    # Azure Resource endpoint (e.g. ``https://acme.openai.azure.com``)
    # on the target. Deployment name is stored in ``target.model``
    # and substituted into ``/openai/deployments/{model}/...`` at
    # request time. ``api-version`` is Azure-specific and lives in
    # ``target.provider_options.api_version`` — added as a URL query
    # parameter. Auth uses raw ``api-key`` header (no Bearer prefix).
    "azure_openai": IntegrationConfig(
        base_url="",  # unused when allows_endpoint_override=True
        auth_header="api-key",
        bearer_prefix=False,
        operation_paths={
            "openai_chat_completions": "/openai/deployments/{model}/chat/completions",
        },
        allows_endpoint_override=True,
        query_params_from_options=("api_version",),
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

        # PR 6 — path templating for per-tenant integrations (Azure).
        # Only ``{model}`` substitution is supported; anything else is
        # a config bug and left in the URL to surface a clear 404.
        # Review fix — quote the model so slashes / spaces / control
        # characters in a deployment name can't smuggle path segments
        # (a name like ``prod/../secret`` shouldn't be able to redirect
        # the request).
        if "{model}" in upstream_path:
            from urllib.parse import quote
            upstream_path = upstream_path.replace("{model}", quote(target.model, safe=""))

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

        # PR 6 — query params from provider_options (Azure api-version).
        # Underscore→dash on the wire so the vendor sees the header/
        # param name in the shape they document (``api-version``).
        url = base_url + upstream_path
        if config.query_params_from_options:
            from urllib.parse import urlencode
            opts = getattr(target, "provider_options", None) or {}
            params: dict[str, str] = {}
            for opt_name in config.query_params_from_options:
                val = opts.get(opt_name)
                if val:
                    params[opt_name.replace("_", "-")] = str(val)
            if params:
                url = url + ("&" if "?" in url else "?") + urlencode(params)

        client = await self._get_client()
        try:
            response = await client.post(
                url,
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
        Per-tenant integrations (``custom``, ``azure_openai``) set
        ``allows_endpoint_override=True`` and use ``target.endpoint``
        verbatim — that's the whole point.

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
                    "target.endpoint is only honored for per-tenant "
                    "integrations (custom, azure_openai). Remove "
                    "endpoint from this target or switch integration if "
                    "the override was intentional."
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
