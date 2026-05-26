import argparse
import json
import sys
import time
import urllib.parse
from pathlib import Path

import yaml

from conduct_cli import api

RESET  = "\033[0m"
BOLD   = "\033[1m"
GREEN  = "\033[32m"
RED    = "\033[31m"
BLUE   = "\033[34m"
GRAY   = "\033[90m"
CYAN   = "\033[36m"
YELLOW = "\033[33m"

CONFIG_PATH = Path.home() / ".conduct" / "config.json"


# ── Config helpers ────────────────────────────────────────────────────────────

def _load_config() -> dict:
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text())
    return {}


def _save_config(data: dict):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(data, indent=2))


def _resolve(args, key: str, config_key=None):
    """Return value from CLI args first, then config file."""
    val = getattr(args, key.replace("-", "_"), None)
    if val:
        return val
    cfg = _load_config()
    return cfg.get(config_key or key)


def _require_auth(args):
    """Return (server, workspace_id, api_key, token) — exit if not configured."""
    server     = _resolve(args, "server")
    workspace  = _resolve(args, "workspace")
    api_key    = _resolve(args, "api_key", "api_key")
    token      = _resolve(args, "token")

    if not server:
        print(f"{RED}No server set. Run: conduct login --server <url> --api-key <key>{RESET}")
        sys.exit(1)
    if not workspace:
        print(f"{RED}No workspace set. Run: conduct login --workspace <id>{RESET}")
        sys.exit(1)
    if not api_key and not token:
        print(f"{RED}No credentials. Run: conduct login --api-key <key>{RESET}")
        sys.exit(1)

    return server.rstrip("/"), workspace, api_key, token


# ── Stream helper ─────────────────────────────────────────────────────────────

def _stream_run(server: str, workflow_id: str, run_id: str, workspace_id: str, token=None, api_key=None) -> bool:
    hdrs = api.headers(workspace_id, token, "application/json", api_key)
    url  = f"{server}/workflows/{workflow_id}/runs/{run_id}/stream"

    for data in api.stream(url, hdrs):
        kind    = data.get("kind", "")
        bid     = data.get("block_id") or ""
        payload = data.get("payload", data)
        prefix  = f"[{bid}] " if bid else ""

        if kind == "block_started":
            label = payload.get("label") or payload.get("type", "")
            print(f"{BLUE}    ▶ {prefix}{label}{RESET}")
        elif kind == "block_completed":
            summary = payload.get("summary") or json.dumps(payload, default=str)[:120]
            print(f"{GREEN}    ✓ {prefix}{summary}{RESET}")
        elif kind == "block_failed":
            err = payload.get("error", json.dumps(payload, default=str)[:200])
            print(f"{RED}    ✗ {prefix}{err}{RESET}")
        elif kind == "brain_tool_call":
            summary = payload.get("summary", payload.get("tool", ""))
            print(f"{GRAY}      · {summary}{RESET}")
        elif kind == "run_completed":
            print(f"{BOLD}{GREEN}    ✓ done{RESET}")
        elif kind == "run_failed":
            err = payload.get("error", "")
            print(f"{BOLD}{RED}    ✗ failed: {err}{RESET}")
        else:
            print(f"{GRAY}    {kind}: {json.dumps(payload, default=str)[:120]}{RESET}")

        if kind in ("run_completed", "run_failed"):
            return kind == "run_completed"

    return False


