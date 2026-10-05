"""Endpoint × Role RBAC matrix — Phase 1 of the test-harness plan.

Two layers, both generated from source-of-truth:

A. Static consistency (AST scan of router files, DB read-only):
     - every code-declared permission exists in the `permissions` table
     - every seeded permission is used by at least one endpoint (or allowlisted)

B. Runtime probing (real TestClient, real DB, real require_permission):
     - for each (route, role): unauthorised roles get 403,
       authorised roles get anything-but-403.

The static layer uses AST parsing (like scripts/check_auth_coverage.py) so
it doesn't depend on Python import order or the conftest closure patch —
those two coupling points broke it in CI on the first run.

The runtime layer uses effective routes (including nested routers) and their
permission dependencies, then restores real checks with dependency overrides.
"""
from __future__ import annotations

import ast
import inspect
import os
import re
import uuid
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path

import pytest
from fastapi import APIRouter, Depends, FastAPI, HTTPException
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy import text

import app.core.auth as _auth_mod
from app.core.auth import get_user_id, get_workspace_id
from app.core.database import SessionLocal
from app.main import app

# ── Constants ────────────────────────────────────────────────────────────────
ROLES = ("admin", "security", "developer", "viewer")
TEST_WS_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
USER_IDS = {role: f"user_matrix_{role}" for role in ROLES}
UUID_ZERO = "00000000-0000-0000-0000-000000000000"

# Permissions in the seed that aren't reachable from any current endpoint.
# Each entry is deliberate code debt — either the endpoint exists but isn't
# gated yet, or the perm is scaffolded for near-future work. Delete from the
# seed if that stops being true.
UNUSED_PERMISSION_ALLOWLIST: set[str] = {
    "guard.activity.export",   # export endpoint not shipped yet
    "guard.spend.view_all",    # spend read is currently gated by view_own only
    "guard.spend.view_own",    # same — reserved for split later
}

APPS_API = Path(__file__).resolve().parent.parent  # apps/api/


# ── AST scan (static source of truth for {function: permission}) ────────────
def _scan_router_file(path: Path) -> dict[str, str]:
    """Return {function_name: permission_string} for endpoints in this file."""
    out: dict[str, str] = {}
    try:
        tree = ast.parse(path.read_text())
    except SyntaxError:
        return out
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        # Only care about functions decorated with `<something>.<verb>(...)`.
        # Router variable name varies (router, r, audit_router, sub_r, ...),
        # so we don't pin it — the verb + kind check is enough.
        if not any(
            isinstance(d, ast.Call)
            and isinstance(d.func, ast.Attribute)
            and d.func.attr in {"get", "post", "put", "patch", "delete"}
            for d in node.decorator_list
        ):
            continue
        # Look for any `require_permission("X")` call anywhere in the
        # function's arg list — defaults, kw defaults, and Annotated[]
        # type annotations all count (Depends can live in any of them).
        signature_nodes: list[ast.AST] = list(node.args.defaults)
        signature_nodes.extend(kw for kw in node.args.kw_defaults if kw is not None)
        signature_nodes.extend(a.annotation for a in node.args.args if a.annotation is not None)
        signature_nodes.extend(a.annotation for a in node.args.kwonlyargs if a.annotation is not None)

        for sig_node in signature_nodes:
            for sub in ast.walk(sig_node):
                if (
                    isinstance(sub, ast.Call)
                    and isinstance(sub.func, ast.Name)
                    and sub.func.id == "require_permission"
                    and sub.args
                    and isinstance(sub.args[0], ast.Constant)
                    and isinstance(sub.args[0].value, str)
                ):
                    out[node.name] = sub.args[0].value
                    break
            if node.name in out:
                break
    return out


def _discover_permissions() -> dict[str, str]:
    """Walk router files, return {function_name: permission}. Same convention
    as scripts/check_auth_coverage.py."""
    root = APPS_API / "app"
    files = list((root / "routers").glob("*.py")) + list((root / "modules").glob("*/routers/*.py"))
    merged: dict[str, str] = {}
    for f in files:
        merged.update(_scan_router_file(f))
    return merged


ENDPOINT_PERMISSIONS = _discover_permissions()


def _substitute_path_params(path: str) -> str:
    path = path.replace("{workspace_id}", str(TEST_WS_ID))
    return re.sub(r"\{[^}]+\}", UUID_ZERO, path)


