from datetime import timedelta
from types import SimpleNamespace

import pytest

from app.modules.guard.mcp_reconciliation import reconcile, registration_view
from tests.test_discovery_evidence import NOW, row

REF = "b" * 64
FINDING = {"id": REF, "name": "docs", "scope": "user", "transport": "stdio", "disabled": False}


def test_client_claims_never_become_registration_or_enforcement():
    result = reconcile(row(mcp_links=None, evidence={"mcp_servers": [{**FINDING,
        "approved": True, "governed": True, "server_id": "server"}]}), {}, NOW)
    finding = result["servers"][0]
    assert finding["registration_status"] == "unlinked"
    assert finding["registration"] is None
    assert finding["endpoint_identity"] == "unverified"
    assert finding["enforcement_status"] == "not_observed"


@pytest.mark.parametrize("state", ["approved", "quarantined", "revoked", "needs_review"])
def test_registration_review_is_separate_from_device_enforcement(state):
    registered = {"server": {"id": "server", "name": "docs", "review_status": state}}
    result = reconcile(row(mcp_links={"revision": 4, "bindings": {REF: {"server_id": "server"}}},
                           evidence={"mcp_servers": [FINDING]}), registered, NOW)
    assert result["revision"] == 4
    finding = result["servers"][0]
    assert finding["registration"]["review_status"] == state
    assert finding["association_source"] == "administrator"
    assert finding["enforcement_status"] == "not_observed"


@pytest.mark.parametrize("evidence,last_seen,status", [
    ({"mcp_servers": [FINDING]}, NOW - timedelta(days=2), "stale"),
    ({"mcp_servers": [{**FINDING, "disabled": True}]}, NOW, "disabled"),
    ({"mcp_servers": []}, NOW, "not_reported"),
    ({"mcp_servers": [FINDING], "config_unreadable": True}, NOW, "unreadable"),
])
def test_stale_disabled_missing_and_deleted_registration(evidence, last_seen, status):
    result = reconcile(row(mcp_links={"bindings": {REF: {"server_id": "deleted"}}},
                           evidence=evidence, last_seen_at=last_seen), {}, NOW)["servers"][0]
    assert result["discovery_status"] == status
    assert result["registration_status"] == "registration_missing"
    assert result["registration"] is None


@pytest.mark.parametrize("value,expected", [(None, "not_enrolled"), ({}, "invalid"),
    ({"state": "approved"}, "needs_review"),
    ({"state": "approved", "approved_digest": "a", "observed_digest": "b"}, "needs_review"),
    ({"state": "approved", "approved_digest": "a", "observed_digest": "a"}, "approved")])
def test_registration_projection_excludes_credentials_and_flags_drift(value, expected):
    result = registration_view(SimpleNamespace(id="id", name="docs", governance=value,
                                                encrypted_auth="private", url="private"))
    assert result == {"id": "id", "name": "docs", "review_status": expected}
