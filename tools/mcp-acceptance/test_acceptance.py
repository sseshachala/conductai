import copy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

spec = importlib.util.spec_from_file_location("mcp_native_acceptance", Path(__file__).with_name("acceptance.py"))
acceptance = importlib.util.module_from_spec(spec)
spec.loader.exec_module(acceptance)


def plan():
    return json.loads(Path(__file__).with_name("plan.example.json").read_text())


def report():
    return {"version": 1, "deployment": "onprem", "clients": {
        name: {scenario: {"status": "Pending"} for scenario in acceptance.SCENARIOS}
        for name in acceptance.CLIENTS}}


def test_example_is_valid_but_does_not_claim_completed_acceptance():
    acceptance.validate(plan())
    text = acceptance.matrix(report())
    assert "Passed" not in text
    assert all(name in text for name in acceptance.CLIENTS.values())
    assert "Scoped Agents secret" in text


@pytest.mark.parametrize("change", ["version", "client", "checks", "api", "mutation", "switch", "approval"])
def test_invalid_plans_fail_closed(change):
    p = plan()
    config = p["clients"]["copilot-cli"]
    if change == "version":
        p["version"] = 2
    elif change == "client":
        p["clients"]["inspector"] = p["clients"].pop("copilot-cli")
    elif change == "checks":
        config["phases"]["connect"]["checks"] = []
    elif change == "api":
        p["api"] = "https://user:secret@example.test/mcp"
    else:
        scenario = {"mutation": "mutation", "switch": "workspace-switch", "approval": "approval"}[change]
        config["phases"][scenario] = copy.deepcopy(config["phases"]["connect"])
    with pytest.raises(acceptance.CheckFailed):
        acceptance.validate(p)


def test_connect_cannot_pass_on_denial_only():
    p = plan()
    p["clients"]["copilot-cli"]["phases"]["connect"]["checks"] = [
        {"kind": "denied", "token_env": "FIXTURE_TOKEN", "status": 401}]
    with pytest.raises(acceptance.CheckFailed):
        acceptance.validate(p)


def test_approval_cannot_pass_on_state_checks_without_resumed_mcp_evidence():
    p = plan()
    check = {"kind": "json", "path": "/fixture", "pointer": [], "equals": True}
    p["clients"]["copilot-cli"]["phases"]["approval"] = {
        "checks": [check], "verify": [["verify"]], "after": [["restore"]],
        "rounds": [{"checks": [check], "control_after": [["approve"]]}, {"checks": [check]}],
    }
    with pytest.raises(acceptance.CheckFailed):
        acceptance.validate(p)


def test_native_command_keeps_observer_and_fixture_secrets_out_of_client(monkeypatch):
    monkeypatch.setenv("MCP_ACCEPTANCE_OBSERVER_TOKEN", "synthetic-observer-secret")
    monkeypatch.setenv("FIXTURE_DATABASE_URL", "synthetic-private-dsn")

    def run(argv, **kwargs):
        assert argv[:2] == ["rtk", "proxy"]
        assert "MCP_ACCEPTANCE_OBSERVER_TOKEN" not in kwargs["env"]
        assert "FIXTURE_DATABASE_URL" not in kwargs["env"]
        return SimpleNamespace(returncode=0, stdout="synthetic-secret-output", stderr="")

    monkeypatch.setattr(acceptance.subprocess, "run", run)
    assert acceptance.command(["copilot", "--version"], marker="test-marker") == "synthetic-secret-output"


def test_copilot_canary_uses_explicit_tools_and_environment_references(monkeypatch):
    config = plan()["clients"]["copilot-cli"]
    config.update(version="1.0.91", disabled_servers=["agent-booster"],
                  additional_mcp_config="/tmp/nonsecret-config.json", native_env=["MCP_NATIVE_TOKEN"])
    calls = []

    def execute(argv, **kwargs):
        calls.append((argv, kwargs))
        return "GitHub Copilot CLI 1.0.91" if "--version" in argv else "marker"

    monkeypatch.setattr(acceptance, "command", execute)
    acceptance.CopilotClient(config).run({"allowed_tools": ["guard_activity"], "output_text": "{marker}"}, "marker", 1)
    argv, options = calls[-1]
    assert "--no-custom-instructions" in argv and "--disable-builtin-mcps" in argv
    assert argv[argv.index("--log-level") + 1] == "none"
    assert argv[argv.index("--additional-mcp-config") + 1] == "@/tmp/nonsecret-config.json"
    assert "conduct(guard_activity)" in argv and "conduct(conduct_current_workspace)" not in argv
    assert options["allowed_env"] == ["MCP_NATIVE_TOKEN"]


def test_bearer_canary_does_not_claim_oauth_acceptance():
    result = report()
    result["authentication"] = {"copilot-cli": "Bearer token"}
    row = next(line for line in acceptance.matrix(result).splitlines() if line.startswith("| Copilot CLI"))
    assert "Bearer token" in row and "OAuth" not in row


