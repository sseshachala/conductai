"""Guard proxy `/proxy/*` byte-parity regression tests.

Locks in pre-refactor behavior of the OpenAI / Anthropic / Perplexity proxies.
Auth-guard fixtures need no DB or upstream mock (401 short-circuits both).
Authed fixtures mock the upstream provider at the httpx layer so the test is
hermetic — no live API calls.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.regression.conftest import load_fixture, render_headers, requires_db
from tests.regression.test_mcp_parity import _apply_custom_assertion, _replay

PROXY_FIXTURES_NO_DB = [
    "proxy_openai_missing_auth",
    "proxy_anthropic_missing_auth",
]

PROXY_FIXTURES_DB = [
    "proxy_openai_authed",
]


@pytest.mark.parametrize("fixture_name", PROXY_FIXTURES_NO_DB)
def test_proxy_no_db_fixture(fixture_name: str, client: TestClient) -> None:
    _replay(client, load_fixture(fixture_name))


@requires_db
@pytest.mark.parametrize("fixture_name", PROXY_FIXTURES_DB)
def test_proxy_db_fixture(
    fixture_name: str,
    client: TestClient,
    seeded_workspace,
    monkeypatch,
) -> None:
    """DB-backed proxy fixture. If the fixture declares `upstream_mock`,
    patch httpx.AsyncClient.post to return the mocked response so no live API
    call is made. Otherwise (e.g. proxy_openai_authed_no_api_key which
    short-circuits at the API-key check), no mock is installed."""
    fixture = load_fixture(fixture_name)
    _, token = seeded_workspace

    mock = fixture.get("upstream_mock")
    if mock:
        import httpx

        class _MockResp:
            def __init__(self, status: int, body: dict):
                self.status_code = status
                self._body = body
                self.headers = {"content-type": "application/json"}
                self.text = str(body)

            def json(self):
                return self._body

            async def aread(self):
                import json as _j
                return _j.dumps(self._body).encode()

        async def _mock_post(self, url, **kwargs):
            if mock["url_match"] in url:
                return _MockResp(mock["status"], mock["body"])
            raise RuntimeError(f"unmocked upstream call to {url}")

        monkeypatch.setattr(httpx.AsyncClient, "post", _mock_post, raising=False)

    _replay(client, fixture, token=token)
