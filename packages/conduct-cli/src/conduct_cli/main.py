from __future__ import annotations
import argparse
import importlib.metadata
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import yaml

from conduct_cli import deployment
from conduct_cli import guard as _guard
from conduct_cli.commands.audit import cmd_audit, register_audit
from conduct_cli.commands.auth import (
    cmd_login,
    cmd_sync,
)
from conduct_cli.commands.config_io import (
    cmd_export_gateway_config,
    cmd_import_cedar,
    cmd_import_gateway_config,
    cmd_skill,
)
from conduct_cli.commands.diagnostics import (
    cmd_memory,
    cmd_test_guard,
)
from conduct_cli.commands.mcp_setup import (
    cmd_mcp_install,
)
from conduct_cli.commands.playbooks import (
    cmd_install,
    cmd_install_all,
    cmd_playbooks,
    cmd_reset,
)
from conduct_cli.commands.run import (
    cmd_run,
    cmd_test,
)
from conduct_cli.commands.session_report import (
    cmd_session_report,
)
from conduct_cli.commands.sessions import (
    cmd_sessions,
)
from conduct_cli.commands.shared import (
    BOLD,
    CYAN,
    GRAY,
    GREEN,
    RED,
    RESET,
    YELLOW,
    _load_config,
)
from conduct_cli.commands.workspace import (
    cmd_agents,
    cmd_create,
    cmd_credentials,
    cmd_delete,
    cmd_environments,
    cmd_projects,
    cmd_set,
)
from conduct_cli.commands.workspace_switch import (
    cmd_switch,
    cmd_whoami,
)

_UPDATE_CACHE = Path.home() / ".conduct" / "update_check.json"
_UPDATE_TTL   = 86400  # check PyPI at most once per 24 hours


def _auto_update() -> None:
    """Check PyPI for a newer conduct-cli version and upgrade + re-exec if found."""
    # Skip inside CI or if explicitly disabled
    if os.environ.get("CONDUCT_NO_AUTOUPDATE") or os.environ.get("CI"):
        return
    if any(arg == "--server" or arg.startswith("--server=") for arg in sys.argv) or deployment.api_url(_load_config()) != deployment.SAAS_API:
        return

    now = time.time()

    # Respect the 24-hour cache
    if _UPDATE_CACHE.exists():
        try:
            cached = json.loads(_UPDATE_CACHE.read_text())
            if now - cached.get("ts", 0) < _UPDATE_TTL:
                return
        except Exception:
            pass

    # Get installed version
    try:
        current = importlib.metadata.version("conduct-cli")
    except Exception:
        return

    # Fetch latest from PyPI (short timeout — never block the user)
    try:
        req = urllib.request.Request(
            "https://pypi.org/pypi/conduct-cli/json",
            headers={"Accept": "application/json", "User-Agent": f"conduct-cli/{current}"},
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            latest = json.loads(resp.read())["info"]["version"]
    except Exception:
        return

    # Save check timestamp regardless of result
    try:
        _UPDATE_CACHE.parent.mkdir(parents=True, exist_ok=True)
        _UPDATE_CACHE.write_text(json.dumps({"ts": now, "latest": latest, "current": current}))
    except Exception:
        pass

    if latest == current:
        return

    print(f"{YELLOW}conduct-cli {current} → {latest} available. Updating…{RESET}")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--upgrade", "conduct-cli", "-q"],
        capture_output=True,
    )
    if result.returncode == 0:
        print(f"{GREEN}✓ Updated to {latest}.{RESET}\n")
        # Re-exec so the new version handles this command
        os.execv(sys.executable, [sys.executable, "-m", "conduct_cli.main"] + sys.argv[1:])
    else:
        print(f"{YELLOW}Auto-update failed — run: pip install --upgrade conduct-cli{RESET}\n")


# ── Entry point ───────────────────────────────────────────────────────────────

_GUARD_CONFIG = Path.home() / ".conduct" / "config.json"
_GUARD_SKIP   = Path.home() / ".conduct" / ".setup_skip"


