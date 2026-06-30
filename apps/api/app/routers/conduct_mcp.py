"""
conduct/mcp — DEPRECATED. Unified MCP is at /guard/mcp.

All tools (guard + conduct platform) are served from /guard/mcp.
This router redirects for backwards compatibility.
"""
from fastapi import APIRouter, Query, Request
from fastapi.responses import RedirectResponse

router = APIRouter(prefix="/conduct/mcp", tags=["conduct-mcp"])

# Keep a dummy export so main.py import doesn't break
conduct_well_known_router = APIRouter(tags=["conduct-mcp"])


def _redirect(workspace_id: str, token: str | None) -> str:
    url = f"/guard/mcp?workspace_id={workspace_id}"
    if token:
        url += f"&token={token}"
    return url


@router.get("")
async def conduct_mcp_sse_redirect(workspace_id: str = Query(...), token: str | None = Query(None)):
    return RedirectResponse(_redirect(workspace_id, token), status_code=301)


@router.post("")
async def conduct_mcp_post_redirect(workspace_id: str = Query(...), token: str | None = Query(None)):
    return RedirectResponse(_redirect(workspace_id, token), status_code=308)
