#!/usr/bin/env python3
"""
CI gate: every FastAPI endpoint must declare an auth dependency.

Scans all router files under app/routers/ and app/modules/*/routers/
and fails if any @router.{method} endpoint has no recognised auth Depends().

Recognised auth dependencies (from app/core/auth.py):
  get_workspace_id, require_permission, get_current_user,
  get_guard_org_id, get_guard_hook_auth, require_workspace_role

Intentionally public endpoints must be added to ALLOWLIST below.
"""
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # apps/api/

AUTH_DEPS = {
    "get_workspace_id",
    "get_workspace_id_sse",
    "require_permission",
    "require_workspace_role",
    "require_workspace_role_sse",
    "get_current_user",
    "get_user_id",
    "get_user_workspace_role_sse",
    "get_guard_org_id",
    "get_guard_hook_auth",
    "_require_admin",
    "_require_super_admin",
    "_bearer",
    "_get_optional_user_id",
}

# Endpoints that are intentionally public — no auth required.
# Format: "routers/filename.py::function_name"
ALLOWLIST = {
    # Health / readiness
    "routers/health.py::health",
    "routers/health.py::ready",
    # OAuth / OIDC discovery (must be public by spec)
    "routers/oauth.py::oauth_authorize",
    "routers/oauth.py::oauth_token",
    "routers/oauth.py::oauth_metadata",
    "routers/oauth.py::protected_resource_metadata",
    "routers/oauth.py::protected_resource_metadata_guard",
    # Clerk webhooks (auth via webhook signature, not Bearer)
    "routers/webhooks.py::clerk_webhook",
    "routers/webhooks.py::stripe_webhook",
    # GitHub webhooks (auth via X-Hub-Signature-256)
    "routers/github_webhook.py::github_webhook",
    # Guard MCP (has its own internal auth)
    "modules/guard/routers/mcp.py::mcp_endpoint",
    "modules/guard/routers/mcp.py::mcp_sse",
    "modules/guard/routers/mcp.py::well_known_oauth",
    "modules/guard/routers/mcp.py::well_known_protected_resource",
    "modules/guard/routers/mcp.py::well_known_protected_resource_guard",
    # Guard proxy (has its own internal auth)
    "modules/guard/routers/proxy.py::proxy_llm",
    # Credential broker (auth via X-Cred-Token: cond_cred_*)
    "routers/credentials.py::retrieve_cred",
    # Token endpoints (auth via X-Api-Key or refresh token)
    "routers/tokens.py::mint_access_token",
    "routers/tokens.py::mint_session_token",
    # CLI token refresh (auth via refresh_token in body — RFC-style rotation)
    "modules/auth/cli_token.py::refresh_cli_token",
    # RFC 8693 token exchange: Clerk JWT → cond_agt_* (subject_token in body)
    "modules/auth/token_exchange.py::token_exchange",
    # Guard join (auth via invite_code in body)
    "modules/guard/routers/config.py::join_guard",
    # Guard hook events (workspace_id validated against guard_config — no Clerk auth by design)
    "modules/guard/routers/events.py::ingest_event",
    "modules/guard/routers/events.py::update_usage",
    "modules/guard/routers/events.py::ingest_batch",
    # Guard budget check (workspace_id validated against guard_config — called pre-tool-use)
    "modules/guard/routers/spend.py::budget_check",
    # Telemetry ingest (auth via Authorization or X-Workspace-Id header — alternative auth)
    "modules/telemetry/routes.py::ingest_event",
    # Playbook catalog (intentionally public — no user data returned)
    "routers/playbooks.py::list_playbooks",
    "routers/playbooks.py::get_playbook",
    # Project templates (intentionally public — no user data)
    "routers/projects.py::list_templates",
    # Admin approve (auth via X-Admin-Secret HMAC — internal ops endpoint)
    "routers/projects.py::admin_approve",
    # Share link resolver (auth via opaque token in URL path)
    "routers/share.py::resolve_share",
    # YAML validation / graph conversion — stateless, no DB reads, no user data
    "routers/workflows.py::validate_workflow_yaml",
    "routers/workflows.py::workflow_yaml_from_graph",
    # Eval/benchmark endpoints — aggregate report data committed to git, no user data
    "routers/eval.py::get_eval_summary",
    "routers/eval.py::get_playbook_eval",
    "routers/eval.py::list_playbook_evals",
    "routers/eval.py::list_benchmark_editions",
    "routers/eval.py::get_benchmark_edition",
}

HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options"}


def _is_auth_depends(node: ast.expr) -> bool:
    """Return True if node is Depends(<auth-dep>) or Depends(<auth-dep>(...)). """
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if not (isinstance(func, ast.Name) and func.id == "Depends"):
        return False
    if not node.args:
        return False
    inner = node.args[0]
    if isinstance(inner, ast.Name) and inner.id in AUTH_DEPS:
        return True
    if isinstance(inner, ast.Call):
        fn = inner.func
        if isinstance(fn, ast.Name) and fn.id in AUTH_DEPS:
            return True
    return False


def _has_auth(funcdef: ast.FunctionDef) -> bool:
    """Return True if any argument has an auth Depends() — in defaults or Annotated[]."""
    # Check plain defaults: foo: str = Depends(get_workspace_id)
    for arg in funcdef.args.defaults + funcdef.args.kw_defaults:
        if arg is not None and _is_auth_depends(arg):
            return True
    # Check Annotated[X, Depends(...)] in annotations
    all_args = funcdef.args.args + funcdef.args.posonlyargs + funcdef.args.kwonlyargs
    for arg in all_args:
        ann = arg.annotation
        if ann is None:
            continue
        # Annotated[X, Depends(...)] → Subscript with Tuple slice
        if isinstance(ann, ast.Subscript) and isinstance(ann.value, ast.Name) and ann.value.id == "Annotated":
            sl = ann.slice
            elts = sl.elts if isinstance(sl, ast.Tuple) else [sl]
            for elt in elts:
                if _is_auth_depends(elt):
                    return True
    return False


def _scan_file(path: Path) -> list[str]:
    """Return list of 'relative/path.py::func_name' for unprotected endpoints."""
    try:
        tree = ast.parse(path.read_text())
    except SyntaxError:
        return []

    rel = str(path.relative_to(ROOT / "app"))
    violations = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        # Check if decorated with @router.{method}
        for dec in node.decorator_list:
            is_route = False
            if isinstance(dec, ast.Call):
                fn = dec.func
                if isinstance(fn, ast.Attribute) and fn.attr in HTTP_METHODS:
                    is_route = True
            if not is_route:
                continue
            key = f"{rel}::{node.name}"
            if key in ALLOWLIST:
                continue
            if not _has_auth(node):
                violations.append(key)

    return violations


def main():
    scan_dirs = [
        ROOT / "app" / "routers",
        ROOT / "app" / "modules",
    ]
    all_violations = []
    for d in scan_dirs:
        for path in sorted(d.rglob("*.py")):
            all_violations.extend(_scan_file(path))

    if all_violations:
        print("AUTH COVERAGE FAILURE — endpoints missing auth dependency:\n")
        for v in all_violations:
            print(f"  ✗  {v}")
        print(f"\n{len(all_violations)} endpoint(s) unprotected.")
        print("Add auth (Depends(get_workspace_id) / Depends(require_permission(...)))")
        print("or add to ALLOWLIST in scripts/check_auth_coverage.py if intentionally public.")
        sys.exit(1)
    else:
        print(f"Auth coverage OK — all endpoints protected.")


if __name__ == "__main__":
    main()
