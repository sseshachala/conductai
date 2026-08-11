"""Endpoint × Role RBAC matrix — Phase 1 of the test-harness plan.

Generates tests from three sources of truth:
  1. FastAPI's live route table (`app.routes`) — every endpoint currently mounted.
  2. `permissions` + `role_permissions` seeded by alembic migration 0001.
  3. The `require_permission("...")` closure tagged in conftest.

Layers
------
A. Static consistency (no HTTP, DB read-only):
     - every code-declared permission exists in the `permissions` table
     - every seeded permission is used by at least one endpoint (or allowlisted)

B. Runtime probing (real TestClient, real DB, real require_permission):
     - for each (route, role): unauthorised roles get 403,
       authorised roles get anything-but-403.

The runtime layer boots a TestClient with:
  * `_clerk_enabled` monkeypatched to True (else require_permission short-circuits)
  * `get_user_id` / `get_workspace_id` overridden to point at seeded rows
  * every `require_permission` closure swapped from the conftest noop back to
    the original factory
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

import app.core.auth as _auth_mod
from app.core.auth import _bearer, get_user_id, get_workspace_id  # noqa: F401 (fixture lookup)
from app.core.database import SessionLocal
from app.main import app

# ── Constants ────────────────────────────────────────────────────────────────
ROLES = ("admin", "security", "developer", "viewer")
TEST_WS_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
USER_IDS = {role: f"user_matrix_{role}" for role in ROLES}

# Path params get a syntactically valid UUID (routes typed as UUID reject
# anything else with 422 before Depends runs).
UUID_ZERO = "00000000-0000-0000-0000-000000000000"

# Seeded permissions that intentionally aren't reachable from any route yet
# (kept for future use / policy grammar).  Add sparingly.
UNUSED_PERMISSION_ALLOWLIST: set[str] = set()


# ── Route discovery ──────────────────────────────────────────────────────────
def _walk_dependants(dep):
    """Yield every Dependant reachable from `dep` (root included)."""
    yield dep
    for child in dep.dependencies:
        yield from _walk_dependants(child)


def _permission_for_route(route) -> str | None:
    """Return the `require_permission('...')` string declared on this route,
    by finding the tagged closure conftest planted."""
    dependant = getattr(route, "dependant", None)
    if dependant is None:
        return None
    for dep in _walk_dependants(dependant):
        call = getattr(dep, "call", None)
        perm = getattr(call, "__conduct_permission__", None)
        if perm:
            return perm
    return None


def _substitute_path_params(path: str) -> str:
    # /workflows/{workflow_id}/runs → /workflows/00000000-.../runs
    return re.sub(r"\{[^}]+\}", UUID_ZERO, path)


def _discover_routes() -> list[dict]:
    out: list[dict] = []
    for r in app.routes:
        methods = getattr(r, "methods", None) or set()
        methods = {m for m in methods if m != "HEAD"}
        if not methods:
            continue
        perm = _permission_for_route(r)
        if not perm:
            continue
        for method in sorted(methods):
            out.append({
                "method": method,
                "path": r.path,
                "url": _substitute_path_params(r.path),
                "permission": perm,
                "name": r.name,
            })
    return out


ROUTES = _discover_routes()


# ── DB helpers ───────────────────────────────────────────────────────────────
def _db_available() -> bool:
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


DB_AVAILABLE = _db_available()
requires_db = pytest.mark.skipif(not DB_AVAILABLE, reason="Postgres not reachable")


def _seeded_permissions() -> set[str]:
    with SessionLocal() as db:
        return {r[0] for r in db.execute(text("SELECT name FROM permissions")).fetchall()}


def _seeded_role_permissions() -> dict[str, set[str]]:
    with SessionLocal() as db:
        rows = db.execute(text("""
            SELECT r.name, p.name
            FROM roles r
            JOIN role_permissions rp ON rp.role_id = r.id
            JOIN permissions p ON p.id = rp.permission_id
            WHERE r.workspace_id IS NULL
        """)).fetchall()
    out: dict[str, set[str]] = {r: set() for r in ROLES}
    for role_name, perm_name in rows:
        out.setdefault(role_name, set()).add(perm_name)
    return out


# ── Static tests (Layer A) ───────────────────────────────────────────────────
def test_routes_discovered():
    # If this trips, either the app has no permission-gated routes (unlikely)
    # or the closure-tagging hook in conftest broke.
    assert ROUTES, "No permission-gated routes discovered — conftest tagging may be broken"


@requires_db
def test_every_code_permission_is_seeded():
    seeded = _seeded_permissions()
    used = {r["permission"] for r in ROUTES}
    missing = sorted(used - seeded)
    assert not missing, (
        f"{len(missing)} permission(s) referenced in code but not in DB seed. "
        f"Add to alembic migration 0001 `permissions` insert, or fix the typo: {missing}"
    )


@requires_db
def test_every_seeded_permission_is_used_or_allowlisted():
    seeded = _seeded_permissions()
    used = {r["permission"] for r in ROUTES}
    orphans = sorted(seeded - used - UNUSED_PERMISSION_ALLOWLIST)
    assert not orphans, (
        f"{len(orphans)} permission(s) seeded but no endpoint uses them. "
        f"Delete from seed or add to UNUSED_PERMISSION_ALLOWLIST with a comment: {orphans}"
    )


@requires_db
def test_write_verbs_do_not_use_view_permission():
    """Cheap sanity: POST/PUT/PATCH/DELETE should not gate on a `*.view` perm."""
    write_verbs = {"POST", "PUT", "PATCH", "DELETE"}
    offenders = [
        f'{r["method"]} {r["path"]} → {r["permission"]}'
        for r in ROUTES
        if r["method"] in write_verbs and r["permission"].endswith(".view")
    ]
    assert not offenders, f"Mutating routes gated only by a .view permission: {offenders}"


# ── Runtime probing (Layer B) ────────────────────────────────────────────────
@pytest.fixture(scope="module")
def seeded_matrix_env():
    """Seed a test workspace + one user per role. Idempotent."""
    if not DB_AVAILABLE:
        pytest.skip("Postgres not reachable")
    with SessionLocal() as db:
        now = datetime.now(timezone.utc)
        db.execute(text("""
            INSERT INTO workspaces (id, name, owner_id, plan, is_approved, created_at, updated_at)
            VALUES (:id, 'matrix-test', :owner, 'free', true, :now, :now)
            ON CONFLICT (id) DO NOTHING
        """), {"id": str(TEST_WS_ID), "owner": USER_IDS["admin"], "now": now})
        for role, uid in USER_IDS.items():
            db.execute(text("""
                INSERT INTO workspace_users (workspace_id, clerk_user_id, role, joined_at)
                VALUES (:ws, :uid, :role, :now)
                ON CONFLICT (workspace_id, clerk_user_id)
                    DO UPDATE SET role = EXCLUDED.role
            """), {"ws": str(TEST_WS_ID), "uid": uid, "role": role, "now": now})
        db.commit()
    yield
    with SessionLocal() as db:
        db.execute(text("DELETE FROM workspaces WHERE id = :id"), {"id": str(TEST_WS_ID)})
        db.commit()


@pytest.fixture
def matrix_client(seeded_matrix_env, monkeypatch, request):
    """TestClient with real require_permission wired back in and get_user_id
    / get_workspace_id overridden to point at the seeded matrix env.

    Parametrize the containing test with `role` and inject via
    `request.node.callspec.params['role']` — see `probe_matrix` below.
    """
    from tests.conftest import _ORIG_REQUIRE_PERMISSION  # noqa: WPS433

    # 1. Force Clerk to appear enabled so require_permission actually runs.
    monkeypatch.setattr(_auth_mod, "_clerk_enabled", lambda: True)

    # 2. Rewire every route's noop closure back to the real check for its
    #    declared permission. Keep originals for teardown.
    swapped: list[tuple[object, str, object]] = []
    for r in app.routes:
        dep = getattr(r, "dependant", None)
        if dep is None:
            continue
        for d in _walk_dependants(dep):
            perm = getattr(getattr(d, "call", None), "__conduct_permission__", None)
            if perm:
                swapped.append((d, "call", d.call))
                d.call = _ORIG_REQUIRE_PERMISSION(perm)

    role = request.node.callspec.params["role"]
    app.dependency_overrides[get_user_id] = lambda: USER_IDS[role]
    app.dependency_overrides[get_workspace_id] = lambda: str(TEST_WS_ID)

    yield TestClient(app, raise_server_exceptions=False)

    for target, attr, orig in swapped:
        setattr(target, attr, orig)
    app.dependency_overrides.pop(get_user_id, None)
    app.dependency_overrides.pop(get_workspace_id, None)


def _probe(client: TestClient, method: str, url: str):
    kwargs: dict = {}
    if method in {"POST", "PUT", "PATCH"}:
        kwargs["json"] = {}
    return client.request(method, url, **kwargs)


@requires_db
@pytest.mark.matrix
@pytest.mark.parametrize("role", ROLES)
@pytest.mark.parametrize(
    "route",
    ROUTES,
    ids=[f'{r["method"]} {r["path"]}' for r in ROUTES],
)
def test_rbac_matrix(matrix_client, role, route):
    """For every (endpoint, role) pair:
       - role lacks permission → status 403
       - role has permission   → status is anything but 403
    """
    role_perms = _seeded_role_permissions()[role]
    should_pass = route["permission"] in role_perms

    resp = _probe(matrix_client, route["method"], route["url"])

    if should_pass:
        assert resp.status_code != 403, (
            f'{role} has {route["permission"]} but got 403 on '
            f'{route["method"]} {route["path"]} — body: {resp.text[:200]}'
        )
    else:
        assert resp.status_code == 403, (
            f'{role} lacks {route["permission"]} but got {resp.status_code} on '
            f'{route["method"]} {route["path"]} — body: {resp.text[:200]}'
        )