@pytest.mark.parametrize("field,value", [
    ("clerk_user_id", "another-actor"), ("agent_identity_id", "another-agent"),
    ("workspace_id", "another-workspace"), ("source", "hook"), ("ts", "2020-01-01T00:00:00+00:00"),
])
def test_audit_rejects_wrong_attribution_or_stale_evidence(field, value):
    config = plan()["clients"]["copilot-cli"]
    row = {"id": str(uuid4()), "input_summary": "test-marker", "tool_call": "guard_activity",
           "decision": "allowed", "workspace_id": config["workspace_id"], "source": "mcp",
           "clerk_user_id": config["actor_id"], "agent_identity_id": config["agent_identity_id"],
           "ts": "2026-10-05T12:00:01+00:00"}
    row[field] = value
    observer = object.__new__(acceptance.Observer)
    observer.get = lambda *args: [row]
    with pytest.raises(acceptance.CheckFailed):
        observer.check({"kind": "audit", "tool": "guard_activity", "decision": "allowed"},
                       config, "test-marker", "2026-10-05T12:00:00+00:00")


def test_audit_report_contains_references_not_payloads():
    config = plan()["clients"]["copilot-cli"]
    event = str(uuid4())
    row = {"id": event, "input_summary": "test-marker private-payload", "tool_call": "guard_activity",
           "decision": "allowed", "workspace_id": config["workspace_id"], "source": "mcp",
           "clerk_user_id": config["actor_id"], "agent_identity_id": config["agent_identity_id"],
           "ts": "2026-10-05T12:00:01+00:00"}
    observer = object.__new__(acceptance.Observer)
    observer.get = lambda *args: [row]
    result = observer.check({"kind": "audit", "tool": "guard_activity", "decision": "allowed"},
                            config, "test-marker", "2026-10-05T12:00:00+00:00")
    assert result == {"kind": "audit", "event_ids": [event]}


def test_revocation_probe_requires_actual_http_denial(monkeypatch):
    observer = object.__new__(acceptance.Observer)
    observer.api = "https://conduct.test"
    observer.http = SimpleNamespace(post=lambda *args: (200, {}, {}))
    monkeypatch.setenv("MCP_NATIVE_REVOKED_TOKEN", "synthetic-fixture-token")
    with pytest.raises(acceptance.CheckFailed):
        observer.check({"kind": "denied", "status": 401, "token_env": "MCP_NATIVE_REVOKED_TOKEN"},
                       {"workspace_id": "fixture"}, "marker", acceptance.now())


def test_cleanup_always_runs_and_cleanup_failure_cannot_pass(monkeypatch):
    config = plan()["clients"]["copilot-cli"]
    config["phases"]["connect"]["after"] = [["restore-fixture"]]
    calls = []
    monkeypatch.setattr(acceptance.CopilotClient, "run", lambda *args: {"adapter": "native-copilot-cli"})

    def execute(argv, **kwargs):
        calls.append(argv)
        raise acceptance.CheckFailed("fixture restoration failed")

    monkeypatch.setattr(acceptance, "command", execute)
    observer = SimpleNamespace(wait=lambda *args: [{"kind": "audit"}])
    with pytest.raises(acceptance.CheckFailed):
        acceptance.run_phase("copilot-cli", "connect", config, observer, allow_mutation=True, allow_cloud=False, timeout=1)
    assert calls == [["restore-fixture"]]


def test_mutations_and_cloud_tasks_need_separate_explicit_consent():
    config = plan()["clients"]["copilot-cli"]
    config["phases"]["revocation"] = {"checks": []}
    with pytest.raises(acceptance.CheckFailed):
        acceptance.run_phase("copilot-cli", "revocation", config, None, allow_mutation=False, allow_cloud=False, timeout=1)
    with pytest.raises(acceptance.CheckFailed):
        acceptance.run_phase("github-agent", "connect", config, None, allow_mutation=True, allow_cloud=False, timeout=1)


def test_read_phase_cannot_run_cleanup_commands_without_mutation_consent():
    config = plan()["clients"]["copilot-cli"]
    config["phases"]["connect"]["after"] = [["restore-fixture"]]
    with pytest.raises(acceptance.CheckFailed):
        acceptance.run_phase("copilot-cli", "connect", config, None, allow_mutation=False, allow_cloud=False, timeout=1)


def test_ordinary_actions_job_is_not_github_agent_evidence(monkeypatch):
    config = {"repo": "fixture-org/mcp-test", "version": "2026-10-05"}
    monkeypatch.setattr(acceptance, "github_api", lambda *args, **kwargs: {
        "number": 1, "assignees": [{"login": "github-actions[bot]"}]})
    with pytest.raises(acceptance.CheckFailed):
        acceptance.GithubAgent(config).run({}, "marker", 1)


def test_no_probes_is_nonzero_and_publishes_pending(tmp_path):
    p = plan()
    p["clients"] = {}
    source, results, matrix = tmp_path / "plan.json", tmp_path / "result.json", tmp_path / "matrix.md"
    source.write_text(json.dumps(p))
    assert acceptance.main(["--plan", str(source), "--report", str(results), "--matrix", str(matrix), "--require-all"]) == 1
    assert "Passed" not in matrix.read_text()
    assert all(cell["status"] == "Pending" for client in json.loads(results.read_text())["clients"].values() for cell in client.values())


def test_browser_adapter_rejects_remote_debugging_and_lookalike_origins():
    with pytest.raises(acceptance.CheckFailed):
        acceptance.BrowserClient("chatgpt", {"cdp": "http://public.example:9222", "page_prefix": "https://chatgpt.com/"})
    with pytest.raises(acceptance.CheckFailed):
        acceptance.BrowserClient("chatgpt", {"cdp": "http://127.0.0.1:9222", "page_prefix": "https://chatgpt.com.evil.example/"})
