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
    # PR 7 — Custom is a template, not a preset. The admin supplies
    # ``target.endpoint`` (full base URL up to ``/v1``) +
    # ``target.provider_options`` to override auth header shape and
    # inject extra headers. Defaults below match OpenRouter (Bearer +
    # ``authorization``) — safe fallback for the most common shape.
    # Path suffixes stay pinned per Operation because a custom proxy
    # sitting in front of OpenAI-shape or Anthropic-shape upstreams
    # will use the same routes the vendor documents.
    "custom": IntegrationConfig(
        base_url="",  # unused; target.endpoint is required
        auth_header="authorization",
        bearer_prefix=True,
        operation_paths={
            "openai_chat_completions": "/chat/completions",
            "openai_responses":        "/responses",
            "anthropic_messages":      "/messages",
            "anthropic_count_tokens":  "/messages/count_tokens",
        },
        allows_endpoint_override=True,
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

        base_url = self._resolve_base_url(target, config)

        api_key = credential_resolver(target.credential_ref)
        if not api_key:
            raise ValueError(
                f"credential_resolver returned empty for "
                f"{target.credential_ref!r}"
            )

        request_body = dict(payload)
        request_body["model"] = target.model

        # PR 7 — custom integration lets the admin override the preset's
        # auth header shape + inject extra static headers per-target.
        # For every other integration these come from the pinned config.
        auth_header, bearer_prefix, static_extra_headers = _effective_auth(target, config)

        headers = {
            "content-type": "application/json",
            auth_header: (
                f"Bearer {api_key}" if bearer_prefix else api_key
            ),
            **static_extra_headers,
            **(client_headers or {}),
        }
        # content-type + auth stay under transport control regardless of
        # what the client sent.
        headers["content-type"] = "application/json"
        headers[auth_header] = (
            f"Bearer {api_key}" if bearer_prefix else api_key
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


def _effective_auth(
    target: HTTPPassthroughTarget,
    config: IntegrationConfig,
) -> tuple[str, bool, dict[str, str]]:
    """Resolve the auth header shape + static extras for this attempt.

    Every integration except ``custom`` uses the values pinned in
    ``IntegrationConfig``. Custom targets let the admin override them
    via ``target.provider_options``:

    - ``auth_header`` (str, default from config)
    - ``bearer_prefix`` (bool, default from config)
    - ``extra_headers`` (dict[str, str], default from config)

    Kept separate from ``execute`` so the override rules stay a small,
    testable unit — and so future integrations that need similar
    per-target flexibility can opt in without another branch inside
    the hot path.
    """
    if target.integration != "custom":
        return config.auth_header, config.bearer_prefix, dict(config.extra_headers)
    opts = getattr(target, "provider_options", None) or {}
    auth_header = str(opts.get("auth_header") or config.auth_header)
    # Explicit `False` from admin must beat the `True` default.
    if "bearer_prefix" in opts:
        bearer_prefix = bool(opts["bearer_prefix"])
    else:
        bearer_prefix = config.bearer_prefix
    raw_extras = opts.get("extra_headers") or {}
    if not isinstance(raw_extras, dict):
        raw_extras = {}
    extras = {str(k): str(v) for k, v in raw_extras.items()}
    return auth_header, bearer_prefix, extras


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
