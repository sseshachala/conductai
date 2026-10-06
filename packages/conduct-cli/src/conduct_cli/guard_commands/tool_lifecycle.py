"""Manage only Conduct-owned entries; every edit is scoped and repeatable."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shlex
import subprocess

from conduct_cli.deployment import is_hosted_mcp_move, resolve
from conduct_cli.tool_adapters import ADAPTERS, CONDUCT_MCP_KEY, LEGACY_MCP_KEYS
from conduct_cli.tool_config import edit_document
from . import shared

MODULES = {"conduct_cli.hooks.pretooluse", "conduct_cli.hooks.posttooluse",
           "conduct_cli.hooks.stop", "conduct_cli.hooks.precompact",
           "conduct_cli.hooks.session_start", "conduct_cli.hooks.session_usage"}


def disabled(tool):
    path = Path.home() / ".conduct" / "disabled-tools.json"
    if not path.exists():
        return False
    data = json.loads(path.read_text())
    if not isinstance(data, dict):
        raise ValueError("Invalid disabled-tool configuration")
    return data.get(tool) is True


def _command(argv):
    return subprocess.list2cmdline(argv) if os.name == "nt" else shlex.join(argv)


def _split_command(command, windows=None):
    windows = os.name == "nt" if windows is None else windows
    argv = shlex.split(command, posix=not windows)
    return [arg[1:-1] if windows and len(arg) >= 2 and arg[0] == arg[-1] == '"'
            else arg for arg in argv]


def owned_hook(entry, tool):
    if not isinstance(entry, dict):
        raise ValueError("Invalid hook entry")
    args = entry.get("args")
    if tool == "copilot-cli" and isinstance(args, list):
        return len(args) == 4 and args[:2] == ["-m", "conduct_cli.hooks.copilot"] and args[2] in {
            "pre", "post", "failure", "session-start", "session-end"}
    command = entry.get("command", "")
    if not isinstance(command, str):
        return False
    if tool in {"cursor", "windsurf"}:
        from .editor_setup import owned
        return owned(entry, tool)
    try:
        argv = _split_command(command)
    except ValueError:
        return False
    if command == "conductguard-post":
        return True
    if len(argv) >= 3 and argv[1] == "-m" and argv[2] in MODULES:
        return len(argv) == 3 or (argv[2] == "conduct_cli.hooks.session_usage"
                                 and len(argv) == 4 and argv[3] == tool)
    roots = [Path.home() / ".conduct", Path.home() / ".conductguard", shared.GUARD_DIR]
    scripts = {str(root / name) for root in roots for name in (
        "hook.py", "guard-stop.py", "guard-precompact.py", "guard-session-start.py")}
    return len(argv) in {2, 3} and argv[1] in scripts and (len(argv) == 2 or argv[2] == "post")


def configure_hooks(tool, python, hook_path=None, remove=False):
    adapter = ADAPTERS[tool]
    if adapter.hooks is None or not adapter.root().is_dir():
        return False
    if tool in {"cursor", "windsurf"}:
        from .editor_setup import configure
        return configure(tool, python, remove=remove)
    path = adapter.root() / ("settings.json" if tool == "claude-code" else
                              "hooks/conduct-guard.json" if tool == "copilot-cli" else "hooks.json")
    if remove and not path.exists():
        return False
    with edit_document(path) as document:
        hooks = document.setdefault("hooks", {})
        if not isinstance(hooks, dict):
            raise ValueError("Invalid hook map")
        before = json.dumps(document, sort_keys=True)
        if tool == "copilot-cli":
            modes = {"preToolUse": "pre", "postToolUse": "post", "postToolUseFailure": "failure",
                     "sessionStart": "session-start", "sessionEnd": "session-end"}
        else:
            modes = {"PreToolUse": "pre", "PostToolUse": "post", "SessionStart": "usage",
                     "Stop": "usage", "SessionEnd": "usage"}
        for event in sorted(set(hooks) | set(modes)):
            groups = hooks.get(event, [])
            if not isinstance(groups, list):
                raise ValueError("Invalid hook groups")
            kept = []
            for group in groups:
                if not isinstance(group, dict):
                    raise ValueError("Invalid hook group")
                if tool == "copilot-cli":
                    if not owned_hook(group, tool):
                        kept.append(group)
                else:
                    commands = group.get("hooks", [])
                    if not isinstance(commands, list):
                        raise ValueError("Invalid hook commands")
                    def replace(entry):
                        if not owned_hook(entry, tool):
                            return False
                        if remove or modes.get(event) in {"pre", "post"}:
                            return True
                        argv = _split_command(entry.get("command", ""))
                        return len(argv) == 4 and argv[1:3] == ["-m", "conduct_cli.hooks.session_usage"] and argv[3] == tool
                    remaining = [entry for entry in commands if not replace(entry)]
                    if remaining:
                        kept.append({**group, "hooks": remaining})
                    elif not commands:
                        kept.append(group)
            if not remove and event in modes:
                mode = modes[event]
                if tool == "copilot-cli":
                    kept.append({"type": "command", "exec": python,
                                 "args": ["-m", "conduct_cli.hooks.copilot", mode, str(hook_path or shared.GUARD_DIR / "hook.py")],
                                 "timeoutSec": 30})
                else:
                    argv = [python, "-m", "conduct_cli.hooks.session_usage", tool] if mode == "usage" else (
                        [python, str(hook_path)] + (["post"] if mode == "post" else []) if hook_path else
                        [python, "-m", "conduct_cli.hooks.posttooluse" if mode == "post" else "conduct_cli.hooks.pretooluse"])
                    kept.append({**({"matcher": ".*"} if mode != "usage" else {}),
                                 "hooks": [{"type": "command", "command": _command(argv)}]})
                    if tool == "claude-code" and event == "Stop":
                        stop = shared.GUARD_DIR / "guard-stop.py"
                        if stop.exists() and not any(owned_hook(entry, tool) and "guard-stop.py" in entry.get("command", "")
                                                     for group in kept for entry in group.get("hooks", [])):
                            kept.insert(0, {"hooks": [{"type": "command", "command": _command([python, str(stop)])}]})
            if kept:
                hooks[event] = kept
            else:
                hooks.pop(event, None)
        if tool == "copilot-cli" and not remove:
            document.setdefault("version", 1)
        return before != json.dumps(document, sort_keys=True)


def owned_mcp(entry, endpoint):
    if not isinstance(entry, dict):
        return False
    if entry.get("command") in {"conduct-mcp", "conductguard-mcp"}:
        return True
    args = entry.get("args")
    if entry.get("command") == "npx" and isinstance(args, list):
        return len(args) == 5 and args[:3] == ["-y", "mcp-remote", endpoint] and args[3] == "--header" and (
            isinstance(args[4], str) and args[4].startswith("Authorization: Bearer cond_agt_"))
    headers = entry.get("headers", {})
    return entry.get("url") == endpoint and isinstance(headers, dict) and any(
        key.lower() == "authorization" and isinstance(value, str) and value.startswith("Bearer cond_agt_")
        for key, value in headers.items())


def _endpoint(entry):
    args = entry.get("args") if isinstance(entry, dict) else None
    return args[2] if isinstance(args, list) and len(args) == 5 else (entry or {}).get("url")


def ours_mcp(entry, endpoint):
    """Owned for this endpoint, or a managed entry left on the pre-#2360 hosted MCP host."""
    return owned_mcp(entry, endpoint) or (managed_mcp(entry) and is_hosted_mcp_move(_endpoint(entry), endpoint))


