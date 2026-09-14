"""Canonical Gateway request entry point.

The public ``/gateway/v1`` router depends on this module rather than on the
legacy ``routers.proxy`` module.  The implementation is intentionally kept
behind one function while the legacy lifecycle is extracted in follow-up
steps; this prevents new Gateway behavior from being added to the legacy
router surface.
"""
from __future__ import annotations

from typing import Any

from fastapi import BackgroundTasks, Request


async def handle_gateway_request(
    request: Request,
    background: BackgroundTasks,
    **kwargs: Any,
) -> Any:
    """Dispatch one canonical Gateway request.

    Compatibility delegation is temporary: callers only depend on this
    neutral entry point, so the underlying lifecycle can be moved without
    changing Gateway routes or the legacy API.
    """
    from app.modules.guard.routers.proxy import _proxy

    return await _proxy(request, background, **kwargs)

