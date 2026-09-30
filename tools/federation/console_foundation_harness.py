"""Real DB/auth checks for #2297; no proxy login or external IdP is simulated as success."""
from datetime import datetime, timedelta, timezone
import json
from unittest.mock import patch
from uuid import uuid4

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

import phase2_harness


def main():
    # Reuse the disposable DB safety gate and real encrypted machine credentials.
    fixture = phase2_harness.main()
    from app.core import auth
    from app.core.auth_deployment import validate_api_auth, validate_auth_mode
    from app.core.config import settings
    from app.core.database import SessionLocal
    from app.core.stream_auth import get_workspace_id_sse, get_user_workspace_role_sse
    from app.models.workspace_user import WorkspaceUser

    ws, other = str(fixture["workspace"]), str(fixture["other"])
    admin, viewer = "console-admin-" + uuid4().hex, "console-viewer-" + uuid4().hex
    with SessionLocal() as db:
        db.add_all([WorkspaceUser(workspace_id=ws, clerk_user_id=admin, role="admin"),
                    WorkspaceUser(workspace_id=ws, clerk_user_id=viewer, role="viewer")])
        db.commit()

    app = FastAPI()

    @app.get("/identity")
    def identity(user=Depends(auth.get_user_id), workspace=Depends(auth.get_workspace_id)):
        return {"user": user, "workspace": workspace}

    @app.get("/admin")
    def admin_only(role=Depends(auth.require_permission("guard.settings.edit"))):
        return {"role": role}

    @app.get("/stream-auth")
    def stream_auth(workspace=Depends(get_workspace_id_sse), role=Depends(get_user_workspace_role_sse)):
        return {"workspace": workspace, "role": role}

    assert not app.dependency_overrides
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = {**json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key())), "kid": "console-fixture"}
    settings.auth_mode = "clerk"
    settings.environment = "production"
    settings.clerk_audience = "console-fixture"
    issuer = "https://" + settings.clerk_frontend_api

    def credential(subject, **overrides):
        now = datetime.now(timezone.utc)
        claims = {"sub": subject, "iss": issuer, "aud": settings.clerk_audience,
                  "iat": now, "exp": now + timedelta(minutes=5), **overrides}
        return jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": "console-fixture"})

    def headers(subject, **overrides):
        return {"Authorization": "Bearer " + credential(subject, **overrides), "X-Workspace-Id": ws}

    # Only public-key transport is substituted; signature/auth/DB/RBAC are real.
    with patch.object(auth, "_get_jwks", return_value={"keys": [public_key]}), TestClient(app) as client:
        validate_api_auth(settings)
        assert client.get("/identity").status_code == 401
        assert client.get("/identity", headers={"X-Auth-User": admin, "X-Workspace-Id": ws}).status_code == 401
        result = client.get("/identity", headers=headers(viewer))
        assert result.status_code == 200 and result.json() == {"user": viewer, "workspace": ws}
        assert client.get("/admin", headers=headers(admin)).status_code == 200
        assert client.get("/admin", headers=headers(viewer)).status_code == 403
        assert client.get("/identity", headers={**headers(admin), "X-Workspace-Id": other}).status_code == 403
        for invalid in ({"aud": "wrong"}, {"iss": "https://wrong.invalid"},
                        {"exp": datetime.now(timezone.utc) - timedelta(minutes=5)}):
            assert client.get("/identity", headers=headers(viewer, **invalid)).status_code == 401
        assert client.get("/admin", headers=fixture["headers"]).status_code == 200
        assert client.get("/admin", headers=fixture["developer_headers"]).status_code == 403
        stream = client.get("/stream-auth", params={"token": credential(viewer), "workspace_id": ws,
                                                   "api_key": "forged"})
        assert stream.status_code == 200 and stream.json()["role"] == "viewer"
        machine = fixture["headers"]["Authorization"][7:]
        assert client.get("/stream-auth", params={"token": machine, "workspace_id": other}).status_code == 403

        # Missing console credentials is never a development/admin fallback.
        settings.clerk_secret_key = settings.clerk_frontend_api = ""
        validate_auth_mode(settings)  # Worker imports remain valid.
        try:
            validate_api_auth(settings)
        except ValueError:
            pass
        else:
            raise AssertionError("API startup accepted missing Clerk configuration")
        assert client.get("/identity").status_code == 401
        assert client.get("/stream-auth", params={"workspace_id": ws}).status_code == 401
        assert client.get("/admin", headers=fixture["headers"]).status_code == 200

    print("PASS: console foundation, signed Clerk fixtures, real DB roles, machine compatibility, HTTP/SSE isolation, fail-closed configuration")
    print("Not a proxy/Keycloak login test; no external provider or production workspace contacted.")


if __name__ == "__main__":
    main()
