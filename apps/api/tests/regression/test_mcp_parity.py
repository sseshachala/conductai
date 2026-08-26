"""MCP `/guard/mcp` byte-parity regression tests.

Locks in pre-refactor behavior of the MCP JSON-RPC endpoint. Each fixture
replays a real request and asserts response matches the golden shape.

Fixtures marked `requires_db: true` use the `seeded_workspace` fixture to
mint a real workspace + agent token; they skip locally when Postgres isn't
reachable (CI has real Postgres).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.regression.conftest import (
    load_fixture,
    render_headers,
    requires_db,
)

MCP_FIXTURES_NO_DB = [
    "mcp_initialize",
]

MCP_FIXTURES_DB = [
    "mcp_initialize_authenticated",
    "mcp_tools_list",
    "mcp_tool_call_allow",
    "mcp_tool_call_unknown",
]


def _assert_body_match(actual: dict, expected: dict, path: str = "") -> None:
    """Extra keys in actual are allowed — we're locking in a subset contract."""
    for key, want in expected.items():
        full = f"{path}.{key}" if path else key
        assert key in actual, f"missing key `{full}` in response body"
        if isinstance(want, dict):
            assert isinstance(actual[key], dict), f"expected dict at `{full}`"
            _assert_body_match(actual[key], want, full)
        else:
            assert actual[key] == want, f"value mismatch at `{full}`: expected {want!r}, got {actual[key]!r}"


def _get_nested(obj: dict, dotted: str):
    cur = obj
    for part in dotted.split("."):
        cur = cur[part]
    return cur


def _apply_custom_assertion(body: dict, resp_status: int, assertion: dict) -> None:
    kind = assertion["kind"]
    if kind == "tools_include":
        tools = body.get("result", {}).get("tools", [])
        names = {t.get("name") for t in tools}
        missing = set(assertion["names"]) - names
        assert not missing, f"tools/list missing expected tools: {missing}"
    elif kind == "result_has_content_type":
        content = body.get("result", {}).get("content", [])
        assert isinstance(content, list) and content, "result.content should be a non-empty list"
        types = {c.get("type") for c in content}
        assert assertion["type"] in types, f"expected content type {assertion['type']!r} in {types}"
    elif kind == "response_signals_error":
        has_error_env = "error" in body
        result_is_error = body.get("result", {}).get("isError") is True
        content = body.get("result", {}).get("content", [])
        error_words = ("error", "unknown", "not found", "invalid", "missing")
        has_error_text = any(
            any(w in (c.get("text", "").lower()) for w in error_words) for c in content
        )
        assert has_error_env or result_is_error or has_error_text, (
            f"expected error signal (error envelope, isError=true, or error/unknown/not-found text). body={body}"
        )
    elif kind == "status_in_range":
        assert assertion["min"] <= resp_status <= assertion["max"], (
            f"status {resp_status} outside [{assertion['min']}, {assertion['max']}]"
        )
    elif kind == "body_has_openai_choices":
        assert "choices" in body and isinstance(body["choices"], list) and body["choices"], (
            f"expected non-empty choices[]; body={body}"
        )
    elif kind == "body_error_message_contains":
        msg = body.get("error", {}).get("message", "") if isinstance(body.get("error"), dict) else ""
        assert assertion["text"].lower() in msg.lower(), (
            f"expected {assertion['text']!r} in error.message, got {msg!r}"
        )
    else:
        pytest.fail(f"unknown custom assertion kind: {kind}")


def _replay(client: TestClient, fixture: dict, token: str | None = None):
    req = fixture["request"]
    resp = client.request(
        req["method"],
        req["path"],
        headers=render_headers(req["headers"], token),
        json=req["body"],
    )

    expected = fixture["expected_response"]
    assert resp.status_code == expected["status"], (
        f"status mismatch: got {resp.status_code}, body={resp.text[:400]}"
    )

    try:
        body = resp.json()
    except ValueError:
        body = {}

    if "body_match" in expected:
        _assert_body_match(body, expected["body_match"])

    for dotted in expected.get("body_present_keys", []):
        try:
            _get_nested(body, dotted)
        except KeyError as e:
            pytest.fail(f"required key `{dotted}` missing: {e}")

    for header_name in expected.get("headers_present", []):
        assert header_name in resp.headers, f"required header `{header_name}` missing"

    for assertion in expected.get("custom_assertions", []):
        _apply_custom_assertion(body, resp.status_code, assertion)


@pytest.mark.parametrize("fixture_name", MCP_FIXTURES_NO_DB)
def test_mcp_no_db_fixture(fixture_name: str, client: TestClient) -> None:
    _replay(client, load_fixture(fixture_name))


@requires_db
@pytest.mark.parametrize("fixture_name", MCP_FIXTURES_DB)
def test_mcp_db_fixture(fixture_name: str, client: TestClient, seeded_workspace) -> None:
    _, token = seeded_workspace
    _replay(client, load_fixture(fixture_name), token=token)
