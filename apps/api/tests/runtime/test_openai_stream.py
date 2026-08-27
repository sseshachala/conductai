"""Sanity check for OpenAI adapter's stream() — no real API call."""
from __future__ import annotations

from unittest.mock import patch, MagicMock

# Import llm_client first so its re-export at the bottom runs before
# our test triggers a partial import of app.runtime.adapters.openai.
import app.runtime.llm_client  # noqa: F401
from app.runtime.adapters.openai import OpenAIClient


class _FakeStreamResponse:
    """Mimic httpx.Response as returned by httpx.stream() context manager."""
    def __init__(self, lines: list[str], status_code: int = 200):
        self.status_code = status_code
        self._lines = lines

    def iter_lines(self):
        yield from self._lines

    def iter_bytes(self):  # only used on error path
        yield b""


class _FakeStreamCM:
    def __init__(self, resp):
        self._resp = resp
    def __enter__(self):
        return self._resp
    def __exit__(self, *a):
        return False


def test_stream_yields_deltas_and_terminates_on_done():
    lines = [
        'data: {"choices":[{"delta":{"content":"Hello"}}]}',
        'data: {"choices":[{"delta":{"content":" "}}]}',
        'data: {"choices":[{"delta":{"content":"world"}}]}',
        'data: [DONE]',
        'data: {"choices":[{"delta":{"content":"ignored"}}]}',  # after DONE
    ]
    fake_resp = _FakeStreamResponse(lines)
    with patch("httpx.stream", return_value=_FakeStreamCM(fake_resp)):
        client = OpenAIClient(api_key="stub")
        out = list(client.stream(model="gpt-4o-mini", messages=[{"role": "user", "content": "hi"}], system="You are helpful."))
    assert out == ["Hello", " ", "world"], out


def test_stream_skips_choice_less_and_content_less_deltas():
    lines = [
        'data: {"choices":[]}',                                # no choices at all
        'data: {"choices":[{"delta":{}}]}',                     # empty delta
        'data: {"choices":[{"delta":{"role":"assistant"}}]}',   # role-only delta (first frame)
        'data: {"choices":[{"delta":{"content":"ok"}}]}',
        'data: [DONE]',
    ]
    fake_resp = _FakeStreamResponse(lines)
    with patch("httpx.stream", return_value=_FakeStreamCM(fake_resp)):
        client = OpenAIClient(api_key="stub")
        out = list(client.stream(model="gpt-4o-mini", messages=[], system=""))
    assert out == ["ok"], out


def test_stream_raises_on_http_error_body():
    fake_resp = _FakeStreamResponse(lines=[], status_code=401)
    fake_resp.iter_bytes = lambda: iter([b'{"error":{"message":"bad key"}}'])
    with patch("httpx.stream", return_value=_FakeStreamCM(fake_resp)):
        client = OpenAIClient(api_key="stub")
        try:
            list(client.stream(model="gpt-4o-mini", messages=[], system=""))
        except Exception as e:
            assert "401" in str(e) and "bad key" in str(e), str(e)
        else:
            raise AssertionError("expected exception on 401")
