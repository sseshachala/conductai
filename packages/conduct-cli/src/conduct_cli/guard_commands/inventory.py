"""Privacy-preserving local facts, shared by discovery and watch."""
from __future__ import annotations

import hashlib
import http.client
import json
import os
import shutil
import tempfile
import uuid
from pathlib import Path
from urllib.parse import urlparse

TOOLS = ("claude-code", "codex", "cursor", "windsurf", "copilot-cli")
DEPENDENCIES = {"langchain": "langchain", "crewai": "crewai", "autogen-agentchat": "autogen",
                "openai-agents": "openai-agents", "llama-index": "llama-index",
                "@langchain/core": "langchain", "@openai/agents": "openai-agents"}


def device_id():
    directory = Path.home() / ".conduct"
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / "discovery-device-id"
    if not destination.exists():
        # Publish a complete ID atomically so parallel hooks never read an empty file.
        with tempfile.NamedTemporaryFile(mode="w", dir=directory, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(str(uuid.uuid4()))
        try:
            try:
                os.link(temporary, destination)
            except FileExistsError:
                pass
        finally:
            temporary.unlink()
    return str(uuid.UUID(destination.read_text().strip()))


def canonical_tool(tool):
    return {"claude_code": "claude-code", "codex_cli": "codex",
            "codex-desktop": "codex"}.get(tool, tool)


def tool_root(tool):
    home = Path.home()
    return {"claude-code": home / ".claude", "codex": Path(os.getenv("CODEX_HOME", str(home / ".codex"))),
            "cursor": home / ".cursor", "windsurf": home / ".codeium" / "windsurf",
            "copilot-cli": Path(os.getenv("COPILOT_HOME", str(home / ".copilot"))).expanduser()}.get(tool)


def installation_id(tool, root=None):
    root = root or tool_root(canonical_tool(tool))
    if root is None:
        return None
    return hashlib.sha256((canonical_tool(tool) + ":" + str(root.resolve())).encode()).hexdigest()


def _document(path):
    if not path.exists():
        return {}
    if path.stat().st_size > 1_000_000:
        raise ValueError("Oversized configuration")
    if path.suffix == ".toml":
        try:
            import tomllib
        except ImportError:
            import tomli as tomllib
        result = tomllib.loads(path.read_text())
    else:
        result = json.loads(path.read_text())
    if not isinstance(result, dict):
        raise ValueError("Expected an object")
    return result


def _managed_hook(entries):
    if not isinstance(entries, list):
        return False
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        command = entry.get("command", "")
        if isinstance(command, str) and any(marker in command for marker in
                ("conduct_cli.hooks.", "conductguard-", "/.conduct/hook.py", "\\.conduct\\hook.py")):
            return True
        args = entry.get("args", [])
        if isinstance(args, list) and "conduct_cli.hooks.copilot" in args:
            return True
        if _managed_hook(entry.get("hooks", [])):
            return True
    return False


def _gateway(value, provider):
    if not isinstance(value, str):
        return False
    from conduct_cli.deployment import resolve
    from .shared import _load_guard_config
    gateway = resolve(_load_guard_config()).gateway
    return bool(gateway and value.rstrip("/") in
                {f"{gateway}/{provider}", f"{gateway}/{provider}/v1"})


def verify_gateway(report, token, config=None):
    """Probe the configured Gateway only; never follow redirects or send prompts."""
    from conduct_cli.deployment import resolve
    from .shared import _load_guard_config
    gateway = resolve(config if config is not None else _load_guard_config()).gateway
    if not gateway:
        return
    endpoint = urlparse(gateway)
    results = {}
    for item in report["agents"]:
        evidence = item["evidence"]
        provider = {"claude-code": "anthropic", "codex": "openai", "copilot-cli": "openai"}.get(item["framework"])
        if not provider or not evidence.get("gateway_configured"):
            continue
        if provider not in results:
            status = "unavailable"
            if not token or not token.startswith("cond_agt_"):
                status = "authentication_failed"
            else:
                transport = http.client.HTTPSConnection if endpoint.scheme == "https" else http.client.HTTPConnection
                connection = transport(endpoint.netloc, timeout=8)
                try:
                    connection.request("GET", f"{endpoint.path}/{provider}/v1/models", headers={"Authorization": f"Bearer {token}"})
                    response = connection.getresponse()
                    if response.status in (401, 403):
                        status = "authentication_failed"
                    elif response.status == 200:
                        payload = json.loads(response.read(1_000_001))
                        catalog_key = "models" if provider == "openai" else "data"
                        if isinstance(payload, dict) and isinstance(payload.get(catalog_key), list):
                            status = "connection_verified"
                except (OSError, ValueError, http.client.HTTPException):
                    pass
                finally:
                    connection.close()
            results[provider] = status
        evidence["gateway_connection_status"] = results[provider]


def collect(config_only=False):
    records, errors = {}, set()

    def record(tool, root=None, detection="installed"):
        key = installation_id(tool, root)
        item = records.setdefault(key, {
            "installation_id": key, "framework": tool, "name": tool, "source": "inventory",
            "detection": detection, "evidence": {"signals": []},
        })
        if detection == "running":
            item["detection"] = "running"
        return item

    for tool in TOOLS:
        root = tool_root(tool)
        executable = {"claude-code": "claude", "copilot-cli": "copilot"}.get(tool, tool)
        if not root.exists() and not shutil.which(executable):
            continue
        evidence = record(tool)["evidence"]
        evidence["signals"] = ["tool_installation"]
        try:
            if tool == "codex":
                data = _document(root / "config.toml")
                servers = data.get("mcp_servers", {})
                provider = data.get("model_providers", {}).get(data.get("model_provider"), {})
                evidence["gateway_configured"] = _gateway(provider.get("base_url"), "openai")
                hooks = _document(root / "hooks.json").get("hooks", {})
                evidence["hooks_configured"] = _managed_hook(hooks.get("PreToolUse", []))
            elif tool == "copilot-cli":
                from .copilot import configured
                evidence["gateway_configured"] = configured()
                servers = _document(root / "mcp-config.json").get("mcpServers", {})
                hooks = _document(root / "hooks" / "conduct-guard.json").get("hooks", {})
                evidence["hooks_configured"] = _managed_hook(hooks.get("preToolUse", []))
            else:
                filename = {"claude-code": "settings.json", "cursor": "mcp.json", "windsurf": "mcp_config.json"}[tool]
                data = _document(root / filename)
                servers = data.get("mcpServers", {})
                hooks = data.get("hooks", {}) if tool == "claude-code" else _document(root / "hooks.json").get("hooks", {})
                evidence["hooks_configured"] = _managed_hook(hooks.get("PreToolUse", []))
                if tool == "claude-code":
                    environment = data.get("env", {})
                    url = environment.get("ANTHROPIC_BASE_URL", os.environ.get("ANTHROPIC_BASE_URL"))
                    evidence["gateway_configured"] = _gateway(url, "anthropic")
            evidence["mcp_configured"] = any(key in {"conduct", "conduct-guard"} for key in servers)
        except (OSError, ValueError, TypeError, AttributeError):
            evidence.clear()
            evidence.update(signals=["tool_installation"], config_unreadable=True)
            errors.add("config_unreadable")

    # Only dependency names from the current project's structured manifests.
    for filename in ("package.json", "pyproject.toml"):
        try:
            data = _document(Path.cwd() / filename)
            if filename == "package.json":
                dependencies = set(data.get("dependencies", {})) | set(data.get("devDependencies", {}))
            else:
                from packaging.requirements import Requirement
                dependencies = {Requirement(value).name.lower() for value in data.get("project", {}).get("dependencies", [])}
            for dependency in sorted(dependencies & DEPENDENCIES.keys()):
                item = record(DEPENDENCIES[dependency], Path.cwd(), "possible_integration")
                item["evidence"]["signals"] = ["dependency_manifest"]
        except (OSError, ValueError, TypeError, AttributeError):
            errors.add("manifest_unreadable")

    if not config_only:
        try:
            import psutil
            names = {"claude": "claude-code", "codex": "codex", "cursor": "cursor",
                     "windsurf": "windsurf", "copilot": "copilot-cli"}
            for process in psutil.process_iter(["name", "exe"]):
                try:
                    name = Path(process.info.get("exe") or process.info.get("name") or "").name.lower().removesuffix(".exe")
                    if name in names:
                        record(names[name], detection="running")["evidence"]["signals"].append("running_executable")
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    errors.add("process_unreadable")
        except (OSError, ImportError):
            errors.add("process_scan_unavailable")
    for item in records.values():
        item["evidence"]["signals"] = sorted(set(item["evidence"]["signals"]))
    return {"schema_version": 2, "device_id": device_id(), "agents": list(records.values()),
            "status": "partial" if errors else "complete", "errors": sorted(errors), "config_only": config_only}
