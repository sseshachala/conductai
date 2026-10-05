from pathlib import Path

import pytest
import yaml

from app import worker
from app.modules.guard import audit_retention
from app.modules.guard.observability.metrics import GUARD_AUDIT_RETENTION_RUNS
from app.modules.guard.routers.audit_retention import HoldIn
from tests.guard.test_audit_archive import archive_settings


class LoopStopped(Exception):
    pass


def test_retention_daemon_safe_off_and_independent(monkeypatch):
    monkeypatch.setattr(worker.settings, "guard_audit_retention_enabled", False)
    assert worker._start_audit_retention() is None
    created = []
    class FakeThread:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.started = False
            created.append(self)
        def start(self):
            self.started = True
    monkeypatch.setattr(worker.settings, "guard_audit_retention_enabled", True)
    monkeypatch.setattr(worker.threading, "Thread", FakeThread)
    thread = worker._start_audit_retention()
    assert thread is created[0] and thread.started
    assert thread.kwargs == {"target": worker._audit_retention_loop, "daemon": True, "name": "audit-retention"}


@pytest.mark.parametrize("failure", [False, True])
def test_retention_daemon_records_results_and_survives_errors(monkeypatch, failure):
    calls = []
    def run_once():
        calls.append(1)
        if failure:
            raise TimeoutError("storage failure")
        return {"errors": 0}
    monkeypatch.setattr(audit_retention, "run_audit_retention_once", run_once)
    monkeypatch.setattr(worker.settings, "guard_audit_retention_dry_run", True)
    monkeypatch.setattr(worker.time, "sleep", lambda _seconds: (_ for _ in ()).throw(LoopStopped()))
    counter = GUARD_AUDIT_RETENTION_RUNS.labels(outcome="error" if failure else "success", dry_run="true")
    before = counter._value.get()
    with pytest.raises(LoopStopped):
        worker._audit_retention_loop()
    assert calls == [1] and counter._value.get() == before + 1


@pytest.mark.parametrize("days", [None, 1])
def test_invalid_policy_never_opens_database(archive_settings, days):
    archive_settings.guard_audit_retention_days = days
    def forbidden_session():
        raise AssertionError("Invalid retention policy must not query the database")
    with pytest.raises(ValueError):
        audit_retention.run_audit_retention_once(settings_obj=archive_settings, session_factory=forbidden_session)
    archive_settings.guard_audit_retention_enabled = False
    assert audit_retention.run_audit_retention_once(settings_obj=archive_settings, session_factory=forbidden_session)["errors"] == 0


def test_apply_rejects_missing_archive_keys_before_database(archive_settings):
    archive_settings.guard_audit_archive_signing_key = None
    def forbidden_session():
        raise AssertionError("Archive keys must be checked before database access")
    with pytest.raises(ValueError, match="keys"):
        audit_retention.run_audit_retention_once(settings_obj=archive_settings, session_factory=forbidden_session)


@pytest.mark.parametrize("start,end", [
    ("2026-01-02T00:00:00", None),
    ("2026-01-02T00:00:00Z", "2026-01-01T00:00:00Z"),
    ("2026-01-02T00:00:00Z", "2026-01-03T00:00:00"),
])
def test_hold_range_must_be_aware_and_ordered(start, end):
    with pytest.raises(ValueError):
        HoldIn(starts_at=start, ends_at=end, reason="test")


def test_render_and_helm_keep_cleanup_off_and_do_not_choose_compliance_period():
    root = Path(__file__).resolve().parents[4]
    render = yaml.safe_load((root / "render.yaml").read_text())
    checked = []
    for service in render["services"]:
        if service["name"] not in ("delegator-api", "delegator-worker"):
            continue
        checked.append(service["name"])
        env = {row["key"]: row.get("value") for row in service["envVars"]}
        assert str(env["GUARD_AUDIT_RETENTION_ENABLED"]).lower() == "false"
        assert str(env["GUARD_AUDIT_RETENTION_DRY_RUN"]).lower() == "true"
        assert "GUARD_AUDIT_RETENTION_DAYS" not in env
    assert set(checked) == {"delegator-api", "delegator-worker"}
    for filename in ("values.yaml", "customer.example.yaml"):
        values = yaml.safe_load((root / "deploy/helm/conduct" / filename).read_text())
        env = values["config"]["extraEnv"]
        assert str(env["GUARD_AUDIT_RETENTION_ENABLED"]).lower() == "false"
        assert str(env["GUARD_AUDIT_RETENTION_DRY_RUN"]).lower() == "true"
        assert "GUARD_AUDIT_RETENTION_DAYS" not in env
