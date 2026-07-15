import json
import socket
import sys
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

from conduct_cli.api import _friendly, headers, req, req_text, stream, find_or_create_workflow


# ---------------------------------------------------------------------------
# _friendly
# ---------------------------------------------------------------------------

def test_friendly_unknown_code_returns_detail_unchanged():
    assert _friendly(500, "internal error") == "internal error"


def test_friendly_401_appends_hint():
    result = _friendly(401, "Unauthorized")
    assert "run `conduct login` to re-authenticate" in result


def test_friendly_403_appends_hint():
    result = _friendly(403, "Forbidden")
    assert "check your permissions" in result


def test_friendly_404_appends_hint():
    result = _friendly(404, "Not Found")
    assert "not found" in result.lower()


def test_friendly_429_appends_hint():
    result = _friendly(429, "Too Many Requests")
    assert "rate limited" in result


def test_friendly_401_no_double_append_when_hint_already_in_detail():
    detail = "run `conduct login` to re-authenticate"
    assert _friendly(401, detail) == detail


def test_friendly_case_insensitive_no_double_append():
    detail = "Run `Conduct Login` To Re-Authenticate"
    assert _friendly(401, detail) == detail


# ---------------------------------------------------------------------------
# headers
# ---------------------------------------------------------------------------

def test_headers_always_sets_content_type_and_workspace_id():
    h = headers("ws-1")
    assert h["Content-Type"] == "application/json"
    assert h["X-Workspace-Id"] == "ws-1"


def test_headers_sets_bearer_when_token_given():
    h = headers("ws-1", token="tok123")
    assert h["Authorization"] == "Bearer tok123"
    assert "X-Api-Key" not in h


def test_headers_sets_api_key_and_no_authorization():
    h = headers("ws-1", api_key="key-abc")
    assert h["X-Api-Key"] == "key-abc"
    assert "Authorization" not in h


def test_headers_api_key_takes_precedence_over_token():
    h = headers("ws-1", token="tok", api_key="key")
    assert h["X-Api-Key"] == "key"
    assert "Authorization" not in h


def test_headers_custom_content_type():
    h = headers("ws-1", content_type="text/plain")
    assert h["Content-Type"] == "text/plain"


# ---------------------------------------------------------------------------
# req
# ---------------------------------------------------------------------------

def _make_urlopen_response(body: bytes):
    mock_resp = MagicMock()
    mock_resp.read.return_value = body
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


def test_req_returns_parsed_json_on_200():
    payload = {"id": "abc"}
    with patch("urllib.request.urlopen", return_value=_make_urlopen_response(json.dumps(payload).encode())):
        result = req("GET", "http://example.com/x", {})
    assert result == payload


def test_req_returns_empty_dict_on_empty_body():
    with patch("urllib.request.urlopen", return_value=_make_urlopen_response(b"")):
        result = req("GET", "http://example.com/x", {})
    assert result == {}


def test_req_http_error_json_body_exits_1(capsys):
    import urllib.error
    err = urllib.error.HTTPError(
        url="http://x", code=400, msg="Bad Request",
        hdrs=None, fp=BytesIO(b'{"detail": "bad input"}')
    )
    with patch("urllib.request.urlopen", side_effect=err):
        with pytest.raises(SystemExit) as exc:
            req("GET", "http://example.com/x", {})
    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert "bad input" in captured.out


def test_req_http_error_401_detail_in_output(capsys):
    import urllib.error
    err = urllib.error.HTTPError(
        url="http://x", code=401, msg="Unauthorized",
        hdrs=None, fp=BytesIO(b'{"detail": "token expired"}')
    )
    with patch("urllib.request.urlopen", side_effect=err):
        with pytest.raises(SystemExit):
            req("GET", "http://example.com/x", {})
    captured = capsys.readouterr()
    assert "token expired" in captured.out
    assert "HTTP 401:" not in captured.out


def test_req_http_error_non_json_body(capsys):
    import urllib.error
    err = urllib.error.HTTPError(
        url="http://x", code=500, msg="Error",
        hdrs=None, fp=BytesIO(b"plain error text")
    )
    with patch("urllib.request.urlopen", side_effect=err):
        with pytest.raises(SystemExit):
            req("GET", "http://example.com/x", {})
    captured = capsys.readouterr()
    assert "plain error text" in captured.out


def test_req_socket_timeout_exits_1(capsys):
    with patch("urllib.request.urlopen", side_effect=socket.timeout()):
        with pytest.raises(SystemExit) as exc:
            req("GET", "http://example.com/x", {})
    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert "timed out" in captured.out


def test_req_sends_body_as_json():
    payload = {"id": "abc"}
    captured_request = {}

    def fake_urlopen(request, timeout=30):
        captured_request["data"] = request.data
        return _make_urlopen_response(b"{}")

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        req("POST", "http://example.com/x", {}, body={"key": "val"})

    assert json.loads(captured_request["data"]) == {"key": "val"}


def test_req_sends_no_body_when_body_is_none():
    captured_request = {}

    def fake_urlopen(request, timeout=30):
        captured_request["data"] = request.data
        return _make_urlopen_response(b"{}")

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        req("GET", "http://example.com/x", {}, body=None)

    assert captured_request["data"] is None


# ---------------------------------------------------------------------------
# req_text
# ---------------------------------------------------------------------------