def _poll_run(server: str, workflow_id: str, run_id: str, hdrs: dict) -> bool:
    """Poll run status until terminal — fallback when SSE stream unavailable."""
    terminal = {"succeeded", "failed", "cancelled"}
    for _ in range(120):  # max 10 min
        time.sleep(5)
        try:
            run = api.req("GET", f"{server}/workflows/{workflow_id}/runs/{run_id}", hdrs)
            status = run.get("status", "")
            print(f"{GRAY}    status: {status}{RESET}", end="\r")
            if status in terminal:
                print()
                return status == "succeeded"
        except Exception:
            pass
    print(f"{RED}    timed out waiting for run{RESET}")
    return False


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_login(args):
    server    = args.server
    api_key   = args.api_key
    workspace = args.workspace
    token     = args.token

    if not server and not api_key and not workspace:
        cfg = _load_config()
        if cfg:
            print(f"{BOLD}Current config ({CONFIG_PATH}):{RESET}")
            print(f"  server:    {cfg.get('server', '—')}")
            print(f"  workspace: {cfg.get('workspace', '—')}")
            print(f"  api_key:   {'set' if cfg.get('api_key') else '—'}")
        else:
            print("No config found. Run: conduct login --server <url> --api-key <key> --workspace <id>")
        return

    cfg = _load_config()
    if server:    cfg["server"]    = server.rstrip("/")
    if api_key:   cfg["api_key"]   = api_key
    if workspace: cfg["workspace"] = workspace
    if token:     cfg["token"]     = token

    # Validate by hitting /workflows
    s   = cfg["server"]
    ws  = cfg.get("workspace", "")
    ak  = cfg.get("api_key")
    tok = cfg.get("token")
    if ws and (ak or tok):
        hdrs = api.headers(ws, tok, "application/json", ak)
        try:
            api.req("GET", f"{s}/workflows", hdrs)
            print(f"{GREEN}✓ Connected to {s}{RESET}")
        except SystemExit:
            print(f"{RED}Could not connect — check your server URL, workspace ID, and API key.{RESET}")
            sys.exit(1)

    _save_config(cfg)
    print(f"{GREEN}✓ Config saved to {CONFIG_PATH}{RESET}")


def cmd_agents(args):
    server, workspace_id, api_key, token = _require_auth(args)
    hdrs = api.headers(workspace_id, token, "application/json", api_key)

    project_filter = getattr(args, "project", None)
    url = f"{server}/workflows"
    if project_filter:
        # find project by name first
        projects = api.req("GET", f"{server}/workspaces/{workspace_id}/projects", hdrs)
        match = next((p for p in projects if p["name"].lower() == project_filter.lower()), None)
        if not match:
            print(f"{RED}Project '{project_filter}' not found.{RESET}")
            sys.exit(1)
        url += f"?project_id={match['id']}"

    workflows = api.req("GET", url, hdrs)

    if not workflows:
        print("No agents found.")
        return

    # Fetch projects for name lookup
    try:
        projects = api.req("GET", f"{server}/workspaces/{workspace_id}/projects", hdrs)
        proj_map = {str(p["id"]): p["name"] for p in projects}
    except Exception:
        proj_map = {}

    print(f"\n{BOLD}{'Agent':<35} {'Project':<20} {'Playbook':<25} {'Last run':<12} {'ID'}{RESET}")
    print("─" * 110)

    for wf in workflows:
        name        = wf.get("name", "")[:34]
        project     = proj_map.get(str(wf.get("project_id", "")), "—")[:19]
        slug        = (wf.get("playbook_slug") or "—")[:24]
        last_status = wf.get("last_run_status") or "—"
        wf_id       = str(wf.get("id", ""))

        status_color = GREEN if last_status == "succeeded" else RED if last_status == "failed" else GRAY
        print(f"  {name:<35} {project:<20} {slug:<25} {status_color}{last_status:<12}{RESET} {GRAY}{wf_id}{RESET}")

    print()


