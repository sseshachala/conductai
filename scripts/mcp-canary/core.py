"""Dependency-free validation, durable client ledger, and recorder reconciliation."""
from __future__ import annotations

import html
import json
import math
import os
from pathlib import Path
import re
import sqlite3
from urllib.parse import urlsplit
from uuid import UUID


def validate(config: dict, approved_target: str | None = None) -> dict:
    c = dict(config)
    url = urlsplit(c["base_url"])
    if url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password:
        raise ValueError("base_url must be an HTTP(S) origin without credentials")
    if url.path not in {"", "/"} or url.query or url.fragment:
        raise ValueError("base_url must contain only the origin")
    c["base_url"] = c["base_url"].rstrip("/")
    UUID(c["workspace_id"])
    if url.hostname not in {"localhost", "127.0.0.1", "::1"}:
        if url.scheme != "https" or approved_target != f'{c["base_url"]}|{c["workspace_id"]}':
            raise ValueError("Remote load requires HTTPS and --approve-target 'ORIGIN|WORKSPACE_ID'")
    if c["endpoint"] not in {"/guard/mcp", "/mcp"}:
        raise ValueError("endpoint must be /guard/mcp or /mcp")
    bounds = {
        "duration_seconds": (1, 3600), "spawn_rate": (0.1, 100),
        "rps": (0.1, 1000), "concurrency": (1, 2000),
        "max_requests": (1, 100000), "timeout_seconds": (1, 60),
        "drain_seconds": (1, 300), "reconnect_every": (0, 10000),
        "abort_error_rate": (0, 1), "abort_p95_ms": (1, 60000),
        "min_achieved_rps_ratio": (0.01, 1),
    }
    for key, (low, high) in bounds.items():
        value = c[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
            raise ValueError(f"Invalid {key}; expected {low}..{high}")
    for key in ("concurrency", "max_requests", "reconnect_every"):
        if not isinstance(c[key], int):
            raise ValueError(f"{key} must be an integer")
    agents = c["agents"]
    if not 1 <= len(agents) <= 2000:
        raise ValueError("Provide 1..2000 distinct agent identities")
    if c["duration_seconds"] < len(agents) / c["spawn_rate"]:
        raise ValueError("Duration is shorter than the agent ramp")
    if c["max_requests"] < len(agents) * 5:
        raise ValueError("Request budget cannot initialize and exercise every agent")
    ids, tokens = set(), set()
    for agent in agents:
        UUID(agent["id"])
        token = os.environ.get(agent["token_env"], "")
        if not token.startswith("cond_agt_") or agent["id"] in ids or token in tokens:
            raise ValueError("Agent IDs and nonempty credentials must be distinct")
        ids.add(agent["id"])
        tokens.add(token)
    if not os.environ.get(c["observer_token_env"]):
        raise ValueError("Observer credential environment variable is missing")
    if not c["scenarios"] or len({s["name"] for s in c["scenarios"]}) != len(c["scenarios"]):
        raise ValueError("Provide uniquely named scenarios")
    for scenario in c["scenarios"]:
        if scenario["decision"] not in {"allowed", "blocked"}:
            raise ValueError("Initial contract supports allowed/blocked only; warnings may deduplicate")
        audit_decision = scenario.get("audit_decision", scenario["decision"])
        supported = {"allowed", "audited"} if scenario["decision"] == "allowed" else {"blocked"}
        if audit_decision not in supported:
            raise ValueError("audit_decision must match the expected wire verdict")
        if not isinstance(scenario["tool_input"], dict) or "canary_call" in scenario["tool_input"]:
            raise ValueError("tool_input must be an object without reserved canary_call")
        if not re.fullmatch(r"[\w.-]{1,80}", scenario["tool_name"]):
            raise ValueError("Invalid intent tool name")
    return c


def rpc_result(status: int, data: object, request_id: str | None) -> dict:
    if request_id is None:
        if status not in {202, 204}:
            raise ValueError("notification_not_acknowledged")
        return {}
    if status != 200:
        raise ValueError(f"http_{status}")
    if not isinstance(data, dict) or data.get("jsonrpc") != "2.0" or data.get("id") != request_id:
        raise ValueError("invalid_rpc_envelope")
    if "error" in data:
        raise ValueError("rpc_error")
    result = data.get("result")
    if not isinstance(result, dict) or result.get("isError"):
        raise ValueError("tool_error")
    return result


def verdict(result: dict) -> str:
    content = result.get("content", [])
    text = "\n".join(x.get("text", "") for x in content if x.get("type") == "text").strip()
    text = re.sub(r"^\[ws:[^\]]+\]\s*", "", text)
    if text.startswith("BLOCKED"):
        return "blocked"
    if text == "ok" or text.startswith("ok ") or text.startswith("ok\n"):
        return "allowed"
    raise ValueError("unexpected_verdict")


class Ledger:
    def __init__(self, path: Path):
        self.db = sqlite3.connect(path)
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("""CREATE TABLE calls (
            id TEXT PRIMARY KEY, agent TEXT, session TEXT, scenario TEXT, tool TEXT,
            decision TEXT, started REAL, latency REAL, outcome TEXT)""")
        self.db.commit()

    def begin(self, call_id, agent, session, scenario, started):
        self.db.execute("INSERT INTO calls VALUES (?,?,?,?,?,?,?,NULL,'pending')", (
            call_id, agent, session, scenario["name"], scenario["tool_name"],
            scenario.get("audit_decision", scenario["decision"]), started))
        self.db.commit()

    def finish(self, call_id, latency, outcome):
        self.db.execute("UPDATE calls SET latency=?, outcome=? WHERE id=?", (latency, outcome, call_id))
        self.db.commit()

    def calls(self):
        self.db.row_factory = sqlite3.Row
        return [dict(row) for row in self.db.execute("SELECT * FROM calls ORDER BY started")]


MARKER = re.compile(r'"canary_call"\s*:\s*"([a-f0-9]{32})"')


def reconcile(calls: list[dict], events: list[dict], workspace_id: str) -> dict:
    expected = {c["id"]: c for c in calls}
    seen = {key: [] for key in expected}
    for event in {e["id"]: e for e in events}.values():
        match = MARKER.search(event.get("input_summary") or "")
        if match and match[1] in seen:
            seen[match[1]].append(event)
    failures = []
    for call_id, call in expected.items():
        rows = seen[call_id]
        if len(rows) != 1:
            failures.append({"call": call_id, "kind": "missing" if not rows else "duplicate", "count": len(rows)})
        for event in rows:
            checks = {
                "workspace": (event.get("workspace_id"), workspace_id),
                "identity": (event.get("agent_identity_id"), call["agent"]),
                "session": (event.get("hook_session_id"), call["session"]),
                "decision": (event.get("decision"), call["decision"]),
                "tool": (event.get("tool_call"), call["tool"]),
                "source": (event.get("source"), "mcp"),
            }
            for kind, (actual, wanted) in checks.items():
                if actual != wanted:
                    failures.append({"call": call_id, "event": event["id"], "kind": kind})
    return {"expected": len(calls), "matched": sum(bool(v) for v in seen.values()), "failures": failures}


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[max(0, math.ceil(len(ordered) * fraction) - 1)], 2)


def write_report(directory: Path, report: dict, calls: list[dict]):
    report["agents"] = {}
    for agent in sorted({c["agent"] for c in calls}):
        subset = [c for c in calls if c["agent"] == agent]
        times = [c["latency"] for c in subset if c["latency"] is not None]
        report["agents"][agent] = {"calls": len(subset), "errors": sum(c["outcome"] != "ok" for c in subset),
                                    "p50_ms": percentile(times, .5), "p95_ms": percentile(times, .95), "p99_ms": percentile(times, .99)}
    content = json.dumps(report, indent=2)
    (directory / "report.json").write_text(content + "\n")
    # No response bodies, supplied inputs, tokens, or emails enter the artifacts.
    (directory / "report.html").write_text(
        '<!doctype html><meta charset="utf-8"><title>MCP Canary</title>'
        '<h1>MCP Canary: ' + html.escape(report["status"]) + '</h1><pre>' + html.escape(content) + '</pre>')
