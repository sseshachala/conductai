"""Explicit inventory associations, never execution authorization or endpoint verification."""
from app.modules.guard.discovery_inventory import agent_view, clean_mcp_servers


def registration_view(row):
    value = row.governance
    state = value.get("state") if isinstance(value, dict) else None
    review = "not_enrolled" if value is None else state if state in {
        "needs_review", "approved", "quarantined", "revoked"
    } else "invalid"
    if review == "approved" and (not value.get("approved_digest") or
                                value.get("observed_digest") != value.get("approved_digest")):
        review = "needs_review"
    return {"id": str(row.id), "name": row.name, "review_status": review}


def reconcile(row, registrations, now=None):
    agent = agent_view(row, now)
    links = row.mcp_links or {}
    bindings = links.get("bindings", {})
    findings = {item["id"]: item for item in clean_mcp_servers((row.evidence or {}).get("mcp_servers"))}
    result = []
    for reference in sorted(findings.keys() | bindings.keys()):
        finding = findings.get(reference)
        binding = bindings.get(reference, {})
        server = registrations.get(binding.get("server_id"))
        result.append({
            "reference_id": reference, "name": finding["name"] if finding else "No longer reported",
            "scope": finding["scope"] if finding else None,
            "transport": finding["transport"] if finding else None,
            "discovery_status": "not_reported" if finding is None else "unreadable" if agent["evidence"].get("config_unreadable")
                                else "stale" if agent["freshness"] != "fresh"
                                else "disabled" if finding["disabled"] else "discovered",
            "registration_status": "linked" if server else "registration_missing" if binding else "unlinked",
            "registration": server, "linked_at": binding.get("linked_at"),
            "association_source": "administrator" if binding else None,
            "endpoint_identity": "unverified", "enforcement_status": "not_observed",
        })
    return {"agent_id": str(row.id), "framework": row.framework, "device_id": agent["device_id"],
            "installation_id": agent["installation_id"], "last_seen_at": row.last_seen_at,
            "revision": links.get("revision", 0), "servers": result}