def managed_mcp(entry):
    """Recognize managed credentials when switching the selected deployment."""
    if not isinstance(entry, dict):
        return False
    args = entry.get("args")
    endpoint = args[2] if isinstance(args, list) and len(args) == 5 else entry.get("url")
    return owned_mcp(entry, endpoint) if isinstance(endpoint, str) else (
        entry.get("command") in {"conduct-mcp", "conductguard-mcp"})


def configure_mcp(tool, config, remove=False, project=None):
    selected = resolve(config)
    token = config.get("agent_token", "")
    if not remove and not token.startswith("cond_agt_"):
        raise ValueError("A Conduct agent credential is required")
    changed = False
    adapter = ADAPTERS[tool]
    for source in adapter.mcp_sources(project):
        if source.scope == "legacy-user" and not source.path.exists():
            continue
        if not source.path.exists() and (remove or source.scope != "user" or not adapter.root().is_dir()):
            continue
        with edit_document(source.path) as document:
            servers = document.setdefault(source.key, {})
            if not isinstance(servers, dict):
                raise ValueError("Invalid MCP server map")
            for key in (CONDUCT_MCP_KEY, *LEGACY_MCP_KEYS):
                prior = servers.get(key)
                if prior is not None and ours_mcp(prior, selected.mcp) and (remove or key in LEGACY_MCP_KEYS):
                    del servers[key]
                    changed = True
                elif prior is not None and key in LEGACY_MCP_KEYS and not remove and CONDUCT_MCP_KEY not in servers:
                    servers[CONDUCT_MCP_KEY] = servers.pop(key)  # rename; ownership checks below still apply
                    changed = True
            if not remove and source.scope == "user":
                key = CONDUCT_MCP_KEY
                entry = {"type": "http", "url": selected.mcp, "headers": {"Authorization": f"Bearer {token}"}} if tool == "copilot-cli" else {
                    "command": "npx", "args": ["-y", "mcp-remote", selected.mcp, "--header", f"Authorization: Bearer {token}"]}
                prior = servers.get(key)
                if prior is not None and prior != entry and not managed_mcp(prior):
                    raise ValueError("User-owned MCP override; left unchanged")
                if prior != entry:
                    servers[key] = entry
                    changed = True
    return changed


