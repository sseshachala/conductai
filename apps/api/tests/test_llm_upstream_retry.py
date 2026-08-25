"""
Tests for LLM upstream failure handling — retries on transient/WAF-shaped errors,
never on real provider errors, and surfaces LLMUpstreamError with bounded
diagnostic fields so no HTML leaks into customer-visible events.

Covers the failure class documented in project_session_july28_upstream_hardening.md.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.runtime.dag_runner import _classify_failure, _with_retry
from app.runtime.llm_client import (
    GuardProxyBlocked,
    LLMUpstreamError,
    _extract_upstream_ids,
    _sanitize_body_snippet,
    _should_retry,
    make_retry_info,
    post_with_retry,
    raise_if_guard_proxy_blocked,
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
    err =LLMUpstreamError(
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


# ── Fix #1: idempotency key includes __for_each_index ─────────────────────────

def _run_agentic_and_capture_key(state: dict) -> str | None:
    """Run brain agentic path, capture idempotency_key passed to llm.create()."""
    captured: dict = {}
    mock_llm = MagicMock()

    def _capture_create(**kwargs):
        captured["idempotency_key"] = kwargs.get("idempotency_key")
        from app.runtime.llm_client import LLMResponse, LLMTextBlock, LLMUsage
        return LLMResponse(
            content=[LLMTextBlock(text="ok")],
            stop_reason="end_turn",
            usage=LLMUsage(input_tokens=1, output_tokens=1),
            cost_usd=0.0,
            _raw_content=[{"type": "text", "text": "ok"}],
        )

    mock_llm.create.side_effect = _capture_create

    redis_mock = MagicMock()
    redis_mock.get.return_value = None
    block = {"id": "brain-1", "type": "brain",
             "data": {"isAgentic": True, "description": "sys", "max_turns": 1}}
    artifacts = {"brain-1": {"system_prompt": "sys", "is_agentic": True}}

    with (
        patch("app.runtime.blocks.brain_block.AnthropicClient", return_value=mock_llm),
        patch("app.runtime.blocks.brain_block._get_redis", return_value=redis_mock),
    ):
        from app.runtime.blocks.brain_block import _execute_brain
        _execute_brain(block=block, state=state, compiled_artifacts=artifacts,
                       run_id="run-1", block_id="brain-1")
    return captured.get("idempotency_key")


def test_idempotency_key_no_for_each_index_absent():
    """No __for_each_index in state → key is base shape."""
    key = _run_agentic_and_capture_key({})
    assert key == "conduct-run-1-brain-1-0"


def test_idempotency_key_includes_for_each_index():
    """Iterations of same brain block inside for_each get distinct keys."""
    k0 = _run_agentic_and_capture_key({"__for_each_index": 0})
    k1 = _run_agentic_and_capture_key({"__for_each_index": 1})
    k2 = _run_agentic_and_capture_key({"__for_each_index": 2})
    assert k0 == "conduct-run-1-brain-1-0-fe0"
    assert k1 == "conduct-run-1-brain-1-0-fe1"
    assert k2 == "conduct-run-1-brain-1-0-fe2"
    assert len({k0, k1, k2}) == 3  # no collisions


# ── Fix #3: on_retry callback wired end-to-end ────────────────────────────────

def test_on_retry_called_per_retry_attempt():
    """post_with_retry calls on_retry once per retry (not on success or final failure)."""
    responses = [
        _mock_response(502, "err1", {"content-type": "text/html", "cf-ray": "ray-1"}),
        _mock_response(502, "err2", {"content-type": "text/html", "cf-ray": "ray-2"}),
        _mock_response(200, "{}", {"content-type": "application/json"}),
    ]
    retry_events: list[dict] = []
    with patch("httpx.post", side_effect=responses), patch("time.sleep"):
        post_with_retry(
            url="https://api.example.com/v1/x",
            headers={},
            json_body={"k": "v"},
            provider="openai",
            on_retry=retry_events.append,
        )
    # Two retries before success → two on_retry calls
    assert len(retry_events) == 2
    assert retry_events[0]["attempt"] == 1
    assert retry_events[1]["attempt"] == 2
    assert retry_events[0]["cf_ray"] == "ray-1"
    assert retry_events[1]["cf_ray"] == "ray-2"


def test_make_retry_info_shape_is_stable():
    """Adapters and post_with_retry must produce identical dict shape."""
    info = make_retry_info(
        provider="anthropic", status=502, content_type="text/html",
        attempt=2, max_attempts=3, cf_ray="ray-x", request_id="req-y",
    )
    assert set(info.keys()) == {
        "provider", "status", "content_type", "attempt", "max_attempts",
        "cf_ray", "request_id",
    }


# ── Fix #4: GuardProxyBlocked routing ─────────────────────────────────────────

def test_raise_if_guard_proxy_blocked_on_guard_block():
    """guard_block JSON error → GuardProxyBlocked with policy-shaped str()."""
    resp = _mock_response(
        403,
        '{"error":{"type":"guard_block","message":"cost limit","rule_id":"max-spend-daily"}}',
        {"content-type": "application/json"},
    )
    with pytest.raises(GuardProxyBlocked) as excinfo:
        raise_if_guard_proxy_blocked(provider="openai", response=resp)
    e = excinfo.value
    assert e.error_type == "guard_block"
    assert e.rule_id == "max-spend-daily"
    assert "[ConductGuard] Blocked by policy 'max-spend-daily'" in str(e)


def test_raise_if_guard_proxy_blocked_on_config_error():
    """conduct_guard_proxy JSON error → GuardProxyBlocked with proxy-shaped str()."""
    resp = _mock_response(
        502,
        '{"error":{"type":"conduct_guard_proxy","message":"upstream missing"}}',
        {"content-type": "application/json"},
    )
    with pytest.raises(GuardProxyBlocked) as excinfo:
        raise_if_guard_proxy_blocked(provider="anthropic", response=resp)
    assert excinfo.value.error_type == "conduct_guard_proxy"
    assert "[ConductProxy]" in str(excinfo.value)


def test_raise_if_guard_proxy_blocked_ignores_normal_json_error():
    """Provider's own JSON errors (auth failure, bad request) are not intercepted."""
    resp = _mock_response(
        401,
        '{"error":{"type":"invalid_request_error","message":"bad key"}}',
        {"content-type": "application/json"},
    )
    # Should NOT raise — caller handles as usual
    raise_if_guard_proxy_blocked(provider="openai", response=resp)


