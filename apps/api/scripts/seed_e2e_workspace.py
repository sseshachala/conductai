#!/usr/bin/env python3
"""Seed DEV_WORKSPACE_ID + admin membership so Playwright golden flows have a
real workspace to poke at. Idempotent. Uses ORM (no raw SQL)."""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.auth import DEV_USER_ID, DEV_WORKSPACE_ID  # noqa: E402
from app.core.database import SessionLocal  # noqa: E402
from app.models.workspace import Workspace  # noqa: E402
from app.models.workspace_user import WorkspaceUser  # noqa: E402


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

        wu = (
            db.query(WorkspaceUser)
            .filter_by(workspace_id=DEV_WORKSPACE_ID, clerk_user_id=DEV_USER_ID)
            .one_or_none()
        )
        if wu is None:
            db.add(WorkspaceUser(
                workspace_id=DEV_WORKSPACE_ID,
                clerk_user_id=DEV_USER_ID,
                role="admin",
                joined_at=now,
            ))

        db.commit()
    print(f"Seeded {DEV_WORKSPACE_ID} + admin membership for {DEV_USER_ID}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
