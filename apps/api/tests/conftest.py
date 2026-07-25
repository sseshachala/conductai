"""
Shared test fixtures + safety nets.

Tests should run without a real Postgres or Redis — these set env vars early
so the settings module picks up dev-safe defaults even if the developer hasn't
sourced an .env file.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Make `import app.*` resolve from the apps/api root so tests don't depend on
# the cwd they're invoked from.
HERE = Path(__file__).resolve()
APPS_API = HERE.parent.parent
if str(APPS_API) not in sys.path:
    sys.path.insert(0, str(APPS_API))

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test_marshal")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
os.environ.setdefault("ANTHROPIC_API_KEY", "")
os.environ.setdefault("ENCRYPTION_KEY", "test-key-32-bytes-long-xxxxxxxx!")

# ── Patch require_permission to a permissive noop BEFORE app.main is imported.
# `require_permission("perm.name")` is a FACTORY called at route-definition time;
# FastAPI stores the returned _check closure in Depends(). Overriding the factory
# via app.dependency_overrides[require_permission] doesn't work — the override
# never fires because FastAPI looks up the closure, not the factory.
# Patching the factory HERE (before routers register) makes all routes use the
# permissive check. Tests that need to exercise real permission enforcement should
# use the `real_require_permission` fixture below to restore the original.
import app.core.auth as _auth_mod  # noqa: E402

_ORIG_REQUIRE_PERMISSION = _auth_mod.require_permission


def _permissive_permission(permission: str):
    async def _check() -> str:
        return "admin"
    return _check


_auth_mod.require_permission = _permissive_permission


import pytest  # noqa: E402


@pytest.fixture
def real_require_permission():
    """Opt-in: restore the real require_permission for a test that actually
    needs to exercise RBAC enforcement. Reverts on teardown."""
    _auth_mod.require_permission = _ORIG_REQUIRE_PERMISSION
    yield
    _auth_mod.require_permission = _permissive_permission

