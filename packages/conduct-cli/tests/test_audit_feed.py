import io
import json
from email.message import Message
from urllib.error import HTTPError

import pytest

from conduct_cli.commands import audit_feed


def _reply(page=None, *, error=None, is_error=False, text=""):
    if error:
        return {"jsonrpc": "2.0", "id": "1", "error": {"code": -32600, "message": error}}
    result = {"content": [{"type": "text", "text": text}]}
    if page is not None:
        result["structuredContent"] = page
    if is_error:
        result["isError"] = True
    return {"jsonrpc": "2.0", "id": "1", "result": result}


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture
def mcp(monkeypatch):
    calls, replies = [], []
    monkeypatch.setattr(audit_feed, "_load_config",
                        lambda: {"agent_token": "cond_agt_s1_x", "api_url": "https://api.test"})

    def fake_urlopen(req, timeout=None):
        calls.append({"url": req.full_url, "auth": req.headers.get("Authorization"),
                      "body": json.loads(req.data)})
        nxt = replies.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return _Resp(json.dumps(nxt).encode())

    monkeypatch.setattr(audit_feed.urllib.request, "urlopen", fake_urlopen)
    return calls, replies


def _page(ids, cursor, more=False):
    return {"kind": "audit_feed", "events": [{"id": i} for i in ids], "next_cursor": cursor, "has_more": more}


def test_drains_pages_and_checkpoints_cursor(mcp, tmp_path):
    calls, replies = mcp
    replies += [_reply(_page(["a", "b"], "c1", more=True)), _reply(_page(["c"], "c2"))]
    state, out = tmp_path / "cursor", io.StringIO()
    n = audit_feed.run_feed(since="2026-11-01T00:00:00Z", limit=2, follow=False, interval=0, state=state, out=out)
    assert n == 3
    assert [json.loads(line)["id"] for line in out.getvalue().splitlines()] == ["a", "b", "c"]
    assert state.read_text() == "c2"
    first, second = (c["body"]["params"] for c in calls)
    assert first == {"name": "get_audit_feed", "arguments": {"limit": 2, "since": "2026-11-01T00:00:00Z"}}
    assert second["arguments"] == {"limit": 2, "cursor": "c1"}
    assert calls[0]["auth"] == "Bearer cond_agt_s1_x" and calls[0]["url"].endswith("/mcp")


def test_resumes_from_saved_cursor_and_ignores_since(mcp, tmp_path):
    calls, replies = mcp
    state = tmp_path / "cursor"
    state.write_text("saved")
    replies.append(_reply(_page([], "saved")))
    audit_feed.run_feed(since="2026-01-01T00:00:00Z", limit=500, follow=False, interval=0, state=state, out=io.StringIO())
    assert calls[0]["body"]["params"]["arguments"] == {"limit": 500, "cursor": "saved"}


def test_follow_sleeps_between_polls(mcp, tmp_path):
    _, replies = mcp
    replies += [_reply(_page(["a"], "c1")), _reply(_page([], "c1"))]
    sleeps = []

    def stop_after_two(seconds):
        sleeps.append(seconds)
        if len(sleeps) == 2:
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        audit_feed.run_feed(since=None, limit=500, follow=True, interval=30, state=tmp_path / "c",
                            out=io.StringIO(), sleep=stop_after_two)
    assert sleeps == [30, 30]


@pytest.mark.parametrize("reply,message", [
    (_reply(error="Unauthorized tool"), "MCP error: Unauthorized tool"),
    (_reply({"error": "forbidden: reading the audit feed requires platform.audit_log.view"}), "forbidden"),
    (_reply(is_error=True, text="Tool 'get_audit_feed' failed: boom"), "failed: boom"),
])
def test_errors_surface_and_cursor_untouched(mcp, tmp_path, reply, message):
    _, replies = mcp
    replies.append(reply)
    state = tmp_path / "cursor"
    with pytest.raises(audit_feed.FeedError, match=message):
        audit_feed.run_feed(since=None, limit=500, follow=False, interval=0, state=state, out=io.StringIO())
    assert not state.exists()


def test_refreshes_token_once_on_401(mcp, monkeypatch, tmp_path):
    calls, replies = mcp
    replies += [HTTPError("https://api.test/mcp", 401, "expired", Message(), io.BytesIO()), _reply(_page(["a"], "c1"))]
    refreshed = []
    monkeypatch.setattr("conduct_cli.commands.auth._refresh_agent_token",
                        lambda expected_config=None: refreshed.append(1) or True)
    assert audit_feed.run_feed(since=None, limit=500, follow=False, interval=0,
                               state=tmp_path / "c", out=io.StringIO()) == 1
    assert refreshed == [1] and len(calls) == 2


def test_cli_parses_feed_subcommand():
    import argparse
    from conduct_cli.commands.audit import register_audit
    parser = argparse.ArgumentParser()
    register_audit(parser.add_subparsers(dest="command"))
    args = parser.parse_args(["audit", "feed", "--follow", "--output", "x.ndjson", "--limit", "100"])
    assert (args.audit_command, args.follow, args.output, args.limit, args.interval) == ("feed", True, "x.ndjson", 100, 60.0)