def run(args):
    tool = args.tool
    config = shared._require_guard_config()
    if args.action == "verify":
        from .inventory import collect, verify_gateway
        report = collect(config_only=True, project=args.project)
        report["agents"] = [item for item in report["agents"] if item["framework"] == tool]
        verify_gateway(report, config["agent_token"], config)
        print(json.dumps(report, indent=2))
        return
    remove = args.action in {"disable", "remove"}
    state = Path.home() / ".conduct" / "disabled-tools.json"
    # Stop collectors and future automatic sync before removing configuration.
    with edit_document(state) as document:
        document[tool] = remove
    try:
        from .hooks import _best_python
        configure_hooks(tool, _best_python(), remove=remove)
        configure_mcp(tool, config, remove=remove, project=args.project)
        configure_gateway(tool, config, remove=remove)
    except (OSError, ValueError, TimeoutError):
        raise SystemExit("Tool configuration could not be completed; fix the configuration and repeat the command.") from None
    print(f"{tool}: {'removed' if remove else 'configured'}. Restart the tool. Other entries and shared credentials are unchanged.")


def configure_gateway(tool, config, remove=False):
    selected = resolve(config)
    if tool == "codex" and remove:
        path = ADAPTERS[tool].root() / "config.toml"
        if path.exists():
            with edit_document(path) as document:
                providers = document.get("model_providers", {})
                prior = providers.get("conduct", {})
                if (isinstance(prior, dict) and selected.gateway
                        and prior.get("base_url") == selected.gateway.rstrip("/") + "/openai/v1"
                        and prior.get("env_key") == "CONDUCT_GATEWAY_TOKEN"):
                    del providers["conduct"]
                    if document.get("model_provider") == "conduct":
                        saved = Path.home() / ".conduct" / "codex-provider.json"
                        previous = json.loads(saved.read_text()).get("previous") if saved.exists() else None
                        if isinstance(previous, str):
                            document["model_provider"] = previous
                        else:
                            document.pop("model_provider", None)
    if not remove and selected.gateway:
        from .gateway import _configure_codex_proxy, _write_proxy_env
        if tool == "codex":
            _configure_codex_proxy(selected.gateway)
        if tool in {"claude-code", "codex", "copilot-cli"}:
            _write_proxy_env(config["agent_token"], selected.gateway)
    if remove:
        from .gateway import _write_private_env, SHELL_RC_MARKER
        for name in ("env", "env.ps1"):
            path = Path.home() / ".conduct" / name
            if path.exists():
                content = path.read_text(encoding="utf-8")
                if content.startswith(SHELL_RC_MARKER):
                    _write_private_env(path, content)
