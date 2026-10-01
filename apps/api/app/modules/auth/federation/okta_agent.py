"""Okta agent trust storage, separate from Okta service credentials."""
from contextlib import contextmanager
from urllib.parse import urlsplit

from sqlalchemy import text

from app.models.integration import Integration
from .models import FederationConnection


@contextmanager
def workspace_scope(db, workspace):
    previous = db.execute(text("SELECT current_setting('app.current_workspace', true)")).scalar()
    db.execute(text("SELECT set_config('app.current_workspace', :ws, true)"), {"ws": str(workspace)})
    try:
        yield
    finally:
        db.execute(text("SELECT set_config('app.current_workspace', :ws, true)"), {"ws": previous or ""})


def connection(db, integration):
    with workspace_scope(db, integration.workspace_id):
        return db.query(FederationConnection).filter(
            FederationConnection.workspace_id == integration.workspace_id,
            FederationConnection.integration_id == integration.id,
            FederationConnection.authentication_mode == "okta_agent",
        ).populate_existing().first()


def candidates(db, issuer):
    # The compatibility index is only a candidate directory, never authority.
    # Read the actual trust under each workspace's existing RLS policy.
    rows = []
    for integration in db.query(Integration).filter(
        Integration.handle == "okta", Integration.okta_issuer == issuer,
    ).all():
        trust = connection(db, integration)
        if trust is not None and trust.config.get("issuer") == issuer:
            rows.append(trust)
    return rows


def valid_config(config):
    issuer = config.get("issuer")
    audience = config.get("audience")
    if (not isinstance(issuer, str) or not isinstance(audience, str) or not audience.strip()
            or any(character.isspace() for character in issuer)):
        return False
    try:
        url = urlsplit(issuer)
        valid = url.scheme == "https" and bool(url.hostname) and not (
            url.username or url.password or url.query or url.fragment
        )
        return bool(valid and config.get("jwks_uri") == issuer.rstrip("/") + "/v1/keys"
                    and config.get("token_profile") == "okta_agent_jwt"
                    and config.get("algorithms") == ["RS256"])
    except ValueError:
        return False
