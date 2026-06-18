"""
conduct — internal Conduct platform tool.

Security Loop actions (emit_finding, update_finding, trigger_fix) have been
removed. Guard handles security enforcement. This stub returns a safe no-op
for any legacy calls that reference those actions.
"""
from __future__ import annotations

TOOL_MAP: dict[str, str] = {}


def execute(action: str, params: dict, creds: dict, db=None, workspace_id: str = "") -> dict:
    return {"skipped": True, "reason": f"conduct action '{action}' is no longer supported"}
