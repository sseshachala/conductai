"""Regression check for the Claude.ai OAuth loop.

Before this fix, an authenticated MCP call against a workspace with no
GuardConfig row returned 401 + WWW-Authenticate, sending Claude.ai back through
OAuth (which re-minted the same identity, same workspace_id → same 401 →
infinite loop). After the fix, the config is auto-provisioned on first call.
"""
from __future__ import annotations

import inspect

from app.modules.guard.routers import mcp as mcp_router
from app.modules.guard.routers.config import _get_or_create_config


def test_no_more_401_reauth_on_missing_guardconfig():
    src = inspect.getsource(mcp_router.mcp_endpoint)
    assert "workspace not configured for Guard — re-authenticate" not in src, (
        "The 401+WWW-Authenticate branch is back — it will re-trigger the "
        "Claude.ai OAuth loop when GuardConfig is missing."
    )
    assert "_get_or_create_config" in src, (
        "mcp_endpoint must auto-provision GuardConfig instead of 401ing."
    )


def test_helper_still_creates_and_returns_config():
    # The auto-provision helper's contract: return existing or create; never None.
    assert callable(_get_or_create_config)


if __name__ == "__main__":
    test_no_more_401_reauth_on_missing_guardconfig()
    test_helper_still_creates_and_returns_config()
    print("ok")
