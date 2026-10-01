"""Resolve and apply optional inference routing for the selected deployment."""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

from conduct_cli.deployment import SAAS_API, gateway_from_metadata, resolve
from . import gateway, shared


def has_managed_routing() -> bool:
    if any((shared.GUARD_DIR / name).exists() for name in ("env", "env.ps1")):
        return True
    codex = Path.home() / ".codex" / "config.toml"
    if codex.exists() and "[model_providers.conduct]" in codex.read_text():
        return True
    for relative in ("Library/Application Support/Claude/claude_desktop_config.json",
                     "AppData/Roaming/Claude/claude_desktop_config.json"):
        path = Path.home() / relative
        if path.exists():
            try:
                if json.loads(path.read_text()).get("apiBaseUrl"):
                    return True
            except (ValueError, OSError):
                return True
    return False


def resolve_routing(cfg: dict, args) -> str | None:
    explicit = getattr(args, "proxy_url", None) or os.environ.get("CONDUCT_PROXY_URL")
    selected = {**cfg, **({"gateway_url": explicit} if explicit else {})}
    endpoints = resolve(selected)
    if selected.get("gateway_url") or selected.get("proxy_url"):
        return endpoints.gateway
    metadata = {}
    try:
        headers = {"Content-Type": "application/json"}
        if cfg.get("agent_token"):
            headers["Authorization"] = "Bearer " + cfg["agent_token"]
        request = urllib.request.Request(endpoints.api + "/guard/proxy-config", headers=headers)
        with urllib.request.urlopen(request, timeout=10) as response:
            metadata = json.loads(response.read())
        result = gateway_from_metadata(selected, metadata)
    except Exception:
        # A custom API's legacy default may still advertise SaaS; never use it.
        result = endpoints.gateway
    if result is None and endpoints.api != SAAS_API:
        if has_managed_routing():
            raise ValueError("Custom Gateway is not configured but managed routing files exist. "
                             "Set --proxy-url to your Gateway before syncing; existing files were not changed.")
        print("Gateway setup skipped: this custom deployment has no configured Gateway. "
              "Policy hooks and MCP still use the selected API.")
    return result


def apply_routing(cfg: dict, args, proxy_url: str | None) -> None:
    if not proxy_url:
        return
    agent_token = cfg.get("agent_token", "")
    rc_path, newly_sourced = gateway._write_proxy_env(
        agent_token, proxy_url, copilot=not getattr(args, "no_copilot_proxy", False))
    if agent_token:
        env_name = "env.ps1" if sys.platform == "win32" else "env"
        activate_cmd = f". {rc_path}" if sys.platform == "win32" else f"source {rc_path}"
        print(f"  Proxy env written: ~/.conduct/{env_name} -> {proxy_url}")
        if newly_sourced:
            print(f"  Run `{activate_cmd}` (or open a new shell) to activate.")
    if not getattr(args, "no_codex_proxy", False) and agent_token:
        if gateway._configure_codex_proxy(proxy_url):
            gateway._configure_codex_launch_env(agent_token)
            print("  Codex proxy configured. Fully quit and restart Codex to reload its environment.")
