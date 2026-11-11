import json

from conduct_cli import tool_correlation as tc
from conduct_cli.hooks import posttooluse


def test_parse_header_drops_malformed():
    assert tc.parse_correlation_header(
        "call_a=9c4f3e21a7b0d8e1,x,y=,z=nothex,call_b=1f8b3c22e5a06d94"
    ) == {"call_a": "9c4f3e21a7b0d8e1", "call_b": "1f8b3c22e5a06d94"}
    assert tc.parse_correlation_header(None) == {}


def test_correlation_for_tool_use_from_header_string():
    data = {"tool_use_id": "call_a", "conduct_tool_correlation_ids": "call_a=9c4f3e21a7b0d8e1"}
    assert tc.correlation_id_for_tool_use(data) == "9c4f3e21a7b0d8e1"
    assert tc.correlation_id_for_tool_use({**data, "tool_use_id": "other"}) is None
    assert tc.correlation_id_for_tool_use({"tool_use_id": "x"}) is None


def test_post_usage_includes_correlation_id(monkeypatch):
    appended = []
    monkeypatch.setattr(posttooluse, "load_config", lambda: {"api_url": "https://api.test", "workspace_id": "w"})
    monkeypatch.setattr(posttooluse, "journal_append", lambda p, u, endpoint: appended.append(p))
    monkeypatch.setattr(posttooluse, "ensure_drain_daemon", lambda _p: None)
    posttooluse._post_usage("s", "bash", None, None, None, tool_use_id="call_a", correlation_id="9c4f3e21a7b0d8e1")
    assert json.loads(appended[0])["correlation_id"] == "9c4f3e21a7b0d8e1"