def test_dag_runner_classifies_guard_proxy_config_error():
    """conduct_guard_proxy → PROXY_CONFIG_ERROR with operator-actionable next_action."""
    err =GuardProxyBlocked(
        provider="anthropic", status=502, error_type="conduct_guard_proxy",
        message="upstream not configured",
    )
    result = _classify_failure(err)
    assert result["code"] == "PROXY_CONFIG_ERROR"
    assert result["category"] == "configuration"
    assert result["stop_reason"] == "proxy_misconfigured"
    assert "Settings" in result["next_action"] or "proxy" in result["next_action"].lower()


def test_dag_runner_classifies_guard_block_as_policy():
    """guard_block reuses existing Guard UX path via string match."""
    err =GuardProxyBlocked(
        provider="openai", status=403, error_type="guard_block",
        message="cost limit", rule_id="max-spend-daily",
    )
    result = _classify_failure(err)
    assert result["code"] == "GUARD_POLICY_BLOCKED"


# ── Fix #5: outer_attempt caps internal retries ───────────────────────────────

def test_outer_attempt_caps_internal_retries():
    """When adapter is called with outer_attempt > 1, internal retries drop to 1."""
    calls: list = []
    responses = [
        _mock_response(502, "", {"content-type": "text/html"}),
        _mock_response(502, "", {"content-type": "text/html"}),
        _mock_response(502, "", {"content-type": "text/html"}),
    ]

    def counting_post(*a, **kw):
        calls.append(True)
        return responses[len(calls) - 1]

    with patch("httpx.post", side_effect=counting_post), patch("time.sleep"):
        with pytest.raises(LLMUpstreamError):
            post_with_retry(
                url="https://api.example.com/v1/x",
                headers={}, json_body={"k": "v"},
                provider="openai", max_attempts=1,
            )
    # With max_attempts=1 (outer_attempt > 1 in adapter maps to this), single call
    assert len(calls) == 1


# ── Sanitizer: entity-encoded HTML is neutralized (was XSS bypass) ────────────

def test_sanitizer_neutralizes_single_encoded_html():
    """`&lt;script&gt;` must not slip through as a live tag."""
    out = _sanitize_body_snippet("&lt;script&gt;alert(1)&lt;/script&gt; safe")
    assert "<script>" not in out
    assert "alert(1)" not in out
    assert "safe" in out


def test_sanitizer_neutralizes_double_encoded_html():
    """Common pattern: HTML-escaped error page that itself contains encoded tags."""
    out = _sanitize_body_snippet("&amp;lt;script&amp;gt;alert(2)&amp;lt;/script&amp;gt; safe2")
    assert "<script>" not in out
    assert "alert(2)" not in out
    assert "safe2" in out


def test_sanitizer_neutralizes_triple_encoded_html():
    """Pathological but possible: triple-encoded input still fully decoded before stripping."""
    out = _sanitize_body_snippet("&amp;amp;lt;script&amp;amp;gt;alert(3)&amp;amp;lt;/script&amp;amp;gt; safe3")
    assert "<script>" not in out
    assert "alert(3)" not in out


