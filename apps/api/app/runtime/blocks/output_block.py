"""
Output block executor.

Sends run results via Slack, email, or webhook.
Extracted from app.runtime.executor.
"""
from __future__ import annotations

import json
import os

import structlog
import asyncio

log = structlog.get_logger(__name__)


# ── output template helpers ───────────────────────────────────────────────────

def _build_run_summary(state: dict) -> str:
    """Build a human-readable bullet-point summary from accumulated block outputs."""
    lines = []

    # Prepend finding context when triggered by a security finding
    trigger = state.get("_trigger") or {}
    if trigger.get("finding_id"):
        sev = str(trigger.get("severity") or "unknown").upper()
        ftype = trigger.get("type") or "finding"
        repo = trigger.get("repo_full_name") or ""
        loc = trigger.get("file") or ""
        if trigger.get("line"):
            loc = f"{loc}:{trigger['line']}"
        desc = str(trigger.get("description") or "")[:120]
        tool = trigger.get("tool") or ""
        parts = [f"*Triggered by:* [{sev}] {ftype}"]
        if repo:
            parts.append(f"Repo: {repo}")
        if loc:
            parts.append(f"File: {loc}")
        if tool:
            parts.append(f"Tool: {tool}")
        if desc:
            parts.append(f"Finding: {desc}")
        lines.append("\n".join(parts))
        lines.append("")  # blank separator

    for key, val in state.items():
        if key.startswith("__"):
            continue
        if not isinstance(val, dict):
            continue
        # Skip skipped/dry-run blocks
        if val.get("skipped") or val.get("dry_run"):
            continue
        # Pick best one-liner
        summary = None
        if val.get("pr_url"):
            summary = f"PR opened \u2192 {val['pr_url']}"
        elif val.get("html_url") and val.get("clone_url"):
            summary = f"Repo created \u2192 {val['html_url']}"
        elif val.get("branch"):
            summary = f"Branch created: {val['branch']}"
        elif val.get("full_name"):
            summary = f"Repo: {val['full_name']}"
        elif val.get("ts") and val.get("channel"):
            summary = f"Slack message sent to {val['channel']}"
        elif val.get("identifier") and val.get("title"):
            summary = f"Linear {val['identifier']}: {val['title']}"
        elif val.get("droplet_id"):
            summary = f"Droplet {val['droplet_id']} \u2014 {val.get('status', '?')}"
        elif val.get("state") and val.get("url"):
            summary = f"Deployment {val['state']} \u2192 {val['url']}"
        elif val.get("triggered") and val.get("service_id"):
            summary = f"Railway service {val['service_id']} redeployed"
        elif val.get("route"):
            route = val["route"]
            summary = f"\u2192 {route}" if route in ("pass", "fail") else f"Logic route: {route}"
        elif isinstance(val.get("output"), str):
            summary = val["output"][:120]
        if summary:
            lines.append(f"\u2022 {key}: {summary}")
    return "\n".join(lines) if lines else "No results recorded."


def _load_template(name: str) -> str:
    path = os.path.join(os.path.dirname(__file__), "..", "..", "templates", name)
    try:
        with open(os.path.abspath(path)) as f:
            return f.read()
    except FileNotFoundError:
        return "{run_summary}"


def _fill_template(template: str, state: dict, workflow_name: str = "Agent", trace_url: str = "") -> tuple[str, str]:
    """Return (subject, body) filled from template."""
    run_summary = _build_run_summary(state)
    triggered_by = str(state.get("__triggered_by", "manual"))

    # Split subject line if present (first line starting with "Subject:")
    lines = template.strip().splitlines()
    subject = f"Conduct AI: {workflow_name} completed"
    body_lines = lines
    if lines and lines[0].lower().startswith("subject:"):
        subject = lines[0][8:].strip()
        body_lines = lines[2:] if len(lines) > 2 else []

    body = "\n".join(body_lines)
    replacements = {
        "{workflow_name}": workflow_name,
        "{status}": "completed",
        "{duration}": "\u2014",
        "{triggered_by}": triggered_by,
        "{run_summary}": run_summary,
        "{trace_url}": trace_url or "(see Conduct AI dashboard)",
    }
    for k, v in replacements.items():
        subject = subject.replace(k, v)
        body = body.replace(k, v)

    return subject, body


# ── block executor ────────────────────────────────────────────────────────────

def _resolve_slack_mcp(workspace_id: str) -> tuple[str, str, str] | None:
    """Return (url, transport, token) for the workspace's Slack MCP server, or None."""
    if not workspace_id:
        return None
    try:
        from app.core.database import get_db as _get_db
        from app.runtime.mcp_credentials import resolve_mcp_server
        db = next(_get_db())
        try:
            resolved = resolve_mcp_server(server_name="slack", workspace_id=workspace_id, db=db)
        finally:
            db.close()
        if not resolved or not resolved[2]:
            return None
        return resolved
    except Exception:
        return None


