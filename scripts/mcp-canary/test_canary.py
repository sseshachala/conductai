"""Unit and real-HTTP harness tests; no Conduct production services involved."""
import json
import importlib.util
import os
from pathlib import Path
import subprocess
import sqlite3
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from uuid import uuid4
from urllib.parse import parse_qs, urlsplit

import pytest

from core import Ledger, reconcile, rpc_result, validate, verdict

HERE = Path(__file__).parent


def configuration(monkeypatch):
    config = json.loads((HERE / "example.json").read_text())
    for agent in config["agents"]:
        monkeypatch.setenv(agent["token_env"], "cond_agt_" + agent["id"])
    monkeypatch.setenv(config["observer_token_env"], "observer-test-placeholder")
    return config


def test_remote_requires_exact_origin_and_workspace(monkeypatch):
    c = configuration(monkeypatch)
    c["base_url"] = "https://api.example.test"
    with pytest.raises(ValueError, match="Remote"):
        validate(c)
    assert validate(c, c["base_url"] + "|" + c["workspace_id"])
    c["base_url"] += "?token=secret"
    with pytest.raises(ValueError):
        validate(c)


@pytest.mark.parametrize("field,value", [("rps", 0), ("rps", float("nan")), ("concurrency", 1.5),
                                         ("max_requests", 1), ("duration_seconds", 999999)])
def test_bounds(monkeypatch, field, value):
    c = configuration(monkeypatch)
    c[field] = value
    with pytest.raises(ValueError):
        validate(c)


def test_reused_tokens_not_distinct_agents(monkeypatch):
    c = configuration(monkeypatch)
    monkeypatch.setenv(c["agents"][1]["token_env"], os.environ[c["agents"][0]["token_env"]])
    with pytest.raises(ValueError):
        validate(c)


def test_audit_decision_is_explicit_and_not_a_relaxed_match(monkeypatch, tmp_path):
    c = configuration(monkeypatch)
    c['scenarios'][0]['audit_decision'] = 'audited'
    validate(c)
    ledger = Ledger(tmp_path / 'audit.sqlite')
    ledger.begin('call', 'agent', 'session', c['scenarios'][0], 1)
    assert ledger.calls()[0]['decision'] == 'audited'
    ledger.db.close()
    c['scenarios'][0]['audit_decision'] = 'blocked'
    with pytest.raises(ValueError, match='audit_decision'):
        validate(c)


@pytest.mark.parametrize("data", [{"jsonrpc": "2.0", "id": "a", "error": {"code": -1}},
    {"jsonrpc": "2.0", "id": "a", "result": {"isError": True}},
    {"jsonrpc": "2.0", "id": "other", "result": {}}, "html sign-in"])
def test_http_200_is_not_success(data):
    with pytest.raises(ValueError):
        rpc_result(200, data, "a")


def test_workspace_prefix_and_verdict():
    assert verdict({"content": [{"type": "text", "text": "[ws:12345678] ok"}]}) == "allowed"
    assert verdict({"content": [{"type": "text", "text": "BLOCKED policy"}]}) == "blocked"
    with pytest.raises(ValueError):
        verdict({"content": [{"type": "text", "text": "advisory: failed open"}]})


def test_ledger_survives_reopen_and_reconciliation_is_strict(tmp_path):
    ledger = Ledger(tmp_path / "ledger.sqlite")
    call_id = uuid4().hex
    ledger.begin(call_id, "agent", "session", {"name": "allowed", "tool_name": "read", "decision": "allowed"}, 1)
    calls = ledger.calls()
    assert calls[0]["outcome"] == "pending"
    event = {"id": "event1", "workspace_id": "ws", "agent_identity_id": "agent", "hook_session_id": "session",
             "tool_call": "read", "decision": "allowed", "source": "mcp", "input_summary": json.dumps({"canary_call": call_id})}
    assert not reconcile(calls, [event, event], "ws")["failures"]  # overlapping pages, not duplicate records
    assert reconcile(calls, [event, {**event, "id": "event2"}], "ws")["failures"][0]["kind"] == "duplicate"
    assert reconcile(calls, [], "ws")["failures"][0]["kind"] == "missing"
    bad = {**event, "agent_identity_id": None, "workspace_id": "other", "hook_session_id": "wrong", "decision": "blocked"}
    assert {f["kind"] for f in reconcile(calls, [bad], "ws")["failures"]} == {"identity", "workspace", "session", "decision"}
    ledger.db.close()
    with sqlite3.connect(tmp_path / "ledger.sqlite") as reopened:
        assert reopened.execute("SELECT outcome FROM calls WHERE id=?", (call_id,)).fetchone() == ("pending",)


