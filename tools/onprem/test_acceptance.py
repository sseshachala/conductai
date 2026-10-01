import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

spec = importlib.util.spec_from_file_location("onprem_acceptance", Path(__file__).with_name("acceptance.py"))
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


@pytest.fixture
def plan(tmp_path):
    values = json.loads(Path(__file__).with_name("acceptance.example.json").read_text())
    for key in ("ca", "cli_config", "delegation_config"):
        values[key] = key + ".json"
        (tmp_path / values[key]).write_text(json.dumps({"api_url": "https://api.example.internal",
            "issuer": "https://idp.example.internal/realms/test"}))
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(values))
    return path


def test_plan_resolves_files_relative_to_manifest(plan):
    result = runner.load_plan(plan)
    assert Path(result["ca"]).parent == plan.parent


@pytest.mark.parametrize("url", ["http://api.example.internal", "https://user:password@api.example.internal",
                                 "https://api.example.internal?token=secret", "https://api.example.internal/#token"])
def test_rejects_unsafe_endpoint(url):
    with pytest.raises(ValueError):
        runner.https_url(url)


def test_rejects_cross_deployment_config(plan):
    (plan.parent / "delegation_config.json").write_text(json.dumps({"api_url": "https://different.example.internal"}))
    with pytest.raises(ValueError, match="same installation"):
        runner.load_plan(plan)


def test_rejects_extra_secret_field(plan):
    data = json.loads(plan.read_text())
    data["client_secret"] = "synthetic-not-real"
    plan.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="non-secret"):
        runner.load_plan(plan)


def test_all_commands_require_revocation_and_both_inference_paths(plan):
    commands = dict(runner.commands(runner.load_plan(plan), "all"))
    assert set(commands) == {"console", "delegation", "outages"}
    assert "--revoke" in commands["delegation"]
    for flag in ("--inference", "--fault-tests", "--gateway-url", "--litellm-url", "--block-marker"):
        assert flag in commands["outages"]


def test_false_or_missing_attestations_never_pass(tmp_path):
    path = tmp_path / "evidence.json"
    for doc in ({}, dict.fromkeys(runner.ATTESTATIONS, False), dict.fromkeys(runner.ATTESTATIONS, "true")):
        path.write_text(json.dumps(doc))
        with pytest.raises(ValueError):
            runner.evidence(path)
    path.write_text(json.dumps(dict.fromkeys(runner.ATTESTATIONS, True)))
    assert len(runner.evidence(path)) == 64


def test_check_is_not_a_test_pass(plan, monkeypatch, capsys):
    monkeypatch.setattr(runner.subprocess, "run", lambda *a, **k: pytest.fail("check must not execute tests"))
    assert runner.main(["--plan", str(plan), "--check"]) == 0
    assert "no acceptance checks passed" in capsys.readouterr().out


@pytest.mark.parametrize("code", [0, 1])
def test_reports_only_sanitized_status_and_never_certifies_airgap(plan, monkeypatch, code):
    monkeypatch.setattr(runner.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda _: "TEST")
    monkeypatch.setattr(runner.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=code))
    report = plan.parent / "report.json"
    assert runner.main(["--plan", str(plan), "--stage", "delegation", "--allow-disposable-tests",
                        "--report", str(report)]) == code
    data = json.loads(report.read_text())
    assert data["airgap"]["status"] == "not_verified"
    assert "example.internal" not in report.read_text()
    assert "checks_passed_airgap_pending" == data["status"] if code == 0 else data["status"] == "failed"


def test_refuses_report_overwrite(plan, monkeypatch):
    monkeypatch.setattr(runner.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda _: "TEST")
    monkeypatch.setattr(runner.subprocess, "run", lambda *a, **k: pytest.fail("must not run"))
    with pytest.raises(FileExistsError):
        runner.main(["--plan", str(plan), "--stage", "console", "--allow-disposable-tests", "--report", str(plan)])


def test_all_requires_airgap_evidence(plan, monkeypatch):
    monkeypatch.setattr(runner.sys.stdin, "isatty", lambda: True)
    with pytest.raises(SystemExit):
        runner.main(["--plan", str(plan), "--allow-disposable-tests", "--report", str(plan.parent / "report.json")])
