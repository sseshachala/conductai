"""Exercise the CLI verifier against the real Gateway route response contracts."""
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.mark.parametrize("tool", ["claude-code", "codex", "copilot-cli"])
def test_cli_accepts_gateway_catalog_contract(monkeypatch, tool):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[4] / "packages/conduct-cli/src"))
    from conduct_cli.guard_commands import inventory
    from app.modules.guard.routers import gateway_proxy

    app = FastAPI()
    app.include_router(gateway_proxy.router)
    app.dependency_overrides[gateway_proxy._gateway_principal] = lambda: ("workspace", "user", None)
    app.dependency_overrides[gateway_proxy.get_db] = lambda: None
    monkeypatch.setattr(gateway_proxy, "_anthropic_catalog", lambda *a: [])
    monkeypatch.setattr(gateway_proxy, "_record_audit", lambda *a, **kw: None)
    client = TestClient(app)

    class Connection:
        def __init__(self, *args, **kwargs):
            self.response = None

        def request(self, method, path, headers):
            self.response = client.request(method, path, headers=headers)

        def getresponse(self):
            return SimpleNamespace(status=self.response.status_code,
                                   read=lambda limit: self.response.content[:limit])

        def close(self):
            pass

    monkeypatch.setattr(inventory.http.client, "HTTPSConnection", Connection)
    report = {"agents": [{"framework": tool, "evidence": {"gateway_configured": True}}]}
    inventory.verify_gateway(report, "cond_agt_contract_test",
                             {"api_url": "https://api.example", "gateway_url": "https://gateway.example/gateway/v1"})
    assert report["agents"][0]["evidence"]["gateway_connection_status"] == "connection_verified"
