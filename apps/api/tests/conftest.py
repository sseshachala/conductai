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
# CI passes ANTHROPIC_API_KEY as an empty string when the GH secret isn't set,
# so setdefault() is a no-op — force a non-empty dummy so the LLM client's
# missing-key check doesn't short-circuit patched tests.
if not os.environ.get("ANTHROPIC_API_KEY"):
    os.environ["ANTHROPIC_API_KEY"] = "sk-ant-test-dummy-key"
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
    # Tag so test_endpoint_matrix can find each route's declared permission at
    # runtime by walking route.dependant.dependencies.
    _check.__conduct_permission__ = permission  # type: ignore[attr-defined]
    return _check


_auth_mod.require_permission = _permissive_permission


import pytest  # noqa: E402


@pytest.fixture
def real_require_permission():
    """Opt-in: restore the real require_permission for a test that actually
    needs to exercise RBAC enforcement.

    Routers have already baked in the permissive closure at collection time
    (see docstring at top of file). Restoring the factory alone doesn't help
    existing routes — we walk app.router.routes and swap each dep.call
    tagged with __conduct_permission__ back to the real check closure.

    Reverts on teardown so subsequent tests keep the permissive default.
    """
    from app.main import app as _app

    _auth_mod.require_permission = _ORIG_REQUIRE_PERMISSION

    _swapped = []

    def _walk(dependant):
        for dep in dependant.dependencies:
            perm = getattr(dep.call, "__conduct_permission__", None)
            if perm:
                _swapped.append((dep, dep.call))
                dep.call = _ORIG_REQUIRE_PERMISSION(perm)
            _walk(dep)

    for route in _app.router.routes:
        d = getattr(route, "dependant", None)
        if d is not None:
            _walk(d)

    yield

    for dep, original in _swapped:
        dep.call = original
    _auth_mod.require_permission = _permissive_permission

