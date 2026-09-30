"""Management API lifecycle with real auth, PostgreSQL and HTTP routing."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

import phase2_harness


def main():
    fixture = phase2_harness.main()
    from app.modules.auth.federation.router import router
    from app.modules.auth.federation.management import router as management
    from app.modules.auth.federation.delegation_router import router as delegation
    app = FastAPI()
    for route in (router, management, delegation):
        app.include_router(route)
    ws, headers = fixture["workspace"], fixture["headers"]
    base = f"/workspaces/{ws}/federation"
    with TestClient(app) as client:
        assert client.get(base + "/overview").status_code == 401
        assert client.get(base + "/overview", headers=fixture["developer_headers"]).status_code == 403
        assert client.get(base.replace(str(ws), str(fixture["other"])) + "/overview", headers=headers).status_code == 403
        payload = {"name": "External production", "config": fixture["config"]}
        assert client.post(base + "/connections", headers=fixture["developer_headers"], json=payload).status_code == 403
        result = client.post(base + "/connections", headers=headers, json=payload)
        assert result.status_code == 201, result.text
        connection = result.json()
        assert connection["config"]["integration_type"] == "generic"
        assert connection["config"]["status"] == "draft"
        assert client.post(base + "/connections", headers=headers, json=payload).status_code == 409
        assert client.post(base + "/connections", headers=headers, json={
            "name": "Unsafe active create", "config": dict(fixture["config"], status="active"),
        }).status_code == 422
        path = f"/workspaces/{ws}/integrations/{connection['integration_id']}/federation"
        # Public-endpoint restrictions are reused by validation, not bypassed by admin UI.
        private = {**connection["config"], "jwks_uri": "https://127.0.0.1/keys"}
        response = client.put(path, headers=headers, json={"expected_revision": 1, "config": private})
        assert response.status_code == 200
        check = client.post(path + "/validate", headers=headers, json={"expected_revision": 2, "config": private})
        assert check.status_code == 422, check.text
        assert "federation_endpoint_not_public" in check.text
        assert client.get(path, headers=headers).json()["config"]["status"] == "draft"
        # Only JWKS transport is synthetic; management/auth/database paths remain real.
        import json
        import jwt
        from unittest.mock import patch
        from cryptography.hazmat.primitives.asymmetric import rsa
        from app.modules.auth.federation.verifier import KeyCache
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        jwk = {**json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key())), "kid": "fixture"}
        with patch("app.modules.auth.federation.verifier.KeyCache", lambda: KeyCache(fetch=lambda _: {"keys": [jwk]})):
            check = client.post(path + "/validate", headers=headers, json={"expected_revision": 2, "config": private})
            assert check.status_code == 200 and check.json()["signing_keys"] == 1
            assert client.post(path + "/validate", headers=fixture["developer_headers"],
                               json={"expected_revision": 2, "config": private}).status_code == 403
            assert client.post(path + "/validate", headers=headers,
                               json={"expected_revision": 1, "config": private}).status_code == 409
        assert client.get(path, headers=headers).json()["config"]["status"] == "draft"
        active = {**connection["config"], "status": "active"}
        response = client.put(path, headers=headers, json={"expected_revision": 2, "config": active})
        assert response.status_code == 200
        assert client.put(path, headers=headers, json={"expected_revision": 2, "config": active}).status_code == 409
        principal, binding, grant = (str(uuid4()) for _ in range(3))
        approval = {"expected_revision": 0, "status": "active", "actions": ["mcp.guard_check_prompt"]}
        principal_body = {**approval, "issuer": active["issuer"], "subject": "synthetic-subject", "kind": "human"}
        binding_body = {**approval, "caller_id": fixture["caller_id"], "connection_id": connection["id"]}
        grant_body = {**approval, "binding_id": binding, "principal_id": principal,
                      "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()}
        for kind, identifier, body in (("principals", principal, principal_body), ("bindings", binding, binding_body), ("grants", grant, grant_body)):
            response = client.put(f"{base}/{kind}/{identifier}", headers=headers, json=body)
            assert response.status_code == 200, response.text
        overview = client.get(base + "/overview", headers=headers).json()
        assert len(overview["connections"]) == 2 and len(overview["principals"]) == 1
        assert overview["grants"][0]["id"] == grant
        assert overview["principals"][0]["display_name"] is None
        principal_path = f"{base}/principals/{principal}"
        renamed = client.put(principal_path, headers=headers, json={
            **principal_body, "expected_revision": 1, "display_name": " Alice Test "})
        assert renamed.status_code == 200 and renamed.json()["display_name"] == "Alice Test"
        assert client.get(base + "/overview", headers=headers).json()["principals"][0]["display_name"] == "Alice Test"
        # An old client can still update approvals without deleting the label.
        legacy = client.put(principal_path, headers=headers, json={**principal_body, "expected_revision": 2})
        assert legacy.status_code == 200 and legacy.json()["display_name"] == "Alice Test"
        assert client.put(principal_path, headers=headers, json={
            **principal_body, "expected_revision": 3, "subject": "changed", "display_name": "Other"}).status_code == 409
        assert client.put(principal_path, headers=fixture["developer_headers"], json={
            **principal_body, "expected_revision": 3, "display_name": "Other"}).status_code == 403
        cleared = client.put(principal_path, headers=headers, json={
            **principal_body, "expected_revision": 3, "display_name": ""})
        assert cleared.status_code == 200 and cleared.json()["display_name"] is None
        assert all(set(c) == {"id", "name"} for c in overview["callers"])
        assert "encrypted_credentials" not in str(overview) and "token_prefix" not in str(overview)
        result = client.put(f"{base}/grants/{grant}", headers=headers,
                            json={**grant_body, "expected_revision": 1, "status": "disabled"})
        assert result.status_code == 200
        assert client.get(base + "/overview", headers=headers).json()["grants"][0]["status"] == "disabled"
    print("PASS: generic OIDC management, admin-only access, tenant isolation, draft lifecycle, SSRF rejection, revisions, delegation and revocation")


if __name__ == "__main__":
    main()
