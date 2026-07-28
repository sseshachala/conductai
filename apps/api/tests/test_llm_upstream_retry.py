"""
Tests for LLM upstream failure handling — retries on transient/WAF-shaped errors,
never on real provider errors, and surfaces LLMUpstreamError with bounded
diagnostic fields so no HTML leaks into customer-visible events.

Covers the failure class documented in project_session_july28_upstream_hardening.md.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.runtime.llm_client import (
    LLMUpstreamError,
    _extract_upstream_ids,
    _should_retry,
    post_with_retry,
)


# ── _should_retry decision table ──────────────────────────────────────────────

def test_should_retry_html_403_yes():
    assert _should_retry(403, "text/html; charset=utf-8") is True


def test_should_retry_json_403_no():
    """JSON 403 = real auth failure. Retrying could DoS the provider."""
    assert _should_retry(403, "application/json") is False


def test_should_retry_json_401_no():
    assert _should_retry(401, "application/json") is False


def test_should_retry_429_yes():
    assert _should_retry(429, "application/json") is True


def test_should_retry_500_yes():
    assert _should_retry(500, "application/json") is True


def test_should_retry_502_yes():
    assert _should_retry(502, "text/html") is True


def test_should_retry_200_no():
    assert _should_retry(200, "application/json") is False


# ── _extract_upstream_ids — header-first, HTML fallback ───────────────────────

def test_extract_ids_from_headers_prefers_cf_ray():
    headers = {"cf-ray": "a223cdce792e97a5-MIA", "content-type": "text/html"}
    body = ""
    cf_ray, req_id = _extract_upstream_ids(headers, body)
    assert cf_ray == "a223cdce792e97a5-MIA"
    assert req_id is None


def test_extract_render_request_id_from_body():
    headers = {"content-type": "text/html"}
    body = '<p>Request ID: <code class="type-mono-01">a223cdce792e97a5</code></p>'
    cf_ray, req_id = _extract_upstream_ids(headers, body)
    assert cf_ray is None
    assert req_id == "a223cdce792e97a5"


def test_extract_ids_both_present():
    headers = {"cf-ray": "ray123-MIA"}
    body = '<p>Request ID: <code>deadbeef</code></p>'
    cf_ray, req_id = _extract_upstream_ids(headers, body)
    assert cf_ray == "ray123-MIA"
    assert req_id == "deadbeef"


def test_extract_ids_missing_gracefully_returns_none():
    cf_ray, req_id = _extract_upstream_ids({}, "")
    assert cf_ray is None
    assert req_id is None


# ── LLMUpstreamError — bounded snippet, safe str() ────────────────────────────

def test_upstream_error_str_is_short_and_safe():
    """str(exc) is what dag_runner writes to block_failed. Must not contain HTML."""
    huge_html = "<!DOCTYPE html><script>alert(1)</script>Blocked " + "X" * 50_000
    err = LLMUpstreamError(
        provider="anthropic", status=403, content_type="text/html",
        body_snippet=huge_html,
        cf_ray="ray-1", request_id="req-1", attempts=3,
    )
    s = str(err)
    assert "HTTP 403" in s
    assert "cf_ray=ray-1" in s
    assert "render_req=req-1" in s
    assert "3 attempts" in s
    assert "<!DOCTYPE" not in s
    assert len(s) < 200  # short message
    # Sanitized snippet is plain text (tags/scripts stripped), also bounded
    assert "<script>" not in err.body_snippet
    assert "alert(1)" not in err.body_snippet


def test_upstream_error_snippet_is_bounded():
    """body_snippet stored on the exception must be capped after sanitization."""
    huge = "X" * 50_000
    err = LLMUpstreamError(
        provider="openai", status=502, content_type="text/html",
        body_snippet=huge,
        cf_ray=None, request_id=None, attempts=3,
    )
    assert len(err.body_snippet) <= 2000


# ── post_with_retry — retry semantics + LLMUpstreamError shape ────────────────

def _mock_response(status, text="", headers=None):
    m = MagicMock()
    m.status_code = status
    m.text = text
    m.headers = headers or {"content-type": "application/json"}
    return m


def test_post_with_retry_html_403_then_success():
    """Retry on HTML 403 until success returns response cleanly."""
    responses = [
        _mock_response(403, "<html>Blocked</html>", {"content-type": "text/html"}),
        _mock_response(200, "{}", {"content-type": "application/json"}),
    ]
    with patch("httpx.post", side_effect=responses), patch("time.sleep"):
        resp = post_with_retry(
            url="https://api.example.com/v1/x",
            headers={},
            json_body={"k": "v"},
            provider="openai",
        )
    assert resp.status_code == 200


def test_post_with_retry_exhausts_and_raises_llm_upstream_error():
    """Three consecutive HTML 403s raise LLMUpstreamError with parsed IDs."""
    resp_html = _mock_response(
        403,
        '<p>Request ID: <code class="type-mono-01">a223cdce792e97a5</code></p>',
        {"content-type": "text/html", "cf-ray": "a223d6f119c83405-MIA"},
    )
    with patch("httpx.post", return_value=resp_html), patch("time.sleep"):
        with pytest.raises(LLMUpstreamError) as excinfo:
            post_with_retry(
                url="https://api.example.com/v1/x",
                headers={},
                json_body={"k": "v"},
                provider="anthropic",
            )
    e = excinfo.value
    assert e.provider == "anthropic"
    assert e.status == 403
    assert e.cf_ray == "a223d6f119c83405-MIA"
    assert e.request_id == "a223cdce792e97a5"
    assert e.attempts == 3
    # HTML body is captured for the event but bounded
    assert len(e.body_snippet) <= 2000


def test_post_with_retry_json_401_not_retried():
    """Real auth failure returns the response; caller handles it. No retry."""
    resp_401 = _mock_response(401, '{"error":"invalid_key"}', {"content-type": "application/json"})
    call_count = {"n": 0}

    def counting_post(*a, **kw):
        call_count["n"] += 1
        return resp_401

    with patch("httpx.post", side_effect=counting_post), patch("time.sleep"):
        resp = post_with_retry(
            url="https://api.example.com/v1/x",
            headers={},
            json_body={"k": "v"},
            provider="openai",
        )
    assert resp.status_code == 401
    assert call_count["n"] == 1  # no retries on JSON 4xx


def test_post_with_retry_honors_retry_after_header():
    """Retry-After (seconds) directs the wait time between attempts."""
    slept: list[float] = []
    responses = [
        _mock_response(429, "", {"content-type": "application/json", "retry-after": "2"}),
        _mock_response(200, "{}", {"content-type": "application/json"}),
    ]
    with patch("httpx.post", side_effect=responses):
        with patch("time.sleep", side_effect=slept.append):
            resp = post_with_retry(
                url="https://api.example.com/v1/x",
                headers={},
                json_body={"k": "v"},
                provider="openai",
            )
    assert resp.status_code == 200
    assert len(slept) == 1
    # sleep should be ~2s plus jitter, capped at 10s
    assert 2.0 <= slept[0] <= 2.5


def test_post_with_retry_network_error_becomes_upstream_error():
    """ConnectError on final attempt → LLMUpstreamError (status=0)."""
    import httpx as _httpx
    with patch("httpx.post", side_effect=_httpx.ConnectError("boom")), patch("time.sleep"):
        with pytest.raises(LLMUpstreamError) as excinfo:
            post_with_retry(
                url="https://api.example.com/v1/x",
                headers={},
                json_body={"k": "v"},
                provider="perplexity",
            )
    assert excinfo.value.status == 0
    assert "network error" in excinfo.value.body_snippet.lower()
    assert excinfo.value.attempts == 3


# ── Brain block integration: both paths handle upstream failure cleanly ───────

def _capture_events_and_run_brain(block_data, mock_side_effect):
    """Helper: run _execute_brain with a mock LLM raising the given error,
    return (raised_exc, list_of_emitted_events)."""
    block = {"id": "brain-1", "type": "brain", "data": block_data}
    artifacts = {"brain-1": {"system_prompt": "sys", "is_agentic": block_data.get("isAgentic", False)}}
    emitted: list[dict] = []
    mock_llm = MagicMock()
    mock_llm.create.side_effect = mock_side_effect
    redis_mock = MagicMock()
    redis_mock.get.return_value = None

    def _capture_emit(db, run_id, block_id, kind, payload):
        emitted.append({"kind": kind, "payload": payload})

    with (
        patch("app.runtime.blocks.brain_block.AnthropicClient", return_value=mock_llm),
        patch("app.runtime.blocks.brain_block.OpenAIClient", return_value=mock_llm),
        patch("app.runtime.blocks.brain_block._get_redis", return_value=redis_mock),
        patch("app.runtime.runtime._emit", side_effect=_capture_emit),
    ):
        from app.runtime.blocks.brain_block import _execute_brain
        raised = None
        try:
            _execute_brain(
                block=block, state={}, compiled_artifacts=artifacts,
                run_id="run-x", block_id="brain-1", db=MagicMock(),
            )
        except Exception as e:
            raised = e
    return raised, emitted


def test_brain_agentic_path_surfaces_upstream_error_cleanly():
    """Agentic path: LLMUpstreamError → llm_upstream_blocked event + short exception."""
    err = LLMUpstreamError(
        provider="anthropic", status=403, content_type="text/html",
        body_snippet="<!DOCTYPE html>" + "X" * 3000,
        cf_ray="ray-agentic-MIA", request_id="render-req-1", attempts=3,
    )
    raised, events = _capture_events_and_run_brain(
        {"label": "t", "isAgentic": True, "description": "sys", "prompt": "do", "max_turns": 3},
        mock_side_effect=err,
    )
    assert isinstance(raised, LLMUpstreamError)
    # str(exc) is what dag_runner writes — must be clean
    assert "<!DOCTYPE" not in str(raised)
    assert "ray-agentic-MIA" in str(raised)
    # llm_upstream_blocked event carries the full diagnostic
    blocked = [e for e in events if e["kind"] == "llm_upstream_blocked"]
    assert len(blocked) == 1
    p = blocked[0]["payload"]
    assert p["provider"] == "anthropic"
    assert p["status"] == 403
    assert p["cf_ray"] == "ray-agentic-MIA"
    assert p["render_request_id"] == "render-req-1"
    assert len(p["body_snippet"]) <= 2000


def test_brain_single_call_path_surfaces_upstream_error_cleanly():
    """Single-call path: same guarantees as agentic."""
    err = LLMUpstreamError(
        provider="openai", status=502, content_type="text/html",
        body_snippet="Bad Gateway",
        cf_ray="ray-single-MIA", request_id=None, attempts=3,
    )
    raised, events = _capture_events_and_run_brain(
        {"label": "t", "isAgentic": False, "description": "sys", "prompt": "do"},
        mock_side_effect=err,
    )
    assert isinstance(raised, LLMUpstreamError)
    assert "HTTP 502" in str(raised)
    assert "ray-single-MIA" in str(raised)
    blocked = [e for e in events if e["kind"] == "llm_upstream_blocked"]
    assert len(blocked) == 1
    assert blocked[0]["payload"]["turn"] == 0  # single-call = turn 0


# ── dag_runner integration: LLMUpstreamError → clean classified failure ───────

def test_dag_runner_classifies_upstream_error():
    """_classify_failure treats LLMUpstreamError as infrastructure with a
    specific reason code, so /run-events shows a proper 'upstream blocked'
    state instead of generic EXECUTION_ERROR."""
    from app.runtime.dag_runner import _classify_failure
    err = LLMUpstreamError(
        provider="anthropic", status=403, content_type="text/html",
        body_snippet="x",
        cf_ray="ray-abc-MIA", request_id="req-xyz", attempts=3,
    )
    result = _classify_failure(err)
    assert result["code"] == "LLM_UPSTREAM_BLOCKED"
    assert result["category"] == "infrastructure"
    assert result["stop_reason"] == "upstream_blocked"
    assert "ray-abc-MIA" in result["next_action"]
    assert "req-xyz" in result["next_action"]
    # message stays short — no HTML dump
    assert len(result["message"]) < 300
