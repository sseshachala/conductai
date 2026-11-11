import io
import json
import urllib.parse
from types import SimpleNamespace

import pytest

from conduct_cli import audit_sinks as sinks
from conduct_cli.commands import audit_feed

EVENT = {"id": "e1", "ts": "2026-09-01T12:00:00+00:00", "decision": "blocked", "previous_hash": "",
         "entry_hash": "abc", "chain_position": 1}


class FakeHttp:
    """Scripted responses: each item is (status, body_dict_or_bytes, headers) or an exception."""

    def __init__(self, *responses):
        self.responses, self.calls = list(responses), []

    def post(self, url, data, headers):
        self.calls.append({"url": url, "data": data, "headers": headers})
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        status, body, hdrs = r
        return status, body if isinstance(body, bytes) else json.dumps(body).encode(), hdrs or {}


def hec(http, **kw):
    kw.setdefault("sleep", lambda s: None)
    return sinks.SplunkHecSink("https://splunk.test:8088", "HEC-SECRET", http=http, **kw)


def sentinel(http, **kw):
    kw.setdefault("sleep", lambda s: None)
    return sinks.SentinelSink("https://dce.eastus-1.ingest.monitor.azure.com", "dcr-123", "Custom-ConductAudit_CL",
                              "tenant-1", "client-1", "CLIENT-SECRET", http=http, **kw)


OK = (200, {"text": "Success", "code": 0}, None)


def test_hec_request_shape():
    http = FakeHttp(OK)
    hec(http, index="conduct").send([EVENT])
    call = http.calls[0]
    assert call["url"] == "https://splunk.test:8088/services/collector/event"
    assert call["headers"]["Authorization"] == "Splunk HEC-SECRET"
    rec = json.loads(call["data"])
    assert rec["event"] == EVENT and rec["sourcetype"] == "conduct:guard:audit" and rec["index"] == "conduct"
    assert isinstance(rec["time"], float)


def test_hec_batches_by_count_and_size():
    http = FakeHttp(OK, OK, OK)
    hec(http, max_events=2).send([dict(EVENT, id=str(i)) for i in range(5)])
    assert [c["data"].count(b'"sourcetype"') for c in http.calls] == [2, 2, 1]
    http = FakeHttp(OK, OK)
    hec(http, max_bytes=len(json.dumps(EVENT)) + 150).send([EVENT, EVENT])
    assert len(http.calls) == 2


def test_retries_5xx_and_network_errors_with_backoff():
    sleeps = []
    http = FakeHttp((503, b"busy", None), sinks._Retryable("network error"), (500, b"", None), OK)
    hec(http, sleep=sleeps.append, backoff=1, rng=lambda: 1.0).send([EVENT])
    assert len(http.calls) == 4 and sleeps == [1.0, 2.0, 4.0]


def test_retry_after_is_honoured_and_capped():
    sleeps = []
    http = FakeHttp((429, b"", {"Retry-After": "7"}), OK)
    hec(http, sleep=sleeps.append).send([EVENT])
    assert sleeps == [7.0]


def test_gives_up_after_attempts_without_leaking_secret():
    http = FakeHttp(*[(500, b"", None)] * 3)
    with pytest.raises(sinks.SinkError) as ei:
        hec(http, attempts=3).send([EVENT])
    assert "3 attempts" in str(ei.value) and "HEC-SECRET" not in str(ei.value)


def test_client_errors_are_not_retried():
    http = FakeHttp((403, b"Invalid token", None))
    with pytest.raises(sinks.SinkError, match="403"):
        hec(http).send([EVENT])
    assert len(http.calls) == 1


def test_hec_non_zero_code_is_not_an_ack():
    http = FakeHttp((200, {"text": "Incorrect data format", "code": 5}, None))
    with pytest.raises(sinks.SinkError):
        hec(http).send([EVENT])


def test_sentinel_authenticates_then_posts_array_with_timegenerated():
    http = FakeHttp((200, {"access_token": "TOK", "expires_in": 3600}, None), (204, b"", None))
    sentinel(http).send([EVENT])
    token_call, post = http.calls
    assert token_call["url"] == "https://login.microsoftonline.com/tenant-1/oauth2/v2.0/token"
    form = urllib.parse.parse_qs(token_call["data"].decode())
    assert form["grant_type"] == ["client_credentials"] and form["scope"] == ["https://monitor.azure.com//.default"]
    assert post["url"] == ("https://dce.eastus-1.ingest.monitor.azure.com/dataCollectionRules/dcr-123/streams/"
                           "Custom-ConductAudit_CL?api-version=2023-01-01")
    assert post["headers"]["Authorization"] == "Bearer TOK"
    body = json.loads(post["data"])
    assert body == [dict(EVENT, TimeGenerated=EVENT["ts"])]


