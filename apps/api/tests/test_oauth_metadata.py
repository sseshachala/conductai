"""Shape check for /.well-known/oauth-authorization-server."""
from __future__ import annotations

from app.modules.auth.oauth.metadata import build_authorization_server_metadata


def test_metadata_advertises_all_three_grants():
    m = build_authorization_server_metadata()
    grants = m["grant_types_supported"]
    assert "authorization_code" in grants
    assert "refresh_token" in grants
    assert "urn:ietf:params:oauth:grant-type:token-exchange" in grants


def test_metadata_pkce_s256_only():
    m = build_authorization_server_metadata()
    assert m["code_challenge_methods_supported"] == ["S256"]


def test_metadata_endpoints_point_at_issuer():
    m = build_authorization_server_metadata()
    issuer = m["issuer"]
    assert m["token_endpoint"].startswith(issuer)
    assert m["authorization_endpoint"].startswith(issuer)
    assert m["registration_endpoint"].startswith(issuer)


def test_metadata_response_types_and_public_client_auth():
    m = build_authorization_server_metadata()
    assert m["response_types_supported"] == ["code"]
    assert m["token_endpoint_auth_methods_supported"] == ["none"]
