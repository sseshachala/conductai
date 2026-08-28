"""Guard router — upstream provider fanout for proxied LLM calls.

Single source of truth for \"send this call to the right provider and handle
streaming / non-streaming / error responses.\"

Public API:
- upstream(...)            — send a request to the upstream provider, return Response
- fail_closed(status, msg) — build a canonical Conduct error JSONResponse

Callers:
- HTTP proxy handler (app/modules/guard/routers/proxy.py) — external agents
- Lens LLM client (planned, #1218 Step 3) — in-process, dogfood

Extracted from proxy.py in #1218 Step 1c. Behavior byte-identical to the
pre-refactor implementation; regression harness (tests/regression/) locks
that in.
"""
from __future__ import annotations

import json
import time
from typing import AsyncIterator
from urllib.parse import urlparse as _urlparse

import httpx
import structlog
from fastapi import BackgroundTasks
from fastapi.responses import JSONResponse, StreamingResponse

from app.guard.audit import record as _record_audit
from app.modules.guard.circuit_breaker import get_breaker as _get_breaker

log = structlog.get_logger(__name__)


# ─── Public helpers ───────────────────────────────────────────────────────────

def fail_closed(status: int, message: str) -> JSONResponse:
    """Security tool failing open is worse than no tool. Surface clear errors."""
    return JSONResponse(
        status_code=status,
        content={"error": {"type": "conduct_guard_proxy", "message": message}},
    )


# ─── Private helpers ──────────────────────────────────────────────────────────

def _safe_json(b: bytes, *, fallback: dict) -> dict:
    try:
        return json.loads(b)
    except Exception:
        try:
            snippet = (b[:400] or b"").decode("utf-8", errors="replace")
        except Exception:
            snippet = repr(b[:400])
        log.warning("guard.proxy.upstream_unparseable_body",
                    snippet=snippet, byte_length=len(b or b""))
        return fallback


async def _stream_chunks(
    client: httpx.AsyncClient, resp: httpx.Response,
    background: BackgroundTasks, audit_args: tuple,
    upstream_url: str | None = None,
) -> AsyncIterator[bytes]:
    """Pass-through every chunk. Schedule the audit event after the stream
    closes — we don't parse mid-stream in V1."""
    collected = bytearray()
    try:
        async for chunk in resp.aiter_bytes():
            collected.extend(chunk)
            yield chunk
    finally:
        await resp.aclose()
        await client.aclose()
        background.add_task(
            _record_audit, *audit_args[:6], audit_args[6],
            int((time.monotonic() - audit_args[7]) * 1000),
            body=audit_args[8], response_bytes=bytes(collected), upstream=upstream_url,
            prompt_summary=audit_args[9] if len(audit_args) > 9 else "",
            user_email=audit_args[10] if len(audit_args) > 10 else None,
            conductai_run_id=audit_args[11] if len(audit_args) > 11 else None,
            conductai_workflow=audit_args[12] if len(audit_args) > 12 else None,
            conductai_workflow_id=audit_args[13] if len(audit_args) > 13 else None,
            hook_session_id=audit_args[14] if len(audit_args) > 14 else None,
            routing_meta=audit_args[15] if len(audit_args) > 15 else None,
        )


# ─── Public API — upstream fanout ─────────────────────────────────────────────

