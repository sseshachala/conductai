import io
import json
from email.message import Message
from urllib.error import HTTPError

import pytest

from conduct_cli.commands import audit_feed


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _ok(ids, cursor):
    page = {"kind": "audit_feed", "events": [{"id": i} for i in ids], "next_cursor": cursor, "has_more": False}
    return {"jsonrpc": "2.0", "id": "1", "result": {"content": [{"type": "text", "text": ""}],
                                                    "structuredContent": page}}


@pytest.fixture
def mcp(monkeypatch):
    calls, replies = [], []
    # A feed-token collector has no login on the host: config holds no agent token.
    monkeypatch.setattr(audit_feed, "_load_config", lambda: {"api_url": "https://api.test"})

    def fake_urlopen(req, timeout=None):
        calls.append({"auth": req.headers.get("Authorization")})
        nxt = replies.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return _Resp(json.dumps(nxt).encode())

    monkeypatch.setattr(audit_feed.urllib.request, "urlopen", fake_urlopen)
    return calls, replies


def _run(tmp_path, token):
    return audit_feed.run_feed(since=None, limit=5, follow=False, interval=0,
                               state=tmp_path / "c", out=io.StringIO(), feed_token=token)


def test_feed_token_works_without_login(mcp, tmp_path):
    calls, replies = mcp
    replies.append(_ok(["a"], "c1"))
    assert _run(tmp_path, "cond_feed_abc") == 1
    assert calls[0]["auth"] == "Bearer cond_feed_abc"


def test_no_token_at_all_explains_both_options(mcp, tmp_path):
    with pytest.raises(audit_feed.FeedError, match="--token-file"):
        _run(tmp_path, None)


def test_feed_token_401_does_not_refresh_and_says_revoked(mcp, tmp_path, monkeypatch):
    calls, replies = mcp
    replies.append(HTTPError("u", 401, "x", Message(), None))
    monkeypatch.setattr("conduct_cli.commands.auth._refresh_agent_token",
                        lambda **k: pytest.fail("must not refresh a service token"))
    with pytest.raises(audit_feed.FeedError, match="revoked"):
        _run(tmp_path, "cond_feed_abc")
    assert len(calls) == 1


def test_resolve_feed_token_precedence_and_errors(tmp_path):
    f = tmp_path / "tok"
    f.write_text("cond_feed_file\n")
    env = {"CONDUCT_FEED_TOKEN": "cond_feed_env"}
    assert audit_feed.resolve_feed_token(str(f), env) == "cond_feed_file"
    assert audit_feed.resolve_feed_token(None, env) == "cond_feed_env"
    assert audit_feed.resolve_feed_token(None, {}) is None
    with pytest.raises(audit_feed.FeedError, match="cannot read"):
        audit_feed.resolve_feed_token(str(tmp_path / "missing"), {})
    f.write_text("  \n")
    with pytest.raises(audit_feed.FeedError, match="empty"):
        audit_feed.resolve_feed_token(str(f), {})


def test_errors_never_echo_the_token(mcp, tmp_path):
    calls, replies = mcp
    replies.append(HTTPError("u", 500, "x", Message(), None))
    with pytest.raises(audit_feed.FeedError) as ei:
        _run(tmp_path, "cond_feed_SECRET")
    assert "SECRET" not in str(ei.value)
