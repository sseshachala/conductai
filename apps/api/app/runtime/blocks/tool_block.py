"""
Tool block executor.

Dispatches integration actions (GitHub, Slack, Linear, DigitalOcean, Vercel, Railway, Conduct).
Extracted from app.runtime.executor.
"""
from __future__ import annotations

import structlog

log = structlog.get_logger(__name__)


def _execute_tool(
    block: dict,
    state: dict,
    credentials: dict,
    allowed_hosts: list[str] | None = None,
    db=None,
    workspace_id: str = "",
) -> dict:
    from app.runtime.integrations import github, slack, linear, digitalocean, vercel, railway, conduct
    from app.runtime.executor import (
        _check_egress,
        _dry_run_mock,
        _INTEGRATION_HOSTS,
        _resolve_refs,
    )

    dry_run = state.get("__dry_run", False)
    data = block["data"]
    integration = data.get("integration")
    config = data.get("config", {})
    params = _resolve_refs(config.get("params", {}), state)

    if not integration:
        return {"skipped": True, "reason": "No integration configured"}

    action = config.get("action", "")

    if integration == "conduct":
        return conduct.execute(action, params, creds={}, db=db, workspace_id=workspace_id)

    _HANDLE_ALIASES_GLOBAL: dict[str, list[str]] = {"github": ["git"]}

    if dry_run:
        creds = credentials.get(integration, {})
        if not creds:
            for alias in _HANDLE_ALIASES_GLOBAL.get(integration, []):
                creds = credentials.get(alias) or {}
                if creds:
                    break
        if not creds:
            env_vars = credentials.get("env_vars") or {}
            _FLAT_FALLBACKS_DRY: dict[str, list[str]] = {
                "github": ["GITHUB_TOKEN", "GIT_TOKEN"],
                "slack": ["SLACK_BOT_TOKEN"],
                "linear": ["LINEAR_API_KEY"],
                "digitalocean": ["DIGITALOCEAN_TOKEN", "DO_TOKEN"],
                "vercel": ["VERCEL_TOKEN"],
                "railway": ["RAILWAY_TOKEN"],
            }
            has_flat = any(env_vars.get(k) for k in _FLAT_FALLBACKS_DRY.get(integration, []))
            if not has_flat:
                return {"dry_run": True, "warning": f"No credentials for {integration} — would fail in a real run", "action": action}
        return _dry_run_mock(integration, action, params)

    creds = credentials.get(integration, {})
    if not creds:
        # Env-var UI stores GITHUB_TOKEN under handle "git", SLACK_BOT_TOKEN under "slack", etc.
        # Try the canonical handle aliases before falling back to the legacy "env_vars" blob.
        _HANDLE_ALIASES: dict[str, list[str]] = {
            "github": ["git"],
        }
        for alias in _HANDLE_ALIASES.get(integration, []):
            aliased = credentials.get(alias) or {}
            if aliased:
                creds = aliased
                break

    if not creds:
        # Legacy fallback: keys stored raw under "env_vars" handle.
        env_vars = credentials.get("env_vars") or {}
        _FLAT_FALLBACKS: dict[str, list[str]] = {
            "github":       ["GITHUB_TOKEN", "GIT_TOKEN"],
            "slack":        ["SLACK_BOT_TOKEN"],
            "linear":       ["LINEAR_API_KEY"],
            "digitalocean": ["DIGITALOCEAN_TOKEN", "DO_TOKEN"],
            "vercel":       ["VERCEL_TOKEN"],
            "railway":      ["RAILWAY_TOKEN"],
        }
        for key in _FLAT_FALLBACKS.get(integration, []):
            val = env_vars.get(key)
            if val:
                creds = {"token": val, "api_key": val}
                break

    if not creds:
        return {"skipped": True, "reason": f"No credentials for {integration}"}

    target_host = _INTEGRATION_HOSTS.get(integration)
    if target_host:
        _check_egress(target_host, allowed_hosts)

    if integration == "github":
        return github.execute(action, params, creds)
    if integration == "slack":
        return slack.execute(action, params, creds)
    if integration == "linear":
        return linear.execute(action, params, creds)
    if integration == "digitalocean":
        return digitalocean.execute(action, params, creds)
    if integration == "vercel":
        return vercel.execute(action, params, creds)
    if integration == "railway":
        return railway.execute(action, params, creds)

    return {"skipped": True, "reason": f"Integration '{integration}' not yet implemented"}