async def upstream(
    *, upstream: str, path: str, body: dict, real_key: str,
    auth_header_out: str, bearer: bool, is_stream: bool,
    background: BackgroundTasks, audit_args: tuple,
    extra_headers: dict | None = None,
    upstream_api_key: str | None = None,
    vendor_key: str | None = None,
    provider: str = "",
) -> StreamingResponse | JSONResponse:
    """Forward a policy-approved request to the upstream provider.

    Handles: BYO gateway adapters (Portkey/Helicone/Azure/OpenRouter),
    circuit breaker, streaming + non-streaming responses, upstream 5xx tracking,
    content-encoding decompression (gzip/br/deflate), and audit scheduling."""
    headers = {
        "content-type": "application/json",
        "accept": "text/event-stream" if is_stream else "application/json",
        # httpx auto-negotiates br/gzip/deflate but with stream=True the
        # response body arrives already-decoded while `content-encoding: br`
        # remains on the headers. Our manual `brotli.decompress(full)` then
        # explodes on plaintext. Force uncompressed responses — Guard's
        # proxy is CPU-bound already, wire-bytes savings are marginal.
        "accept-encoding": "identity",
    }

    _requested_model = body.get("model") or ""
    if upstream_api_key:
        from app.runtime.adapters.gateway import gateway_adapt as _gw_adapt
        _gw = _gw_adapt(upstream, upstream_api_key, provider, _requested_model)
        if _gw.headers:
            headers.update(_gw.headers)
            if vendor_key:
                headers[auth_header_out] = f"Bearer {vendor_key}" if bearer else vendor_key
        else:
            headers[auth_header_out] = f"Bearer {real_key}" if bearer else real_key
        if _gw.model and _requested_model and _gw.model != _requested_model:
            body["model"] = _gw.model
    else:
        headers[auth_header_out] = f"Bearer {real_key}" if bearer else real_key

    if provider == "anthropic":
        headers.setdefault("anthropic-version", "2023-06-01")
    if extra_headers:
        headers.update(extra_headers)

    headers = {k: str(v).strip() for k, v in headers.items()}

    _up_path = _urlparse(upstream).path.rstrip("/")
    _req_path = path[len(_up_path):] if _up_path and path.startswith(_up_path) else path
    _full_url = upstream.rstrip("/") + _req_path

    _breaker = _get_breaker()
    _breaker_key = provider or "default"
    if not _breaker.allow(_breaker_key):
        log.warning("guard.proxy.breaker_open", provider=_breaker_key,
                    snapshot=_breaker.snapshot(_breaker_key))
        return fail_closed(
            503,
            f"Guard circuit breaker OPEN for provider={_breaker_key} — "
            f"upstream failing repeatedly; retry after ~{int(_breaker.recovery_timeout)}s",
        )

    client = httpx.AsyncClient(timeout=httpx.Timeout(600.0))

    try:
        req = client.build_request("POST", _full_url, json=body, headers=headers)
        log.info("guard.proxy.forward", url=_full_url,
                 headers={k: v for k, v in headers.items() if "key" not in k.lower() and "auth" not in k.lower()})
        resp = await client.send(req, stream=True)
    except Exception as e:
        _breaker.record_failure(_breaker_key)
        await client.aclose()
        import traceback as _tb
        log.warning("guard.proxy.upstream_unreachable", url=_full_url,
                    exc_type=type(e).__name__, err=str(e),
                    traceback=_tb.format_exc())
        return fail_closed(502, f"Upstream {_full_url} unreachable: {type(e).__name__}: {e}")

    if resp.status_code >= 500:
        _breaker.record_failure(_breaker_key)
    elif resp.status_code < 400:
        _breaker.record_success(_breaker_key)

    if resp.status_code >= 400:
        err_body = await resp.aread()
        await resp.aclose()
        await client.aclose()
        return JSONResponse(
            status_code=resp.status_code,
            content=_safe_json(err_body, fallback={"error": "upstream error"}),
        )

    if is_stream:
        return StreamingResponse(
            _stream_chunks(client, resp, background, audit_args, upstream_url=upstream),
            media_type=resp.headers.get("content-type", "text/event-stream"),
        )

    full = await resp.aread()
    _enc = (resp.headers.get("content-encoding") or "").lower().strip()
    if _enc == "gzip":
        try:
            import gzip as _gzip
            full = _gzip.decompress(full)
        except Exception as e:
            log.warning("guard.proxy.gzip_decompress_failed", err=str(e))
    elif _enc in ("br", "brotli"):
        try:
            import brotli as _brotli
            full = _brotli.decompress(full)
        except ImportError:
            log.warning("guard.proxy.brotli_missing", note="pip install brotli")
        except Exception as e:
            log.warning("guard.proxy.brotli_decompress_failed", err=str(e))
    elif _enc == "deflate":
        try:
            import zlib as _zlib
            full = _zlib.decompress(full)
        except Exception as e:
            log.warning("guard.proxy.deflate_decompress_failed", err=str(e))
    await resp.aclose()
    await client.aclose()
    background.add_task(
        _record_audit, *audit_args[:6], audit_args[6],
        int((time.monotonic() - audit_args[7]) * 1000),
        body=audit_args[8], response_bytes=full, upstream=upstream,
        prompt_summary=audit_args[9] if len(audit_args) > 9 else "",
        user_email=audit_args[10] if len(audit_args) > 10 else None,
        conductai_run_id=audit_args[11] if len(audit_args) > 11 else None,
        conductai_workflow=audit_args[12] if len(audit_args) > 12 else None,
        conductai_workflow_id=audit_args[13] if len(audit_args) > 13 else None,
        hook_session_id=audit_args[14] if len(audit_args) > 14 else None,
        routing_meta=audit_args[15] if len(audit_args) > 15 else None,
    )
    _resp_headers = {
        k: v for k, v in resp.headers.items()
        if k.lower() != "content-encoding" and k.lower() != "content-length"
    }
    return JSONResponse(
        status_code=resp.status_code,
        content=_safe_json(full, fallback={}),
        headers=_resp_headers,
    )
