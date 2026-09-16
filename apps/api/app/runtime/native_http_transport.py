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

Streaming (PR 2.5): when ``stream=True`` the transport returns a
``StreamingUpstream`` — a small wrapper holding the live httpx.Response
so ``_execute_v2`` can construct a ``StreamingResponse`` around
``aiter_bytes()``. Upstream 4xx/5xx surfaced from streaming attempts are
raised as ``httpx.HTTPStatusError`` (with ``.response.status_code`` set)
so the coordinator's retry classifier walks them the same way it walks
non-streaming errors. Once we've returned a ``StreamingUpstream``, the
coordinator commits — no retry after headers.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
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


@dataclass
class StreamingUpstream:
    """A live streaming response from the vendor.

    Coordinator commits the moment this is returned — no retry after
    headers. Caller (``_execute_v2``) must consume ``response.aiter_bytes()``
    and call ``response.aclose()`` when done. The stream generator built
    downstream owns both.
    """
    status_code: int
    headers: dict[str, str]
    response: httpx.Response
    provider: str


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
        """Forward the payload to the vendor's endpoint.

        Non-streaming: returns the parsed JSON body (dict).
        Streaming: returns a ``StreamingUpstream`` holding the live
        ``httpx.Response`` so ``_execute_v2`` can wrap ``aiter_bytes()``
        in a ``StreamingResponse``. The caller owns ``response.aclose()``.
        """
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
        if stream:
            # Belt-and-braces: the client set ``stream: true`` in the
            # body already, but forwarding the payload verbatim means we
            # only trust that flag as far as ``payload`` did.
            request_body["stream"] = True

        headers = {
            "content-type": "application/json",
            auth_header: f"Bearer {api_key}" if bearer_prefix else api_key,
            **extra_headers,
        }

        client = await self._get_client()
        content_bytes = json.dumps(request_body).encode("utf-8")

        if stream:
            return await self._execute_stream(
                client=client,
                target=target,
                operation=operation,
                url=base_url + upstream_path,
                headers=headers,
                content=content_bytes,
            )

        try:
            response = await client.post(
                base_url + upstream_path,
                headers=headers,
                content=content_bytes,
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

    async def _execute_stream(
        self,
        *,
        client: httpx.AsyncClient,
        target: NativeHTTPTarget,
        operation: Operation,
        url: str,
        headers: dict[str, str],
        content: bytes,
    ) -> StreamingUpstream:
        """Send a streaming request and return the live response object.

        Peeks headers before returning. Any 4xx/5xx here is raised as
        ``httpx.HTTPStatusError`` (with status_code populated) so the
        coordinator's ``_is_retryable`` walks it — same semantics as
        non-streaming. If headers are ok, we return the still-open
        response; the caller becomes responsible for ``aclose()``.
        """
        request = client.build_request(
            "POST", url, headers=headers, content=content,
        )
        try:
            response = await client.send(request, stream=True)
        except httpx.HTTPError as exc:
            log.warning(
                "gateway.v2.native_http.stream_transport_error",
                target_id=target.id,
                provider=target.provider,
                operation=operation,
                err_class=type(exc).__name__,
            )
            raise

        if response.status_code >= 400:
            # Read the error body then close, so nothing leaks and the
            # coordinator sees a clean HTTPStatusError with status_code.
            try:
                await response.aread()
            finally:
                await response.aclose()
            log.info(
                "gateway.v2.native_http.stream_upstream_error",
                target_id=target.id,
                provider=target.provider,
                operation=operation,
                status_code=response.status_code,
            )
            raise httpx.HTTPStatusError(
                f"upstream returned {response.status_code}",
                request=request,
                response=response,
            )

        return StreamingUpstream(
            status_code=response.status_code,
            headers=dict(response.headers),
            response=response,
            provider=target.provider,
        )


__all__ = ["NativeHTTPTransport", "StreamingUpstream"]
