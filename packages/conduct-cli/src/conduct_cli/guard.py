"""Guard command parsing, dispatch and backwards-compatible imports."""
from __future__ import annotations

from pathlib import Path as Path
import json as json
import os as os
import sys
import time as time
import urllib.request  # noqa: F401 -- compatibility for existing import paths

from conduct_cli.guard_commands.shared import (  # noqa: F401
    RESET,
    BOLD,
    GREEN,
    RED,
    BLUE,
    GRAY,
    CYAN,
    YELLOW,
    CONDUCT_HOME,
    GUARD_DIR,
    CONFIG_PATH,
    POLICY_PATH,
    active_policy_path,
    _load_guard_config,
    _save_guard_config,
    _require_guard_config,
    _api_url,
    _default_agent_token,
    _req,
    _parse_since,
    _copilot_home,
    _copilot_cli_installed,
)

from conduct_cli.guard_commands.policy import (  # noqa: F401
    _bash_command_words,
    _check_policy,
    _save_policy,
    _load_policy,
    cmd_guard_lint,
)

from conduct_cli.guard_commands.hooks import (  # noqa: F401
    _THIN_LAUNCHERS,
    _is_thin_launcher,
    _best_python,
    _write_hook,
    _write_session_hook,
    _install_session_hooks,
    _install_copilot_hooks,
    _install_codex_hook,
    _install_claude_hook,
)

from conduct_cli.guard_commands.mcp import (  # noqa: F401
    _vscode_mcp_paths,
    _MCP_TARGETS,
    _register_mcp,
    _patch_claude_desktop_proxy,
    _patch_copilot_mcp,
    _write_mcp_file,
)

from conduct_cli.guard_commands.instructions import (  # noqa: F401
    _GUARD_RULES_TEXT,
    _patch_cursor_global_rules,
    _patch_tool_instruction_files,
    _reset_tool_instruction_files,
    _write_cursorrules,
)

from conduct_cli.guard_commands.setup import (  # noqa: F401
    _PERSONA_LABELS,
    _ensure_persona,
    cmd_guard_install,
    _write_signing_key,
    cmd_guard_join,
    _check_and_upgrade_packages,
    _proactive_token_refresh,
    cmd_guard_sync,
)

from conduct_cli.guard_commands.gateway import (  # noqa: F401
    _configure_codex_proxy,
    _configure_codex_launch_env,
    _read_conduct_env_var,
    _is_anthropic_proxied,
    _is_openai_proxied,
    CONDUCT_DIR,
    PROXY_ENV_FILE,
    PROXY_OVERRIDE,
    DEFAULT_PROXY_URL,
    SHELL_RC_MARKER,
    SHELL_SOURCE_LINE,
    _gateway_v1_url,
    _KEY_PATTERNS,
    _SCAN_PATHS,
    _scan_local_keys,
    _post_local_findings,
    _LEGACY_CLAUDE_BYPASSES,
    _remove_legacy_claude_bypass,
    _write_proxy_env_windows,
    _OLD_GATEWAY_HOST,
    _NEW_GATEWAY_HOST,
    _migrate_proxy_env_if_stale,
    _write_proxy_env,
)

from conduct_cli.guard_commands.discovery import (  # noqa: F401
    _detect_ai_tools,
    _report_tools_to_server,
    _discover_config_agents,
    _scan_processes,
    cmd_guard_discover,
)

from conduct_cli.guard_commands.watch import (  # noqa: F401
    _WATCH_PID,
    _WATCH_LOG,
    _WATCH_INTERVAL,
    _is_watch_running,
    _watch_loop,
    cmd_guard_watch,
)

from conduct_cli.guard_commands.reporting import (  # noqa: F401
    _report_savings,
    cmd_guard_replay_events,
    cmd_guard_status,
    cmd_guard_savings,
    cmd_guard_session,
    cmd_guard_audit,
)

