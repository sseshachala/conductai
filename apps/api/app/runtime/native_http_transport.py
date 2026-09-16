"""Native HTTP transport for v2 targets that hit the vendor directly.

Proxies the client's request body to the vendor's endpoint with only
the credential swapped in — no SDK translation. Preserves the vendor's
own protocol contract end-to-end so admins get the same shape they
would from calling Anthropic / OpenAI directly.

Reused across every ``transport=native_http`` target that the coordinator
walks. Registered per-provider in ``_ENDPOINTS`` below; publish gates
against ``_NATIVE_HTTP_CERTIFIED`` in the capability catalog, so a
provider that isn't listed here can't reach a certified state.

Coordinator retries are Conduct-owned. This transport does zero retries
on its own — same contract the LiteLLM transport follows.
"""
from __future__ import annotations

import json
from typing import Any

import httpx
import structlog

from app.modules.guard.gateway_config import NativeHTTPTarget, Operation


log = structlog.get_logger(__name__)


# Vendor endpoint + auth-header shape per certified provider. Publish
# rejects a native_http target whose provider isn't a key here, matching
# the capability catalog's launch matrix.
#
# Values: (base_url, auth_header, bearer_prefix, extra_headers).
_ENDPOINTS: dict[str, tuple[str, str, bool, dict[str, str]]] = {
    "anthropic": (
        "https://api.anthropic.com",
        "x-api-key",
        False,
        {"anthropic-version": "2023-06-01"},
    ),
    "openai": (
        "https://api.openai.com",
        "authorization",
        True,
        {},
    ),
}


# Operation → upstream URL path per provider. Publish catches the
# uncertified combinations via `_NATIVE_HTTP_CERTIFIED`.
_OPERATION_PATHS: dict[tuple[str, Operation], str] = {
    ("anthropic", "anthropic_messages"):        "/v1/messages",
    ("anthropic", "anthropic_count_tokens"):    "/v1/messages/count_tokens",
    ("openai",    "openai_chat_completions"):   "/v1/chat/completions",
    ("openai",    "openai_responses"):          "/v1/responses",
}


class NativeHTTPTransport:
    """Executes a native_http target against the vendor's API.

    One instance per worker process; state per attempt lives on the
    ``execute`` call frame. Uses a lazily-initialised shared httpx
    ``AsyncClient`` with a bounded connection pool so v2 traffic
    doesn't spin up a client per request.
    """

    name = "native_http"

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
        target: NativeHTTPTarget,
        operation: Operation,
        payload: dict[str, Any],
        credential_resolver,
        stream: bool = False,
    ) -> Any:
        """Forward the payload to the vendor's endpoint and return the
        parsed JSON response.

        Streaming is intentionally refused here — the coordinator + gateway
        handler wrap streaming responses in ``StreamingResponse``, not
        ``JSONResponse``. Streaming support lands with PR 2.5.
        """
        if stream:
            # Symmetric refusal with the LiteLLM transport — coordinator
            # decides at plan build time whether streaming is possible.
            raise NotImplementedError(
                "NativeHTTPTransport streaming lands in PR 2.5 — the "
                "gateway handler currently refuses stream=true for v2."
            )

        if target.provider not in _ENDPOINTS:
            raise ValueError(
                f"native_http target {target.id!r} uses provider "
                f"{target.provider!r} which has no vendor endpoint "
                f"registered. Extend `_ENDPOINTS` and the capability "
                f"catalog together."
            )
        endpoint_key = (target.provider, operation)
        if endpoint_key not in _OPERATION_PATHS:
            raise ValueError(
                f"native_http target {target.id!r} advertises operation "
                f"{operation!r} which has no upstream URL path for "
                f"provider {target.provider!r}."
            )

        base_url, auth_header, bearer_prefix, extra_headers = _ENDPOINTS[target.provider]
        upstream_path = _OPERATION_PATHS[endpoint_key]

        api_key = credential_resolver(target.credential_ref)
        if not api_key:
            raise ValueError(
                f"credential_resolver returned empty for "
                f"{target.credential_ref!r}"
            )

        # Client's body is forwarded verbatim except the ``model`` field
        # is replaced with the target's own model id (the client's model
        # was the cond-... identifier or an alias, not the upstream id).
        request_body = dict(payload)
        request_body["model"] = target.model

        headers = {
            "content-type": "application/json",
            auth_header: f"Bearer {api_key}" if bearer_prefix else api_key,
            **extra_headers,
        }

        client = await self._get_client()
        try:
            response = await client.post(
                base_url + upstream_path,
                headers=headers,
                content=json.dumps(request_body).encode("utf-8"),
            )
        except httpx.HTTPError as exc:
            # Let the coordinator's retry classifier decide via the
            # exception class name (matches LiteLLM transient set).
            log.warning(
                "gateway.v2.native_http.transport_error",
                target_id=target.id,
                provider=target.provider,
                operation=operation,
                err_class=type(exc).__name__,
            )
            raise

        if response.status_code >= 400:
            # 4xx from the vendor is a permanent failure for this
            # attempt; 5xx is transient. Both routes come back through
            # response.raise_for_status() so the coordinator sees an
            # httpx.HTTPStatusError with a status_code attribute — its
            # `_is_retryable` walks that.
            log.info(
                "gateway.v2.native_http.upstream_error",
                target_id=target.id,
                provider=target.provider,
                operation=operation,
                status_code=response.status_code,
            )
            response.raise_for_status()

        try:
            return response.json()
        except Exception as exc:
            log.warning(
                "gateway.v2.native_http.response_parse_error",
                target_id=target.id,
                err=str(exc),
            )
            raise


__all__ = ["NativeHTTPTransport"]
