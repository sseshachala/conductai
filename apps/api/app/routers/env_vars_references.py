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

    # MCP servers — two paths resolve to the same handle:
    #   1. embedded credential in encrypted_auth (some registrations paste
    #      the token directly);
    #   2. resolver map ``runtime/mcp_credentials._SERVER_CRED_MAP`` that
    #      maps server name → (integration handle, field) so the runtime
    #      goes look up the token from the Integration store at call time.
    # Path 2 leaves no trace in encrypted_auth but is exactly the case the
    # reviewer flagged (a bare Slack server → slack.token). Enumerate both.
    from app.runtime.mcp_credentials import _SERVER_CRED_MAP  # local import to
    # avoid a hard runtime dep just for the reference check.

    mapped_names = {
        server_name
        for server_name, (mapped_handle, _field) in _SERVER_CRED_MAP.items()
        if mapped_handle == handle
    }
    mcp_rows = db.query(McpServer).filter(
        McpServer.workspace_id == workspace_id,
    ).all()
    for m in mcp_rows:
        hit = False
        if m.encrypted_auth and handle in str(m.encrypted_auth):
            hit = True
        # A stored server named ``slack``/``github``/etc. (or one whose
        # display name matches the map key) resolves via the map. Match
        # both the raw ``name`` and a lowercased variant for tolerance.
        name_lc = (m.name or "").lower()
        if not hit and (m.name in mapped_names or name_lc in mapped_names):
            hit = True
        if hit and m.name not in report["mcp_servers"]:
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
