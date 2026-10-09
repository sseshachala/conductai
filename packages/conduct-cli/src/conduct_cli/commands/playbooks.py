"""Playbook listing, install, reset, and install-all commands."""
from __future__ import annotations

import sys

from conduct_cli import api
from conduct_cli.commands.shared import (
    BOLD,
    CYAN,
    GRAY,
    GREEN,
    RED,
    RESET,
    YELLOW,
    _require_auth,
)
from conduct_cli.commands.workspace import _resolve_project


# ── Playbook commands ─────────────────────────────────────────────────────────

def cmd_playbooks(args):
    server, workspace_id, token = _require_auth(args)
    hdrs = api.headers(workspace_id, token, "application/json")
    slug = getattr(args, "slug", None)

    if slug:
        pb = api.req("GET", f"{server}/workflows/playbooks/{slug}", hdrs)
        print(f"\n{BOLD}{pb['icon']}  {pb['name']}{RESET}")
        print(f"  {pb['description']}")
        tags = "  ".join(pb.get("tags", []))
        if tags:
            print(f"  {GRAY}{tags}{RESET}")
        if pb.get("github_webhook"):
            events = ", ".join(pb.get("github_events", []))
            print(f"  {GRAY}Trigger: GitHub webhook ({events}){RESET}")
            print(f"  {GRAY}Requires: --repo owner/repo{RESET}")
        elif pb.get("requires_repo"):
            print(f"  {GRAY}Trigger: inbound webhook — POST your payload to the webhook URL{RESET}")
            print(f"  {GRAY}Requires: --repo owner/repo (agent clones this repo at runtime){RESET}")
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
    server, workspace_id, token = _require_auth(args)
    hdrs = api.headers(workspace_id, token, "application/json")

    slug = args.slug

    # Fetch playbook to validate slug + get declared inputs
    pb = api.req("GET", f"{server}/workflows/playbooks/{slug}", hdrs)
    declared_inputs = pb.get("inputs", {})

    # Require --repo for all playbooks
    if not args.repo and pb.get("requires_repo"):
        if pb.get("github_webhook"):
            events = ", ".join(pb.get("github_events", []))
            print(f"{RED}Error: --repo is required for this agent.{RESET}")
            print(f"  It listens for GitHub {events} events — Conduct must register a webhook on the target repo.")
        else:
            print(f"{RED}Error: --repo is required for this agent.{RESET}")
            print(f"  It clones and operates on a GitHub repository at runtime.")
        print(f"\n  Usage: conduct install {slug} --repo owner/repo\n")
        sys.exit(1)

    # Parse --input key=val pairs
    raw_inputs: dict = {}
    for pair in (args.input or []):
        if "=" not in pair:
            print(f"{RED}Bad --input format '{pair}'. Expected key=value.{RESET}")
            sys.exit(1)
        k, v = pair.split("=", 1)
        raw_inputs[k.strip()] = v.strip()

    # --repo satisfies repo/github_repo inputs — must run before the required-input check.
    if args.repo:
        if "github_repo" in declared_inputs:
            raw_inputs.setdefault("github_repo", args.repo)
        if "repo" in declared_inputs:
            raw_inputs.setdefault("repo", args.repo)

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

    # Agent name — explicit --name wins; otherwise auto-suffix with 4-char ID
    # e.g. "Security Autopilot Fix [A4B2]" so multiple installs are distinguishable
    import random, string
    _base = _FRIENDLY_NAMES.get(slug) or pb["name"]
    _uid  = "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
    agent_name = args.name or f"{_base} [{_uid}]"

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
    elif args.repo:
        if pb.get("github_webhook"):
            print(f"{GREEN}✓ GitHub webhook registered{RESET} on {args.repo}")
        else:
            print(f"{GREEN}✓ Target repo stored:{RESET} {args.repo}")

    print(f"\n  Run a test: {CYAN}conduct test \"{agent_name}\"{RESET}\n")


# ── Reset command ─────────────────────────────────────────────────────────────

def cmd_reset(args):
    server, workspace_id, token = _require_auth(args)
    hdrs = api.headers(workspace_id, token, "application/json")
    proj = _resolve_project(server, workspace_id, hdrs, args.name)
    project_id = proj["id"]

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


# ── Install-all command ───────────────────────────────────────────────────────

# All known playbook slugs in install order
_ALL_SLUGS = [
    "autopilot_full",
    "autopilot_approved",
    "incident_responder",
    "dependency_updater",
    "postmortem_drafter",
    "terraform_reviewer",
    "security_patch_updater",
]
# Not here: autopilot_quick + factory (archived, #2379); thirdparty_autopilot_fix
# needs per-issue inputs (upstream_owner/upstream_repo/issue_number).

_FRIENDLY_NAMES = {
    "autopilot_full":           "Autopilot Full",
    "autopilot_approved":       "Autopilot + Approval",
    "incident_responder":       "Incident Responder",
    "dependency_updater":       "Dependency Updater",
    "security_patch_updater":   "Security Patch Updater",
    "postmortem_drafter":       "Postmortem Drafter",
    "terraform_reviewer":       "Terraform Plan Reviewer",
    "thirdparty_autopilot_fix": "Third-Party Autopilot Fix",
}


def cmd_install_all(args):
    server, workspace_id, token = _require_auth(args)

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
