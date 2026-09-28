import http.server
import io
import urllib.parse
import webbrowser
from unittest.mock import Mock

import pytest

from conduct_cli import main as cli


@pytest.fixture
def callback(monkeypatch):
    captured = {}
    server = Mock()

    def make_server(address, handler):
        captured["handler"] = handler
        assert address[0] == "127.0.0.1"
        return server

    monkeypatch.setattr(http.server, "HTTPServer", make_server)
    monkeypatch.setattr(cli, "_find_free_port", lambda: 12345)

    def request(query):
        handler = captured["handler"].__new__(captured["handler"])
        handler.path = "/callback?" + urllib.parse.urlencode(query)
        handler.wfile = io.BytesIO()
        handler.send_response = Mock()
        handler.send_header = Mock()
        handler.end_headers = Mock()
        handler.do_GET()
        return handler

    return captured, request, server


def test_exchange_completes_before_secret_free_hosted_redirect(callback, monkeypatch):
    captured, request, server = callback
    exchange = Mock(return_value={"agent_token": "test-agent", "workspace_id": "workspace"})
    monkeypatch.setattr(cli, "_exchange_clerk_token", exchange)

    def open_browser(url):
        state = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(url).query))["state"]
        captured["response"] = request({"state": state, "workspace_id": "workspace", "clerk_token": "test-clerk"})
        exchange.assert_called_once()

    monkeypatch.setattr(webbrowser, "open", open_browser)
    result = cli._web_login_flow("https://api.example", "https://app.conductai.ai")
    response = captured["response"]
    response.send_response.assert_called_once_with(303)
    headers = dict(call.args for call in response.send_header.call_args_list)
    assert headers["Location"] == "https://conductai.ai/cli-connected"
    assert headers["Referrer-Policy"] == "no-referrer"
    assert headers["Cache-Control"] == "no-store"
    assert "test-clerk" not in str(headers) and "test-agent" not in str(headers)
    assert result["agent_token"] == "test-agent"
    server.server_close.assert_called_once()


def test_invalid_state_does_not_finish_login(callback, monkeypatch):
    _, request, _ = callback

    def open_browser(url):
        state = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(url).query))["state"]
        bad = request({"state": "wrong", "workspace_id": "workspace", "agent_token": "bad"})
        bad.send_response.assert_called_once_with(400)
        assert "Location" not in dict(call.args for call in bad.send_header.call_args_list)
        request({"state": state, "workspace_id": "workspace", "agent_token": "good"})

    monkeypatch.setattr(webbrowser, "open", open_browser)
    assert cli._web_login_flow("https://api.example", "https://app.conductai.ai")["agent_token"] == "good"


@pytest.mark.parametrize("payload", [{}, {"workspace_id": "workspace"}, {"workspace_id": "workspace", "clerk_token": "bad"}])
def test_failed_callback_never_redirects_to_success(callback, monkeypatch, payload):
    captured, request, _ = callback
    monkeypatch.setattr(cli, "_exchange_clerk_token", Mock(side_effect=SystemExit(1)))

    def open_browser(url):
        state = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(url).query))["state"]
        captured["response"] = request({**payload, "state": state})

    monkeypatch.setattr(webbrowser, "open", open_browser)
    with pytest.raises(SystemExit) as error:
        cli._web_login_flow("https://api.example", "https://app.conductai.ai")
    assert error.value.code == 1
    response = captured["response"]
    response.send_response.assert_called_once_with(400)
    assert "Location" not in dict(call.args for call in response.send_header.call_args_list)


def test_custom_web_deployment_keeps_its_own_confirmation_page(callback, monkeypatch):
    captured, request, _ = callback

    def open_browser(url):
        state = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(url).query))["state"]
        captured["response"] = request({"state": state, "workspace_id": "workspace", "agent_token": "test"})

    monkeypatch.setattr(webbrowser, "open", open_browser)
    cli._web_login_flow("http://localhost:8000", "http://localhost:3100")
    headers = dict(call.args for call in captured["response"].send_header.call_args_list)
    assert headers["Location"] == "http://localhost:3100/cli-connected"
