#!/usr/bin/env python3
"""Run a bounded, single-generator Locust canary. No production defaults."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import time
import uuid

from core import Ledger, percentile, reconcile, rpc_result, validate, verdict, write_report


def fetch_events(client, config, since, deadline):
    """Read after load stops; bounded scans, dedup by immutable event ID.

    Offset pagination is the current API contract. A changing dataset cannot
    prove completeness: the caller requires two identical settled scans.
    """
    rows = {}
    for page in range(500):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ValueError("observer_deadline_inconclusive")
        response = client.get(config["base_url"] + "/guard/events", params={
            "since": since, "ai_tool": "mcp_canary", "limit": 200, "offset": page * 200,
        }, timeout=min(config["timeout_seconds"], remaining), allow_redirects=False)
        if response.status_code != 200:
            raise ValueError("observer_http_error")
        batch = response.json()
        if not isinstance(batch, list):
            raise ValueError("observer_invalid_response")
        for row in batch:
            if not isinstance(row, dict) or not row.get("id"):
                raise ValueError("observer_invalid_row")
            rows[row["id"]] = row
        if len(batch) < 200:
            return list(rows.values())
        time.sleep(.1)  # Keep observer traffic out of the measured load budget.
    raise ValueError("observer_page_cap_inconclusive")


def run(config, output):
    # Locust uses gevent. Patch before importing its HTTP stack.
    from gevent import monkey
    monkey.patch_all()
    import gevent
    from gevent.lock import BoundedSemaphore, Semaphore
    import requests
    from locust import HttpUser, task
    from locust.env import Environment
    from locust.exception import StopUser

    output.mkdir(parents=True, exist_ok=False)
    os.chmod(output, 0o700)
    ledger = Ledger(output / "ledger.sqlite")
    started = time.monotonic()
    since = datetime.now(timezone.utc).isoformat()
    run_id = uuid.uuid4().hex
    report = {
        "run_id": run_id, "since": since, "status": "FAIL", "scope": "MCP guard_check decision recording",
        "target": config["base_url"], "endpoint": config["endpoint"], "workspace_id": config["workspace_id"],
        "configured_agents": len(config["agents"]), "limits": {k: v for k, v in config.items() if isinstance(v, (int, float))},
        "limitations": ["Not upstream MCP tool execution", "Not a database-outage or disconnect fault test",
                        "Single load-generator process; closed-loop capped arrivals", "REST visibility, not SSE/UI delivery latency"],
    }
    (output / "run.json").write_text(json.dumps(report, indent=2) + "\n")
    request_count = 0
    failures = 0
    latencies = []
    abort_reason = None
    next_slot = started
    deadline = started + config["duration_seconds"]
    tokens = iter(config["agents"])
    rate_lock = Semaphore()
    slots = BoundedSemaphore(config["concurrency"])
    ready = set()
    setup_failed = set()
    monitor_lag = []

    def reserve():
        nonlocal request_count, next_slot
        with rate_lock:
            if abort_reason or request_count >= config["max_requests"] or time.monotonic() >= deadline:
                raise StopUser()
            gevent.sleep(max(0, next_slot - time.monotonic()))
            if abort_reason or time.monotonic() >= deadline:
                raise StopUser()
            next_slot = time.monotonic() + 1 / config["rps"]
            request_count += 1

    class CanaryUser(HttpUser):
        host = config["base_url"]

        def rpc(self, method, params, *, scenario=None, notification=False):
            nonlocal failures, abort_reason
            call_id = uuid.uuid4().hex
            request_id = None if notification else call_id
            payload = {"jsonrpc": "2.0", "method": method, "params": params}
            if not notification:
                payload["id"] = request_id
            if scenario:
                payload["params"] = {"name": "guard_check", "arguments": {
                    "tool_name": scenario["tool_name"],
                    "tool_input": {"canary_call": call_id, **scenario["tool_input"]},
                }}
            with slots:
                reserve()
                start = time.monotonic()
                if scenario:
                    ledger.begin(call_id, self.agent["id"], self.session, scenario, time.time())
                outcome = "interrupted"
                try:
                    with gevent.Timeout(config["timeout_seconds"], TimeoutError("request_deadline")), self.client.post(config["endpoint"], json=payload, timeout=config["timeout_seconds"],
                                          allow_redirects=False, catch_response=True, name=method) as response:
                        if response.status_code == 0:
                            raise ValueError("connection_failure")
                        try:
                            data = None if notification else response.json()
                            result = rpc_result(response.status_code, data, request_id)
                            if scenario and verdict(result) != scenario["decision"]:
                                raise ValueError("verdict_mismatch")
                        except (ValueError, TypeError, KeyError, AttributeError):
                            response.failure("MCP contract failure")
                            raise ValueError("mcp_contract_failure") from None
                        session_header = response.headers.get("Mcp-Session-Id")
                        if session_header:
                            self.client.headers["Mcp-Session-Id"] = session_header
                        outcome = "ok"
                        return result
                except Exception:
                    # Do not persist raw exceptions: SDKs may embed response bodies or credentials.
                    outcome = "request_failed"
                    failures += 1
                    return None
                finally:
                    elapsed = (time.monotonic() - start) * 1000
                    latencies.append(elapsed)
                    if scenario:
                        ledger.finish(call_id, elapsed, outcome)
                    if len(latencies) >= 20:
                        if failures / len(latencies) > config["abort_error_rate"]:
                            abort_reason = "error_rate"
                        elif percentile(latencies[-100:], .95) > config["abort_p95_ms"]:
                            abort_reason = "latency"

        def connect(self):
            self.session = str(uuid.uuid4())
            self.client.headers.pop("Mcp-Session-Id", None)
            self.client.headers["X-Session-Id"] = self.session
            result = self.rpc("initialize", {"protocolVersion": "2024-11-05", "capabilities": {},
                                             "clientInfo": {"name": "mcp-canary", "version": "1"}})
            if not result or not result.get("protocolVersion"):
                return False
            self.client.headers["MCP-Protocol-Version"] = result["protocolVersion"]
            if self.rpc("notifications/initialized", {}, notification=True) is None:
                return False
            listing = self.rpc("tools/list", {})
            if not listing or "guard_check" not in {t.get("name") for t in listing.get("tools", [])}:
                return False
            status = self.rpc("tools/call", {"name": "guard_status", "arguments": {}})
            try:
                text = status["content"][0]["text"]
                text = re.sub(r"^\[ws:[^\]]+\]\s*", "", text)
                return json.loads(text)["workspace_id"] == config["workspace_id"]
            except (TypeError, KeyError, ValueError, IndexError):
                return False

        def on_start(self):
            nonlocal abort_reason
            self.agent = next(tokens)
            self.iteration = 0
            self.client.trust_env = False
            self.client.headers.update({"Authorization": "Bearer " + os.environ[self.agent["token_env"]],
                                        "Accept": "application/json, text/event-stream", "X-Claude-Surface": "mcp_canary"})
            if not self.connect():
                setup_failed.add(self.agent["id"])
                abort_reason = "agent_preflight_failed"
                raise StopUser()
            ready.add(self.agent["id"])

        @task
        def check(self):
            if config["reconnect_every"] and self.iteration and self.iteration % config["reconnect_every"] == 0:
                self.client.close()
                if not self.connect():
                    raise StopUser()
            scenario = config["scenarios"][self.iteration % len(config["scenarios"])]
            self.rpc("tools/call", {}, scenario=scenario)
            self.iteration += 1

    observer = requests.Session()
    observer.trust_env = False
    observer.headers.update({"Authorization": "Bearer " + os.environ[config["observer_token_env"]],
                             "X-Workspace-Id": config["workspace_id"]})
    try:
        with gevent.Timeout(config["timeout_seconds"], TimeoutError("observer_deadline")):
            response = observer.get(config["base_url"] + "/guard/events", params={"limit": 1, "ai_tool": "mcp_canary"},
                                    timeout=config["timeout_seconds"], allow_redirects=False)
        if response.status_code != 200 or not isinstance(response.json(), list):
            raise ValueError("observer_preflight_failed")
    except Exception:
        report["observer_error"] = "observer_preflight_failed"
        write_report(output, report, [])
        observer.close()
        ledger.db.close()
        print("FAIL: observer preflight; no agent load started")
        return 1
    started = time.monotonic()
    next_slot = started
    deadline = started + config["duration_seconds"]
    environment = Environment(user_classes=[CanaryUser], stop_timeout=config["timeout_seconds"] + 2)
    runner = environment.create_local_runner()
    try:
        runner.start(len(config["agents"]), spawn_rate=config["spawn_rate"])
        while time.monotonic() < deadline and not abort_reason and request_count < config["max_requests"]:
            tick = time.monotonic()
            gevent.sleep(.25)
            monitor_lag.append(max(0, (time.monotonic() - tick - .25) * 1000))
    except KeyboardInterrupt:
        abort_reason = "operator_interrupt"
    finally:
        runner.quit()
    load_elapsed = time.monotonic() - started
    calls = ledger.calls()
    report.update({"requests": request_count, "completed_requests": len(latencies), "errors": failures,
                   "ready_agents": len(ready), "setup_failed_agents": sorted(setup_failed),
                   "load_seconds": round(load_elapsed, 2), "achieved_rps": round(len(latencies) / load_elapsed, 2),
                   "p50_ms": percentile(latencies, .5), "p95_ms": percentile(latencies, .95),
                   "p99_ms": percentile(latencies, .99), "generator_lag_p99_ms": percentile(monitor_lag, .99),
                   "abort_reason": abort_reason})
    previous = None
    settled = False
    audit = {"expected": len(calls), "matched": 0, "failures": []}
    drain_start = time.monotonic()
    try:
        while time.monotonic() - drain_start < config["drain_seconds"]:
            with gevent.Timeout(max(.01, drain_start + config["drain_seconds"] - time.monotonic()), TimeoutError("drain_deadline")):
                rows = fetch_events(observer, config, since, drain_start + config["drain_seconds"])
            audit = reconcile(calls, rows, config["workspace_id"])
            fingerprint = json.dumps(sorted(rows, key=lambda r: r["id"]), sort_keys=True)
            settled = fingerprint == previous
            previous = fingerprint
            if settled and audit["matched"] == len(calls):
                break
            gevent.sleep(2)
    except Exception:
        report["observer_error"] = "reconciliation_inconclusive"
    finally:
        observer.close()
    report["reconciliation"] = audit
    report["observer_settled"] = settled
    report["drain_elapsed_seconds"] = round(time.monotonic() - drain_start, 2)
    exercised = {(c["agent"], c["scenario"]) for c in calls}
    coverage = all((a["id"], s["name"]) in exercised for a in config["agents"] for s in config["scenarios"])
    report["scenario_coverage_complete"] = coverage
    passed = (bool(calls) and coverage and len(ready) == len(config["agents"]) and not abort_reason
              and not failures and all(c["outcome"] == "ok" for c in calls) and settled
              and not audit["failures"] and "observer_error" not in report
              and report["achieved_rps"] >= config["rps"] * config["min_achieved_rps_ratio"]
              and (report["generator_lag_p99_ms"] or 0) < 250)
    report["status"] = "PASS" if passed else "FAIL"
    write_report(output, report, calls)
    ledger.db.close()
    print(f'{report["status"]}: {len(calls)} checks; report: {output / "report.html"}')
    return 0 if passed else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="New artifact directory; never reused")
    parser.add_argument("--approve-target", help="Explicit remote approval: ORIGIN|WORKSPACE_ID")
    args = parser.parse_args()
    config = validate(json.loads(args.config.read_text()), args.approve_target)
    return run(config, args.output)


if __name__ == "__main__":
    raise SystemExit(main())
