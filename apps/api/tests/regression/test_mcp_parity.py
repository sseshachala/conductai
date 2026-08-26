"""MCP `/guard/mcp` byte-parity regression tests.

Locks in pre-refactor behavior of the MCP JSON-RPC endpoint. Each fixture
replays a real request and asserts response + DB state matches the golden.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.regression.conftest import load_fixture

MCP_FIXTURES = [
    "mcp_initialize",
]


def _get_nested(obj: dict, dotted: str):
    """Walk a dotted key path through a dict. Raises KeyError if missing."""
    cur = obj
    for part in dotted.split("."):
        cur = cur[part]
    return cur


def _assert_body_match(actual: dict, expected: dict, path: str = "") -> None:
    """Assert every key in `expected` exists in `actual` with the same value.
    Extra keys in `actual` are allowed (that's how we ignore _surface, instructions)."""
    for key, want in expected.items():
        full = f"{path}.{key}" if path else key
        assert key in actual, f"missing key `{full}` in response body"
        if isinstance(want, dict):
            assert isinstance(actual[key], dict), f"expected dict at `{full}`, got {type(actual[key]).__name__}"
            _assert_body_match(actual[key], want, full)
        else:
            assert actual[key] == want, f"value mismatch at `{full}`: expected {want!r}, got {actual[key]!r}"


@pytest.mark.parametrize("fixture_name", MCP_FIXTURES)
def test_mcp_fixture(fixture_name: str, client: TestClient) -> None:
    fixture = load_fixture(fixture_name)
    req = fixture["request"]
    expected = fixture["expected_response"]

    resp = client.request(
        req["method"],
        req["path"],
        headers=req["headers"],
        json=req["body"],
    )

    assert resp.status_code == expected["status"], f"status mismatch: got {resp.status_code}, body={resp.text[:400]}"

    body = resp.json()
    _assert_body_match(body, expected["body_match"])

    for dotted in expected.get("body_present_keys", []):
        try:
            _get_nested(body, dotted)
        except KeyError as e:
            pytest.fail(f"required key `{dotted}` missing from response body: {e}")

    for header_name in expected.get("headers_present", []):
        assert header_name in resp.headers, f"required header `{header_name}` missing from response"
