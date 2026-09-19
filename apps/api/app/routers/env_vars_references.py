"""Reference resolver for credential deletion — used by DELETE /env-vars.

Enumerates every place a credential handle could be referenced so the
delete path can refuse to remove one that's still in use.

Hard-checks (authoritative producers, must resolve empty for a safe delete):

- ``gateway_profiles`` — scans ``config``, ``working_copy``, and the
  active ``GatewayProfileRevision.snapshot`` for ``vault://<env_id>/<handle>``.
- ``mcp_servers`` — substring match against ``encrypted_auth``. Coarse but
  avoids decrypting every row; false positives get resolved by force=true.

Soft-check (best-effort, non-authoritative):

- ``workflows_soft`` — greps the current ``WorkflowVersion.yaml_source``
  for ``credentials.<handle>`` substrings. A proper AST resolver would
  live in a shared credential broker (Phase 2 of #2054); until then this
  substring scan is the safety floor.

Return shape is a flat dict of ``scope_name → [display_names]``. Any
non-empty list means the delete should be refused unless the caller
explicitly asked for ``force=true``.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session


def reference_report(
    db: Session,
    workspace_id: str,
    env_id: str,
    handle: str,
) -> dict[str, list[str]]:
    """Return a report of where ``handle`` is referenced across the workspace."""
    from app.models.gateway_profile import (
        GatewayProfile,
        GatewayProfileRevision,
    )
    from app.models.mcp_server import McpServer
    from app.models.workflow import Workflow, WorkflowVersion

    report: dict[str, list[str]] = {
        "gateway_profiles": [],
        "mcp_servers": [],
        "workflows_soft": [],
    }
    vault_ref = f"vault://{env_id}/{handle}"

    # Gateway profiles — enumerate config + working_copy + active revision snapshot.
    profile_rows = db.query(GatewayProfile).filter(
        GatewayProfile.workspace_id == workspace_id,
    ).all()
    active_ids: list[Any] = []
    for p in profile_rows:
        blob = str(p.config or "") + str(p.working_copy or "")
        if vault_ref in blob:
            report["gateway_profiles"].append(p.name)
        if p.active_revision_id is not None:
            active_ids.append(p.active_revision_id)
    if active_ids:
        revs = db.query(GatewayProfileRevision).filter(
            GatewayProfileRevision.id.in_(active_ids),
        ).all()
        for r in revs:
            if vault_ref in str(r.snapshot or ""):
                owner = next(
                    (p.name for p in profile_rows if p.active_revision_id == r.id),
                    str(r.profile_id),
                )
                if owner not in report["gateway_profiles"]:
                    report["gateway_profiles"].append(owner)

    # MCP servers — substring match on ciphertext (false positives OK: force=true).
    mcp_rows = db.query(McpServer).filter(
        McpServer.workspace_id == workspace_id,
    ).all()
    for m in mcp_rows:
        if m.encrypted_auth and handle in str(m.encrypted_auth):
            report["mcp_servers"].append(m.name)

    # Workflows — best-effort yaml substring scan of the current version.
    workflow_rows = db.query(Workflow).filter(
        Workflow.workspace_id == workspace_id,
        Workflow.current_version_id.isnot(None),
    ).all()
    version_ids = [w.current_version_id for w in workflow_rows]
    if version_ids:
        versions = db.query(WorkflowVersion).filter(
            WorkflowVersion.id.in_(version_ids),
        ).all()
        needle = f"credentials.{handle}"
        for v in versions:
            if v.yaml_source and needle in v.yaml_source:
                owner = next(
                    (w.name for w in workflow_rows if w.current_version_id == v.id),
                    str(v.workflow_id),
                )
                if owner not in report["workflows_soft"]:
                    report["workflows_soft"].append(owner)

    return report
