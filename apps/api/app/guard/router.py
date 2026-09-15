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

from app.guard.audit import finalize as _finalize_audit, record as _record_audit
from app.modules.guard.circuit_breaker import get_breaker as _get_breaker

log = structlog.get_logger(__name__)

# Post-P1 v3 review Finding 1: asyncio.shield() does NOT guarantee the
# inner task completes before the outer await returns. We keep a strong
# reference to every in-flight finalize task so the loop can't GC it,
# and we observe the result via done_callback so ops sees the tail.
# The set is per-worker; on graceful shutdown the worker awaits its
# own event loop tasks. Hard-kill loss is caught by Phase 4's reconciler.
import asyncio as _asyncio_module_scope
_PENDING_FINALIZES: set = set()

def _register_finalize_task(task, *, label: str) -> None:
    _PENDING_FINALIZES.add(task)
    def _observe(t):
        _PENDING_FINALIZES.discard(t)
        if t.cancelled():
            log.warning("guard.finalize.cancelled", label=label)
            return
        exc = t.exception()
        if exc is not None:
            log.error("guard.finalize.failed", label=label, err=str(exc))
    task.add_done_callback(_observe)


def _schedule_audit(
    background: BackgroundTasks,
    audit_args: tuple,
    *,
    response_bytes: bytes | None,
    upstream: str | None,
    execution_status: str = "success",
    result_summary: str | None = None,
) -> None:
    # Phase 2 of #1959 — index 18 = durable row id from a prior
    # insert_accepted(). When set, dispatch to finalize() which
    # updates the row from 'accepted' -> 'finalized' rather than
    # writing a new one. audit_args[16]/[17] (agent identity, route)
    # already landed on the accepted row so we don't re-thread them.
    _durable_row_id = audit_args[18] if len(audit_args) > 18 else None
    if _durable_row_id:
        background.add_task(
            _finalize_audit,
            _durable_row_id,
            audit_args[0],           # workspace_id
            decision=audit_args[5],
            provider=audit_args[3],
            model=audit_args[4],
            body=audit_args[8],
            response_bytes=response_bytes,
            duration_ms=int((time.monotonic() - audit_args[7]) * 1000),
            rule_id=audit_args[6],
            routing_meta=audit_args[15] if len(audit_args) > 15 else None,
            execution_status=execution_status,
            result_summary=result_summary,
            clerk_user_id=audit_args[1],
            ai_tool=audit_args[2],
            user_email=audit_args[10] if len(audit_args) > 10 else None,
        )
        return

    background.add_task(
        _record_audit, *audit_args[:6], audit_args[6],
        int((time.monotonic() - audit_args[7]) * 1000),
        body=audit_args[8], response_bytes=response_bytes, upstream=upstream,
        prompt_summary=audit_args[9] if len(audit_args) > 9 else "",
        user_email=audit_args[10] if len(audit_args) > 10 else None,
        conductai_run_id=audit_args[11] if len(audit_args) > 11 else None,
        conductai_workflow=audit_args[12] if len(audit_args) > 12 else None,
        conductai_workflow_id=audit_args[13] if len(audit_args) > 13 else None,
        hook_session_id=audit_args[14] if len(audit_args) > 14 else None,
        routing_meta=audit_args[15] if len(audit_args) > 15 else None,
        # Phase 0 of #1959 — index 16 (Gateway/proxy path only). Older callers
        # that still build a 16-tuple pass None here, matching pre-Phase 0
        # behavior; the writer already tolerates None.
        agent_identity_id=audit_args[16] if len(audit_args) > 16 else None,
        # Follow-up to #1971 — index 17 = FastAPI request path.
        route=audit_args[17] if len(audit_args) > 17 else None,
        execution_status=execution_status,
        result_summary=result_summary,
    )


# ─── Public helpers ───────────────────────────────────────────────────────────

