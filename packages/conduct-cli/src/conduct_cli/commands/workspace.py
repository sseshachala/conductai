"""Agents, environments, credentials, and project commands."""
from __future__ import annotations

import sys

from conduct_cli import api
from conduct_cli.commands.shared import (
    BOLD,
    GRAY,
    GREEN,
    RED,
    RESET,
    YELLOW,
    _require_auth,
)


def cmd_agents(args):
    server, workspace_id, token = _require_auth(args)
    hdrs = api.headers(workspace_id, token, "application/json")

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


# ── Environment helpers ───────────────────────────────────────────────────────

def _list_environments(server: str, workspace_id: str, hdrs: dict) -> list:
    return api.req("GET", f"{server}/environments", hdrs)


def _resolve_environment(server: str, workspace_id: str, hdrs: dict, name: str) -> dict:
    envs = _list_environments(server, workspace_id, hdrs)
    match = next((e for e in envs if e["name"].lower() == name.lower()), None)
    if not match:
        print(f"{RED}Environment '{name}' not found. Run 'conduct environments' to list environments.{RESET}")
        sys.exit(1)
    return match


# ── Environment commands ──────────────────────────────────────────────────────

def cmd_environments(args):
    server, workspace_id, token = _require_auth(args)
    hdrs = api.headers(workspace_id, token, "application/json")
    envs = _list_environments(server, workspace_id, hdrs)

    if not envs:
        print("No environments found. Create one: conduct create environment <name>")
        return

    print(f"\n{BOLD}{'Environment':<30} {'ID'}{RESET}")
    print("─" * 70)
    for e in envs:
        print(f"  {e['name']:<30} {GRAY}{e['id']}{RESET}")
    print()


def cmd_credentials(args):
    server, workspace_id, token = _require_auth(args)
    hdrs = api.headers(workspace_id, token, "application/json")
    env = _resolve_environment(server, workspace_id, hdrs, args.environment)

    rows = api.req("GET", f"{server}/credentials/env-vars/{env['id']}", hdrs)

    if not rows:
        print(f"No credentials in environment '{args.environment}'.")
        print(f"  Add one: conduct set credential --environment \"{args.environment}\" --key GITHUB_TOKEN --value <token>")
        return

    print(f"\n{BOLD}Credentials — {args.environment}{RESET}\n")
    print(f"{BOLD}{'Key':<30} {'Value'}{RESET}")
    print("─" * 55)
    for row in rows:
        key = row["key"]
        val = row["value"]
        masked = val[:4] + "***" if val and len(val) > 4 else "***"
        print(f"  {key:<30} {GRAY}{masked}{RESET}")
    print()


def _do_set_credential(server, workspace_id, token, env_name, key, value):
    hdrs = api.headers(workspace_id, token, "application/json")
    env = _resolve_environment(server, workspace_id, hdrs, env_name)

    existing = api.req("GET", f"{server}/credentials/env-vars/{env['id']}", hdrs)
    merged = [{"key": r["key"], "value": r["value"]} for r in existing if r["key"] != key]
    merged.append({"key": key, "value": value})

    api.req("PUT", f"{server}/credentials/env-vars/{env['id']}", hdrs, merged)
    masked = value[:4] + "***" if len(value) > 4 else "***"
    print(f"{GREEN}✓ {key}{RESET} set in environment '{env_name}'  {GRAY}({masked}){RESET}")


def _do_delete_credential(server, workspace_id, token, env_name, key, yes):
    hdrs = api.headers(workspace_id, token, "application/json")
    env = _resolve_environment(server, workspace_id, hdrs, env_name)

    existing = api.req("GET", f"{server}/credentials/env-vars/{env['id']}", hdrs)
    filtered = [r for r in existing if r["key"] != key]

    if len(filtered) == len(existing):
        print(f"{YELLOW}Key '{key}' not found in environment '{env_name}'.{RESET}")
        sys.exit(1)

    if not yes:
        confirm = input(f"{YELLOW}Delete '{key}' from environment '{env_name}'? Type 'yes' to confirm: {RESET}").strip().lower()
        if confirm != "yes":
            print("Cancelled.")
            return

    api.req("PUT", f"{server}/credentials/env-vars/{env['id']}", hdrs, filtered)
    print(f"{GREEN}✓ {key}{RESET} removed from environment '{env_name}'")


def cmd_set(args):
    if args.set_command == "credential":
        server, workspace_id, token = _require_auth(args)
        _do_set_credential(server, workspace_id, token,
                           args.environment, args.key, args.value)
    elif args.set_command == "environment":
        server, workspace_id, token = _require_auth(args)
        hdrs = api.headers(workspace_id, token, "application/json")

        workflows = api.req("GET", f"{server}/workflows", hdrs)
        wf = next((w for w in workflows if w["name"].lower() == args.agent.lower()), None)
        if not wf:
            print(f"{RED}Agent '{args.agent}' not found. Run 'conduct agents' to list agents.{RESET}")
            sys.exit(1)

        env = _resolve_environment(server, workspace_id, hdrs, args.environment)
        api.req("PATCH", f"{server}/workflows/{wf['id']}/environment", hdrs, {"environment_id": env["id"]})
        print(f"{GREEN}✓ Environment '{args.environment}' assigned to agent '{args.agent}'{RESET}")
    else:
        print(f"Usage: conduct set [credential|environment] ...")
        sys.exit(1)


