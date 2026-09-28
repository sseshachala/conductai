"""One evidence projection for the API, Lens, MCP and knowledge index."""
from datetime import datetime, timedelta, timezone
import uuid

from sqlalchemy.dialects.postgresql import insert

from app.modules.guard.models import DiscoveredAgent

FRESH_FOR = timedelta(hours=24)
SIGNALS = {"tool_installation", "running_executable", "dependency_manifest"}
TOOLS = {"claude-code", "codex", "cursor", "windsurf", "copilot-cli"}
FRAMEWORKS = TOOLS | {"langchain", "crewai", "autogen", "openai-agents", "llama-index"}
GATEWAY_CHECKS = {"connection_verified", "authentication_failed", "unavailable"}


def clean_evidence(value):
    value = value if isinstance(value, dict) else {}
    signals = value.get("signals", [])
    return {
        **({"gateway_connection_status": value["gateway_connection_status"]}
           if isinstance(value.get("gateway_connection_status"), str) and value["gateway_connection_status"] in GATEWAY_CHECKS else {}),
        "signals": sorted({s for s in signals if isinstance(s, str) and s in SIGNALS}) if isinstance(signals, list) else [],
        **{key: value[key] for key in ("hooks_configured", "mcp_configured", "gateway_configured", "config_unreadable")
           if isinstance(value.get(key), bool)},
    }


def _recent(value, now):
    if value is None:
        return False
    value = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
    return now - FRESH_FOR <= value <= now


def agent_view(row, now=None):
    now = now or datetime.now(timezone.utc)
    evidence = clean_evidence(row.evidence)
    normalized = bool(row.device_id and row.installation_id)
    fresh = normalized and _recent(row.last_seen_at, now)
    observed = normalized and bool(row.hook_event_id) and _recent(row.hook_observed_at, now)
    hooks = "observed" if observed else "configured" if fresh and evidence.get("hooks_configured") else "unverified"
    gateway = "configured" if fresh and evidence.get("gateway_configured") else "unverified"
    checked_at = None
    try:
        checked_at = datetime.fromisoformat((row.evidence or {}).get("gateway_checked_at", ""))
    except (ValueError, TypeError):
        pass
    if gateway == "configured" and _recent(checked_at, now):
        gateway = evidence.get("gateway_connection_status", gateway)
    detection = row.detection if normalized and row.detection in {"installed", "running", "possible_integration"} else "legacy_unverified"
    if detection == "possible_integration":
        action = {"label": "Review integration", "command": None,
                  "detail": "A dependency declaration does not prove an agent is running. Review its runtime and configure a Gateway integration with a Conduct credential."}
    elif hooks == "observed":
        action = {"label": "Hook activity confirmed", "command": None,
                  "detail": "No hook setup action is needed. Recent installation-linked hook activity is recorded."}
    elif row.framework in TOOLS:
        action = {"label": "Configure tool", "command": "conduct guard sync",
                  "detail": "Run on this device, restart the tool, then run conduct guard discover. Configuration alone does not prove all calls are governed."}
    else:
        action = {"label": "Rescan device", "command": "conduct guard discover",
                  "detail": "Upgrade the CLI and rescan. Legacy records cannot identify an individual installation."}
    return {
        "id": str(row.id), "name": row.framework or "Unknown", "framework": row.framework,
        "source": "inventory" if normalized else row.source, "location": None, "risk_score": None,
        "device_id": str(row.device_id) if row.device_id else None,
        "installation_id": row.installation_id, "detection": detection,
        "freshness": "fresh" if fresh else "stale" if normalized else "unverified",
        "hooks_status": hooks, "gateway_status": gateway,
        "gateway_checked_at": checked_at if normalized else None,
        "gateway_remediation": {"label": "Gateway connection check", "command": "conduct guard discover --verify-gateway",
                                "detail": "A CLI-reported authenticated model-list check verifies connectivity with the CLI credential, not this tool's inference traffic or provider credentials."},
        "mcp_configured": fresh and evidence.get("mcp_configured", False),
        "under_guard": observed, "proxy_routed": False,
        "first_seen_at": row.first_seen_at, "last_seen_at": row.last_seen_at,
        "hook_observed_at": row.hook_observed_at,
        "hook_event_id": str(row.hook_event_id) if row.hook_event_id else None,
        "evidence": evidence if normalized else {}, "remediation": action,
        "evidence_note": "Hook activity is a reported, installation-linked event, not proof of continuous enforcement. Gateway configuration is not proof of model traffic.",
    }


def summarize(agents):
    return {
        "total": len(agents),
        "confirmed": sum(a["detection"] in {"installed", "running"} for a in agents),
        "possible_integrations": sum(a["detection"] == "possible_integration" for a in agents),
        "recent_hook_evidence": sum(a["hooks_status"] == "observed" for a in agents),
        "needs_attention": sum(a["detection"] != "legacy_unverified" and (a["hooks_status"] != "observed" or a["freshness"] != "fresh") for a in agents),
        "stale": sum(a["freshness"] == "stale" for a in agents),
        "legacy_unverified": sum(a["detection"] == "legacy_unverified" for a in agents),
        "evidence_note": "Counts represent findings, not a universal protection percentage. Missing or stale evidence is not proof of no activity.",
    }


def workspace_inventory(db, workspace_id):
    rows = db.query(DiscoveredAgent).filter(DiscoveredAgent.workspace_id == uuid.UUID(str(workspace_id))).order_by(
        DiscoveredAgent.last_seen_at.desc(), DiscoveredAgent.id).all()
    now = datetime.now(timezone.utc)
    return [agent_view(row, now) for row in rows]


def observe_hook(db, workspace_id, device_id, installation_id, framework, event_id, now):
    """Only the event ingestion path can set an observation; scans cannot forge it."""
    if not device_id or not installation_id or framework not in TOOLS:
        return
    statement = insert(DiscoveredAgent).values(
        id=uuid.uuid4(), workspace_id=workspace_id, device_id=device_id,
        installation_id=installation_id, framework=framework, name=framework,
        source=None, detection="running", evidence={}, under_guard=False, proxy_routed=False,
        first_seen_at=now, last_seen_at=now, hook_observed_at=now, hook_event_id=event_id,
    )
    db.execute(statement.on_conflict_do_update(
        constraint="uq_discovered_agents_installation",
        set_={"hook_observed_at": now, "hook_event_id": event_id},
    ))
