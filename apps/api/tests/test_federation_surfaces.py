"""Surface adapters preserve live authorization and reference-only attribution."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from starlette.requests import Request

from app.modules.auth.federation import gateway
from app.modules.auth.federation.attribution import attribution
from app.modules.auth.federation.resolver import FederationDenied


@pytest.mark.asyncio
async def test_each_gateway_target_rechecks_revocation(monkeypatch):
    check = AsyncMock(return_value="allowed")
    live = Mock(side_effect=[None, FederationDenied("federation_grant_inactive")])
    monkeypatch.setattr(gateway, "recheck_gateway", live)
    wrapped = gateway.delegated_policy_check(check, object())
    assert await wrapped("primary") == "allowed"
    with pytest.raises(FederationDenied):
        await wrapped("fallback")
    assert live.call_count == 2
    check.assert_awaited_once_with("primary")


def test_unconfigured_gateway_keeps_existing_policy_callback():
    check = AsyncMock()
    assert gateway.delegated_policy_check(check, None) is check


def test_configured_catalog_is_not_an_inference_grant(monkeypatch):
    monkeypatch.setattr(gateway, "authenticate_context", Mock(return_value=object()))
    request = Request({"type": "http", "headers": []})
    response = gateway.prepare_gateway(request, uuid4(), "cond_api_fixture", operation="model_catalog")
    assert response.status_code == 403
    assert b"identity_required" in response.body


def test_attribution_never_returns_subject_or_token():
    data = {key: str(uuid4()) for key in (
        "request_id", "caller_id", "principal_id", "grant_id", "connection_id")}
    data.update(schema_version=1, mapping_version="1", evidence_expires_at=datetime.now(timezone.utc).isoformat(),
                subject="private-subject", token="private-token", claims={"email": "private"})
    result = attribution({"federation": data})
    assert result["principal_id"] == data["principal_id"]
    assert not {"subject", "token", "claims"}.intersection(result)


@pytest.mark.parametrize("metadata", [None, {}, {"federation": []}, {"federation": {"caller_id": "invalid"}}])
def test_invalid_historical_attribution_is_not_trusted(metadata):
    assert attribution(metadata) is None


def test_federation_denial_uses_nonretryable_permission_contract():
    assert isinstance(FederationDenied("federation_evidence_expired"), PermissionError)
