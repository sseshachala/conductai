from __future__ import annotations

import asyncio
import json
import time

from fastapi import BackgroundTasks

from app.guard.audit import _extract_token_counts
from app.guard.router import _stream_chunks, upstream
from app.modules.guard.routers.proxy import _redact_body


class _Breaker:
    recovery_timeout = 1

    def allow(self, _key):
        return True

    def record_failure(self, _key):
        pass

    def record_success(self, _key):
        pass


class _Response:
    status_code = 429
    headers = {"content-type": "application/json"}

    async def aread(self):
        return b'{"error":{"message":"rate limited"}}'

    async def aclose(self):
        pass


def _audit_args():
    return (
        "workspace", "user", "codex", "openai", "gpt-test", "allowed", None,
        time.monotonic(), {"model": "gpt-test", "input": "hello"}, "hello",
        None, None, None, None, None, None,
    )


def test_openai_responses_stream_usage_is_accounted():
    payload = (
        b'data: {"type":"response.completed","response":{"usage":'
        b'{"input_tokens":12,"output_tokens":7}}}\n\n'
    )
    assert _extract_token_counts({}, payload) == (12, 7)


def test_responses_input_is_redacted_before_forwarding():
    body = {
        "instructions": "Email person@example.com",
        "input": [{"role": "user", "content": [{"type": "input_text", "text": "key sk-abcdefghijklmnopqrstuv"}]}],
    }
    cleaned, findings = _redact_body(body)
    encoded = json.dumps(cleaned)
    assert "person@example.com" not in encoded
    assert "sk-abcdefghijklmnopqrstuv" not in encoded
    assert findings


def test_upstream_error_schedules_flight_recorder_audit(monkeypatch):
    async def _send(self, request, **kwargs):
        return _Response()

    monkeypatch.setattr("app.guard.router._get_breaker", lambda: _Breaker())
    monkeypatch.setattr("httpx.AsyncClient.send", _send)
    background = BackgroundTasks()
    response = asyncio.run(upstream(
        upstream="https://provider.test", path="/v1/responses",
        body={"model": "gpt-test", "input": "hello"}, real_key="test-key",
        auth_header_out="authorization", bearer=True, is_stream=False,
        background=background, audit_args=_audit_args(), provider="openai",
    ))
    assert response.status_code == 429
    assert len(background.tasks) == 1
    assert background.tasks[0].kwargs["execution_status"] == "error"
    assert background.tasks[0].kwargs["result_summary"] == "Upstream HTTP 429"


def test_stream_failure_records_partial_response_as_error():
    class _Client:
        async def aclose(self):
            pass

    class _BrokenStream:
        async def aiter_bytes(self):
            yield b'data: {"type":"response.output_text.delta","delta":"partial"}\n\n'
            raise ConnectionError("provider disconnected")

        async def aclose(self):
            pass

    background = BackgroundTasks()

    async def _consume():
        chunks = []
        try:
            async for chunk in _stream_chunks(
                _Client(), _BrokenStream(), background, _audit_args(),
                upstream_url="https://provider.test",
            ):
                chunks.append(chunk)
        except ConnectionError:
            pass
        return chunks

    assert asyncio.run(_consume())
    assert len(background.tasks) == 1
    task = background.tasks[0]
    assert task.kwargs["execution_status"] == "error"
    assert task.kwargs["result_summary"] == "Upstream stream failed: ConnectionError"
    assert b"partial" in task.kwargs["response_bytes"]