def test_sanitizer_strips_script_and_style_bodies():
    out = _sanitize_body_snippet("<script>alert(4)</script><style>body{}</style> safe4")
    assert "<script>" not in out
    assert "<style>" not in out
    assert "alert(4)" not in out
    assert "safe4" in out


def test_sanitizer_preserves_normal_entities():
    """Plain ampersand should decode cleanly — sanitizer isn't over-eager."""
    out = _sanitize_body_snippet("normal &amp; text")
    assert "&" in out
    assert "normal" in out
    assert "text" in out


# ── Events include content_type + is_final + block_attempt ────────────────────

def test_brain_agentic_event_includes_content_type_and_is_final():
    """llm_upstream_blocked event carries content_type (was missing) + is_final marker."""
    err = LLMUpstreamError(
        provider="anthropic", status=403, content_type="text/html; charset=utf-8",
        body_snippet="Blocked", cf_ray="ray-a", request_id="req-a", attempts=3,
    )
    raised, events = _capture_events_and_run_brain(
        {"label": "t", "isAgentic": True, "description": "sys", "prompt": "do", "max_turns": 3},
        mock_side_effect=err,
    )
    blocked = [e for e in events if e["kind"] == "llm_upstream_blocked"]
    assert len(blocked) == 1
    p = blocked[0]["payload"]
    assert p["content_type"] == "text/html; charset=utf-8"
    assert p["is_final"] is True
    assert p["block_attempt"] == 1  # nothing set state["__block_attempt"]


def test_brain_single_call_event_includes_content_type_and_is_final():
    err = LLMUpstreamError(
        provider="openai", status=502, content_type="text/html",
        body_snippet="Bad Gateway", cf_ray="ray-b", request_id=None, attempts=3,
    )
    raised, events = _capture_events_and_run_brain(
        {"label": "t", "isAgentic": False, "description": "sys", "prompt": "do"},
        mock_side_effect=err,
    )
    blocked = [e for e in events if e["kind"] == "llm_upstream_blocked"]
    p = blocked[0]["payload"]
    assert p["content_type"] == "text/html"
    assert p["is_final"] is True
    assert p["block_attempt"] == 1


# ── outer_attempt from state is forwarded to adapter ──────────────────────────

def test_state_block_attempt_forwards_to_outer_attempt():
    """If future dag_runner sets state['__block_attempt']=N, adapter receives it."""
    captured: dict = {}
    mock_llm = MagicMock()

    def _capture(**kwargs):
        captured.update(kwargs)
        from app.runtime.llm_client import LLMResponse, LLMTextBlock, LLMUsage
        return LLMResponse(
            content=[LLMTextBlock(text="ok")], stop_reason="end_turn",
            usage=LLMUsage(input_tokens=1, output_tokens=1), cost_usd=0.0,
            _raw_content=[{"type": "text", "text": "ok"}],
        )

    mock_llm.create.side_effect = _capture
    block = {"id": "brain-1", "type": "brain",
             "data": {"isAgentic": True, "description": "sys", "max_turns": 1}}
    artifacts = {"brain-1": {"system_prompt": "sys", "is_agentic": True}}
    redis_mock = MagicMock(); redis_mock.get.return_value = None

    with (
        patch("app.runtime.blocks.brain_block.AnthropicClient", return_value=mock_llm),
        patch("app.runtime.blocks.brain_block._get_redis", return_value=redis_mock),
    ):
        from app.runtime.blocks.brain_block import _execute_brain
        _execute_brain(
            block=block, state={"__block_attempt": 2},
            compiled_artifacts=artifacts,
            run_id="run-1", block_id="brain-1",
        )
    assert captured["outer_attempt"] == 2


# ── dag_runner._with_retry never re-invokes on LLMUpstreamError ───────────────

def test_with_retry_does_not_retry_llm_upstream_error():
    """Adapter already ran its own 3-attempt ladder. Block-level retry would
    stack (3×N calls) and emit N false-terminal llm_upstream_blocked events.
    _with_retry must raise LLMUpstreamError on the first hit."""

    calls = {"n": 0}
    err = LLMUpstreamError(
        provider="anthropic", status=403, content_type="text/html",
        body_snippet="Blocked", cf_ray="ray-x", request_id=None, attempts=3,
    )

    def _boom():
        calls["n"] += 1
        raise err

    with pytest.raises(LLMUpstreamError):
        _with_retry(_boom, {"max": 3, "on": ["tool_error"]})

    assert calls["n"] == 1, "LLMUpstreamError must not be retried at block level"
