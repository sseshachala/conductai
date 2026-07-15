import io
import json
import urllib.error
import urllib.parse
import urllib.request
from unittest.mock import MagicMock, call, patch

import pytest

from conduct_cli.main import _exchange_clerk_token, _refresh_agent_token


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_urlopen_response(payload: dict):
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(payload).encode()
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


def _make_http_error(url: str, code: int, body: bytes):
    return urllib.error.HTTPError(url, code, "Error", {}, io.BytesIO(body))


# ---------------------------------------------------------------------------
# _exchange_clerk_token
# ---------------------------------------------------------------------------

def test_exchange_returns_agent_token_on_200():
    payload = {"access_token": "tok_abc", "refresh_token": "ref_xyz", "workspace_id": "ws_1"}
    with patch("urllib.request.urlopen", return_value=_make_urlopen_response(payload)):
        result = _exchange_clerk_token("https://api.example.com", "clerk_tok", "ws_1")
    assert result["agent_token"] == "tok_abc"
    assert result["refresh_token"] == "ref_xyz"
    assert result["workspace_id"] == "ws_1"


def test_exchange_workspace_id_falls_back_to_input():
    payload = {"access_token": "tok_abc"}
    with patch("urllib.request.urlopen", return_value=_make_urlopen_response(payload)):
        result = _exchange_clerk_token("https://api.example.com", "clerk_tok", "ws_fallback")
    assert result["workspace_id"] == "ws_fallback"


def test_exchange_refresh_token_defaults_to_empty_string():
    payload = {"access_token": "tok_abc"}
    with patch("urllib.request.urlopen", return_value=_make_urlopen_response(payload)):
        result = _exchange_clerk_token("https://api.example.com", "clerk_tok", "ws_1")
    assert result["refresh_token"] == ""


def test_exchange_http_error_json_body_exits(capsys):
    body = json.dumps({"detail": "invalid clerk token"}).encode()
    err = _make_http_error("https://api.example.com/token", 401, body)
    with patch("urllib.request.urlopen", side_effect=err):
        with pytest.raises(SystemExit):
            _exchange_clerk_token("https://api.example.com", "bad_tok", "ws_1")
    captured = capsys.readouterr()
    assert "Login failed" in captured.out
    assert "invalid clerk token" in captured.out


def test_exchange_http_error_non_json_body_exits(capsys):
    body = b"Service Unavailable"
    err = _make_http_error("https://api.example.com/token", 503, body)
    with patch("urllib.request.urlopen", side_effect=err):
        with pytest.raises(SystemExit):
            _exchange_clerk_token("https://api.example.com", "bad_tok", "ws_1")
    captured = capsys.readouterr()
    assert "Login failed" in captured.out
    assert "Service Unavailable" in captured.out


def test_exchange_posts_to_correct_url():
    payload = {"access_token": "tok_abc"}
    captured_req = {}

    def fake_urlopen(req, timeout=None):
        captured_req["url"] = req.full_url
        captured_req["method"] = req.method
        captured_req["headers"] = dict(req.headers)
        captured_req["data"] = req.data
        return _make_urlopen_response(payload)

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        _exchange_clerk_token("https://api.example.com", "clerk_tok", "ws_1")

    assert captured_req["url"] == "https://api.example.com/token"
    assert captured_req["method"] == "POST"
    assert captured_req["headers"].get("Content-type") == "application/x-www-form-urlencoded"


def test_exchange_form_body_fields():
    payload = {"access_token": "tok_abc"}
    captured_req = {}

    def fake_urlopen(req, timeout=None):
        captured_req["data"] = req.data
        return _make_urlopen_response(payload)

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        _exchange_clerk_token("https://api.example.com", "clerk_tok", "ws_1")

    parsed = urllib.parse.parse_qs(captured_req["data"].decode())
    assert parsed["grant_type"] == ["urn:ietf:params:oauth:grant-type:token-exchange"]
    assert parsed["subject_token"] == ["clerk_tok"]
    assert parsed["subject_token_type"] == ["urn:ietf:params:oauth:token-type:jwt"]
    assert parsed["resource"] == ["ws_1"]


# ---------------------------------------------------------------------------
# _refresh_agent_token
# ---------------------------------------------------------------------------

def test_refresh_returns_false_when_no_refresh_token():
    with patch("conduct_cli.main._load_config", return_value={}):
        assert _refresh_agent_token() is False