def cmd_test(args):
    server, workspace_id, api_key, token = _require_auth(args)
    hdrs = api.headers(workspace_id, token, "application/json", api_key)

    agent_names = args.agents  # list, or empty if --all
    run_all     = getattr(args, "all", False)

    # Get full workflow list
    workflows = api.req("GET", f"{server}/workflows", hdrs)

    if run_all:
        targets = [wf for wf in workflows if wf.get("playbook_slug")]
        if not targets:
            print("No playbook-based agents found.")
            return
    else:
        targets = []
        for name in agent_names:
            match = next((wf for wf in workflows if wf["name"].lower() == name.lower()), None)
            if not match:
                print(f"{RED}Agent '{name}' not found. Run 'conduct agents' to see available agents.{RESET}")
                sys.exit(1)
            if not match.get("playbook_slug"):
                print(f"{YELLOW}⚠ '{name}' has no playbook_slug — no built-in test payload. Skipping.{RESET}")
                continue
            targets.append(match)

    if not targets:
        print("Nothing to test.")
        return

    print(f"\n{BOLD}▶ conduct test — {len(targets)} agent(s){RESET}\n")

    results = []
    for wf in targets:
        name    = wf["name"]
        wf_id   = str(wf["id"])
        slug    = wf.get("playbook_slug", "")

        print(f"{CYAN}── {name}{RESET} {GRAY}({slug}){RESET}")

        # Fire test trigger
        try:
            run = api.req("POST", f"{server}/workflows/{wf_id}/trigger", hdrs, {})
        except SystemExit:
            results.append((name, False, None))
            print()
            continue

        run_id = run.get("run_id")
        print(f"  {GRAY}run: {run_id}{RESET}")

        # Stream or poll
        try:
            ok = _stream_run(server, wf_id, run_id, workspace_id, token, api_key)
        except Exception:
            ok = _poll_run(server, wf_id, run_id, hdrs)

        results.append((name, ok, run_id))
        print()

    # Summary table
    passed = sum(1 for _, ok, _ in results if ok)
    failed = len(results) - passed

    print(f"{BOLD}{'─' * 60}{RESET}")
    print(f"{BOLD}Results:{RESET}")
    for name, ok, run_id in results:
        icon = f"{GREEN}✓{RESET}" if ok else f"{RED}✗{RESET}"
        rid  = f"{GRAY}{run_id[:8]}…{RESET}" if run_id else ""
        print(f"  {icon}  {name:<40} {rid}")

    print()
    color = GREEN if failed == 0 else RED
    print(f"{BOLD}{color}{passed}/{len(results)} passed{RESET}\n")

    sys.exit(0 if failed == 0 else 1)


# ── Project commands ──────────────────────────────────────────────────────────

def _list_projects(server: str, workspace_id: str, hdrs: dict) -> list:
    return api.req("GET", f"{server}/workspaces/{workspace_id}/projects", hdrs)


def _resolve_project(server: str, workspace_id: str, hdrs: dict, name: str) -> dict:
    projects = _list_projects(server, workspace_id, hdrs)
    match = next((p for p in projects if p["name"].lower() == name.lower()), None)
    if not match:
        print(f"{RED}Project '{name}' not found. Run 'conduct projects' to see available projects.{RESET}")
        sys.exit(1)
    return match


def cmd_projects(args):
    server, workspace_id, api_key, token = _require_auth(args)
    hdrs     = api.headers(workspace_id, token, "application/json", api_key)
    projects = _list_projects(server, workspace_id, hdrs)

    if not projects:
        print("No projects found. Create one: conduct create project <name>")
        return

    print(f"\n{BOLD}{'Project':<35} {'Agents':>6}  {'ID'}{RESET}")
    print("─" * 70)
    for p in projects:
        agents = p.get("agent_count", 0)
        print(f"  {p['name']:<35} {agents:>6}  {GRAY}{p['id']}{RESET}")
    print()


def cmd_create(args):
    server, workspace_id, api_key, token = _require_auth(args)
    hdrs = api.headers(workspace_id, token, "application/json", api_key)

    if args.resource == "project":
        name = args.name.strip()
        result = api.req("POST", f"{server}/workspaces/{workspace_id}/projects", hdrs, {"name": name})
        print(f"{GREEN}✓ Project created:{RESET} {result['name']}  {GRAY}({result['id']}){RESET}")
    else:
        print(f"{RED}Unknown resource '{args.resource}'. Try: conduct create project <name>{RESET}")
        sys.exit(1)


# ── Playbook commands ─────────────────────────────────────────────────────────

