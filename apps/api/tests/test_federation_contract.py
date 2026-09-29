"""Contract invariants only; these tests do not perform token verification."""
from copy import deepcopy
from uuid import uuid4

import pytest
from pydantic import TypeAdapter, ValidationError

from app.modules.auth.federation.contracts import ResolvedIdentityContext


ADAPTER = TypeAdapter(ResolvedIdentityContext)


@pytest.fixture
def delegated():
    workspace, caller, principal = (str(uuid4()) for _ in range(3))
    return {
        "schema_version": 1, "workspace_id": workspace, "mode": "delegated",
        "caller": {"workspace_id": workspace, "agent_identity_id": caller},
        "request_id": "request-1",
        "principal": {
            "workspace_id": workspace, "principal_id": principal, "kind": "human",
            "issuer": "https://issuer.example", "subject": "external-subject",
        },
        "delegation": {
            "workspace_id": workspace, "grant_id": str(uuid4()),
            "caller_agent_identity_id": caller, "principal_id": principal,
            "actions": ["guard.check"], "resources": ["project:example"],
        },
        "evidence": {
            "workspace_id": workspace,
            "issuer": "https://issuer.example", "subject": "external-subject",
            "connection_id": str(uuid4()), "method": "oauth_access_token",
            "audience": "conduct", "mapping_version": "1",
            "verified_at": "2026-09-29T10:00:00Z", "expires_at": "2026-09-29T10:05:00Z",
        },
        "attributes": [{"name": "team", "values": ["engineering"], "source_claim": "groups"}],
    }


@pytest.mark.parametrize("method", ["oauth_access_token", "integration_assertion"])
@pytest.mark.parametrize("kind", ["human", "workload"])
def test_delegated_round_trip(delegated, method, kind):
    delegated["evidence"]["method"] = method
    delegated["principal"]["kind"] = kind
    parsed = ADAPTER.validate_python(delegated)
    assert ADAPTER.validate_json(parsed.model_dump_json()) == parsed
    assert parsed.attributes[0].values == ("engineering",)


def test_service_only_has_no_principal(delegated):
    service = {k: v for k, v in delegated.items() if k not in {"principal", "delegation", "evidence", "attributes"}}
    service["mode"] = "service_only"
    parsed = ADAPTER.validate_python(service)
    assert "principal" not in parsed.model_dump()
    service["principal"] = delegated["principal"]
    with pytest.raises(ValidationError):
        ADAPTER.validate_python(service)


@pytest.mark.parametrize("section,field", [
    ("caller", "workspace_id"), ("principal", "workspace_id"),
    ("delegation", "workspace_id"), ("delegation", "caller_agent_identity_id"),
    ("delegation", "principal_id"),
    ("evidence", "workspace_id"),
])
def test_rejects_mismatched_bindings(delegated, section, field):
    delegated[section][field] = str(uuid4())
    with pytest.raises(ValidationError):
        ADAPTER.validate_python(delegated)


@pytest.mark.parametrize("field", ["principal", "delegation", "evidence"])
def test_required_identity_cannot_be_omitted(delegated, field):
    del delegated[field]
    with pytest.raises(ValidationError):
        ADAPTER.validate_python(delegated)


@pytest.mark.parametrize("section,field,value", [
    ("principal", "subject", ""), ("principal", "subject", "   "),
    ("principal", "subject", 123), ("principal", "email", "person@example.com"),
    ("evidence", "token", "not-a-real-token"), ("evidence", "method", "id_token"),
    ("evidence", "expires_at", "2026-09-29T10:00:00Z"),
    ("evidence", "verified_at", "2026-09-29T10:00:00"),
    ("delegation", "actions", []), ("delegation", "resources", []),
])
def test_rejects_invalid_or_unexpected_fields(delegated, section, field, value):
    delegated[section][field] = value
    with pytest.raises(ValidationError):
        ADAPTER.validate_python(delegated)


def test_duplicate_attribute_mapping_rejected(delegated):
    delegated["attributes"].append(deepcopy(delegated["attributes"][0]))
    with pytest.raises(ValidationError):
        ADAPTER.validate_python(delegated)


def test_context_is_frozen_and_does_not_share_mutable_input(delegated):
    context = ADAPTER.validate_python(delegated)
    delegated["attributes"][0]["values"].append("admin")
    assert context.attributes[0].values == ("engineering",)
    with pytest.raises(ValidationError):
        context.principal.subject = "someone-else"


@pytest.mark.parametrize("field,value", [("schema_version", 2), ("mode", "optional"), ("token", "secret")])
def test_rejects_unknown_version_mode_and_top_level_secrets(delegated, field, value):
    delegated[field] = value
    with pytest.raises(ValidationError):
        ADAPTER.validate_python(delegated)


def test_same_subject_different_issuer_remains_distinct(delegated):
    first = ADAPTER.validate_python(delegated)
    delegated["principal"]["issuer"] = "https://second-issuer.example"
    delegated["evidence"]["issuer"] = "https://second-issuer.example"
    second = ADAPTER.validate_python(delegated)
    assert first.principal != second.principal


@pytest.mark.parametrize("field,value", [
    ("issuer", "https://different-issuer.example"),
    ("issuer", "https://issuer.example/"),
    ("subject", "different-subject"),
])
def test_evidence_must_bind_exact_principal(delegated, field, value):
    delegated["evidence"][field] = value
    with pytest.raises(ValidationError, match="evidence principal mismatch"):
        ADAPTER.validate_python(delegated)
