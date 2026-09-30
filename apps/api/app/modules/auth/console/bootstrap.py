"""Privileged deployment provisioning; never called by a browser login."""
import argparse
from uuid import UUID, uuid4

from sqlalchemy import text

from app.core.database import SessionLocal
from app.models.audit_log import AuditLog
from app.models.workspace import Workspace
from app.models.workspace_user import WorkspaceUser
from .models import ConsoleIdentityMapping
from .session import configured_trust


def provision(db, *, issuer: str, subject: str, workspace_id: UUID, role: str,
              display_name: str | None = None) -> str:
    from app.core.auth import get_valid_roles

    if not subject.strip() or len(subject) > 255:
        raise ValueError("A nonempty subject of at most 255 characters is required")
    if role not in get_valid_roles(db):
        raise ValueError("Unknown Conduct role")
    if db.get(Workspace, workspace_id) is None:
        raise ValueError("Workspace must already exist")
    # Serialize provisioning for a subject so concurrent bootstrap commands are idempotent.
    db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:identity, 0))"),
               {"identity": issuer + "\n" + subject})
    row = db.query(ConsoleIdentityMapping).filter_by(issuer=issuer, subject=subject).first()
    if row is None:
        row = ConsoleIdentityMapping(issuer=issuer, subject=subject, user_id="oidc_" + uuid4().hex,
                                     display_name=display_name, active=True)
        db.add(row)
        db.flush()
    elif not row.active:
        raise ValueError("Identity disabled; bootstrap will not reactivate it")
    membership = db.get(WorkspaceUser, (workspace_id, row.user_id))
    if membership is None:
        db.add(WorkspaceUser(workspace_id=workspace_id, clerk_user_id=row.user_id, role=role,
                             invited_by="deployment-bootstrap"))
    elif membership.role != role:
        raise ValueError("Existing role differs; change it through Conduct membership management")
    db.add(AuditLog(workspace_id=workspace_id, actor_id="deployment-bootstrap",
                    action="console.identity.provisioned", resource_type="console_identity",
                    resource_id=str(row.id), meta={"user_id": row.user_id, "role": role}))
    return row.user_id


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--subject", required=True)
    parser.add_argument("--workspace-id", type=UUID, required=True)
    parser.add_argument("--role", required=True)
    parser.add_argument("--name", default=None)
    args = parser.parse_args()
    trust = configured_trust()
    with SessionLocal.begin() as db:
        user_id = provision(db, issuer=trust.issuer, subject=args.subject,
                            workspace_id=args.workspace_id, role=args.role, display_name=args.name)
    print(f"Console identity provisioned: {user_id}")


if __name__ == "__main__":
    main()