def _api_routes(application=app):
    # FastAPI 0.141 keeps included routers lazy; effective contexts contain
    # the actual mounted paths and dependency trees used to serve requests.
    for route in application.routes:
        if isinstance(route, APIRoute):
            yield route
        elif callable(getattr(route, "effective_route_contexts", None)):
            for context in route.effective_route_contexts():
                if isinstance(context.original_route, APIRoute):
                    yield context


def _walk_dependants(dep):
    yield dep
    for child in dep.dependencies:
        yield from _walk_dependants(child)


def _permission_checks(route):
    for dep in _walk_dependants(route.dependant):
        call = dep.call
        permission = getattr(call, "__conduct_permission__", None)
        if permission is None and inspect.isfunction(call):
            permission = inspect.getclosurevars(call).nonlocals.get("permission")
        if isinstance(permission, str):
            yield call, permission


def _discover_routes(application=app) -> list[dict]:
    out: list[dict] = []
    for r in _api_routes(application):
        permissions = {permission for _, permission in _permission_checks(r)}
        if not permissions:
            continue
        for method in sorted(r.methods - {"HEAD"}):
            out.append({
                "method": method,
                "path": r.path,
                "url": _substitute_path_params(r.path),
                "permissions": permissions,
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
MATRIX_REQUIRED = os.environ.get("ENDPOINT_MATRIX_REQUIRED") == "1"
requires_db = pytest.mark.skipif(
    not DB_AVAILABLE and not MATRIX_REQUIRED, reason="Postgres not reachable",
)


def _require_database(available, required):
    if not available:
        if required:
            pytest.fail("Required endpoint matrix database is unavailable", pytrace=False)
        pytest.skip("Postgres not reachable")


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


# ── Static tests ─────────────────────────────────────────────────────────────
def test_permissions_discovered_from_source():
    assert ENDPOINT_PERMISSIONS, (
        "AST scan found zero `require_permission(...)` calls under app/routers "
        "and app/modules/*/routers — either the scan glob is wrong or the "
        "decorator convention changed."
    )


@pytest.mark.matrix
def test_runtime_routes_discovered():
    assert ROUTES, "Endpoint matrix discovered zero permission-gated routes"


def test_empty_runtime_discovery_fails(monkeypatch):
    monkeypatch.setitem(globals(), "ROUTES", [])
    with pytest.raises(AssertionError, match="zero permission-gated routes"):
        test_runtime_routes_discovered()


def test_nested_router_discovery_preserves_paths_and_distinct_permissions():
    application = FastAPI()
    nested = APIRouter()

    def permission_check():
        return "admin"

    permission_check.__conduct_permission__ = "platform.workflows.edit"

    @nested.get("/items/{item_id}", name="shared_name")
    def first(_: str = Depends(permission_check)):
        return {}

    outer = APIRouter()
    outer.include_router(nested, prefix="/nested")
    application.include_router(outer, prefix="/v1")
    application.include_router(outer, prefix="/v2")

    def other_check():
        return "viewer"

    other_check.__conduct_permission__ = "platform.workflows.view"

    @application.get("/direct", name="shared_name")
    def second(_: str = Depends(other_check)):
        return {}

    routes = _discover_routes(application)
    assert {r["path"] for r in routes} == {
        "/v1/nested/items/{item_id}", "/v2/nested/items/{item_id}", "/direct",
    }
    assert routes[-1]["permissions"] == {"platform.workflows.view"}
    assert routes[0]["permissions"] == {"platform.workflows.edit"}
    assert routes[0]["url"] == f"/v1/nested/items/{UUID_ZERO}"


def test_required_matrix_database_fails_instead_of_skipping():
    with pytest.raises(pytest.fail.Exception, match="database is unavailable"):
        _require_database(False, True)
    with pytest.raises(pytest.skip.Exception, match="Postgres not reachable"):
        _require_database(False, False)
    _require_database(True, True)


def test_probe_path_uses_the_seeded_workspace():
    assert _substitute_path_params("/workspaces/{workspace_id}/gateways/{gateway_id}") == (
        f"/workspaces/{TEST_WS_ID}/gateways/{UUID_ZERO}"
    )


@pytest.mark.parametrize("allowed", [True, False])
def test_nested_router_override_runs_real_check_and_records_outcome(allowed):
    application = FastAPI()
    router = APIRouter()

    def noop():
        return "admin"

    noop.__conduct_permission__ = "example.edit"

    @router.get("/protected")
    def protected(_: str = Depends(noop)):
        return {"ok": True}

    application.include_router(router, prefix="/nested")

    def identity():
        return "viewer"

    def real_check(user: str = Depends(identity)):
        if not allowed:
            raise HTTPException(status_code=403, detail="Permission denied")
        return user

    results = []
    route = next(_api_routes(application))
    call, permission = next(_permission_checks(route))
    application.dependency_overrides[call] = _tracked_check(real_check, permission, results)
    with TestClient(application) as client:
        response = client.get("/nested/protected")
    assert response.status_code == (200 if allowed else 403)
    assert results == [("example.edit", "viewer" if allowed else None)]


@requires_db
def test_every_code_permission_is_seeded():
    seeded = _seeded_permissions()
    used = set(ENDPOINT_PERMISSIONS.values())
    missing = sorted(used - seeded)
    assert not missing, (
        f"{len(missing)} permission(s) referenced in code but not in DB seed. "
        f"Add to alembic migration 0001 `permissions` insert or fix the typo: {missing}"
    )


@requires_db
def test_every_seeded_permission_is_used_or_allowlisted():
    seeded = _seeded_permissions()
    used = set(ENDPOINT_PERMISSIONS.values())
    orphans = sorted(seeded - used - UNUSED_PERMISSION_ALLOWLIST)
    assert not orphans, (
        f"{len(orphans)} permission(s) seeded but no endpoint uses them. "
        f"Delete from seed or add to UNUSED_PERMISSION_ALLOWLIST with a comment: {orphans}"
    )


# POST endpoints that only read/simulate but use POST because the input is a
# body. Legit; excluded from the write-verb heuristic.
WRITE_VERB_ALLOWLIST: set[tuple[str, str]] = {
    ("POST", "/workflows/{workflow_id}/validate"),   # dry validation of YAML
    ("POST", "/eval/run/{slug}"),                    # eval simulation
    ("POST", "/eval/run"),                           # eval simulation
    ("POST", "/guard/policies/lint"),                # static lint
    ("POST", "/guard/trial/demo/{verb}"),           # fixed sandbox demo, no workspace edits
    ("POST", "/guard/fixture-approvals/consume"),     # caller-bound, preapproved one-use action
}


@requires_db
def test_write_verbs_do_not_use_view_permission():
    write_verbs = {"POST", "PUT", "PATCH", "DELETE"}
    offenders = [
        f'{r["method"]} {r["path"]} → {permission}'
        for r in ROUTES
        for permission in r["permissions"]
        if r["method"] in write_verbs
        and permission.endswith(".view")
        and (r["method"], r["path"]) not in WRITE_VERB_ALLOWLIST
    ]
    assert not offenders, f"Mutating routes gated only by a .view permission: {offenders}"


# ── Runtime probing (Layer B) ────────────────────────────────────────────────
@pytest.fixture(scope="module")
def seeded_matrix_env():
    _require_database(DB_AVAILABLE, MATRIX_REQUIRED)
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
    # Teardown is best-effort — probes create integrations / audit rows
    # via side effects and not every FK cascades. CI DB is ephemeral so
    # leaked rows are harmless. Swallowing the error keeps the job green
    # when only test data (not test assertions) is dirty.
    try:
        with SessionLocal() as db:
            db.execute(text("DELETE FROM workspaces WHERE id = :id"), {"id": str(TEST_WS_ID)})
            db.commit()
    except Exception as exc:
        print(f"[matrix-teardown] non-fatal cleanup error: {exc!r}")


def _tracked_check(check, permission, results):
    @wraps(check)
    def tracked(*args, **kwargs):
        try:
            role = check(*args, **kwargs)
        except HTTPException as exc:
            if exc.status_code == 403:
                results.append((permission, None))
            raise
        results.append((permission, role))
        return role
    return tracked


@pytest.mark.parametrize("error", [RuntimeError("broken check"), HTTPException(500)])
def test_permission_errors_are_not_recorded_as_completed_decisions(error):
    results = []

    def broken_check():
        raise error

    with pytest.raises(type(error)):
        _tracked_check(broken_check, "example.edit", results)()
    assert results == []


@pytest.fixture
def matrix_client(seeded_matrix_env, monkeypatch, request):
    """Keep identity fixtures local while exercising real DB-backed RBAC."""
    from tests.conftest import _ORIG_REQUIRE_PERMISSION

    monkeypatch.setattr(_auth_mod, "_clerk_enabled", lambda: True)

    results = []
    for route in _api_routes():
        for call, permission in _permission_checks(route):
            real_check = _ORIG_REQUIRE_PERMISSION(permission)
            monkeypatch.setitem(
                app.dependency_overrides, call,
                _tracked_check(real_check, permission, results),
            )

    role = request.node.callspec.params["role"]
    monkeypatch.setitem(app.dependency_overrides, get_user_id, lambda: USER_IDS[role])
    monkeypatch.setitem(app.dependency_overrides, get_workspace_id, lambda: str(TEST_WS_ID))
    client = TestClient(app, raise_server_exceptions=False)
    client.permission_results = results
    yield client
    client.close()


def _probe(client: TestClient, method: str, url: str):
    kwargs: dict = {}
    if method in {"POST", "PUT", "PATCH"}:
        kwargs["json"] = {}
    return client.request(method, url, **kwargs)


# Endpoints that legitimately return 403 for business reasons (not for
# missing permission). Admin has the right perm but the endpoint still 403s
# because of resource state (e.g. can't delete built-in pack rules). Auth
# passed — the 403 is a policy/state assertion. Add sparingly with a comment.
BUSINESS_403_ALLOWLIST: set[tuple[str, str]] = {
    ("DELETE", "/guard/policies/{rule_id}"),  # pack rules cannot be deleted
}

# Response-body markers that indicate the 403 came from post-auth logic
# (resource missing, internal error, state check) rather than the perm dep.
# Endpoints returning these should ideally emit 404/500 — separate bug, but
# for the RBAC matrix a body-match here means auth passed.
NON_AUTH_403_MARKERS = (
    "not found",
    "does not exist",
    "an internal error occurred",
)


def _body_has_non_auth_marker(resp) -> bool:
    body = (resp.text or "").lower()
    return any(m in body for m in NON_AUTH_403_MARKERS)


def _is_non_auth_403(resp) -> bool:
    return resp.status_code == 403 and _body_has_non_auth_marker(resp)


@requires_db
@pytest.mark.matrix
@pytest.mark.parametrize("role", ROLES)
@pytest.mark.parametrize(
    "route",
    ROUTES or [None],
    ids=[f'{r["method"]} {r["path"]}' for r in ROUTES] or ["no-routes"],
)
def test_rbac_matrix(matrix_client, role, route):
    assert route is not None, "Endpoint matrix discovered zero permission-gated routes"
    role_perms = _seeded_role_permissions()[role]
    should_pass = route["permissions"] <= role_perms
    key = (route["method"], route["path"])

    resp = _probe(matrix_client, route["method"], route["url"])
    checked = set(matrix_client.permission_results)
    if should_pass:
        assert {(p, role) for p in route["permissions"]} <= checked, (
            "Request did not complete its real permission checks"
        )
    else:
        assert any((p, None) in checked for p in route["permissions"] - role_perms), (
            "Request was rejected without exercising its real permission denial"
        )

    if should_pass:
        # Authorised: must NOT be a permission 403. Three ways a 403 is OK:
        #   1. Endpoint on BUSINESS_403_ALLOWLIST (pack rules, etc.)
        #   2. Response body has a NON_AUTH_403_MARKERS phrase — the 403 came
        #      from post-auth logic (resource missing, internal error masked)
        #   3. Anything else — 200/201/400/404/422 all mean auth passed
        if resp.status_code == 403 and (key in BUSINESS_403_ALLOWLIST or _is_non_auth_403(resp)):
            return
        assert resp.status_code != 403, (
            f'{role} has {route["permissions"]} but got 403 on '
            f'{route["method"]} {route["path"]} — body: {resp.text[:200]}'
        )
    else:
        # A completed real denial must reach the client as a permission 403.
        assert resp.status_code == 403, (
            f'{role} lacks {route["permissions"]} but got {resp.status_code} on '
            f'{route["method"]} {route["path"]} — body: {resp.text[:200]}'
        )