def _execute_output(
    block: dict,
    state: dict,
    credentials: dict | None = None,  # kept for backward compat — ignored, broker is source of truth
    workflow_name: str = "Agent",
    trace_url: str = "",
    run_id: str = "",
    workspace_id: str = "",
) -> dict:
    from app.runtime.integrations import slack, email as email_integration
    from app.core.config import settings
    from app.runtime.tool_engine import _resolve_refs
    from app.core.credentials import fetch_credential

    from app.runtime.run_contract import cred_from_state, get_email_creds
    _cred_token, _cred_api_url, _cred_handles = cred_from_state(state)

    dry_run = state.get("__dry_run", False)
    data = block["data"]
    integration = data.get("integration", "slack")
    config = data.get("config", {})

    if dry_run:
        summary = _build_run_summary(state)
        return {"dry_run": True, "integration": integration, "preview": summary, "note": f"Dry run \u2014 would send via {integration}"}

    results: dict = {}

    send_slack = integration in ("slack", "both")
    send_email = integration in ("email", "both")

    if send_slack:
        slack_creds = fetch_credential(_cred_token, "slack", _cred_api_url) if "slack" in _cred_handles else {}
        channel = _resolve_refs(config.get("channel", "#general"), state)
        if not channel:
            results["slack"] = {"sent": False, "reason": "No Slack channel configured"}
        else:
            try:
                _, body = _fill_template(_load_template("slack_output.txt"), state, workflow_name, trace_url)
                use_approval = config.get("approval", False) and bool(run_id)
                mcp_slack = None if use_approval else _resolve_slack_mcp(workspace_id)
                if mcp_slack:
                    # Route through Slack MCP server — no separate credential needed
                    from app.runtime.integrations.mcp_client import call_tool
                    mcp_url, mcp_transport, mcp_token = mcp_slack
                    try:
                        r = call_tool(mcp_url, mcp_token or None, "post_message",
                                      {"channel": channel, "text": body}, transport=mcp_transport)
                        results["slack"] = r if isinstance(r, dict) else {"output": str(r)}
                    except (asyncio.TimeoutError, TimeoutError):
                        results["slack"] = {"sent": False, "error": f"Slack MCP timeout — server at {mcp_url} did not respond within 30s"}
                elif use_approval:
                    if not slack_creds:
                        results["slack"] = {"sent": False, "reason": "No Slack credentials configured"}
                    else:
                        r = slack.execute("post_approval_message", {
                            "channel": channel, "text": body,
                            "run_id": run_id, "callback_url": trace_url,
                        }, slack_creds)
                        results["slack"] = r
                elif slack_creds:
                    r = slack.execute("post_message", {"channel": channel, "text": body}, slack_creds)
                    results["slack"] = r
                else:
                    results["slack"] = {"sent": False, "reason": "No Slack credentials configured — add token in Integrations"}
            except Exception as e:
                results["slack"] = {"sent": False, "error": str(e)}

    if send_email:
        email_creds = dict(get_email_creds(_cred_token, _cred_api_url, _cred_handles))
        if not email_creds.get("resend_api_key") and settings.resend_api_key:
            email_creds["resend_api_key"] = settings.resend_api_key
        to = _resolve_refs(config.get("to", ""), state)
        from_address = config.get("from_address") or settings.email_from
        if not email_creds:
            results["email"] = {"sent": False, "reason": "No email credentials configured \u2014 add Resend or SendGrid in Settings"}
        elif not to:
            results["email"] = {"sent": False, "reason": "No recipient address configured \u2014 set 'Email address' on the output block"}
        else:
            try:
                subject, body = _fill_template(_load_template("email_output.txt"), state, workflow_name, trace_url)
                r = email_integration.execute("send_email", {"to": to, "subject": subject, "body": body, "from_address": from_address}, email_creds)
                results["email"] = r
            except Exception as e:
                results["email"] = {"sent": False, "error": str(e)}

    if integration == "webhook":
        import hashlib
        import hmac as hmac_lib
        import urllib.request
        webhook_url = _resolve_refs(config.get("webhook_url", ""), state)
        webhook_secret = config.get("webhook_secret", "")
        if not webhook_url:
            return {"sent": False, "reason": "No webhook URL configured"}
        payload = json.dumps({
            "workflow": workflow_name,
            "trace_url": trace_url,
            "state": {k: v for k, v in state.items() if not k.startswith("__")},
        }, default=str).encode()
        headers = {"Content-Type": "application/json", "User-Agent": "ConductAI/1.0"}
        if webhook_secret:
            sig = hmac_lib.new(webhook_secret.encode(), payload, hashlib.sha256).hexdigest()
            headers["X-ConductAI-Signature"] = f"sha256={sig}"
        try:
            req = urllib.request.Request(webhook_url, data=payload, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=15) as resp:
                return {"sent": True, "integration": "webhook", "status_code": resp.status}
        except Exception as e:
            return {"sent": False, "integration": "webhook", "error": str(e)}

    if not results:
        return {"sent": False, "reason": "No integration configured"}

    return {"sent": True, "integration": integration, **results}