def _check_guard_setup(command: str) -> None:
    """On first run after install, prompt user to run conduct guard sync."""
    # Skip if: already set up, user said skip, or running guard sync/login itself
    if command in ("guard", "login", "whoami", "version"):
        return
    if _GUARD_CONFIG.exists() or _GUARD_SKIP.exists():
        return
    print(
        f"\n{YELLOW}{BOLD}⚡ Conduct Guard is not set up on this machine.{RESET}\n"
        f"   Run {BOLD}conduct guard sync{RESET} to register policy hooks and MCP servers.\n"
        f"   (This takes ~5 seconds and only needs to happen once per machine.)\n"
        f"   To skip this reminder: {BOLD}conduct guard skip-setup{RESET}\n"
    )


def main():
    _auto_update()

    # Auto-heal ~/.conduct/env for the 0.14.9 gateway URL migration. Silent
    # when already migrated or user has a custom URL — never blocks the CLI.
    try:
        from conduct_cli.guard import _migrate_proxy_env_if_stale
        if deployment.api_url(_load_config()) == deployment.SAAS_API and _migrate_proxy_env_if_stale():
            print("conduct: migrated ~/.conduct/env to gateway.conductai.ai (0.14.9). Re-source your shell or open a new terminal.")
    except Exception:
        pass

    parser = argparse.ArgumentParser(
        prog="conduct",
        description="Conduct AI — agent CLI",
    )
    # Global overrides (optional — config file is preferred)
    parser.add_argument("--server",    help="API URL (default: from ~/.conduct/config.json)")
    parser.add_argument("--token",     help=argparse.SUPPRESS)
    parser.add_argument("--workspace", help="Workspace ID")

    sub = parser.add_subparsers(dest="command")

    # conduct login
    login_p = sub.add_parser("login", help="Authenticate with Conduct (opens browser)")
    login_p.add_argument("--server", help="API base URL (default: https://api.conductai.ai)")
    login_p.add_argument("--web-url", help="Console origin for browser login (required for a new custom server)")
    login_p.add_argument("--gateway-url", help="Optional Gateway base URL including /gateway/v1")
    login_p.add_argument("--mcp-url", help="Optional separate MCP URL (default: API origin plus /mcp)")
    login_p.add_argument("--no-sync", action="store_true", help="Authenticate without installing or changing tool hooks")
    login_p.add_argument("--token",  help="Paste an agent token directly instead of opening a browser")

    # conduct agents
    agents_p = sub.add_parser("agents", help="List all agents")
    agents_p.add_argument("--project", help="Filter by project name")

    # conduct test
    test_p = sub.add_parser("test", help="Fire test trigger on one or more agents")
    test_p.add_argument("agents", nargs="*", metavar="agent_name", help="Agent name(s) to test")
    test_p.add_argument("--all",      action="store_true", help="Test all playbook-based agents")
    test_p.add_argument("--parallel", action="store_true", help="Fire all triggers at once, poll concurrently (faster for many agents)")
    test_p.add_argument("--project",  metavar="name",       help="Limit to agents in this project")
    test_p.add_argument("--repo",     metavar="owner/repo", help="Override repo in test payload (e.g. sseshachala/conductai-testbed-node)")
    test_p.add_argument("--pr",       metavar="number",     help="Inject a real PR number into the test payload (e.g. 246)")

    # conduct environments
    sub.add_parser("environments", help="List all environments in the workspace")

    # conduct credentials --environment <name>
    creds_p = sub.add_parser("credentials", help="List credentials in an environment")
    creds_p.add_argument("--environment", required=True, metavar="name", help="Environment name")

    # conduct set credential|environment
    set_p = sub.add_parser("set", help="Set a credential or assign an environment to an agent")
    set_sub = set_p.add_subparsers(dest="set_command")

    set_cred_p = set_sub.add_parser("credential", help="Set a credential in an environment")
    set_cred_p.add_argument("--environment", required=True, metavar="name", help="Environment name")
    set_cred_p.add_argument("--key",         required=True, metavar="KEY",  help="Env var name (e.g. GITHUB_TOKEN)")
    set_cred_p.add_argument("--value",       required=True, metavar="VALUE", help="Credential value")

    set_env_p = set_sub.add_parser("environment", help="Assign an environment to an agent")
    set_env_p.add_argument("--agent",       required=True, metavar="name", help="Agent name (e.g. 'PR Reviewer')")
    set_env_p.add_argument("--environment", required=True, metavar="name", help="Environment name")

    # conduct projects
    sub.add_parser("projects", help="List all projects in the workspace")

    # conduct create [environment|project] <name>
    create_p = sub.add_parser("create", help="Create a project or environment")
    create_p.add_argument("create_args", nargs="+", metavar="[environment|project] name",
                          help="Type (optional) and name — e.g. 'environment Production' or 'MyProject'")

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

    # conduct delete [environment|project|credential] <name>
    delete_p = sub.add_parser("delete", help="Delete a project, environment, or credential")
    delete_p.add_argument("delete_args", nargs="+", metavar="[environment|project|credential] name",
                          help="Type (optional) and name, e.g. 'environment Production' or 'MyProject'")
    delete_p.add_argument("--environment", metavar="name", help="Environment name (for 'delete credential')")
    delete_p.add_argument("--key",         metavar="KEY",  help="Credential key (for 'delete credential')")
    delete_p.add_argument("--yes",   action="store_true", help="Skip confirmation prompt")
    delete_p.add_argument("--purge", action="store_true", help="Also erase analytics, audit logs, API keys, and environments (irreversible)")

    # conduct reset <name>
    reset_p = sub.add_parser("reset", help="Delete all agents in a project (clean slate)")
    reset_p.add_argument("name",  help="Project name")
    reset_p.add_argument("--yes", action="store_true", help="Skip confirmation prompt")

    # conduct install-all
    ia_p = sub.add_parser("install-all", help="Install all playbooks into a project")
    ia_p.add_argument("--project",  help="Project name (uses default project if omitted)")
    ia_p.add_argument("--repo",     help="GitHub repo (owner/repo)")
    ia_p.add_argument("--input",    action="append", metavar="key=value",
                      help="Input value applied to all playbooks (repeatable)")

    # conduct run (existing)
    run_p = sub.add_parser("run", help="Run an installed agent by name")
    run_p.add_argument("agent",       help="Agent name (e.g. 'security_autopilot_fix')")
    run_p.add_argument("--project",   metavar="name",  help="Narrow to a specific project")
    run_p.add_argument("--input",     action="append", metavar="key=value", help="Runtime input (repeatable)")
    run_p.add_argument("--max-turns", dest="max_turns", type=int, metavar="N", help="Max agentic turns (default: auto)")
    run_p.add_argument("--lens",      dest="lens", action="store_true",
                       help="Attach the run to a fresh Lens session; prints /lens/<id> URL on success (#1515 P2)")

    # conduct switch [workspace]
    switch_p = sub.add_parser("switch", help="Switch active workspace (or list workspaces)")
    switch_p.add_argument("workspace", nargs="?", metavar="name_or_id",
                          help="Workspace name or UUID prefix to switch to (omit to list)")

    # conduct token show
    sub.add_parser("token", help="Show your agent token (masked by default)")

    # conduct whoami
    sub.add_parser("whoami", help="Show current workspace, server, agent token, and Guard/Booster status")

    # conduct guard
    guard_p, _guard_sub = _guard.register_guard_parser(sub)

    # conduct mcp
    sessions_p = sub.add_parser("sessions", help="Show active Claude Code / Codex sessions")
    sessions_p.add_argument("--watch", action="store_true", help="Refresh every 5s (table view)")
    sessions_p.add_argument("--tui",   action="store_true", help="Full-screen TUI with live panels")

    mcp_p = sub.add_parser("mcp", help="Manage the Conduct MCP server")
    mcp_sub = mcp_p.add_subparsers(dest="mcp_command")
    mcp_sub.add_parser("install", help="Register conduct-mcp in Claude Code and Codex")

    # conduct skill
    skill_p = sub.add_parser("skill", help="Manage Guard skill packs")
    skill_sub = skill_p.add_subparsers(dest="skill_command")
    skill_sub.add_parser("list", help="List available and installed skill packs")
    skill_install_p = skill_sub.add_parser("install", help="Install a skill pack")
    skill_install_p.add_argument("slug", help="Pack slug, e.g. conduct-owasp")
    skill_uninstall_p = skill_sub.add_parser("uninstall", help="Uninstall a skill pack")
    skill_uninstall_p.add_argument("slug", help="Pack slug, e.g. conduct-owasp")

    # conduct import-cedar
    ic_p = sub.add_parser(
        "import-cedar",
        help="Import Cedar policies (Cedar JSON format) as a Guard pack",
    )
    ic_p.add_argument("file", help="Path to a .json file containing a Cedar policy or a list of Cedar policies")
    ic_p.add_argument("--pack-slug", required=True, help="Slug for the new pack (e.g. my-cedar-import)")
    ic_p.add_argument("--pack-name", required=True, help="Human-readable pack name")
    ic_p.add_argument("--pack-version", default="1.0.0", help="Pack version (default: 1.0.0)")
    ic_p.add_argument("--pack-description", default=None, help="Optional description")
    ic_p.add_argument("--install", action="store_true", help="Install immediately (default is preview only)")
    ic_p.add_argument("--yes", action="store_true", help="Skip confirmation prompt when installing")

    # conduct import --gateway-config <file>
    # conduct export --gateway-config <profile-id-or-cond-code> [--out FILE]
    #
    # Both commands share ``--gateway-config`` as the surface. Adding
    # future importable resource types (e.g. --guard-pack, --persona)
    # is a matter of extending these two parsers, keeping the noun
    # namespace ``conduct import`` / ``conduct export`` uncluttered.
    imp_p = sub.add_parser(
        "import",
        help="Import a resource from JSON (currently: Gateway Profile v2)",
    )
    imp_p.add_argument(
        "--gateway-config",
        metavar="FILE",
        help="Path to a Gateway Profile v2 JSON file (working_copy shape).",
    )
    imp_p.add_argument(
        "--name",
        metavar="NAME",
        default=None,
        help="Override the profile name in the JSON. Useful when the "
             "source name is already taken in the target workspace.",
    )

    exp_p = sub.add_parser(
        "export",
        help="Export a resource as portable JSON (currently: Gateway Profile v2)",
    )
    exp_p.add_argument(
        "--gateway-config",
        metavar="PROFILE",
        help="Profile UUID, cond_code (8 chars), or full cond-<code>-<alias> identifier.",
    )
    exp_p.add_argument(
        "--out",
        metavar="FILE",
        default=None,
        help="Write JSON to FILE (default: stdout).",
    )

    sub.add_parser("sync", help="Sync Guard policies (and Security Loop policies if installed)")

    # conduct test-guard / verify
    verify_p = sub.add_parser("verify", help="OWASP Agentic Top 10 coverage + governance grade")
    verify_p.add_argument("--evidence",  metavar="FILE", default=None, help="Write evidence artifact to FILE.")
    verify_p.add_argument("--badge",     action="store_true",          help="Print markdown badge and exit.")
    verify_p.add_argument("--min-grade", metavar="GRADE", default=None,help="Exit 1 if governance grade is below this (A–F).")
    verify_p.add_argument("--strict",    action="store_true",          help="Exit 1 if any blocked events in last 24h (CI mode).")
    verify_p.add_argument("--format",    choices=["text", "json"],     default="text", help="Output format (default: text)")
    verify_p.add_argument("--since",     default="24h",                help="Time window for blocked event check (e.g. 7d, 24h)")
    verify_p.add_argument("--run",       action="store_true",          help="Fire live adversarial test battery and show per-test verdicts.")
    sub.add_parser("test-guard",            help="Fire a synthetic event per guard policy rule and show decisions")
    sr_p = sub.add_parser("session-report", help="Analyse local AI coding sessions with paxel and send report to admin")
    sr_p.add_argument("--developer", default=None, help="Developer name (defaults to OS username)")

    memory_p = sub.add_parser("memory", help="Search team session memories")
    memory_sub = memory_p.add_subparsers(dest="memory_command")
    mem_search_p = memory_sub.add_parser("search", help="Search team memories")
    mem_search_p.add_argument("query", nargs="+", help="Search query")
    mem_search_p.add_argument("--repo", help="Filter by repo (owner/repo)")
    mem_search_p.add_argument("--limit", type=int, default=5, help="Max results")
    register_audit(sub)

    args = parser.parse_args()

    _check_guard_setup(args.command or "")

    if args.command == "guard" and getattr(args, "guard_command", None) == "skip-setup":
        _GUARD_SKIP.parent.mkdir(parents=True, exist_ok=True)
        _GUARD_SKIP.touch()
        print(f"{GREEN}✓ Setup reminder suppressed.{RESET} Run `conduct guard sync` anytime to enable Guard.")
        return

    if args.command == "login":
        cmd_login(args)
    elif args.command == "agents":
        cmd_agents(args)
    elif args.command == "environments":
        cmd_environments(args)
    elif args.command == "credentials":
        cmd_credentials(args)
    elif args.command == "set":
        if not args.set_command:
            set_p.print_help()
            sys.exit(1)
        cmd_set(args)
    elif args.command == "projects":
        cmd_projects(args)
    elif args.command == "create":
        create_args = getattr(args, "create_args", None)
        if create_args:
            cmd_create(args)
        else:
            create_p.print_help()
    elif args.command == "playbooks":
        cmd_playbooks(args)
    elif args.command == "install":
        cmd_install(args)
    elif args.command == "delete":
        delete_args = getattr(args, "delete_args", None)
        if delete_args:
            cmd_delete(args)
        else:
            delete_p.print_help()
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
    elif args.command == "switch":
        cmd_switch(args)
    elif args.command == "token":
        cfg = _load_config()
        token = cfg.get("agent_token", "")
        if not token:
            print(f"{RED}No agent token found. Run: conduct login{RESET}")
            sys.exit(1)
        print(f"\n{BOLD}Agent token{RESET} (paste as Bearer value in MCP server auth):\n")
        print(f"  {CYAN}Bearer {token}{RESET}\n")
        print(f"{GRAY}Token expires: {cfg.get('token_expires_at', 'unknown')}{RESET}")
        print(f"{GRAY}Workspace:     {cfg.get('workspace_id', '')}{RESET}\n")
    elif args.command == "whoami":
        cmd_whoami(args)
    elif args.command == "sessions":
        cmd_sessions(args)
    elif args.command == "guard":
        _guard.dispatch_guard(args, guard_p)
    elif args.command == "mcp":
        if getattr(args, "mcp_command", None) == "install":
            cmd_mcp_install(args)
        else:
            mcp_p.print_help()
    elif args.command == "skill":
        cmd_skill(args)
    elif args.command == "import-cedar":
        cmd_import_cedar(args)
    elif args.command == "import":
        # Only Gateway Profile v2 import today. Other imports (Guard
        # skill packs, personas, etc.) already have their own commands.
        if getattr(args, "gateway_config", None):
            args.file = args.gateway_config
            cmd_import_gateway_config(args)
        else:
            print(f"{RED}Usage: conduct import --gateway-config <file.json>{RESET}", file=sys.stderr)
            sys.exit(1)
    elif args.command == "export":
        if getattr(args, "gateway_config", None):
            args.target = args.gateway_config
            cmd_export_gateway_config(args)
        else:
            print(f"{RED}Usage: conduct export --gateway-config <profile-id-or-cond-code>{RESET}", file=sys.stderr)
            sys.exit(1)
    elif args.command == "sync":
        cmd_sync(args)
    elif args.command == "verify":
        _guard.cmd_verify(args)
    elif args.command == "test-guard":
        cmd_test_guard(args)
    elif args.command == "session-report":
        cmd_session_report(args)
    elif args.command == "memory":
        cmd_memory(args)
    elif args.command == "audit":
        cmd_audit(args)
    else:
        parser.print_help()


# ponytail: telemetry error interceptor (#718)
from .log_util import install_error_interceptor as _ei
main = _ei(main)

if __name__ == "__main__":
    main()