def cmd_playbooks(args):
    server, workspace_id, api_key, token = _require_auth(args)
    hdrs = api.headers(workspace_id, token, "application/json", api_key)
    slug = getattr(args, "slug", None)

    if slug:
        pb = api.req("GET", f"{server}/workflows/playbooks/{slug}", hdrs)
        print(f"\n{BOLD}{pb['icon']}  {pb['name']}{RESET}")
        print(f"  {pb['description']}")
        tags = "  ".join(pb.get("tags", []))
        if tags:
            print(f"  {GRAY}{tags}{RESET}")
        inputs = pb.get("inputs", {})
        if inputs:
            print(f"\n{BOLD}  Inputs:{RESET}")
            for k, v in inputs.items():
                default = v.get("default", "")
                required = "" if default != "" else f" {RED}(required){RESET}"
                desc = v.get("description", "")
                print(f"    {CYAN}--input {k}=<value>{RESET}{required}  {GRAY}{desc}{RESET}")
        print()
    else:
        pbs = api.req("GET", f"{server}/workflows/playbooks", hdrs)
        if not pbs:
            print("No playbooks available.")
            return
        print(f"\n{BOLD}{'Playbook':<30} {'Slug':<30} {'Tags'}{RESET}")
        print("─" * 80)
        for pb in pbs:
            tags = ", ".join(pb.get("tags", []))[:25]
            icon = pb.get("icon", "")
            name = f"{icon} {pb['name']}"[:29]
            print(f"  {name:<30} {pb['slug']:<30} {GRAY}{tags}{RESET}")
        print(f"\n  Run {CYAN}conduct playbooks <slug>{RESET} for input details.\n")


# ── Install command ───────────────────────────────────────────────────────────

def cmd_install(args):
    server, workspace_id, api_key, token = _require_auth(args)
    hdrs = api.headers(workspace_id, token, "application/json", api_key)

    slug = args.slug

    # Fetch playbook to validate slug + get declared inputs
    pb = api.req("GET", f"{server}/workflows/playbooks/{slug}", hdrs)
    declared_inputs = pb.get("inputs", {})

    # Parse --input key=val pairs
    raw_inputs: dict = {}
    for pair in (args.input or []):
        if "=" not in pair:
            print(f"{RED}Bad --input format '{pair}'. Expected key=value.{RESET}")
            sys.exit(1)
        k, v = pair.split("=", 1)
        raw_inputs[k.strip()] = v.strip()

    # Check required inputs (no default and not supplied)
    missing = [
        k for k, v in declared_inputs.items()
        if v.get("default", "__MISSING__") == "__MISSING__" and k not in raw_inputs
    ]
    if missing:
        print(f"{RED}Missing required inputs: {', '.join(missing)}{RESET}")
        print(f"  Use: conduct install {slug} --input key=value ...")
        sys.exit(1)

    # Resolve project
    project_id = None
    if args.project:
        proj = _resolve_project(server, workspace_id, hdrs, args.project)
        project_id = proj["id"]

    # Agent name — default to playbook name
    agent_name = args.name or pb["name"]

    # Repo input — inject into inputs if playbook expects github_repo
    if args.repo:
        if "github_repo" in declared_inputs:
            raw_inputs.setdefault("github_repo", args.repo)
        if "repo" in declared_inputs:
            raw_inputs.setdefault("repo", args.repo)

    body: dict = {
        "name":     agent_name,
        "template": slug,
        "inputs":   raw_inputs,
        "graph":    {"nodes": [], "edges": []},
    }
    if project_id:
        body["project_id"] = project_id
    if args.repo:
        body["repo"] = args.repo

    print(f"\n{BOLD}Installing {pb['icon']} {pb['name']}…{RESET}")
    if project_id:
        print(f"  project:  {args.project}")
    print(f"  agent:    {agent_name}")
    if raw_inputs:
        for k, v in raw_inputs.items():
            masked = v if "token" not in k.lower() and "secret" not in k.lower() else "***"
            print(f"  {k}: {masked}")
    print()

    result = api.req("POST", f"{server}/workflows", hdrs, body)

    wf_id = result.get("id", "")
    print(f"{GREEN}✓ Agent installed:{RESET} {result['name']}  {GRAY}({wf_id}){RESET}")

    webhook_error = result.get("webhook_error")
    if webhook_error:
        print(f"{YELLOW}⚠ Webhook:{RESET} {webhook_error}")
    else:
        print(f"{GREEN}✓ Webhook registered{RESET}" if args.repo else "")

    print(f"\n  Run a test: {CYAN}conduct test \"{agent_name}\"{RESET}\n")