def fail_closed(
    status: int,
    message: str,
    *,
    extra: dict | None = None,
) -> JSONResponse:
    """Security tool failing open is worse than no tool. Surface clear errors.

    `extra` merges into `error.metadata` so blocks can carry structured
    fields (receipt_id, receipt_url) without breaking the canonical shape.
    """
    err: dict = {"type": "conduct_guard_proxy", "message": message}
    if extra:
        err["metadata"] = extra
    return JSONResponse(status_code=status, content={"error": err})


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
    """Pass-through every chunk. Ownership contract for durable rows
    (post-P1 review v2):

    - CancelledError is NEVER treated as success. When cancellation
      reaches this coroutine, execution_status becomes 'interrupted'.
    - Cleanup uses contextlib.suppress so an aclose() failure cannot
      block the finalize. Cleanup failures are logged but never
      swallow the true outcome.
    - Finalize runs under asyncio.shield + asyncio.to_thread so
      cancellation propagates to the caller while the DB write
      completes atomically off the event loop.
    - Lease renewal runs on a heartbeat cadence throughout the stream
      (actor-heartbeat pattern) so a legitimate long stream is never
      orphaned mid-flight.
    """
    import asyncio as _asyncio
    import contextlib as _contextlib
    from app.core.config import settings
    from app.guard.audit import finalize as _finalize_inline
    from app.guard.audit import renew_lease as _renew_lease

    collected = bytearray()
    execution_status = "success"
    result_summary: str | None = None
    _durable_row_id = audit_args[18] if len(audit_args) > 18 else None
    _workspace_id = audit_args[0] if audit_args else None
    _renew_interval = settings.guard_durable_audit_stream_renew_seconds
    _renew_task: _asyncio.Task | None = None

    async def _renewal_loop() -> None:
        while True:
            try:
                await _asyncio.sleep(_renew_interval)
            except _asyncio.CancelledError:
                # Renewal is a heartbeat: cancellation of the outer
                # request is normal; exit cleanly so the finally can
                # finalize the row.
                return
            if _durable_row_id and _workspace_id:
                try:
                    await _asyncio.to_thread(
                        _renew_lease,
                        _durable_row_id,
                        _workspace_id,
                        additional_seconds=settings.guard_durable_audit_lease_seconds,
                    )
                except Exception:
                    log.warning("guard.stream.lease_renew_swallowed")

    try:
        if _durable_row_id and _renew_interval > 0:
            _renew_task = _asyncio.create_task(_renewal_loop())
        async for chunk in resp.aiter_bytes():
            collected.extend(chunk)
            yield chunk
    except _asyncio.CancelledError:
        execution_status = "interrupted"
        result_summary = "Stream interrupted by cancellation (client disconnect or task cancel)"
        raise
    except Exception as exc:
        execution_status = "error"
        result_summary = f"Upstream stream failed: {type(exc).__name__}"
        raise
    finally:
        if _renew_task is not None and not _renew_task.done():
            _renew_task.cancel()
            with _contextlib.suppress(Exception, _asyncio.CancelledError):
                await _renew_task
        # Cleanup is best-effort. A cleanup failure MUST NOT prevent
        # the durable finalize below.
        with _contextlib.suppress(Exception, _asyncio.CancelledError):
            await resp.aclose()
        with _contextlib.suppress(Exception, _asyncio.CancelledError):
            await client.aclose()

        if _durable_row_id:
            # Post-P1 v3 review Finding 1: shield() alone does not
            # guarantee completion. Create a real task, keep a strong
            # ref so the loop can't GC it, observe the result via
            # done_callback. Bounded wait via wait_for + shield so
            # cancellation propagates while the task keeps running
            # under supervision.
            _finalize_task = _asyncio.create_task(
                _asyncio.to_thread(
                    _finalize_inline,
                    _durable_row_id,
                    _workspace_id,
                    decision=audit_args[5],
                    provider=audit_args[3],
                    model=audit_args[4],
                    body=audit_args[8],
                    response_bytes=bytes(collected),
                    duration_ms=int((time.monotonic() - audit_args[7]) * 1000),
                    rule_id=audit_args[6],
                    routing_meta=audit_args[15] if len(audit_args) > 15 else None,
                    execution_status=execution_status,
                    result_summary=result_summary,
                    clerk_user_id=audit_args[1],
                    ai_tool=audit_args[2],
                    user_email=audit_args[10] if len(audit_args) > 10 else None,
                )
            )
            _register_finalize_task(
                _finalize_task,
                label=f"stream:{_durable_row_id}",
            )
            try:
                # Bounded shield: wait up to 5s for the finalize task
                # to complete synchronously. If cancellation reaches us
                # we still propagate but the task keeps running under
                # supervision; Phase 4's reconciler catches the tail on
                # a hard-kill.
                await _asyncio.wait_for(_asyncio.shield(_finalize_task), timeout=5.0)
            except _asyncio.TimeoutError:
                log.info(
                    "guard.stream.finalize_bounded_wait_timeout",
                    row_id=_durable_row_id,
                )
            except _asyncio.CancelledError:
                log.info(
                    "guard.stream.finalize_bounded_wait_cancelled",
                    row_id=_durable_row_id,
                )
                raise
            except Exception:
                log.exception("guard.stream.inline_finalize_failed")
                with _contextlib.suppress(Exception):
                    _schedule_audit(
                        background, audit_args, response_bytes=bytes(collected),
                        upstream=upstream_url, execution_status=execution_status,
                        result_summary=result_summary,
                    )
        else:
            _schedule_audit(
                background, audit_args, response_bytes=bytes(collected),
                upstream=upstream_url, execution_status=execution_status,
                result_summary=result_summary,
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
        message = (
            f"Guard circuit breaker OPEN for provider={_breaker_key} — "
            f"upstream failing repeatedly; retry after ~{int(_breaker.recovery_timeout)}s"
        )
        _schedule_audit(
            background, audit_args, response_bytes=None, upstream=upstream,
            execution_status="error", result_summary=message,
        )
        return fail_closed(
            503,
            message,
        )

    client = httpx.AsyncClient(timeout=httpx.Timeout(600.0))

    try:
        req = client.build_request("POST", _full_url, json=body, headers=headers)
        parsed_upstream = _urlparse(_full_url)
        log.info("guard.proxy.forward",
                 upstream_host=parsed_upstream.hostname,
                 upstream_path=parsed_upstream.path,
                 header_names=sorted(headers))
        resp = await client.send(req, stream=True)
    except Exception as e:
        _breaker.record_failure(_breaker_key)
        await client.aclose()
        log.warning("guard.proxy.upstream_unreachable",
                    upstream_host=parsed_upstream.hostname,
                    upstream_path=parsed_upstream.path,
                    exc_type=type(e).__name__)
        message = f"Upstream provider unreachable: {type(e).__name__}"
        _schedule_audit(
            background, audit_args, response_bytes=None, upstream=upstream,
            execution_status="error", result_summary=message[:500],
        )
        return fail_closed(502, message)

    if resp.status_code >= 500:
        _breaker.record_failure(_breaker_key)
    elif resp.status_code < 400:
        _breaker.record_success(_breaker_key)

    if resp.status_code >= 400:
        err_body = await resp.aread()
        await resp.aclose()
        await client.aclose()
        _schedule_audit(
            background, audit_args, response_bytes=err_body, upstream=upstream,
            execution_status="error", result_summary=f"Upstream HTTP {resp.status_code}",
        )
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
    _schedule_audit(background, audit_args, response_bytes=full, upstream=upstream)
    _resp_headers = {
        k: v for k, v in resp.headers.items()
        if k.lower() != "content-encoding" and k.lower() != "content-length"
    }
    return JSONResponse(
        status_code=resp.status_code,
        content=_safe_json(full, fallback={}),
        headers=_resp_headers,
    )
