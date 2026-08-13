#!/usr/bin/env python3
"""Seed DEV_WORKSPACE_ID + admin membership so Playwright golden flows have
a real workspace to poke at. Also seeds the 4 Clerk sandbox users (admin,
security, developer, viewer) when their IDs are present in the env, so the
per-role flow suite has real workspace_users rows to authenticate against.

Group B extension (#1094): also seed one workflow + one custom guard rule +
one MCP server + one integration credential so the deeper flow specs have
data to interact with.

Idempotent. Uses ORM (no raw SQL)."""
from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.auth import DEV_USER_ID, DEV_WORKSPACE_ID  # noqa: E402
from app.core.database import SessionLocal  # noqa: E402
from app.models.integration import Integration  # noqa: E402
from app.models.mcp_server import McpServer  # noqa: E402
from app.models.workflow import Workflow  # noqa: E402
from app.models.workspace import Workspace  # noqa: E402
from app.models.workspace_user import WorkspaceUser  # noqa: E402
from app.modules.guard.models import WorkspaceCustomRule  # noqa: E402


CLERK_ROLE_ENV = {
    "admin":     "CLERK_TEST_USER_ADMIN",
    "security":  "CLERK_TEST_USER_SECURITY",
    "developer": "CLERK_TEST_USER_DEVELOPER",
    "viewer":    "CLERK_TEST_USER_VIEWER",
}

# Deterministic UUIDs so the seed is idempotent AND the Playwright specs
# can hard-code these in URLs (/workflows/<E2E_WORKFLOW_ID> etc.).
E2E_WORKFLOW_ID = uuid.UUID("22222222-2222-2222-2222-000000000001")
E2E_MCP_SERVER_ID = uuid.UUID("22222222-2222-2222-2222-000000000002")
E2E_INTEGRATION_ID = uuid.UUID("22222222-2222-2222-2222-000000000003")
E2E_CUSTOM_RULE_ID = "e2e-block-rm-rf"


def _upsert_member(db, workspace_id: str, clerk_user_id: str, role: str, now):
    row = (
        db.query(WorkspaceUser)
        .filter_by(workspace_id=workspace_id, clerk_user_id=clerk_user_id)
        .one_or_none()
    )
    if row is None:
        db.add(WorkspaceUser(
            workspace_id=workspace_id,
            clerk_user_id=clerk_user_id,
            role=role,
            joined_at=now,
        ))
    elif row.role != role:
        row.role = role


def _seed_workflow(db, now) -> None:
    if db.get(Workflow, E2E_WORKFLOW_ID):
        return
    db.add(Workflow(
        id=E2E_WORKFLOW_ID,
        workspace_id=DEV_WORKSPACE_ID,
        name="e2e-sample-workflow",
        default_mode="dag",
        playbook_slug="autopilot",
        guard_enabled=True,
        created_at=now,
        updated_at=now,
    ))


def _seed_custom_rule(db, now) -> None:
    key = (DEV_WORKSPACE_ID, E2E_CUSTOM_RULE_ID)
    if db.get(WorkspaceCustomRule, key):
        return
    db.add(WorkspaceCustomRule(
        workspace_id=DEV_WORKSPACE_ID,
        rule_id=E2E_CUSTOM_RULE_ID,
        persona="agent",
        body={
            "id": E2E_CUSTOM_RULE_ID,
            "match_pattern": r"rm\s+-rf\s+/",
            "action": "block",
            "message": "Recursive delete of / blocked by e2e seed rule.",
            "severity": "high",
        },
        enabled=True,
        created_by=DEV_USER_ID,
        created_at=now,
        updated_at=now,
    ))


def _seed_mcp_server(db, now) -> None:
    if db.get(McpServer, E2E_MCP_SERVER_ID):
        return
    db.add(McpServer(
        id=E2E_MCP_SERVER_ID,
        workspace_id=DEV_WORKSPACE_ID,
        name="e2e-mcp",
        url="https://mcp.example.local/",
        transport="http",
        is_system=False,
    ))


def _seed_integration(db, now) -> None:
    if db.get(Integration, E2E_INTEGRATION_ID):
        return
    db.add(Integration(
        id=E2E_INTEGRATION_ID,
        workspace_id=DEV_WORKSPACE_ID,
        service="github",
        auth_method="api_key",
        handle="e2e-github",
        encrypted_credentials=None,  # placeholder; no real secret needed for UI presence tests
        created_at=now,
    ))


def main() -> int:
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        ws = db.get(Workspace, DEV_WORKSPACE_ID)
        if ws is None:
            db.add(Workspace(
                id=DEV_WORKSPACE_ID,
                name="e2e-dev",
                owner_id=DEV_USER_ID,
                plan="free",
                is_approved=True,
                created_at=now,
                updated_at=now,
            ))

        _upsert_member(db, DEV_WORKSPACE_ID, DEV_USER_ID, "admin", now)

        seeded_roles: list[str] = []
        for role, env_key in CLERK_ROLE_ENV.items():
            uid = os.environ.get(env_key)
            if not uid:
                continue
            _upsert_member(db, DEV_WORKSPACE_ID, uid, role, now)
            seeded_roles.append(f"{role}={uid[:12]}…")

        _seed_workflow(db, now)
        _seed_custom_rule(db, now)
        _seed_mcp_server(db, now)
        _seed_integration(db, now)

        db.commit()

    line = f"Seeded {DEV_WORKSPACE_ID} + admin({DEV_USER_ID}) + workflow/rule/mcp/integration"
    if seeded_roles:
        line += f" + Clerk users [{', '.join(seeded_roles)}]"
    print(line, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