# ── Project commands ──────────────────────────────────────────────────────────

def _list_projects(server: str, workspace_id: str, hdrs: dict) -> list:
    return api.req("GET", f"{server}/workspaces/{workspace_id}/projects", hdrs)


def _resolve_project(server: str, workspace_id: str, hdrs: dict, name: str) -> dict:
    projects = _list_projects(server, workspace_id, hdrs)
    match = next((p for p in projects if p["name"].lower() == name.lower()), None)
    if not match:
        print(f"{YELLOW}Project '{name}' not found — creating it…{RESET}")
        match = api.req("POST", f"{server}/workspaces/{workspace_id}/projects", hdrs, {"name": name})
        print(f"  {GREEN}✓ Project created:{RESET} {match['name']}  {GRAY}({match['id']}){RESET}")
    return match


def cmd_projects(args):
    server, workspace_id, token = _require_auth(args)
    hdrs     = api.headers(workspace_id, token, "application/json")
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
    server, workspace_id, token = _require_auth(args)
    hdrs = api.headers(workspace_id, token, "application/json")
    parts = args.create_args

    if parts and parts[0] == "environment":
        name = " ".join(parts[1:]).strip()
        if not name:
            print(f"{RED}Usage: conduct create environment <name>{RESET}")
            sys.exit(1)
        result = api.req("POST", f"{server}/environments", hdrs, {"name": name})
        print(f"{GREEN}✓ Environment created:{RESET} {result['name']}  {GRAY}({result['id']}){RESET}")
    else:
        # conduct create [project] <name> — "project" keyword is optional
        name = " ".join(parts[1:] if parts and parts[0] == "project" else parts).strip()
        if not name:
            print(f"{RED}Usage: conduct create [environment|project] <name>{RESET}")
            sys.exit(1)
        result = api.req("POST", f"{server}/workspaces/{workspace_id}/projects", hdrs, {"name": name})
        print(f"{GREEN}✓ Project created:{RESET} {result['name']}  {GRAY}({result['id']}){RESET}")


def cmd_delete(args):
    server, workspace_id, token = _require_auth(args)
    hdrs = api.headers(workspace_id, token, "application/json")
    parts = args.delete_args

    if parts and parts[0] == "environment":
        name = " ".join(parts[1:]).strip()
        if not name:
            print(f"{RED}Usage: conduct delete environment <name>{RESET}")
            sys.exit(1)
        env = _resolve_environment(server, workspace_id, hdrs, name)
        if not args.yes:
            confirm = input(f"{YELLOW}Delete environment '{env['name']}'? Type 'yes' to confirm: {RESET}").strip().lower()
            if confirm != "yes":
                print("Cancelled.")
                return
        api.req("DELETE", f"{server}/environments/{env['id']}", hdrs)
        print(f"{GREEN}✓ Environment '{env['name']}' deleted.{RESET}")

    elif parts and parts[0] == "credential":
        env_name = getattr(args, "environment", None)
        key      = getattr(args, "key", None)
        if not env_name or not key:
            print(f"{RED}Usage: conduct delete credential --environment <name> --key <KEY>{RESET}")
            sys.exit(1)
        _do_delete_credential(server, workspace_id, token, env_name, key, args.yes)

    else:
        # conduct delete [project] <name> [--yes] [--purge]
        name = " ".join(parts[1:] if parts and parts[0] == "project" else parts).strip()
        if not name:
            print(f"{RED}Usage: conduct delete [environment|project|credential] <name>{RESET}")
            sys.exit(1)
        # ponytail: strict lookup — never create-on-delete (matches _resolve_environment semantics)
        projects = _list_projects(server, workspace_id, hdrs)
        proj = next((p for p in projects if p["name"].lower() == name.lower()), None)
        if not proj:
            print(f"{RED}Project '{name}' not found. Run 'conduct projects' to list projects.{RESET}")
            sys.exit(1)
        purge = getattr(args, "purge", False)
        if purge:
            print(f"{RED}{BOLD}⚠ PURGE mode — this will permanently delete ALL data for '{proj['name']}'{RESET}")
            print(f"{RED}  · All runs, events, and workflow versions{RESET}")
            print(f"{RED}  · Analytics and audit logs{RESET}")
            print(f"{RED}  · API keys and environments{RESET}")
            print(f"{RED}  This cannot be undone.{RESET}\n")
            confirm = input(f"{YELLOW}Type the project name to confirm: {RESET}").strip()
            if confirm != proj["name"]:
                print("Cancelled — name did not match.")
                return
        elif not args.yes:
            confirm = input(f"{YELLOW}Delete project '{proj['name']}' and all its agents? Type 'yes' to confirm: {RESET}").strip().lower()
            if confirm != "yes":
                print("Cancelled.")
                return
        url = f"{server}/workspaces/{workspace_id}/projects/{proj['id']}"
        if purge:
            url += "?purge=true"
        api.req("DELETE", url, hdrs)
        suffix = " (purged)" if purge else ""
        print(f"{GREEN}✓ Project '{proj['name']}' deleted{suffix}.{RESET}")
