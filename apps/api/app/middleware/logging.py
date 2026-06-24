import time
import uuid
import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

log = structlog.get_logger(__name__)


class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        trace_id = str(uuid.uuid4())
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(trace_id=trace_id)

        start = time.monotonic()
        response = await call_next(request)
        duration_ms = int((time.monotonic() - start) * 1000)

        # Skip health check noise. Path-only logging — never include query
        # string per issue #801 (avoids leaking legacy ?token= URLs into
        # structured logs). Render's nginx access log is outside our control;
        # the long-term mitigation is #800 (header auth) + #810 (drop URL
        # fallback when Claude.ai web supports headers).
        if request.url.path not in ("/health", "/health/sandbox"):
            log.info(
                "http.request",
                method=request.method,
                path=request.url.path,
                status=response.status_code,
                duration_ms=duration_ms,
            )

        response.headers["X-Trace-Id"] = trace_id
        return response
