#!/usr/bin/env python3
"""
CI gate: every FastAPI endpoint must declare an auth dependency.

Scans app/routers/, app/modules/, app/main.py and app/mcp/http.py (sync and
async routes, websockets) and fails if any route decorator endpoint has no recognised auth Depends().

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
    "_hook_authenticated_workspace",  # Agent token auth; legacy mode controlled by guard_require_hook_auth.
    "require_platform_operator",
    "_require_admin",
    "_require_super_admin",
    "_bearer",
    "_get_optional_user_id",
    "_gateway_principal",  # gateway_proxy.py: resolve_agent_token on x-api-key / Authorization
}

SCAN_DIRS = ["app/routers", "app/modules"]
SCAN_FILES = ["app/main.py", "app/mcp/http.py"]

# Endpoints that are intentionally public — no auth required.
# Format: "routers/filename.py::function_name"
ALLOWLIST = {
    # --- Public by design -------------------------------------------------
    # Health / readiness / static assets
    "main.py::favicon",  # static icon
    "main.py::health",  # liveness probe, static body
    "main.py::live",  # liveness probe, static body
    "main.py::ready",  # readiness probe
    "main.py::sandbox_health",  # static platform note, no tenant data
    # OAuth / discovery metadata (public by spec)
    "mcp/http.py::oauth_resource_metadata",  # RFC 9728 resource metadata
    "modules/guard/routers/mcp.py::oauth_protected_resource",  # RFC 9728 resource metadata
    "modules/auth/oauth/router.py::oauth_metadata",  # RFC 8414 server metadata
    # OAuth 2.1 + DCR - public by spec.
    "modules/auth/oauth/router.py::dcr_register",  # RFC 7591 dynamic client registration
    "modules/auth/oauth/router.py::authorize",  # browser round-trip; verifies Clerk JWT internally
    "modules/auth/oauth/router.py::authorize_confirm",  # browser round-trip; verifies Clerk JWT internally
    "modules/auth/oauth/router.py::oauth_token",  # PKCE / refresh / RFC 8693 grants
    "modules/auth/oauth/router.py::legacy_token",  # PKCE / refresh grants
    # Public catalogs (no tenant data)
    "routers/playbooks.py::list_playbooks",  # playbook catalog
    "routers/playbooks.py::get_playbook",  # playbook catalog
    "routers/compliance.py::list_pack_catalog",  # skill pack catalog (/packs/available + /packs/catalog)
    "routers/projects_core.py::list_templates",  # project templates
    "routers/eval_reports.py::get_eval_summary",  # aggregate report data committed to git
    "routers/eval_reports.py::get_playbook_eval",  # aggregate report data committed to git
    "routers/eval_reports.py::list_playbook_evals",  # aggregate report data committed to git
    "routers/eval.py::list_benchmark_editions",  # aggregate report data committed to git
    "routers/eval.py::get_benchmark_edition",  # aggregate report data committed to git
    # Static acknowledgements
    "modules/guard/routers/gateway_proxy.py::gateway_anthropic_hello",  # HEAD probe, static 204
    "modules/guard/routers/mcp.py::mcp_terminate",  # stateless session-terminate ack, static 204, no data
    # --- Authenticated in the body ---------------------------------------
    "main.py::metrics",  # X-Metrics-Token check; fail-closed outside local/development
    "main.py::cache_stats",  # X-Metrics-Token check; fail-closed outside local/development
    "mcp/http.py::mcp_endpoint",  # _auth_or_401(request)
    "mcp/http.py::mcp_stream",  # _auth_or_401(request)
    "mcp/http.py::mcp_terminate",  # _auth_or_401(request)
    "modules/auth/console/router.py::exchange_identity",  # shared proxy secret + signed Keycloak identity + active console mapping
    "modules/guard/routers/mcp.py::mcp_endpoint",  # resolve_agent_token inside handler
    "modules/guard/routers/mcp.py::mcp_sse",  # resolve_agent_token inside handler
    "modules/guard/routers/mcp.py::oauth_member_token",  # _verify_clerk_token + _assert_workspace_member
    "modules/guard/routers/proxy.py::ingest_local_audit",  # resolve_agent_token on member token header
    "modules/guard/routers/proxy.py::proxy_anthropic",  # resolve_agent_token via gateway_auth in _proxy
    "modules/guard/routers/proxy.py::proxy_openai",  # resolve_agent_token via gateway_auth in _proxy
    "modules/guard/routers/proxy.py::proxy_perplexity",  # resolve_agent_token via gateway_auth in _proxy
    "modules/guard/routers/gateway_proxy.py::gateway_anthropic",  # gateway_auth in handle_gateway_request
    "modules/guard/routers/gateway_proxy.py::gateway_anthropic_count_tokens",  # gateway_auth in handle_gateway_request
    "modules/guard/routers/gateway_proxy.py::gateway_openai",  # gateway_auth in handle_gateway_request
    "modules/guard/routers/gateway_proxy.py::gateway_openai_responses",  # gateway_auth in handle_gateway_request
    "modules/guard/routers/gateway_proxy.py::gateway_perplexity",  # gateway_auth in handle_gateway_request
    "modules/guard/routers/gateway_proxy.py::gateway_completions",  # gateway_auth in handle_gateway_request
    "modules/guard/routers/events_query.py::stream_events",  # get_workspace_id(stream_credentials(request)) in body (SSE)
    "modules/guard/routers/session_reports.py::get_session_report_html",  # Clerk JWT + guard.activity.view_all check_permission, HTML error pages
    "modules/guard/routers/ws.py::policy_ws",  # websocket; resolve_agent_token via _token_workspace; token workspace must equal requested workspace, checked before accept
    "modules/guard/routers/config.py::join_guard",  # invite_code in body
    "modules/guard/routers/blocks.py::get_receipt_public",  # sha256(share_token) in URL must match audit row and workspace on trial plan
    "modules/guard/routers/trial.py::provision_trial",  # public signup: IP rate-limit (5/hr) + email idempotency
    "modules/guard/routers/trial.py::redeem_trial",  # single-use challenge token in body matched against Redis
    "modules/telemetry/routes.py::ingest_event",  # Authorization or X-Workspace-Id header alternative auth
    "modules/auth/cli_token.py::refresh_cli_token",  # refresh_token in body (RFC-style rotation)
    "routers/webhooks.py::clerk_webhook",  # webhook signature
    "routers/webhooks.py::github_webhook",  # X-Hub-Signature-256 HMAC vs platform secret, fail-closed
    "routers/webhooks.py::github_webhook_by_slug",  # X-Hub-Signature-256 HMAC vs per-workflow secret, fail-closed
    "routers/webhooks_inbound.py::inbound_webhook",  # HMAC / X-Gitlab-Token vs per-workflow secret, fail-closed
    "routers/webhooks_inbound.py::vercel_webhook",  # x-vercel-signature HMAC, fail-closed
    "routers/webhooks_slack.py::slack_interactions",  # Slack signing-secret verification (platform or workspace)
    "routers/credentials.py::retrieve_cred",  # X-Cred-Token cond_cred_*
    "routers/projects.py::admin_approve",  # X-Admin-Secret HMAC
    "routers/share.py::resolve_share",  # opaque token in URL path
    "routers/playbooks.py::submit_playbook",  # Clerk JWT (X-Workspace-Id honoured only for members) or reCAPTCHA for anonymous (header ignored)
    # --- Deferred --------------------------------------------------------
    "modules/guard/routers/spend_budget_check.py::budget_check",  # auth added in follow-up; CLI compat window
}

HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options", "websocket", "api_route", "api_websocket_route"}

FuncDef = ast.FunctionDef | ast.AsyncFunctionDef


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


def _has_auth(funcdef: FuncDef) -> bool:
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


def _route_keys(path: Path, root: Path) -> list[tuple[str, FuncDef]]:
    """Return (key, funcdef) for every route-decorated function (sync or async) in path."""
    try:
        tree = ast.parse(path.read_text())
    except SyntaxError:
        return []
    rel = str(path.relative_to(root / "app"))
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            if not isinstance(dec, ast.Call):
                continue
            fn = dec.func
            if isinstance(fn, ast.Attribute) and fn.attr in HTTP_METHODS:
                out.append((f"{rel}::{node.name}", node))
                break
    return out


def _scan_file(path: Path, root: Path = ROOT, allowlist: set[str] | None = None) -> list[str]:
    """Return list of 'relative/path.py::func_name' for unprotected endpoints."""
    allow = ALLOWLIST if allowlist is None else allowlist
    return [
        key for key, node in _route_keys(path, root)
        if key not in allow and not _has_auth(node)
    ]


def _scan_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for d in SCAN_DIRS:
        files.extend(sorted((root / d).rglob("*.py")))
    files.extend(root / f for f in SCAN_FILES if (root / f).exists())
    return files


def find_stale_allowlist(root: Path = ROOT, allowlist: set[str] | None = None) -> list[str]:
    """Allowlist entries whose file or route no longer exists."""
    allow = ALLOWLIST if allowlist is None else allowlist
    existing = {k for f in _scan_files(root) for k, _ in _route_keys(f, root)}
    return sorted(a for a in allow if a not in existing)


def main():
    all_violations = []
    for path in _scan_files(ROOT):
        all_violations.extend(_scan_file(path))
    stale = find_stale_allowlist()

    failed = False
    if all_violations:
        failed = True
        print("AUTH COVERAGE FAILURE - endpoints missing auth dependency:\n")
        for v in all_violations:
            print(f"  x  {v}")
        print(f"\n{len(all_violations)} endpoint(s) unprotected.")
        print("Add auth (Depends(get_workspace_id) / Depends(require_permission(...)))")
        print("or add to ALLOWLIST in scripts/check_auth_coverage.py with a reason.")
    if stale:
        failed = True
        print("\nSTALE ALLOWLIST ENTRIES - file or route no longer exists:\n")
        for v in stale:
            print(f"  x  {v}")
        print("\nRemove them from ALLOWLIST in scripts/check_auth_coverage.py.")
    if failed:
        sys.exit(1)
    print("Auth coverage OK - all endpoints protected, allowlist current.")


if __name__ == "__main__":
    main()
