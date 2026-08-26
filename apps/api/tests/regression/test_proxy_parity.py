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


class _MockUpstreamResponse:
    """Shape-compatible httpx.Response mock for the guard proxy.

    The guard router at app/guard/router.py::153 issues
    `resp = await client.send(req, stream=True)` and downstream reads
    status_code, headers, aread(), aiter_bytes(), aclose(). This mock
    implements all five so the fixture path is exercised, not just the
    mock's `.json()` sugar.
    """

    def __init__(self, status: int, body: dict, headers: dict | None = None):
        import json as _j
        self.status_code = status
        self._payload = _j.dumps(body).encode()
        self.headers = headers or {"content-type": "application/json"}
        self.text = self._payload.decode()

    def json(self):
        import json as _j
        return _j.loads(self._payload)

    async def aread(self):
        return self._payload

    async def aiter_bytes(self, chunk_size: int = 1024):
        # Yield the payload as one chunk — matches typical streamed response
        # shape from OpenAI/Anthropic/Perplexity when Guard streams through.
        yield self._payload

    async def aclose(self):
        return None


def _install_upstream_mock(monkeypatch, mock_spec: dict) -> dict:
    """Patch httpx.AsyncClient.send to short-circuit upstream calls that
    match mock_spec['url_match']. Returns a hit counter dict the test can
    assert on to prove the mock actually fired — no more silently
    passing against a mock that never runs.
    """
    import httpx

    hits = {"send_calls": 0}

    async def _mock_send(self, request, **kwargs):
        hits["send_calls"] += 1
        url = str(request.url)
        if mock_spec["url_match"] in url:
            return _MockUpstreamResponse(mock_spec["status"], mock_spec["body"])
        raise RuntimeError(f"unmocked upstream call to {url}")

    monkeypatch.setattr(httpx.AsyncClient, "send", _mock_send, raising=False)
    return hits


@requires_db
@pytest.mark.parametrize("fixture_name", PROXY_FIXTURES_DB)
def test_proxy_db_fixture(
    fixture_name: str,
    client: TestClient,
    seeded_workspace,
    monkeypatch,
) -> None:
    """DB-backed proxy fixture. If the fixture declares `upstream_mock`,
    patch httpx.AsyncClient.send (the actual call site — see router.py:153,
    NOT .post which is never called) and assert the mock fires at least
    once."""
    fixture = load_fixture(fixture_name)
    _, token = seeded_workspace

    mock = fixture.get("upstream_mock")
    hits = None
    if mock:
        hits = _install_upstream_mock(monkeypatch, mock)

    _replay(client, fixture, token=token)

    if mock:
        assert hits["send_calls"] >= 1, (
            f"upstream_mock declared for fixture {fixture_name!r} but "
            f"AsyncClient.send was never called — either the router bypassed "
            f"the mock or the request short-circuited before reaching upstream"
        )


def test_upstream_mock_intercepts_client_send(monkeypatch) -> None:
    """Self-check: prove _install_upstream_mock actually patches the right
    method. If httpx.AsyncClient's stream API changes shape, this test fails
    at the mock layer instead of silently letting a real API call escape.
    Catches Copilot review concern B (Aug 2026).
    """
    import asyncio
    import httpx

    hits = _install_upstream_mock(monkeypatch, {
        "url_match": "example.com",
        "status": 200,
        "body": {"ok": True},
    })

    async def _drive():
        async with httpx.AsyncClient() as c:
            req = c.build_request("POST", "https://example.com/v1/foo",
                                  json={"q": "hi"})
            resp = await c.send(req, stream=True)
            body = await resp.aread()
            await resp.aclose()
            return resp.status_code, body

    status, body = asyncio.run(_drive())
    assert status == 200
    assert body == b'{"ok": true}'
    assert hits["send_calls"] == 1
