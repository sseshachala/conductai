"""Real PostgreSQL + ASGI requests, with production auth and no dependency overrides.

Run from apps/api with PYTHONPATH=. against a migrated disposable database named
conduct_federation_test on loopback. Never point this at an existing workspace DB.
"""
import os
import secrets
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.engine import make_url


def main():
    url = make_url(os.environ["DATABASE_URL"])
    if url.host not in ("127.0.0.1", "localhost") or url.database != "conduct_federation_test":
        raise SystemExit("Only the disposable loopback federation database is allowed")
    # Enable real credential validation; these synthetic values never call Clerk.
    os.environ["CLERK_SECRET_KEY"] = "synthetic-harness-only"
    os.environ["CLERK_FRONTEND_API"] = "synthetic.invalid"
    os.environ["ENCRYPTION_KEY"] = secrets.token_hex(32)

    import app.models  # noqa: F401
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError
    from app.core.crypto import encrypt
    from app.core.database import SessionLocal
    from app.models.audit_log import AuditLog
    from app.models.integration import Integration
    from app.models.workspace import Workspace
    from app.models.workspace_user import WorkspaceUser
    from app.modules.agent_identity.models import AgentIdentity
    from app.modules.guard.models import GuardMemberConfig
    from app.modules.auth.federation.models import FederationConnection
    from app.modules.auth.federation.router import router

    ws, other, integration, foreign = (uuid4() for _ in range(4))
    developer = "synthetic-federation-developer-" + uuid4().hex
    admin_token = "cond_api_" + secrets.token_hex(32)
    developer_token = "cond_agt_" + secrets.token_hex(32)
    developer_agent = str(uuid4())
    with SessionLocal() as db:
        assert db.execute(text("SELECT version_num FROM alembic_version")).scalar() == "0154"
        db.add_all([Workspace(id=ws, name="Federation harness"),
                    Workspace(id=other, name="Foreign harness")])
        db.flush()
        db.add_all([Integration(id=integration, workspace_id=ws, service="generic", auth_method="oidc", handle="fixture"),
                    Integration(id=foreign, workspace_id=other, service="generic", auth_method="oidc", handle="fixture")])
        for token, kind, identity in [(admin_token, "api", str(uuid4())),
                                      (developer_token, "cli", developer_agent)]:
            db.add(AgentIdentity(id=identity, workspace_id=ws, name="Synthetic harness",
                                 token_prefix=token[:13], token_encrypted=encrypt({"token": token}),
                                 token_type=kind, created_at=datetime.now(timezone.utc)))
        db.add(WorkspaceUser(workspace_id=ws, clerk_user_id=developer, role="developer"))
        db.flush()
        db.add(GuardMemberConfig(workspace_id=ws, clerk_user_id=developer,
                                 member_token="synthetic-unused", agent_identity_id=developer_agent))
        db.commit()

    app = FastAPI()
    app.include_router(router)
    assert not app.dependency_overrides
    path = f"/workspaces/{ws}/integrations/{integration}/federation"
    config = {"issuer": "https://issuer.example", "jwks_uri": "https://issuer.example/keys",
              "audience": "conduct-test", "token_profile": "at+jwt"}
    headers = {"Authorization": "Bearer " + admin_token, "X-Workspace-Id": str(ws)}
    payload = {"expected_revision": 0, "config": config}
    with TestClient(app) as client:
        assert client.get(path).status_code == 401
        assert client.get(path, headers=headers).status_code == 404
        denied = dict(headers, Authorization="Bearer " + developer_token)
        assert client.put(path, headers=denied, json=payload).status_code == 403
        response = client.put(path, headers=headers, json=payload)
        assert response.status_code == 200, response.text
        saved = response.json()
        assert saved["revision"] == 1 and saved["config"]["status"] == "draft"
        assert client.get(path, headers=headers).json() == saved
        assert client.put(path, headers=headers, json=payload).status_code == 409
        assert client.get(path.replace(str(ws), str(other)), headers=headers).status_code == 403
        assert client.get(path.replace(str(integration), str(foreign)), headers=headers).status_code == 404
        assert client.put(path, headers=headers, json={"expected_revision": 1,
                          "config": dict(config, status="active")}).status_code == 422
        updated = client.put(path, headers=headers, json={"expected_revision": 1,
                             "config": dict(config, status="disabled")})
        assert updated.status_code == 200 and updated.json()["revision"] == 2
        assert client.get(path, headers=denied).status_code == 403

    with SessionLocal() as db:
        logs = db.query(AuditLog).filter(AuditLog.workspace_id == ws,
                                        AuditLog.action == "federation.config.saved").all()
        assert len(logs) == 2
        assert {row.meta["revision"] for row in logs} == {1, 2}
        db.add(FederationConnection(workspace_id=ws, integration_id=foreign, config=config, revision=1))
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
        else:
            raise AssertionError("Database accepted a cross-workspace integration")
    print("PASS: real auth, developer denial, tenant boundaries, revisions, audit, and database constraint")
    print("Synthetic rows retained only in the disposable database; stop its container after testing.")


if __name__ == "__main__":
    main()
