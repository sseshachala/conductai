"""Real DB console authorization checks. Signed fixtures, not a live OIDC login."""
import json
import time
from uuid import uuid4
from unittest.mock import patch

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

import phase2_harness


def main():
    fixture = phase2_harness.main()
    from app.core import auth
    from app.core.config import settings
    from app.core.database import SessionLocal
    from app.core.auth_deployment import validate_api_auth
    from app.modules.auth.console.bootstrap import provision
    from app.modules.auth.console.models import ConsoleIdentityMapping
    from app.modules.auth.console import router as exchange
    from app.modules.auth.console.trust import verify_proxy_identity
    from app.modules.auth.federation.verifier import KeyCache

    settings.auth_mode = "proxy"
    settings.clerk_secret_key = settings.clerk_frontend_api = ""
    settings.console_oidc_issuer = "https://keycloak.console.test/realms/" + uuid4().hex
    settings.console_oidc_client_id = "conduct-console"
    settings.console_oidc_jwks_url = settings.console_oidc_issuer + "/protocol/openid-connect/certs"
    # Random process-local fixture; never printed or persisted.
    import secrets
    settings.console_proxy_secret = secrets.token_urlsafe(48)
    validate_api_auth(settings)
    ws, other = str(fixture["workspace"]), str(fixture["other"])
    with SessionLocal.begin() as db:
        alice = provision(db, issuer=settings.console_oidc_issuer, subject="alice", workspace_id=fixture["workspace"], role="admin")
        bob = provision(db, issuer=settings.console_oidc_issuer, subject="bob", workspace_id=fixture["workspace"], role="viewer")
    with SessionLocal.begin() as db:
        assert provision(db, issuer=settings.console_oidc_issuer, subject="alice", workspace_id=fixture["workspace"], role="admin") == alice

    app = FastAPI()
    app.include_router(exchange.router)

    @app.get("/identity")
    def identity(user=Depends(auth.get_user_id), workspace=Depends(auth.get_workspace_id)):
        return {"user": user, "workspace": workspace}

    @app.get("/admin")
    def admin_only(role=Depends(auth.require_permission("guard.settings.edit"))):
        return {"role": role}

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = {**json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key())), "kid": "console-harness"}
    cache = KeyCache(fetch=lambda _: {"keys": [jwk]})

    def evidence(subject):
        now = int(time.time())
        return jwt.encode({"iss": settings.console_oidc_issuer, "aud": settings.console_oidc_client_id,
                           "azp": settings.console_oidc_client_id, "sub": subject, "typ": "ID",
                           "iat": now, "exp": now + 300}, key, algorithm="RS256", headers={"kid": "console-harness"})

    with patch.object(exchange, "verify_proxy_identity", side_effect=lambda token, trust: verify_proxy_identity(token, trust, cache=cache)), TestClient(app) as client:
        def login(subject):
            return client.post("/auth/console/session", json={"identity_token": evidence(subject)},
                               headers={"X-Conduct-Proxy-Secret": settings.console_proxy_secret})

        a, b = login("alice"), login("bob")
        assert a.status_code == b.status_code == 200
        def headers(response):
            return {"Authorization": "Bearer " + response.json()["token"], "X-Workspace-Id": ws}
        assert client.get("/identity", headers=headers(a)).json() == {"user": alice, "workspace": ws}
        assert client.get("/identity", headers=headers(b)).json() == {"user": bob, "workspace": ws}
        assert client.get("/admin", headers=headers(a)).status_code == 200
        assert client.get("/admin", headers=headers(b)).status_code == 403
        assert client.get("/identity", headers={**headers(a), "X-Workspace-Id": other}).status_code == 403
        assert client.get("/identity", headers={"X-Auth-User": alice}).status_code == 401
        assert client.get("/identity", headers={"Authorization": "Bearer " + evidence("alice")}).status_code == 401
        assert login("unprovisioned").status_code == 403
        assert client.get("/admin", headers=fixture["headers"]).status_code == 200
        assert client.get("/admin", headers=fixture["developer_headers"]).status_code == 403
        # Real CLI token exchange and OAuth consent/code redemption, no auth mocks.
        from app.modules.auth.oauth.grants import token_exchange, authorization_code
        from app.modules.auth.oauth.authorize import start_authorize, confirm_authorize, ConfirmRequest
        from app.models.oauth import OauthClient
        from urllib.parse import urlsplit, parse_qs
        import os
        import base64
        import hashlib

        os.environ["CONDUCT_WEB_URL"] = "https://console.test"
        verifier = secrets.token_urlsafe(48)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
        client_id = "console-test-" + uuid4().hex
        redirect_uri = "http://127.0.0.1:8765/callback"
        with SessionLocal() as db:
            exchanged = token_exchange.handle(a.json()["token"], "urn:ietf:params:oauth:token-type:jwt", ws, db)
            assert exchanged["access_token"].startswith("cond_agt_")
            assert exchanged["refresh_token"].startswith("cond_ref_")
            db.add(OauthClient(client_id=client_id, client_name="Console harness", redirect_uris=[redirect_uri]))
            db.commit()
            consent_url = start_authorize(response_type="code", client_id=client_id,
                redirect_uri=redirect_uri, code_challenge=challenge, code_challenge_method="S256",
                state="fixture-state", scope=None, db=db)
            request_id = parse_qs(urlsplit(consent_url).query)["request_id"][0]
            confirmation = confirm_authorize(ConfirmRequest(request_id=request_id,
                clerk_token=a.json()["token"], workspace_id=ws), db)
            code = parse_qs(urlsplit(confirmation["redirect_url"]).query)["code"][0]
            oauth = authorization_code.handle(code, verifier, client_id, redirect_uri, db)
            assert oauth["access_token"].startswith("cond_agt_")
        assert client.get("/identity", headers={"Authorization": "Bearer " + oauth["access_token"],
                                               "X-Workspace-Id": ws}).json() == {"user": alice, "workspace": ws}
        with SessionLocal.begin() as db:
            db.query(ConsoleIdentityMapping).filter_by(user_id=bob).one().active = False
        assert client.get("/identity", headers=headers(b)).status_code == 401
        assert login("bob").status_code == 403

    print("PASS: console exchange, explicit provisioning, idempotency, admin/viewer roles, tenant isolation, mapping revocation, machine compatibility, CLI exchange, OAuth consent/PKCE redemption")
    print("Signing-key transport injected; this is not a live Keycloak/oauth2-proxy browser test.")


if __name__ == "__main__":
    main()
