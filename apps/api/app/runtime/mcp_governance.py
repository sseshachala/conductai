"""Review state for registered MCP servers used through Conduct resolution."""
import hashlib
import json
import re


class MCPGovernanceDenied(Exception):
    pass


def fingerprint(tools: list[dict]) -> str:
    if not isinstance(tools, list) or len(tools) > 1000:
        raise MCPGovernanceDenied("MCP tool catalog exceeds review limits")
    normalized = []
    seen = set()
    for tool in tools:
        name = tool.get("name") if isinstance(tool, dict) else None
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", name) or name in seen:
            raise MCPGovernanceDenied("MCP tool catalog contains invalid or duplicate names")
        seen.add(name)
        normalized.append(tool)
    try:
        encoded = json.dumps(sorted(normalized, key=lambda t: t["name"]), sort_keys=True,
                             separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()
    except (TypeError, ValueError, RecursionError) as exc:
        raise MCPGovernanceDenied("Invalid MCP tool catalog") from exc
    if len(encoded) > 2 * 1024 * 1024:
        raise MCPGovernanceDenied("MCP tool catalog exceeds review limits")
    return hashlib.sha256(encoded).hexdigest()


def policy(value):
    if value is None:
        return None  # Existing registrations keep their behavior until explicitly enrolled.
    if not isinstance(value, dict) or value.get("state") not in {"needs_review", "approved", "quarantined", "revoked"}:
        raise MCPGovernanceDenied("Invalid MCP review state")
    return value


def assert_connectable(value):
    current = policy(value)
    if current and current["state"] in {"quarantined", "revoked"}:
        raise MCPGovernanceDenied("MCP server is " + current["state"])


def assert_callable(value, digest=None):
    current = policy(value)
    if current is None:
        return
    if current["state"] != "approved":
        raise MCPGovernanceDenied("MCP server requires approval or restoration")
    if digest is not None and digest != current.get("approved_digest"):
        raise MCPGovernanceDenied("MCP tool catalog changed; review required")


def transition(current, action, expected_digest=None):
    current = policy(current)
    if action == "require_review":
        if current:
            raise MCPGovernanceDenied("MCP server is already enrolled")
        return {"state": "needs_review", "revision": 1}
    if not current:
        if action not in {"quarantine", "revoke"}:
            raise MCPGovernanceDenied("Enroll the MCP server for review first")
        current = {"revision": 0}
    updated = {**current, "revision": current["revision"] + 1}
    if action == "approve":
        if current.get("state") not in {"needs_review", "approved"}:
            raise MCPGovernanceDenied("Restore the MCP server before approval")
        if not expected_digest or current.get("observed_digest") != expected_digest:
            raise MCPGovernanceDenied("MCP review is stale; inspect the catalog again")
        updated.update(state="approved", approved_digest=expected_digest)
    elif action == "quarantine":
        updated["state"] = "quarantined"
    elif action == "revoke":
        updated["state"] = "revoked"
    elif action == "restore":
        if current.get("state") not in {"quarantined", "revoked"}:
            raise MCPGovernanceDenied("MCP server is not quarantined or revoked")
        updated = {"state": "needs_review", "revision": updated["revision"]}
    else:
        raise MCPGovernanceDenied("Unknown MCP review action")
    return updated