# ── Reset command ─────────────────────────────────────────────────────────────

def cmd_reset(args):
    server, workspace_id, api_key, token = _require_auth(args)
    hdrs = api.headers(workspace_id, token, "application/json", api_key)

    if args.resource == "project":
        proj = _resolve_project(server, workspace_id, hdrs, args.name)
        project_id = proj["id"]

        # Fetch all workflows in project
        workflows = api.req("GET", f"{server}/workflows?project_id={project_id}", hdrs)
        if not workflows:
            print(f"{YELLOW}Project '{args.name}' has no agents — nothing to reset.{RESET}")
            return

        print(f"\n{BOLD}Reset project '{args.name}' — {len(workflows)} agent(s) will be deleted:{RESET}")
        for wf in workflows:
            print(f"  {GRAY}· {wf['name']}{RESET}")

        if not args.yes:
            confirm = input(f"\n{YELLOW}Type 'yes' to confirm: {RESET}").strip().lower()
            if confirm != "yes":
                print("Cancelled.")
                return

        deleted = failed = 0
        for wf in workflows:
            try:
                api.req("DELETE", f"{server}/workflows/{wf['id']}", hdrs)
                print(f"  {GREEN}✓ deleted:{RESET} {wf['name']}")
                deleted += 1
            except SystemExit:
                print(f"  {RED}✗ failed:{RESET} {wf['name']}")
                failed += 1

        print(f"\n{BOLD}{GREEN}{deleted} deleted{RESET}", end="")
        if failed:
            print(f"  {RED}{failed} failed{RESET}", end="")
        print()
    else:
        print(f"{RED}Unknown resource '{args.resource}'. Try: conduct reset project <name>{RESET}")
        sys.exit(1)


# ── Install-all command ───────────────────────────────────────────────────────

# All known playbook slugs in install order
_ALL_SLUGS = [
    "autopilot_quick",
    "autopilot_full",
    "autopilot_approved",
    "pr_reviewer",
    "ci_notify",
    "incident_responder",
    "dependency_updater",
    "release_notes",
    "issue_triage",
    "copilot_reviewer",
    "security_scanner",
    "security_patch_updater",
]


def cmd_install_all(args):
    server, workspace_id, api_key, token = _require_auth(args)
    hdrs = api.headers(workspace_id, token, "application/json", api_key)

    slugs = _ALL_SLUGS

    print(f"\n{BOLD}▶ conduct install-all — {len(slugs)} playbooks → project '{args.project}'{RESET}")
    if args.repo:
        print(f"  repo: {args.repo}")
    print()

    installed = []
    failed    = []

    for slug in slugs:
        # Build a minimal args-like namespace for cmd_install
        class _A:
            pass
        a          = _A()
        a.slug     = slug
        a.project  = args.project
        a.repo     = args.repo
        a.name     = None
        a.input    = args.input or []

        # Patch server/workspace/auth into the namespace so _require_auth works
        a.server    = server
        a.workspace = workspace_id
        a.api_key   = api_key
        a.token     = token

        try:
            cmd_install(a)
            installed.append(slug)
        except SystemExit:
            failed.append(slug)

    # Summary
    print(f"\n{BOLD}{'─' * 50}{RESET}")
    color = GREEN if not failed else RED
    print(f"{BOLD}{color}{len(installed)}/{len(slugs)} installed{RESET}\n")

    for s in installed:
        print(f"  {GREEN}✓{RESET}  {s}")
    for s in failed:
        print(f"  {RED}✗{RESET}  {s}")
    print()

    if failed:
        print(f"{RED}Some installs failed. Fix the issue, run 'conduct reset project {args.project}', then retry.{RESET}\n")
        sys.exit(1)


