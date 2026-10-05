"""Run native MCP clients and publish only evidence-backed acceptance results."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from urllib.parse import urlencode, urlsplit
import urllib.error
import urllib.request
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from conduct_smoke_test import Client, CheckFailed, endpoint  # noqa: E402

CLIENTS = {
    "claude-ai": "Claude.ai", "chatgpt": "ChatGPT", "copilot-vscode": "Copilot VS Code",
    "copilot-cli": "Copilot CLI", "github-agent": "GitHub coding agent",
}
SCENARIOS = ("connect", "refresh", "reconnect", "workspace-switch", "revocation", "mutation", "approval")
BROWSER_CLIENTS = {"claude-ai", "chatgpt", "copilot-vscode"}
MUTATING = set(SCENARIOS) - {"connect", "reconnect"}
CHILD_ENV = {"PATH", "HOME", "TMPDIR", "SSL_CERT_FILE", "NODE_EXTRA_CA_CERTS",
             "COPILOT_HOME", "COPILOT_GITHUB_TOKEN", "GH_TOKEN", "GITHUB_TOKEN", "GH_HOST"}


def now():
    return datetime.now(timezone.utc).isoformat()


def require(condition, message):
    if not condition:
        raise CheckFailed(message)


def environment(name):
    require(isinstance(name, str) and re.fullmatch(r"[A-Z][A-Z0-9_]*", name), "Invalid environment reference")
    value = os.environ.get(name)
    require(bool(value), "Required acceptance credential is not set")
    return value


def validate(plan):
    require(plan.get("version") == 1, "Acceptance plan version must be 1")
    endpoint(plan["api"])
    require(plan.get("deployment") in {"saas", "onprem"}, "Select saas or onprem")
    require(isinstance(plan.get("clients"), dict), "Client configurations required")
    require(set(plan["clients"]) <= CLIENTS.keys(), "Unknown client")
    for name, config in plan["clients"].items():
        require(config.get("authentication", "OAuth + PKCE") in {"OAuth + PKCE", "Bearer token", "Scoped Agents secret"}, "Unknown authentication mode")
        require(all(isinstance(key, str) and key.startswith("MCP_NATIVE_") for key in config.get("native_env", [])), "Native credential references must use MCP_NATIVE_ names")
        require(isinstance(config.get("version"), str) and re.fullmatch(r"[0-9][A-Za-z0-9 ._+-]{0,79}", config["version"]),
                "Record the real numeric native client version/build")
        require(isinstance(config.get("phases", {}), dict), "Phases must be objects")
        require(set(config.get("phases", {})) <= set(SCENARIOS), "Unknown scenario")
        for scenario, phase in config.get("phases", {}).items():
            require(isinstance(phase, dict), "Phase must be an object")
            require(phase.get("checks"), "Each native phase needs independent server checks")
            if scenario in MUTATING:
                require(phase.get("verify"), "Lifecycle and mutation phases require a fixture verifier")
                require(phase.get("after"), "Lifecycle and mutation phases require fixture cleanup")
            if name in BROWSER_CLIENTS:
                require(phase.get("steps") and phase.get("output_selector"), "Browser phase needs native UI steps and an output assertion")
            if scenario == "workspace-switch":
                require(phase.get("workspace_id") != config.get("workspace_id"), "Workspace switch must select a different workspace")
            for check in phase["checks"]:
                require(check.get("kind") in {"audit", "json", "denied"}, "Unknown server check")
                if check["kind"] == "audit":
                    require(check.get("tool") and check.get("decision"), "Audit check needs tool and decision")
                elif check["kind"] == "json":
                    require(str(check.get("path", "")).startswith("/") and not str(check["path"]).startswith("//"), "JSON check needs an API-relative path")
                    require("equals" in check and isinstance(check.get("pointer"), list), "JSON check needs pointer and expected value")
                else:
                    require(check.get("token_env") and check.get("status") in {401, 403}, "Denial check needs a fixture credential and HTTP status")
            if scenario in {"connect", "refresh", "reconnect", "workspace-switch", "mutation"}:
                require(any(check["kind"] == "audit" for check in phase["checks"]), "Successful native phases require attributed MCP audit evidence")
            if scenario == "mutation":
                require(any(check["kind"] == "json" for check in phase["checks"]), "Mutation needs an independent state assertion")
            if scenario == "revocation":
                require(any(check["kind"] == "denied" for check in phase["checks"]), "Revocation needs a real credential denial")
            if scenario == "approval":
                rounds = phase.get("rounds", [])
                require(len(rounds) >= 2 and rounds[0].get("control_after"), "Approval needs pending and resumed native rounds with an approver action between")
                require(any(check["kind"] == "json" for check in rounds[0].get("checks", [])), "Pending approval must assert no mutation")
                require(any(check["kind"] == "json" for check in phase["checks"]), "Approved mutation needs independent state evidence")
                require(any(check["kind"] == "audit" for check in rounds[-1].get("checks", [])), "Resumed approval needs attributed MCP audit evidence")
    return plan


def substitute(value, marker):
    if isinstance(value, str):
        return value.replace("{marker}", marker)
    if isinstance(value, list):
        return [substitute(item, marker) for item in value]
    if isinstance(value, dict):
        return {key: substitute(item, marker) for key, item in value.items()}
    return value


def command(argv, *, marker, timeout=120, input_data=None, allowed_env=()):
    require(isinstance(argv, list) and argv and all(isinstance(x, str) for x in argv), "Commands must be argument arrays")
    env = {k: v for k, v in os.environ.items() if k in CHILD_ENV or k in allowed_env}
    env["MCP_ACCEPTANCE_MARKER"] = marker
    try:
        result = subprocess.run(["rtk", "proxy", *substitute(argv, marker)], input=input_data,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                timeout=timeout, env=env, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise CheckFailed("Native client or fixture command unavailable/timed out") from None
    # Never print or persist subprocess output: clients and fixture tools can log credentials.
    require(result.returncode == 0, "Native client or fixture command failed")
    return result.stdout


class Observer:
    def __init__(self, plan, ca):
        self.api = endpoint(plan["api"])
        self.token = environment(plan["observer_token_env"])
        self.http = Client(ca)

    def get(self, path, workspace):
        require(path.startswith("/") and not path.startswith("//"), "API-relative path required")
        request = urllib.request.Request(self.api + path, headers={
            "Authorization": "Bearer " + self.token, "X-Workspace-Id": workspace})
        try:
            with self.http.opener.open(request, timeout=20) as response:
                body = response.read(2_000_001)
                require(len(body) <= 2_000_000, "Observer response too large")
                return json.loads(body)
        except (OSError, ValueError, urllib.error.URLError):
            raise CheckFailed("Observer API unavailable or unauthorized") from None

    def check(self, check, config, marker, since):
        workspace = config["workspace_id"]
        if check["kind"] == "denied":
            status, _, _ = self.http.post(self.api + "/mcp", environment(check["token_env"]), {
                "jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
            require(status == check["status"], "Revoked fixture credential was not denied")
            return {"kind": "denied", "status": status}
        if check["kind"] == "json":
            value = self.get(substitute(check["path"], marker), workspace)
            for part in check["pointer"]:
                value = value[part]
            require(value == substitute(check["equals"], marker), "Independent fixture state did not match")
            return {"kind": "json", "matched": True}
        query = urlencode({"since": since, "limit": 200})
        rows = self.get("/guard/events?" + query, workspace)
        require(isinstance(rows, list), "Audit observer returned an invalid result")
        matches = [row for row in rows if marker in str(row.get("input_summary", ""))
                   and row.get("tool_call") == check["tool"] and row.get("decision") == check["decision"]
                   and datetime.fromisoformat(row["ts"].replace("Z", "+00:00")) >= datetime.fromisoformat(since)]
        require(bool(matches), "Expected native MCP audit event not observed")
        for row in matches:
            require(row.get("workspace_id") == workspace, "Native MCP workspace attribution mismatch")
            require(row.get("clerk_user_id") == config["actor_id"], "Native MCP actor attribution mismatch")
            require(row.get("agent_identity_id") == config["agent_identity_id"], "Native MCP agent attribution mismatch")
            require(row.get("source") == "mcp", "Expected an MCP event, not a hook/proxy event")
        return {"kind": "audit", "event_ids": [str(uuid.UUID(row["id"])) for row in matches]}

    def wait(self, checks, config, marker, since, timeout):
        deadline = time.monotonic() + timeout
        while True:
            try:
                return [self.check(check, config, marker, since) for check in checks]
            except CheckFailed:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(1)


class BrowserClient:
    def __init__(self, name, config):
        self.name, self.config = name, config
        parsed = urlsplit(config["cdp"])
        require(parsed.hostname in {"localhost", "127.0.0.1", "::1"} and parsed.scheme in {"http", "ws"},
                "Browser CDP must be loopback-only")
        prefix = urlsplit(config["page_prefix"])
        if name in {"claude-ai", "chatgpt"}:
            expected = "claude.ai" if name == "claude-ai" else "chatgpt.com"
            require(prefix.scheme == "https" and prefix.hostname == expected and prefix.path.startswith("/"), "Select the real native client origin")
        else:
            require(prefix.scheme == "vscode-file", "Select the native VS Code workbench page")

    def run(self, phase, marker, timeout):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise CheckFailed("Install Playwright in the acceptance environment") from None
        with sync_playwright() as playwright:
            browser = playwright.chromium.connect_over_cdp(self.config["cdp"], timeout=timeout * 1000)
            # Attach to the signed-in native client, not a reconstructed chat UI.
            pages = [page for context in browser.contexts for page in context.pages
                     if page.url.startswith(self.config["page_prefix"])]
            require(len(pages) == 1, "Open exactly one matching native client page")
            page = pages[0]
            from playwright.sync_api import expect
            for step in phase["steps"]:
                target = page
                if step.get("page_prefix"):
                    selected = [p for context in browser.contexts for p in context.pages
                                if p.url.startswith(step["page_prefix"])]
                    require(len(selected) == 1, "Native authorization page unavailable")
                    target = selected[0]
                locator = target.locator(step["selector"])
                action = step["action"]
                if action == "click":
                    locator.click(timeout=timeout * 1000)
                elif action == "fill":
                    locator.fill(substitute(step["value"], marker), timeout=timeout * 1000)
                elif action == "fill_env":
                    parsed = urlsplit(target.url)
                    origin = parsed.scheme + "://" + parsed.netloc
                    require(origin in self.config.get("auth_origins", []), "Credentials may only be entered on an explicit test IdP origin")
                    require(step["value"].startswith("MCP_NATIVE_"), "Use a dedicated native test credential reference")
                    locator.fill(environment(step["value"]), timeout=timeout * 1000)
                elif action == "press":
                    locator.press(step["value"], timeout=timeout * 1000)
                elif action == "visible":
                    expect(locator).to_be_visible(timeout=timeout * 1000)
                else:
                    raise CheckFailed("Unsupported native browser action")
            expect(page.locator(phase["output_selector"])).to_contain_text(
                substitute(phase.get("output_text", "{marker}"), marker), timeout=timeout * 1000)
        return {"adapter": "native-browser", "version": self.config["version"]}


class CopilotClient:
    def __init__(self, config):
        self.config = config

    def run(self, phase, marker, timeout):
        server = self.config.get("server_name", "conduct")
        require(re.fullmatch(r"[a-zA-Z0-9_-]+", server), "Invalid MCP server name")
        installed = command(["copilot", "--no-auto-update", "--version"], marker=marker, timeout=30)
        require(self.config["version"] in installed, "Installed Copilot version does not match the plan")
        prompt = phase.get("prompt", 'Use the Conduct MCP tools: call guard_activity with summary "{marker}", '
                           'then call conduct_current_workspace. Do not use shell, files, HTTP, or another MCP server.')
        tools = phase.get("allowed_tools", ["guard_activity", "conduct_current_workspace"])
        require(tools and all(re.fullmatch(r"[a-zA-Z0-9_]+", tool) for tool in tools), "Explicit MCP tool allowlist required")
        argv = ["copilot", "--no-auto-update", "--no-custom-instructions", "--log-level", "none",
                "--disable-builtin-mcps", "-p", substitute(prompt, marker)]
        if self.config.get("additional_mcp_config"):
            argv += ["--additional-mcp-config", "@" + self.config["additional_mcp_config"]]
        for disabled in self.config.get("disabled_servers", []):
            require(re.fullmatch(r"[a-zA-Z0-9_-]+", disabled), "Invalid disabled MCP server name")
            argv += ["--disable-mcp-server", disabled]
        for tool in tools:
            argv += ["--allow-tool", f"{server}({tool})"]
        output = command([*argv,
                 "--deny-tool", "shell", "--deny-tool", "write", "--deny-tool", "read", "--deny-tool", "url"],
                marker=marker, timeout=timeout, allowed_env=self.config.get("native_env", []))
        if phase.get("output_text"):
            require(substitute(phase["output_text"], marker) in output, "Native CLI output assertion failed")
        return {"adapter": "native-copilot-cli", "version": self.config["version"]}


def github_api(path, *, marker, body=None):
    argv = ["gh", "api", path, "-H", "Accept: application/vnd.github+json"]
    if body is not None:
        argv += ["--method", "POST", "--input", "-"]
    raw = command(argv, marker=marker, timeout=60, input_data=json.dumps(body) if body is not None else None)
    try:
        return json.loads(raw)
    except ValueError:
        raise CheckFailed("GitHub returned an invalid response") from None


class GithubAgent:
    def __init__(self, config):
        self.config = config
        require(re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", config["repo"]), "Invalid disposable repository")

    def run(self, phase, marker, timeout):
        repo = self.config["repo"]
        body = phase.get("prompt", 'Use conduct/guard_activity with summary "{marker}", then '
                         'conduct/conduct_current_workspace. Do not use HTTP or shell to call MCP. '
                         'Write the nonsecret marker and workspace UUID to acceptance-result.txt. '
                         'Include the marker in the pull request description. Never print credentials.')
        issue = github_api(f"repos/{repo}/issues", marker=marker, body={
            "title": "MCP acceptance " + marker, "body": substitute(body, marker),
            "assignees": ["copilot-swe-agent[bot]"], "agent_assignment": {
                "target_repo": repo, "base_branch": self.config.get("base_branch", "main"),
                "custom_agent": self.config.get("custom_agent", "conduct-acceptance")}})
        require(any(a.get("login") == "copilot-swe-agent[bot]" for a in issue.get("assignees", [])),
                "GitHub did not assign a real coding agent")
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            prs = github_api(f"repos/{repo}/pulls?state=all&per_page=100", marker=marker)
            for pr in prs:
                if pr.get("user", {}).get("login") != "copilot-swe-agent[bot]":
                    continue
                if marker not in (pr.get("body") or ""):
                    continue
                require(pr.get("head", {}).get("repo", {}).get("full_name") == repo, "Coding-agent PR repository mismatch")
                return {"adapter": "github-coding-agent", "issue": issue["number"], "pull_request": pr["number"],
                        "head_sha": pr["head"]["sha"], "version": self.config["version"]}
            time.sleep(10)
        raise CheckFailed("No actual coding-agent pull request evidence before timeout")


def run_phase(name, scenario, config, observer, *, allow_mutation, allow_cloud, timeout):
    phase = config["phases"][scenario]
    marker = "mcp-acceptance-" + uuid.uuid4().hex
    has_fixture_commands = any(phase.get(key) for key in ("before", "verify", "after"))
    require(allow_mutation or (scenario not in MUTATING and not has_fixture_commands), "Fixture mutation opt-in required")
    require(name != "github-agent" or allow_cloud, "Real GitHub agent opt-in required")
    target = {**config, **{k: phase[k] for k in ("workspace_id", "actor_id", "agent_identity_id") if k in phase}}
    since = now()
    evidence = None
    try:
        for argv in phase.get("before", []):
            command(argv, marker=marker, allowed_env=config.get("fixture_env", []))
        adapter = BrowserClient(name, config) if name in BROWSER_CLIENTS else (
            CopilotClient(config) if name == "copilot-cli" else GithubAgent(config))
        rounds_evidence = []
        for round_config in phase.get("rounds", []):
            require(allow_mutation, "Approval actions require mutation opt-in")
            round_since = now()
            native_round = adapter.run({**phase, **round_config}, marker, timeout)
            round_checks = observer.wait(round_config["checks"], target, marker, round_since, min(timeout, 60))
            rounds_evidence.append({"native": native_round, "checks": round_checks})
            for argv in round_config.get("control_after", []):
                command(argv, marker=marker, allowed_env=config.get("fixture_env", []))
        native = adapter.run(phase, marker, timeout) if not rounds_evidence else rounds_evidence[-1]["native"]
        checks = observer.wait(phase["checks"], target, marker, since, min(timeout, 60))
        for argv in phase.get("verify", []):
            command(argv, marker=marker, allowed_env=config.get("fixture_env", []))
        evidence = {"marker": marker, "native": native, "checks": checks, "rounds": rounds_evidence}
    finally:
        # Restoration failure is a test failure, even if the canary succeeded.
        for argv in phase.get("after", []):
            command(argv, marker=marker, allowed_env=config.get("fixture_env", []))
    return evidence


def matrix(report):
    rows = ["# MCP Client Support", "", "Deployment: " + report["deployment"], "",
            "| Client | Auth | " + " | ".join(SCENARIOS) + " |",
            "|---|---|" + "---|" * len(SCENARIOS)]
    for name, label in CLIENTS.items():
        cells = report["clients"][name]
        auth = report.get("authentication", {}).get(name, "Scoped Agents secret" if name == "github-agent" else "OAuth + PKCE")
        rows.append("| " + label + " | " + auth + " | " + " | ".join(cells[s]["status"] for s in SCENARIOS) + " |")
    rows += ["", "Connect includes discovery, invocation and actor/workspace attribution.",
             "Pending means no completed native run. Server integration tests do not mark native cells passed.",
             "GitHub does not support remote MCP OAuth; secret rotation replaces OAuth refresh.", ""]
    return "\n".join(rows)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--matrix", type=Path, required=True)
    parser.add_argument("--ca")
    parser.add_argument("--client", choices=CLIENTS, action="append")
    parser.add_argument("--allow-fixture-mutations", action="store_true")
    parser.add_argument("--allow-github-agent", action="store_true")
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--require-all", action="store_true")
    args = parser.parse_args(argv)
    require(1 <= args.timeout <= 3600, "Timeout must be 1..3600 seconds")
    plan = validate(json.loads(args.plan.read_text()))
    require(not args.allow_fixture_mutations or plan.get("disposable") is True, "Mutations require a disposable test plan")
    require(not args.allow_github_agent or plan.get("disposable") is True, "Cloud runs require a disposable test repository/plan")
    require(not args.report.exists() and not args.matrix.exists(), "Choose new report/matrix paths")
    report = {"version": 1, "deployment": plan["deployment"], "started_at": now(),
              "authentication": {name: config.get("authentication", "Scoped Agents secret" if name == "github-agent" else "OAuth + PKCE")
                                 for name, config in plan["clients"].items()}, "clients": {
        name: {scenario: {"status": "Pending"} for scenario in SCENARIOS} for name in CLIENTS}}
    observer = None
    for name in args.client or CLIENTS:
        config = plan["clients"].get(name)
        if not config:
            continue
        for scenario in SCENARIOS:
            if scenario not in config.get("phases", {}):
                continue
            cell = report["clients"][name][scenario]
            try:
                observer = observer or Observer(plan, args.ca)
                evidence = run_phase(name, scenario, config, observer, allow_mutation=args.allow_fixture_mutations,
                                     allow_cloud=args.allow_github_agent, timeout=args.timeout)
                cell.update(status="Passed", evidence=evidence)
            except Exception:
                # External/UI exceptions often embed page URLs, OAuth codes or token values.
                cell.update(status="Failed", reason="Native run, independent evidence, or restoration failed")
                print(f"{name} {scenario}: Failed", flush=True)
                # Later phases may depend on earlier state. Do not continue with a broken fixture.
                break
            print(f"{name} {scenario}: {cell['status']}", flush=True)
    report["finished_at"] = now()
    with args.report.open("x") as output:
        json.dump(report, output, indent=2)
        output.write("\n")
    with args.matrix.open("x") as output:
        output.write(matrix(report))
    statuses = [cell["status"] for client in report["clients"].values() for cell in client.values()]
    return 1 if "Passed" not in statuses or "Failed" in statuses or (args.require_all and "Pending" in statuses) else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        raise SystemExit("Acceptance setup failed; credentials and client output omitted") from None
