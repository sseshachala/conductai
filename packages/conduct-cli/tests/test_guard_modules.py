"""The module split must preserve CLI wiring and the compatibility entry point."""
import argparse
import importlib
import inspect
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

from conduct_cli import guard
from conduct_cli.guard_commands import instructions


MODULES = (
    "shared", "policy", "hooks", "mcp", "instructions", "setup", "gateway",
    "discovery", "watch", "reporting", "verification", "booster",
)
COMMANDS = (
    ("sync", "cmd_guard_sync"), ("status", "cmd_guard_status"),
    ("replay-events", "cmd_guard_replay_events"), ("savings", "cmd_guard_savings"),
    ("audit", "cmd_guard_audit"), ("install", "cmd_guard_install"),
    ("discover", "cmd_guard_discover"), ("watch", "cmd_guard_watch"),
    ("lint", "cmd_guard_lint"), ("booster-status", "cmd_guard_booster_status"),
    ("debug-hook pretooluse", "cmd_guard_debug_hook"),
    ("session start", "cmd_guard_session"), ("simulate", "cmd_guard_simulate"),
    ("approvals list", "cmd_guard_approvals"),
)


@pytest.mark.parametrize("module_name", MODULES)
def test_implementation_functions_remain_available_at_legacy_import(module_name):
    module = importlib.import_module("conduct_cli.guard_commands." + module_name)
    for name, value in vars(module).items():
        if inspect.isfunction(value) and value.__module__ == module.__name__:
            assert getattr(guard, name) is value


@pytest.mark.parametrize("module_name", MODULES)
def test_module_can_be_imported_first_in_fresh_process(module_name, tmp_path):
    import os
    env = dict(os.environ, HOME=str(tmp_path), USERPROFILE=str(tmp_path))
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    result = subprocess.run(
        [sys.executable, "-c", f"import conduct_cli.guard_commands.{module_name}; import conduct_cli.guard"],
        env=env, capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("command,handler", COMMANDS)
def test_parser_dispatch_preserves_command_handlers(command, handler, monkeypatch):
    parser = argparse.ArgumentParser()
    guard_parser, _ = guard.register_guard_parser(parser.add_subparsers(dest="command"))
    args = parser.parse_args(["guard", *command.split()])
    target = Mock()
    monkeypatch.setattr(guard, handler, target)
    guard.dispatch_guard(args, guard_parser)
    if handler == "cmd_guard_approvals":
        target.assert_called_once_with(args, guard_parser)
    else:
        target.assert_called_once_with(args)


def test_watch_launcher_import_stays_valid():
    from conduct_cli.guard import _watch_loop
    from conduct_cli.guard_commands.watch import _watch_loop as implementation
    assert _watch_loop is implementation


def test_policy_asset_resolves_from_package_root():
    package_root = Path(guard.__file__).parent
    assert instructions._GUARD_RULES_TEXT == (package_root / "guard_policy.md").read_text().rstrip()


def test_sync_and_discovery_flags_are_unchanged():
    parser = argparse.ArgumentParser()
    guard.register_guard_parser(parser.add_subparsers(dest="command"))
    args = parser.parse_args(["guard", "sync", "--dry-run", "--no-codex-proxy", "--no-local-audit"])
    assert args.dry_run and args.no_codex_proxy and args.no_local_audit
    args = parser.parse_args(["guard", "discover", "--config-only", "--report", "report.json"])
    assert args.config_only and args.report == "report.json"


@pytest.mark.parametrize("flags,expected", [([], True), (["--verify-gateway"], True), (["--no-verify-gateway"], False)])
def test_discovery_gateway_check_defaults_on(flags, expected):
    parser = argparse.ArgumentParser()
    guard.register_guard_parser(parser.add_subparsers(dest="command"))
    args = parser.parse_args(["guard", "discover", *flags])
    assert args.verify_gateway is expected
