"""Provision two real IdP subjects in an isolated browser-test database only."""
import os
import subprocess
from uuid import UUID

if os.environ.get("DATABASE_URL") != "postgresql://postgres@postgres/conduct_console_e2e":
    raise SystemExit("Refusing to provision a non-test database")

admin = os.environ["TEST_ADMIN_SUBJECT"]
viewer = os.environ["TEST_VIEWER_SUBJECT"]
if admin == viewer or not admin.strip() or not viewer.strip():
    raise SystemExit("Two distinct real IdP subjects are required")

subprocess.run(["alembic", "upgrade", "head"], check=True)

from app.core.database import SessionLocal
from app.models.workspace import Workspace
from app.modules.auth.console.bootstrap import provision

# Stable local fixture, not a production workspace or customer identifier.
workspace_id = UUID("bbbbbbbb-0000-4000-8000-000000000001")
with SessionLocal.begin() as db:
    workspace = db.get(Workspace, workspace_id)
    if workspace is None:
        workspace = Workspace(id=workspace_id, name="Console browser acceptance",
                              plan="free", is_approved=True)
        db.add(workspace)
        db.flush()
    for subject, role in ((admin, "admin"), (viewer, "viewer")):
        user_id = provision(db, issuer=os.environ["CONSOLE_OIDC_ISSUER"], subject=subject,
                            workspace_id=workspace_id, role=role, display_name="Console " + role)
        if role == "admin":
            workspace.owner_id = user_id
print("Local admin/viewer provisioned. No other identity was provisioned.")
