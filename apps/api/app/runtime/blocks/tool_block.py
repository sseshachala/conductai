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
    credentials: dict | None = None,  # kept for backward compat — ignored, broker is source of truth
    allowed_hosts: list[str] | None = None,
    db=None,
    workspace_id: str = "",
) -> dict:
    from app.runtime.integrations import github, slack, linear, digitalocean, vercel, railway, conduct
    from app.runtime.tool_engine import (
        _check_egress,
        _dry_run_mock,
        _INTEGRATION_HOSTS,
        _resolve_refs,
    )
    from app.core.credentials import fetch_credential

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

    from app.runtime.run_contract import cred_from_state
    _cred_token, _cred_api_url, _cred_handles = cred_from_state(state)

    _HANDLE_ALIASES_GLOBAL: dict[str, list[str]] = {"github": ["git"]}

    def _fetch_integration_creds(handle: str) -> dict:
        """Fetch creds for handle, trying aliases and env_vars fallback via broker."""
        # Primary handle
        if handle in _cred_handles:
            c = fetch_credential(_cred_token, handle, _cred_api_url)
            if c:
                return c
        # Alias handles (e.g. "git" for "github")
        for alias in _HANDLE_ALIASES_GLOBAL.get(handle, []):
            if alias in _cred_handles:
                c = fetch_credential(_cred_token, alias, _cred_api_url)
                if c:
                    return c
        # env_vars flat-key fallback
        _FLAT_FALLBACKS: dict[str, list[str]] = {
            "github":       ["GITHUB_TOKEN", "GIT_TOKEN"],
            "slack":        ["SLACK_BOT_TOKEN"],
            "linear":       ["LINEAR_API_KEY"],
            "digitalocean": ["DIGITALOCEAN_TOKEN", "DO_TOKEN"],
            "vercel":       ["VERCEL_TOKEN"],
            "railway":      ["RAILWAY_TOKEN"],
        }
        if "env_vars" in _cred_handles:
            env_vars = fetch_credential(_cred_token, "env_vars", _cred_api_url)
            for key in _FLAT_FALLBACKS.get(handle, []):
                val = env_vars.get(key)
                if val:
                    return {"token": val, "api_key": val}
        return {}

    if dry_run:
        creds = _fetch_integration_creds(integration)
        if not creds:
            return {"dry_run": True, "warning": f"No credentials for {integration} — would fail in a real run", "action": action}
        return _dry_run_mock(integration, action, params)

    creds = _fetch_integration_creds(integration)

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