def _build_state(issue: dict, repo_full_name: str) -> dict:
    owner, repo = repo_full_name.split("/", 1)
    trigger = {
        "repo_owner":     owner,
        "repo_name":      repo,
        "repo_full_name": repo_full_name,
        "issue_number":   issue["number"],
        "title":          issue["title"],
        "body":           issue.get("body") or "",
        "url":            issue["url"],
        "author":         issue["author"],
        "labels":         issue["labels"],
        "label_added":    issue["labels"][0] if issue["labels"] else "",
        "default_branch": "main",
        "clone_url":      issue["clone_url"],
    }
    return {"github_issue": trigger, "_trigger": trigger}


def cmd_run(args):
    path = Path(args.yaml)
    if not path.exists():
        print(f"ERROR: file not found: {path}")
        sys.exit(1)

    raw_yaml     = path.read_text()
    cfg          = yaml.safe_load(raw_yaml)
    name         = cfg.get("name", path.stem)
    workflow_id  = cfg.get("id")
    server, workspace_id, api_key, token = _require_auth(args)
    on_block     = cfg.get("on") or {}
    trigger_type = next(iter(on_block), None)
    trigger_cfg  = on_block.get(trigger_type, {})

    json_h = api.headers(workspace_id, token, "application/json", api_key)
    yaml_h = api.headers(workspace_id, token, "application/x-yaml", api_key)

    print(f"\n{BOLD}▶ conduct run — {name}{RESET}")
    print(f"  server: {server}\n")

    if not workflow_id:
        workflow_id = api.find_or_create_workflow(server, name, json_h)
    print(f"  workflow: {workflow_id}")
    print(f"  pushing YAML… ", end="", flush=True)
    api.req_text("PUT", f"{server}/workflows/{workflow_id}/yaml", yaml_h, raw_yaml)
    print(f"{GREEN}ok{RESET}\n")

    if trigger_type == "github_issue_labeled":
        repo  = trigger_cfg.get("repo_allowlist", "")
        label = trigger_cfg.get("label", "")

        print(f"  Fetching issues from {repo} with label '{label}'…")
        qs = urllib.parse.urlencode({"repo": repo, "label": label})
        issues = api.req("GET", f"{server}/credentials/github/issues?{qs}", json_h)

        if not issues:
            print(f"  No open issues found with label '{label}'.")
            return

        print(f"  Found {len(issues)} issue(s)\n")

        passed = failed = 0
        for issue in issues:
            print(f"{CYAN}  ── Issue #{issue['number']}: {issue['title']}{RESET}")
            state = _build_state(issue, repo)

            max_turns = None
            try:
                pf = api.req("POST", f"{server}/workflows/{workflow_id}/preflight", json_h, {
                    "issue_title": issue["title"],
                    "issue_body":  issue.get("body") or "",
                })
                suggested = pf.get("suggested_max_turns", 20)
                if suggested > 20:
                    print(f"{GRAY}  ⚠ estimated {suggested} turns — bumping max_turns{RESET}")
                    max_turns = suggested
            except Exception:
                pass

            payload = {"triggered_by": f"cli:issue#{issue['number']}", "initial_state": state}
            if max_turns:
                payload["max_turns"] = max_turns
            run = api.req("POST", f"{server}/workflows/{workflow_id}/runs", json_h, payload)
            ok  = _stream_run(server, workflow_id, run["id"], workspace_id, token, api_key)
            passed += ok
            failed += not ok
            print()

        print(f"{BOLD}  Summary: {passed} passed, {failed} failed{RESET}\n")

    else:
        run = api.req("POST", f"{server}/workflows/{workflow_id}/runs", json_h, {
            "triggered_by": "cli",
            "initial_state": {},
        })
        _stream_run(server, workflow_id, run["id"], workspace_id, token)


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog="conduct",
        description="Conduct AI — agent CLI",
    )
    # Global overrides (optional — config file is preferred)
    parser.add_argument("--server",    help="API URL (default: from ~/.conduct/config.json)")
    parser.add_argument("--api-key",   dest="api_key", help="CLI API key")
    parser.add_argument("--token",     help="Bearer token (Clerk)")
    parser.add_argument("--workspace", help="Workspace ID")

    sub = parser.add_subparsers(dest="command")

    # conduct login
    login_p = sub.add_parser("login", help="Save connection config (~/.conduct/config.json)")
    login_p.add_argument("--server",    help="API base URL e.g. https://api.conductai.ai")
    login_p.add_argument("--api-key",   dest="api_key", help="CLI API key (set CLI_API_KEY on server)")
    login_p.add_argument("--workspace", help="Workspace ID")
    login_p.add_argument("--token",     help="Bearer token (alternative to API key)")

    # conduct agents
    agents_p = sub.add_parser("agents", help="List all agents")
    agents_p.add_argument("--project", help="Filter by project name")

    # conduct test
    test_p = sub.add_parser("test", help="Fire test trigger on one or more agents")
    test_p.add_argument("agents", nargs="*", metavar="agent_name", help="Agent name(s) to test")
    test_p.add_argument("--all", action="store_true", help="Test all playbook-based agents")

    # conduct projects
    sub.add_parser("projects", help="List all projects in the workspace")

    # conduct create project <name>
    create_p = sub.add_parser("create", help="Create a resource (project, ...)")
    create_p.add_argument("resource", choices=["project"], help="Resource type")
    create_p.add_argument("name",     help="Name of the resource to create")

    # conduct playbooks [slug]
    pb_p = sub.add_parser("playbooks", help="List available playbooks or show detail for one")
    pb_p.add_argument("slug", nargs="?", help="Playbook slug for detail view")

    # conduct install <slug>
    install_p = sub.add_parser("install", help="Install an agent from a playbook")
    install_p.add_argument("slug",             help="Playbook slug (from 'conduct playbooks')")
    install_p.add_argument("--project",        help="Project name to install into")
    install_p.add_argument("--name",           help="Override agent name")
    install_p.add_argument("--repo",           help="GitHub repo (owner/repo) for webhook-based playbooks")
    install_p.add_argument("--input", action="append", metavar="key=value",
                           help="Playbook input value (repeatable, e.g. --input github_token=xxx)")

    # conduct reset project <name>
    reset_p = sub.add_parser("reset", help="Delete all agents in a project (clean slate)")
    reset_p.add_argument("resource", choices=["project"], help="Resource type")
    reset_p.add_argument("name",     help="Project name to reset")
    reset_p.add_argument("--yes",    action="store_true", help="Skip confirmation prompt")

    # conduct install-all
    ia_p = sub.add_parser("install-all", help="Install all playbooks into a project")
    ia_p.add_argument("--project",  required=True, help="Project name")
    ia_p.add_argument("--repo",     help="GitHub repo (owner/repo)")
    ia_p.add_argument("--input",    action="append", metavar="key=value",
                      help="Input value applied to all playbooks (repeatable)")

    # conduct run (existing)
    run_p = sub.add_parser("run", help="Run a workflow from a YAML file")
    run_p.add_argument("yaml", help="Path to workflow YAML")

    args = parser.parse_args()

    if args.command == "login":
        cmd_login(args)
    elif args.command == "agents":
        cmd_agents(args)
    elif args.command == "projects":
        cmd_projects(args)
    elif args.command == "create":
        cmd_create(args)
    elif args.command == "playbooks":
        cmd_playbooks(args)
    elif args.command == "install":
        cmd_install(args)
    elif args.command == "reset":
        cmd_reset(args)
    elif args.command == "install-all":
        cmd_install_all(args)
    elif args.command == "test":
        if not args.agents and not args.all:
            test_p.print_help()
            sys.exit(1)
        cmd_test(args)
    elif args.command == "run":
        cmd_run(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
