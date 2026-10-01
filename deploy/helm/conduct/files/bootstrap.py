"""Create the configured first workspace and explicitly map its administrator."""
import os
from uuid import UUID

from sqlalchemy import text

from app.core.database import SessionLocal
from app.models.workspace import Workspace
from app.modules.auth.console.bootstrap import provision
from app.modules.auth.console.session import configured_trust


def main():
    workspace_id = UUID(os.environ["BOOTSTRAP_WORKSPACE_ID"])
    trust = configured_trust()
    with SessionLocal.begin() as db:
        db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                   {"key": "conduct-chart-bootstrap:" + str(workspace_id)})
        workspace = db.get(Workspace, workspace_id)
        created = workspace is None
        if created:
            workspace = Workspace(id=workspace_id, name=os.environ["BOOTSTRAP_WORKSPACE_NAME"],
                                  plan="free", is_approved=True)
            db.add(workspace)
            db.flush()
        user = provision(db, issuer=trust.issuer, subject=os.environ["BOOTSTRAP_ADMIN_SUBJECT"],
                         workspace_id=workspace_id, role="admin",
                         display_name=os.environ.get("BOOTSTRAP_ADMIN_NAME") or None)
        if created:
            workspace.owner_id = user
    print("Workspace and administrator ready")


if __name__ == "__main__":
    main()