from conduct_cli.guard_commands.verification import (  # noqa: F401
    cmd_guard_debug_hook,
    _PRIV_KEYWORDS,
    _OWASP_MAP,
    _OWASP_UNKNOWN,
    _map_owasp,
    _GRADE_COLORS,
    _GRADE_ORDER,
    _grade_below,
    _VERDICT_COLOR,
    cmd_verify,
    cmd_guard_simulate,
    cmd_guard_approvals,
)

from conduct_cli.guard_commands.booster import (  # noqa: F401
    _ensure_booster,
    cmd_guard_booster_status,
)

def register_guard_parser(sub):
    """Attach the `guard` subparser tree to an existing argparse subparsers object."""
    guard_p = sub.add_parser("guard", help="Guard — team policies and MCP registration")
    guard_sub = guard_p.add_subparsers(dest="guard_command")

    # conduct guard sync
    sync_p = guard_sub.add_parser("sync", help="Refresh policy and re-scan for AI tools")
    sync_p.add_argument("--cursor", action="store_true", help="Write active Guard policies to .cursorrules")
    sync_p.add_argument("--dry-run", action="store_true", help="Preview policy changes without writing anything")
    sync_p.add_argument("--reset-instructions", action="store_true", dest="reset_instructions",
                        help="Remove ConductGuard blocks from all instruction files")
    sync_p.add_argument("--proxy-url", default=None,
                        help="Override the Guard gateway URL (default: https://gateway.conductai.ai/gateway/v1)")
    sync_p.add_argument("--no-codex-proxy", action="store_true",
                        help="Leave Codex model traffic on its current provider")
    sync_p.add_argument("--no-local-audit", action="store_true",
                        help="Skip the local pre-existing API key scan")

    # conduct guard status
    guard_sub.add_parser("status", help="Show today's spend and violations")

    replay_p = guard_sub.add_parser(
        "replay-events",
        help="Retry retained hook events after fixing delivery",
    )
    replay_p.add_argument("--limit", type=int, default=None, help="Maximum events to requeue")
    replay_p.add_argument("--dry-run", action="store_true", help="Show how many events would be requeued")

    # conduct guard savings --team
    guard_sub.add_parser("savings", help="Show org-level token savings across all developers")

    # conduct guard simulate --as-okta-agent <jwt-or-file>  (#1057)
    sim_p = guard_sub.add_parser("simulate", help="Simulate a Guard-authenticated request without executing anything")
    sim_p.add_argument("--as-okta-agent", dest="as_okta_agent", metavar="JWT-OR-FILE",
                       help="Okta-issued JWT string, or a path to a file containing one")

    # conduct guard audit [--since 7d]
    audit_p = guard_sub.add_parser("audit", help="Show recent guard events")
    audit_p.add_argument(
        "--since",
        default="24h",
        metavar="PERIOD",
        help="Time window: 1h, 24h, 7d, 30d (default: 24h)",
    )

    # conduct guard install [--signing-key <hex>]
    install_p = guard_sub.add_parser("install", help="Install Guard hook and download policies")
    install_p.add_argument(
        "--signing-key",
        default=None,
        metavar="HEX",
        help="Hex-encoded 32-byte signing key from POST /workspaces/{id}/signing-key. "
             "Written to ~/.conduct/signing.key.",
    )

    # conduct guard booster-status
    guard_sub.add_parser("booster-status", help="Verify Agent Booster intercept is active for this project")

    # conduct guard skip-setup
    guard_sub.add_parser("skip-setup", help="Suppress the Guard setup reminder (does not disable Guard)")

    # conduct guard debug-hook <toolname>
    debug_hook_p = guard_sub.add_parser(
        "debug-hook",
        help="Run any hook standalone with JSON from stdin and print what it would do",
    )
    debug_hook_p.add_argument(
        "toolname",
        choices=["pretooluse", "posttooluse", "stop", "precompact", "session-start"],
        help="Which hook to test",
    )

    # conduct guard discover
    discover_p = guard_sub.add_parser("discover", help="Scan for AI agents and show Guard coverage")
    discover_p.add_argument("--config-only", action="store_true", help="Skip process scan, config files only")
    gateway_check = discover_p.add_mutually_exclusive_group()
    gateway_check.add_argument("--verify-gateway", dest="verify_gateway", action="store_true", default=True, help="Check Gateway authentication with the CLI credential (default; no inference request)")
    gateway_check.add_argument("--no-verify-gateway", dest="verify_gateway", action="store_false", help="Skip the Gateway connection check")
    discover_p.add_argument("--report", default=None, metavar="FILE", help="Write full JSON report to file")

    # conduct guard watch
    watch_p = guard_sub.add_parser("watch", help="Start background daemon — scans every 15 min, auto-pushes to Guard")
    watch_p.add_argument("--stop",   action="store_true", help="Stop the running watch daemon")
    watch_p.add_argument("--status", action="store_true", help="Show whether the watch daemon is running")

    # conduct guard lint [--file PATH]
    lint_p = guard_sub.add_parser("lint", help="Validate local policy — show errors and warnings")
    lint_p.add_argument("--file", default=None, metavar="FILE",
                        help="Path to policy YAML/JSON (default: ~/.conduct/policy.json)")

    # conduct guard session start|stop
    p_session = guard_sub.add_parser("session", help="Start or stop a named goal session")
    session_sub = p_session.add_subparsers(dest="session_cmd")
    p_sess_start = session_sub.add_parser("start", help="Start a goal session — tags all Guard events with a goal ID")
    p_sess_start.add_argument("--goal", default="", help="Human-readable goal label")
    session_sub.add_parser("stop", help="End the current goal session")
    p_session.set_defaults(func=cmd_guard_session)

    # conduct guard approvals list|approve|reject — HITL decide from CLI (#1140)
    approv_p = guard_sub.add_parser("approvals", help="List and decide Guard HITL approval requests")
    approv_sub = approv_p.add_subparsers(dest="approvals_command")
    list_p = approv_sub.add_parser("list", help="List approval requests")
    list_p.add_argument("--status", default="pending",
                        choices=["pending", "approved", "rejected", "timed_out", "all"],
                        help="Filter by status (default: pending)")
    list_p.add_argument("--limit", type=int, default=50, help="Max rows (default: 50)")
    approve_p = approv_sub.add_parser("approve", help="Approve a pending request by id")
    approve_p.add_argument("request_id", help="Approval request UUID")
    approve_p.add_argument("--reason", default=None, help="Optional decision reason")
    reject_p = approv_sub.add_parser("reject", help="Reject a pending request by id")
    reject_p.add_argument("request_id", help="Approval request UUID")
    reject_p.add_argument("--reason", default=None, help="Optional decision reason")

    return guard_p, guard_sub


def dispatch_guard(args, guard_p):
    """Dispatch to the correct guard handler. Called from main()."""
    guard_command = getattr(args, "guard_command", None)
    if guard_command == "sync":
        cmd_guard_sync(args)
    elif guard_command == "status":
        cmd_guard_status(args)
    elif guard_command == "replay-events":
        cmd_guard_replay_events(args)
    elif guard_command == "savings":
        cmd_guard_savings(args)
    elif guard_command == "audit":
        cmd_guard_audit(args)
    elif guard_command == "install":
        cmd_guard_install(args)
    elif guard_command == "discover":
        cmd_guard_discover(args)
    elif guard_command == "watch":
        cmd_guard_watch(args)
    elif guard_command == "lint":
        cmd_guard_lint(args)
    elif guard_command == "booster-status":
        cmd_guard_booster_status(args)
    elif guard_command == "debug-hook":
        cmd_guard_debug_hook(args)
    elif guard_command == "session":
        cmd_guard_session(args)
    elif guard_command == "simulate":
        cmd_guard_simulate(args)
    elif guard_command == "approvals":
        cmd_guard_approvals(args, guard_p)
    else:
        guard_p.print_help()
        sys.exit(1)
