#!/usr/bin/env python3
"""Seed DEV_WORKSPACE_ID + admin membership so Playwright golden flows have a
real workspace to poke at. Also seeds the 4 Clerk sandbox users (admin,
security, developer, viewer) when their IDs are present in the env, so the
per-role flow suite has real workspace_users rows to authenticate against.
Idempotent. Uses ORM (no raw SQL)."""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.auth import DEV_USER_ID, DEV_WORKSPACE_ID  # noqa: E402
from app.core.database import SessionLocal  # noqa: E402
from app.models.workspace import Workspace  # noqa: E402
from app.models.workspace_user import WorkspaceUser  # noqa: E402


# Env keys the CI job / .env.test set. Missing IDs are OK — the role just
# gets skipped (useful for the admin-only lane before Clerk sandbox exists).
CLERK_ROLE_ENV = {
    "admin":     "CLERK_TEST_USER_ADMIN",
    "security":  "CLERK_TEST_USER_SECURITY",
    "developer": "CLERK_TEST_USER_DEVELOPER",
    "viewer":    "CLERK_TEST_USER_VIEWER",
}


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

        # Dev-mode admin (used by admin-only smoke, no Clerk).
        _upsert_member(db, DEV_WORKSPACE_ID, DEV_USER_ID, "admin", now)

        # Clerk sandbox users, one per role. Missing env → skip.
        seeded_roles: list[str] = []
        for role, env_key in CLERK_ROLE_ENV.items():
            uid = os.environ.get(env_key)
            if not uid:
                continue
            _upsert_member(db, DEV_WORKSPACE_ID, uid, role, now)
            seeded_roles.append(f"{role}={uid}")

        db.commit()

    line = f"Seeded {DEV_WORKSPACE_ID} + admin membership for {DEV_USER_ID}"
    if seeded_roles:
        line += f" + Clerk users [{', '.join(seeded_roles)}]"
    print(line, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