@pytest.mark.parametrize("fault,agent_count", [(None, 2), ("identity", 2), (None, 100), ("missing", 2), ("rpc", 2)])
def test_actual_http_runner_and_artifacts(tmp_path, monkeypatch, fault, agent_count):
    if importlib.util.find_spec("locust") is None:
        pytest.skip("Install harness requirements to run the HTTP integration tests")
    config = configuration(monkeypatch)
    events = []
    config.update(duration_seconds=4, spawn_rate=10, rps=25, max_requests=40,
                  drain_seconds=5, reconnect_every=4, abort_p95_ms=5000)
    if agent_count > 2:
        config["agents"] = [{"id": str(uuid4()), "token_env": f"CANARY_FIXTURE_{i}"} for i in range(agent_count)]
        for agent in config["agents"]:
            monkeypatch.setenv(agent["token_env"], "cond_agt_" + agent["id"])
        config.update(duration_seconds=12, spawn_rate=100, rps=100, max_requests=800, concurrency=20, reconnect_every=0)
    config["scenarios"].append({"name": "block", "tool_name": "mcp_canary_block", "tool_input": {}, "decision": "blocked"})

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, status, body=None):
            raw = json.dumps(body).encode() if body is not None else b""
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Mcp-Session-Id", "test-session")
            self.end_headers()
            self.wfile.write(raw)

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            method, params = body["method"], body["params"]
            if method == "notifications/initialized":
                return self.reply(204)
            if method == "initialize":
                result = {"protocolVersion": "2024-11-05"}
            elif method == "tools/list":
                result = {"tools": [{"name": "guard_check"}]}
            elif params["name"] == "guard_status":
                result = {"content": [{"type": "text", "text": "[ws:00000000] " + json.dumps({"workspace_id": config["workspace_id"]})}]}
            else:
                args = params["arguments"]
                if fault == "rpc":
                    return self.reply(200, {"jsonrpc": "2.0", "id": body["id"], "error": {"code": -32603}})
                blocked = args["tool_name"] == "mcp_canary_block"
                agent = self.headers["Authorization"].removeprefix("Bearer cond_agt_")
                events.append({"id": str(uuid4()), "workspace_id": config["workspace_id"],
                               "agent_identity_id": None if fault == "identity" else agent,
                               "hook_session_id": self.headers["X-Session-Id"], "source": "mcp",
                               "decision": "blocked" if blocked else "allowed", "tool_call": args["tool_name"],
                               "input_summary": json.dumps(args["tool_input"])})
                if fault == "missing":
                    events.pop()
                result = {"content": [{"type": "text", "text": "[ws:00000000] " + ("BLOCKED policy" if blocked else "ok")}]}
            self.reply(200, {"jsonrpc": "2.0", "id": body["id"], "result": result})

        def do_GET(self):
            query = parse_qs(urlsplit(self.path).query)
            offset, limit = int(query.get("offset", [0])[0]), int(query.get("limit", [200])[0])
            self.reply(200, events[offset:offset + limit])

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    config["base_url"] = f"http://127.0.0.1:{server.server_port}"
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config))
    output = tmp_path / "result"
    try:
        result = subprocess.run([sys.executable, str(HERE / "run.py"), "--config", str(path), "--output", str(output)],
                                capture_output=True, text=True, timeout=25)
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
    assert result.returncode == int(fault is not None), result.stderr + result.stdout
    report = json.loads((output / "report.json").read_text())
    assert report["ready_agents"] == agent_count
    assert report["scenario_coverage_complete"]
    assert report["requests"] <= config["max_requests"]
    assert report["status"] == ("FAIL" if fault else "PASS")
    if fault == "identity":
        assert {f["kind"] for f in report["reconciliation"]["failures"]} == {"identity"}
    if fault == "missing":
        assert {f["kind"] for f in report["reconciliation"]["failures"]} == {"missing"}
    if fault == "rpc":
        assert report["errors"] > 0
        assert report["abort_reason"] == "error_rate"
    for artifact in output.iterdir():
        for agent in config["agents"]:
            assert os.environ[agent["token_env"]].encode() not in artifact.read_bytes()