def test_sentinel_caches_token_and_refreshes_once_on_401():
    tok = lambda t: (200, {"access_token": t, "expires_in": 3600}, None)  # noqa: E731
    http = FakeHttp(tok("T1"), (204, b"", None), (204, b"", None), (401, b"", None), tok("T2"), (204, b"", None))
    s = sentinel(http)
    s.send([EVENT])
    s.send([EVENT])  # reuses T1: no new token request
    assert len(http.calls) == 3
    s.send([EVENT])  # 401 -> new token -> success
    assert [c["headers"].get("Authorization") for c in http.calls[3:]] == ["Bearer T1", None, "Bearer T2"]


def test_sentinel_bad_credentials_fail_fast_without_secret():
    http = FakeHttp((401, {"error": "invalid_client"}, None))
    with pytest.raises(sinks.SinkError) as ei:
        sentinel(http).send([EVENT])
    assert "CLIENT-SECRET" not in str(ei.value) and len(http.calls) == 1


def test_sentinel_requires_https():
    with pytest.raises(sinks.SinkError):
        sinks.SentinelSink("http://dce.test", "d", "s", "t", "c", "x")


# ── secrets ──────────────────────────────────────────────────────────────────

def test_read_secret_file_then_env(tmp_path):
    f = tmp_path / "s"
    f.write_text("  from-file\n")
    assert sinks.read_secret(str(f), "X", {"X": "from-env"}) == "from-file"
    assert sinks.read_secret(None, "X", {"X": "from-env"}) == "from-env"
    with pytest.raises(sinks.SinkError, match="not provided"):
        sinks.read_secret(None, "X", {})
    f.write_text("")
    with pytest.raises(sinks.SinkError, match="empty"):
        sinks.read_secret(str(f), "X", {})


def test_build_sink_validates_options(tmp_path):
    ns = lambda **kw: SimpleNamespace(**dict(dict(sink=None, hec_url=None, hec_token_file=None, hec_index=None,  # noqa: E731
                                                  dce_url=None, dcr_id=None, stream=None, tenant_id=None,
                                                  client_id=None, client_secret_file=None), **kw))
    with pytest.raises(sinks.SinkError, match="--hec-url"):
        sinks.build_sink(ns(sink="splunk-hec"), {})
    with pytest.raises(sinks.SinkError, match="--dcr-id"):
        sinks.build_sink(ns(sink="sentinel", dce_url="https://d", stream="s"), {})
    sec = tmp_path / "secret"
    sec.write_text("shh")
    built = sinks.build_sink(ns(sink="sentinel", dce_url="https://d.test", dcr_id="dcr", stream="s",
                                client_secret_file=str(sec)), {"AZURE_TENANT_ID": "t", "AZURE_CLIENT_ID": "c"})
    assert isinstance(built, sinks.SentinelSink)


def test_no_secret_flag_exists_on_the_command_line():
    import argparse
    root = argparse.ArgumentParser()
    sub = root.add_subparsers(dest="c")
    audit_sub = sub.add_parser("audit").add_subparsers(dest="a")
    audit_feed.register_feed(audit_sub)
    flags = [o for act in audit_sub.choices["feed"]._actions for o in act.option_strings]
    assert not [f for f in flags if f in ("--hec-token", "--client-secret", "--token")]


# ── cursor only advances after acknowledgement ───────────────────────────────

class _Sink:
    def __init__(self, fail_on=None):
        self.sent, self.fail_on = [], fail_on

    def send(self, events):
        if self.fail_on is not None and len(self.sent) + 1 == self.fail_on:
            raise sinks.SinkError("down")
        self.sent.append([e["id"] for e in events])


def _pages(monkeypatch):
    pages = [{"events": [{"id": "a"}], "next_cursor": "c1", "has_more": True},
             {"events": [{"id": "b"}], "next_cursor": "c2", "has_more": False}]
    monkeypatch.setattr(audit_feed, "_call_tool", lambda *a, **k: pages.pop(0))


def test_cursor_advances_per_acknowledged_page(monkeypatch, tmp_path):
    _pages(monkeypatch)
    state, sink = tmp_path / "cur", _Sink()
    n = audit_feed.run_feed(since=None, limit=1, follow=False, interval=0, state=state, out=io.StringIO(), sink=sink)
    assert n == 2 and sink.sent == [["a"], ["b"]] and state.read_text() == "c2"


def test_cursor_not_advanced_when_sink_fails(monkeypatch, tmp_path):
    _pages(monkeypatch)
    state, sink = tmp_path / "cur", _Sink(fail_on=2)
    with pytest.raises(sinks.SinkError):
        audit_feed.run_feed(since=None, limit=1, follow=False, interval=0, state=state, out=io.StringIO(), sink=sink)
    assert state.read_text() == "c1"  # page 1 acked, page 2 not
