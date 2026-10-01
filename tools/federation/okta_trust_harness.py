"""Migration and restricted-role Okta trust checks on a disposable database.

Run from apps/api with PYTHONPATH=. and DATABASE_URL pointing to a fresh,
loopback conduct_federation_test database. No external IdP is contacted.
"""
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session


def main():
    url = make_url(os.environ["DATABASE_URL"])
    if url.host not in ("127.0.0.1", "localhost") or url.database != "conduct_federation_test":
        raise SystemExit("Requires disposable loopback conduct_federation_test database")
    api = Path(__file__).resolve().parents[2] / "apps/api"

    def migrate(direction, revision, success=True):
        result = subprocess.run([sys.executable, "-m", "alembic", direction, revision],
                                cwd=api, capture_output=True, text=True, timeout=120)
        assert (result.returncode == 0) == success, result.stderr
        return result

    migrate("upgrade", "0157")
    engine = create_engine(url)
    ws, other = uuid4(), uuid4()
    enabled, disabled, incomplete = uuid4(), uuid4(), uuid4()
    issuer = "https://fixture.okta.example/oauth2/default"
    with engine.begin() as db:
        assert db.execute(text("SELECT count(*) FROM integrations")).scalar_one() == 0, "Use a fresh database"
        for workspace in (ws, other):
            db.execute(text("INSERT INTO workspaces (id, name) VALUES (:id, 'Okta trust fixture')"), {"id": workspace})
        for identifier, workspace, audience, active in [
            (enabled, ws, "api://fixture", True), (disabled, other, "api://disabled", False),
            (incomplete, ws, None, True),
        ]:
            db.execute(text("""INSERT INTO integrations
                (id, workspace_id, service, auth_method, handle, okta_issuer, okta_audience, okta_auth_enabled)
                VALUES (:id, :ws, 'okta', 'api_key', 'okta', :issuer, :aud, :active)"""),
                       {"id": identifier, "ws": workspace, "issuer": issuer, "aud": audience, "active": active})
        db.execute(text("""INSERT INTO federation_connections
            (id, workspace_id, integration_id, revision, config, created_at, updated_at)
            VALUES (:id, :ws, :integration, 7, '{"status":"disabled"}', now(), now())"""),
                   {"id": uuid4(), "ws": ws, "integration": enabled})

    migrate("upgrade", "0158")
    migrate("upgrade", "0158")
    with engine.begin() as db:
        rows = db.execute(text("SELECT integration_id, config, revision FROM federation_connections "
                               "WHERE authentication_mode='okta_agent'" )).all()
        saved = {row.integration_id: row for row in rows}
        assert len(saved) == 3
        assert saved[enabled].config["status"] == "active"
        assert saved[disabled].config["status"] == "disabled"
        assert saved[incomplete].config["status"] == "needs_review"
        assert saved[incomplete].config["requested_enabled"] is True
        db.execute(text("UPDATE integrations SET okta_auth_enabled=okta_auth_enabled WHERE handle='okta'"))
        assert db.execute(text("SELECT max(revision) FROM federation_connections "
                               "WHERE authentication_mode='okta_agent'")).scalar_one() == 1
        assert db.execute(text("SELECT revision FROM federation_connections "
                               "WHERE authentication_mode='delegated'")).scalar_one() == 7
        if not db.execute(text("SELECT 1 FROM pg_roles WHERE rolname='okta_trust_runtime'")).scalar():
            db.execute(text("CREATE ROLE okta_trust_runtime NOLOGIN"))
        db.execute(text("GRANT USAGE ON SCHEMA public TO okta_trust_runtime"))
        db.execute(text("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO okta_trust_runtime"))
        db.execute(text("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO okta_trust_runtime"))

    runtime = create_engine(url)

    @event.listens_for(runtime, "connect")
    def use_runtime(connection, _):
        with connection.cursor() as cursor:
            cursor.execute("SET ROLE okta_trust_runtime")
        connection.commit()

    import app.models  # noqa: F401
    from app.modules.auth.federation.okta_agent import candidates, connection, workspace_scope
    from app.models.integration import Integration
    from app.modules.agent_identity.models import AgentIdentity
    from app.core.auth import _resolve_okta_jwt
    from app.core import okta_jwt
    from fastapi import HTTPException
    import jwt
    from cryptography.hazmat.primitives.asymmetric import rsa
    import json

    with Session(runtime) as db:
        assert db.execute(text("SELECT row_security_active('federation_connections')")).scalar_one()
        assert db.execute(text("SELECT count(*) FROM federation_connections")).scalar_one() == 0
        assert len(candidates(db, issuer)) == 3
        assert db.execute(text("SELECT count(*) FROM federation_connections")).scalar_one() == 0
        with workspace_scope(db, ws):
            assert db.execute(text("SELECT count(*) FROM federation_connections WHERE workspace_id=:ws"),
                              {"ws": other}).scalar_one() == 0
        row = db.get(Integration, enabled)
        row.okta_audience = "api://changed"
        db.flush()
        assert connection(db, row).config["audience"] == "api://changed"
        assert connection(db, row).revision == 2
        db.rollback()
        db.execute(text("DELETE FROM integrations WHERE id=:id"), {"id": disabled})
        with workspace_scope(db, other):
            assert db.execute(text("SELECT count(*) FROM federation_connections WHERE integration_id=:id"),
                              {"id": disabled}).scalar_one() == 0
        db.rollback()

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = dict(json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key())), kid="fixture")
    # Only JWKS transport is replaced; the real verifier still checks signatures.
    from unittest.mock import patch

    with Session(runtime) as db:
        db.add(AgentIdentity(id=str(uuid4()), workspace_id=ws, name="Okta fixture", source="okta",
                             source_id="agent", token_type="external", token_prefix="fixture",
                             token_encrypted="unused", lifecycle_state="active", created_at=datetime.now(timezone.utc)))
        db.commit()

    # Auth checks below use the verifier's existing HTTP transport contract.
    response = type("Response", (), {"raise_for_status": lambda self: None,
                                     "json": lambda self: {"keys": [jwk]}})()
    with patch.object(okta_jwt._default_cache._http, "get", return_value=response):
        token = jwt.encode({"iss": issuer, "aud": "api://fixture", "sub": "agent",
                            "exp": int(datetime.now(timezone.utc).timestamp()) + 300},
                           key, algorithm="RS256", headers={"kid": "fixture"})
        with Session(runtime) as db:
            identity, _ = _resolve_okta_jwt(token, db)
            assert identity.source_id == "agent" and identity.workspace_id == ws
        with Session(runtime) as db:
            db.get(Integration, enabled).okta_auth_enabled = False
            db.commit()
            try:
                _resolve_okta_jwt(token, db)
            except HTTPException as exc:
                assert exc.status_code == 401
            else:
                raise AssertionError("Disabled trust accepted token")

    failed = migrate("downgrade", "0157", success=False)
    assert "data-preserving rollback plan" in failed.stderr
    with engine.begin() as db:
        assert db.execute(text("SELECT count(*) FROM federation_connections")).scalar_one() == 4
        # Explicit cleanup of this harness's trust records permits empty rollback.
        db.execute(text("DELETE FROM federation_connections WHERE authentication_mode='okta_agent'"))
    migrate("downgrade", "0157")
    migrate("upgrade", "0158")
    with engine.begin() as db:
        assert db.execute(text("SELECT count(*) FROM federation_connections")).scalar_one() == 4
    runtime.dispose()
    engine.dispose()
    print("PASS: backfill, disabled/incomplete preservation, idempotence, coexistence, compatibility writes, RLS, real JWT auth, disable, rollback guard and re-upgrade")


if __name__ == "__main__":
    main()