def test_refresh_returns_false_when_refresh_token_empty_string():
    with patch("conduct_cli.main._load_config", return_value={"refresh_token": ""}):
        assert _refresh_agent_token() is False


def test_refresh_returns_true_on_success():
    cfg = {"refresh_token": "ref_old", "api_url": "https://api.example.com"}
    response_payload = {
        "agent_token": "tok_new",
        "refresh_token": "ref_new",
        "workspace_id": "ws_1",
    }
    with patch("conduct_cli.main._load_config", return_value=cfg), \
         patch("conduct_cli.main._atomic_write") as mock_write, \
         patch("urllib.request.urlopen", return_value=_make_urlopen_response(response_payload)):
        result = _refresh_agent_token()

    assert result is True


def test_refresh_updates_config_fields():
    cfg = {"refresh_token": "ref_old", "api_url": "https://api.example.com"}
    response_payload = {
        "agent_token": "tok_new",
        "refresh_token": "ref_new",
        "workspace_id": "ws_99",
    }
    written_data = {}

    def capture_write(path, data):
        written_data.update(data)

    with patch("conduct_cli.main._load_config", return_value=cfg), \
         patch("conduct_cli.main._atomic_write", side_effect=capture_write), \
         patch("urllib.request.urlopen", return_value=_make_urlopen_response(response_payload)):
        _refresh_agent_token()

    assert written_data["agent_token"] == "tok_new"
    assert written_data["refresh_token"] == "ref_new"
    assert written_data["workspace"] == "ws_99"
    assert written_data["workspace_id"] == "ws_99"
    assert "token_expires_at" in written_data


def test_refresh_returns_false_on_network_error():
    cfg = {"refresh_token": "ref_old", "api_url": "https://api.example.com"}
    with patch("conduct_cli.main._load_config", return_value=cfg), \
         patch("urllib.request.urlopen", side_effect=OSError("connection refused")):
        assert _refresh_agent_token() is False


def test_refresh_returns_false_on_bad_json_response():
    cfg = {"refresh_token": "ref_old", "api_url": "https://api.example.com"}
    bad_resp = MagicMock()
    bad_resp.read.return_value = b"not json {"
    bad_resp.__enter__ = lambda s: s
    bad_resp.__exit__ = MagicMock(return_value=False)
    with patch("conduct_cli.main._load_config", return_value=cfg), \
         patch("urllib.request.urlopen", return_value=bad_resp):
        assert _refresh_agent_token() is False


def test_refresh_posts_to_correct_url():
    cfg = {"refresh_token": "ref_tok", "api_url": "https://api.example.com"}
    response_payload = {
        "agent_token": "tok_new",
        "refresh_token": "ref_new",
        "workspace_id": "ws_1",
    }
    captured_req = {}

    def fake_urlopen(req, timeout=None):
        captured_req["url"] = req.full_url
        captured_req["method"] = req.method
        captured_req["data"] = req.data
        captured_req["headers"] = dict(req.headers)
        return _make_urlopen_response(response_payload)

    with patch("conduct_cli.main._load_config", return_value=cfg), \
         patch("conduct_cli.main._atomic_write"), \
         patch("urllib.request.urlopen", side_effect=fake_urlopen):
        _refresh_agent_token()

    assert captured_req["url"] == "https://api.example.com/auth/refresh"
    assert captured_req["method"] == "POST"
    assert captured_req["headers"].get("Content-type") == "application/json"
    body = json.loads(captured_req["data"].decode())
    assert body["refresh_token"] == "ref_tok"


def test_refresh_uses_default_api_url_when_not_in_config():
    cfg = {"refresh_token": "ref_tok"}
    response_payload = {
        "agent_token": "tok_new",
        "refresh_token": "ref_new",
        "workspace_id": "ws_1",
    }
    captured_req = {}

    def fake_urlopen(req, timeout=None):
        captured_req["url"] = req.full_url
        return _make_urlopen_response(response_payload)

    with patch("conduct_cli.main._load_config", return_value=cfg), \
         patch("conduct_cli.main._atomic_write"), \
         patch("urllib.request.urlopen", side_effect=fake_urlopen):
        _refresh_agent_token()

    assert captured_req["url"] == "https://api.conductai.ai/auth/refresh"
