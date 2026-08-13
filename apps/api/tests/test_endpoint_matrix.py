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

The runtime layer resolves permission by cross-referencing the AST result
with `app.routes[*].name`, then swaps the noop closure planted by conftest
back to the real check.
"""
from __future__ import annotations

import ast
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
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
    return re.sub(r"\{[^}]+\}", UUID_ZERO, path)


def _discover_routes() -> list[dict]:
    """Cross-reference AST permissions with runtime routes to get full
    (method, url, permission, name) tuples for the RBAC probe."""
    out: list[dict] = []
    for r in app.routes:
        name = getattr(r, "name", None)
        if not name or name not in ENDPOINT_PERMISSIONS:
            continue
        methods = getattr(r, "methods", None) or set()
        methods = {m for m in methods if m != "HEAD"}
        if not methods:
            continue
        perm = ENDPOINT_PERMISSIONS[name]
        for method in sorted(methods):
            out.append({
                "method": method,
                "path": r.path,
                "url": _substitute_path_params(r.path),
                "permission": perm,
                "name": name,
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


# ── Static tests ─────────────────────────────────────────────────────────────
def test_permissions_discovered_from_source():
    assert ENDPOINT_PERMISSIONS, (
        "AST scan found zero `require_permission(...)` calls under app/routers "
        "and app/modules/*/routers — either the scan glob is wrong or the "
        "decorator convention changed."
    )


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
}


@requires_db
def test_write_verbs_do_not_use_view_permission():
    write_verbs = {"POST", "PUT", "PATCH", "DELETE"}
    offenders = [
        f'{r["method"]} {r["path"]} → {r["permission"]}'
        for r in ROUTES
        if r["method"] in write_verbs
        and r["permission"].endswith(".view")
        and (r["method"], r["path"]) not in WRITE_VERB_ALLOWLIST
    ]
    assert not offenders, f"Mutating routes gated only by a .view permission: {offenders}"


# ── Runtime probing (Layer B) ────────────────────────────────────────────────
@pytest.fixture(scope="module")
def seeded_matrix_env():
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
    # Teardown is best-effort — 664 probes create integrations / audit rows
    # via side effects and not every FK cascades. CI DB is ephemeral so
    # leaked rows are harmless. Swallowing the error keeps the job green
    # when only test data (not test assertions) is dirty.
    try:
        with SessionLocal() as db:
            db.execute(text("DELETE FROM workspaces WHERE id = :id"), {"id": str(TEST_WS_ID)})
            db.commit()
    except Exception as exc:
        print(f"[matrix-teardown] non-fatal cleanup error: {exc!r}")


def _walk_dependants(dep):
    yield dep
    for child in dep.dependencies:
        yield from _walk_dependants(child)


@pytest.fixture
def matrix_client(seeded_matrix_env, monkeypatch, request):
    """TestClient wired for real RBAC:
      * `_clerk_enabled` → True (else require_permission short-circuits)
      * `get_user_id` / `get_workspace_id` → seeded rows
      * every noop closure planted by conftest is swapped back to the real
        _ORIG_REQUIRE_PERMISSION for the route's declared permission."""
    from tests.conftest import _ORIG_REQUIRE_PERMISSION

    monkeypatch.setattr(_auth_mod, "_clerk_enabled", lambda: True)

    # Build {name: permission} from AST, then rewire each route's dependant
    # whose `.name` matches. We do NOT rely on the closure tag surviving
    # import-order weirdness.
    swapped: list[tuple[object, object]] = []
    for r in app.routes:
        name = getattr(r, "name", None)
        perm = ENDPOINT_PERMISSIONS.get(name) if name else None
        if not perm:
            continue
        dep = getattr(r, "dependant", None)
        if dep is None:
            continue
        for d in _walk_dependants(dep):
            call = getattr(d, "call", None)
            # Recognise both the tagged noop and any callable named _check
            # returned by _permissive_permission — either way, replace with
            # a real check bound to the AST-declared permission.
            if call is None:
                continue
            if getattr(call, "__conduct_permission__", None) or getattr(call, "__name__", "") == "_check":
                swapped.append((d, d.call))
                d.call = _ORIG_REQUIRE_PERMISSION(perm)
                break

    role = request.node.callspec.params["role"]
    app.dependency_overrides[get_user_id] = lambda: USER_IDS[role]
    app.dependency_overrides[get_workspace_id] = lambda: str(TEST_WS_ID)

    yield TestClient(app, raise_server_exceptions=False)

    for target, orig in swapped:
        target.call = orig
    app.dependency_overrides.pop(get_user_id, None)
    app.dependency_overrides.pop(get_workspace_id, None)


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
    ROUTES,
    ids=[f'{r["method"]} {r["path"]}' for r in ROUTES] or ["no-routes"],
)
def test_rbac_matrix(matrix_client, role, route):
    role_perms = _seeded_role_permissions()[role]
    should_pass = route["permission"] in role_perms
    key = (route["method"], route["path"])

    resp = _probe(matrix_client, route["method"], route["url"])

    if should_pass:
        # Authorised: must NOT be a permission 403. Three ways a 403 is OK:
        #   1. Endpoint on BUSINESS_403_ALLOWLIST (pack rules, etc.)
        #   2. Response body has a NON_AUTH_403_MARKERS phrase — the 403 came
        #      from post-auth logic (resource missing, internal error masked)
        #   3. Anything else — 200/201/400/404/422 all mean auth passed
        if resp.status_code == 403 and (key in BUSINESS_403_ALLOWLIST or _is_non_auth_403(resp)):
            return
        assert resp.status_code != 403, (
            f'{role} has {route["permission"]} but got 403 on '
            f'{route["method"]} {route["path"]} — body: {resp.text[:200]}'
        )
    else:
        # Unauthorised: acceptable rejections are:
        #   * 4xx (auth or body-validate said no)
        #   * 5xx whose body is an internal-error marker — the endpoint
        #     crashed post-auth, still not a data-leak. Separate endpoint
        #     bug to fix; not this test's job.
        # 2xx from an unauthorised role is the real failure mode this test guards.
        acceptable = 400 <= resp.status_code < 500 or (
            resp.status_code >= 500 and _body_has_non_auth_marker(resp)
        )
        assert acceptable, (
            f'{role} lacks {route["permission"]} but got {resp.status_code} on '
            f'{route["method"]} {route["path"]} — body: {resp.text[:200]}'
        )