def test_req_text_returns_parsed_json_on_200():
    payload = {"ok": True}
    with patch("urllib.request.urlopen", return_value=_make_urlopen_response(json.dumps(payload).encode())):
        result = req_text("POST", "http://example.com/x", {}, "raw body")
    assert result == payload


def test_req_text_http_error_exits_1(capsys):
    import urllib.error
    err = urllib.error.HTTPError(
        url="http://x", code=403, msg="Forbidden",
        hdrs=None, fp=BytesIO(b'{"detail": "access denied"}')
    )
    with patch("urllib.request.urlopen", side_effect=err):
        with pytest.raises(SystemExit) as exc:
            req_text("POST", "http://example.com/x", {}, "body")
    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert "access denied" in captured.out


def test_req_text_timeout_exits_1(capsys):
    with patch("urllib.request.urlopen", side_effect=socket.timeout()):
        with pytest.raises(SystemExit) as exc:
            req_text("POST", "http://example.com/x", {}, "body")
    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert "timed out" in captured.out


def test_req_text_body_sent_as_utf8_not_json_encoded():
    captured_request = {}

    def fake_urlopen(request, timeout=30):
        captured_request["data"] = request.data
        return _make_urlopen_response(b"{}")

    raw = "hello world"
    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        req_text("POST", "http://example.com/x", {}, raw)

    assert captured_request["data"] == raw.encode("utf-8")
    # Must NOT be JSON-encoded (would be b'"hello world"')
    assert captured_request["data"] != json.dumps(raw).encode()


# ---------------------------------------------------------------------------
# stream
# ---------------------------------------------------------------------------

def _byte_reader(data: bytes):
    """Returns a mock resp whose read(1) yields bytes one at a time then b''."""
    buf = bytearray(data)
    idx = [0]

    def read_one(n=1):
        if idx[0] >= len(buf):
            return b""
        byte = bytes([buf[idx[0]]])
        idx[0] += 1
        return byte

    mock_resp = MagicMock()
    mock_resp.read.side_effect = read_one
    return mock_resp


def _stream_urlopen(sse_bytes: bytes):
    mock_resp = _byte_reader(sse_bytes)

    def fake_urlopen(request):
        return mock_resp

    return patch("urllib.request.urlopen", side_effect=fake_urlopen)


def test_stream_yields_single_event_with_data():
    sse = b"data: {\"msg\": \"hello\"}\n\n"
    with _stream_urlopen(sse):
        events = list(stream("http://example.com/sse"))
    assert len(events) == 1
    assert events[0]["msg"] == "hello"


def test_stream_default_kind_is_message():
    sse = b"data: {\"x\": 1}\n\n"
    with _stream_urlopen(sse):
        events = list(stream("http://example.com/sse"))
    assert events[0]["kind"] == "message"


def test_stream_kind_set_from_event_line():
    sse = b"event: run.done\ndata: {\"status\": \"ok\"}\n\n"
    with _stream_urlopen(sse):
        events = list(stream("http://example.com/sse"))
    assert events[0]["kind"] == "run.done"


def test_stream_kind_key_in_data():
    sse = b"event: log\ndata: {\"line\": \"hello\"}\n\n"
    with _stream_urlopen(sse):
        events = list(stream("http://example.com/sse"))
    assert "kind" in events[0]
    assert events[0]["kind"] == "log"


def test_stream_non_json_data_produces_raw():
    sse = b"data: not-valid-json\n\n"
    with _stream_urlopen(sse):
        events = list(stream("http://example.com/sse"))
    assert events[0]["raw"] == "not-valid-json"
    assert "kind" in events[0]


def test_stream_yields_multiple_events():
    sse = (
        b"data: {\"i\": 1}\n\n"
        b"data: {\"i\": 2}\n\n"
        b"data: {\"i\": 3}\n\n"
    )
    with _stream_urlopen(sse):
        events = list(stream("http://example.com/sse"))
    assert len(events) == 3
    assert [e["i"] for e in events] == [1, 2, 3]


def test_stream_raises_runtime_error_on_http_error():
    import urllib.error
    err = urllib.error.HTTPError(
        url="http://x", code=401, msg="Unauthorized",
        hdrs=None, fp=BytesIO(b"not authorized")
    )
    with patch("urllib.request.urlopen", side_effect=err):
        with pytest.raises(RuntimeError, match="Stream 401"):
            list(stream("http://example.com/sse"))


# ---------------------------------------------------------------------------
# find_or_create_workflow
# ---------------------------------------------------------------------------

def test_find_or_create_workflow_returns_existing_id():
    workflows = [{"name": "deploy", "id": "wf-1"}, {"name": "other", "id": "wf-2"}]
    with patch("conduct_cli.api.req") as mock_req:
        mock_req.return_value = workflows
        result = find_or_create_workflow("http://srv", "deploy", {})
    assert result == "wf-1"
    mock_req.assert_called_once_with("GET", "http://srv/workflows", {})


def test_find_or_create_workflow_creates_when_not_found():
    with patch("conduct_cli.api.req") as mock_req:
        mock_req.side_effect = [
            [{"name": "other", "id": "wf-99"}],
            {"id": "wf-new"},
        ]
        result = find_or_create_workflow("http://srv", "new-wf", {})
    assert result == "wf-new"
    assert mock_req.call_count == 2
    create_call = mock_req.call_args_list[1]
    assert create_call.args[0] == "POST"
    assert create_call.args[3]["name"] == "new-wf"
