"""Verify both dispatchers populate _trigger with the fields playbooks need.

security_loop.yaml + security-autopilot-fix.yaml both reference:
  - _trigger.autopilot_enabled  (autopilot_gate)
  - _trigger.slack_alerts_enabled  (slack_gate_alert / dismiss / log)
  - _trigger.slack_channel  (every alert/log/notify output block)

If the trigger never sets these, the template renderer leaks literal
``{{...}}`` into the state, which either crashes logic-block eval or sends
garbage as a Slack channel. See conductai#998.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.models.security_finding import SecurityFinding
from app.routers.security import _trigger_security_loop, trigger_fix


def _mk_finding() -> SecurityFinding:
    return SecurityFinding(
        id="00000000-0000-0000-0000-000000000001",
        workspace_id="ws-1",
        tool="threat_modeler",
        severity="high",
        type="secret-leak",
        file="coworker/secrets.py",
        line=42,
        description="Hardcoded HMAC fallback secret allows signature forgery",
        suggested_fix="Rotate and require config",
        repo_full_name="sseshachala/openworker",
        commit_sha=None,
        source_run_id=None,
        status="open",
    )


def _mk_db(workflow, config_row):
    """Build a db mock: workflow query returns workflow, execute() returns config_row."""
    db = MagicMock()
    # first .query().filter().first() → the workflow lookup
    q = db.query.return_value
    q.filter.return_value = q
    q.first.return_value = workflow
    # .execute(text(...), {...}).first() → security_config row
    db.execute.return_value.first.return_value = config_row
    return db


def _mk_workflow():
    wf = MagicMock()
    wf.current_version_id = "wfv-1"
    wf.workspace_id = "ws-1"
    return wf


def _captured_state(db_mock):
    """Grab the state dict passed to Run(state=...) via db.add()."""
    added = db_mock.add.call_args[0][0]
    return added.state


def _run_trigger(db):
    with patch("app.routers.security.enqueue_run"), \
         patch("app.models.run.Run", side_effect=lambda **kw: MagicMock(**kw, id="run-1")):
        _trigger_security_loop(_mk_finding(), "ws-1", db)


def test_defaults_when_no_security_config_row():
    """Row missing → autopilot off, slack off, channel empty (no crash, safe no-op)."""
    db = _mk_db(_mk_workflow(), None)
    _run_trigger(db)

    trg = _captured_state(db)["_trigger"]
    assert trg["autopilot_enabled"] is False
    assert trg["slack_alerts_enabled"] is False
    assert trg["slack_channel"] == ""


def test_populates_from_security_config_row():
    """Row present → fields flow through, bools coerced, None channel → empty string."""
    # SELECT autopilot_enabled, security_slack_alerts_enabled, security_slack_channel
    row = (True, True, "#sec-alerts")
    db = _mk_db(_mk_workflow(), row)
    _run_trigger(db)

    trg = _captured_state(db)["_trigger"]
    assert trg["autopilot_enabled"] is True
    assert trg["slack_alerts_enabled"] is True
    assert trg["slack_channel"] == "#sec-alerts"


def test_null_channel_becomes_empty_string():
    """DB NULL slack channel → '' so playbook template renders cleanly."""
    row = (False, True, None)
    db = _mk_db(_mk_workflow(), row)
    _run_trigger(db)

    trg = _captured_state(db)["_trigger"]
    assert trg["slack_channel"] == ""
    assert trg["slack_alerts_enabled"] is True


def _mk_db_with_finding_and_workflow(finding, workflow, config_row, workspace=None):
    """Build a db mock that answers .query().filter().first() calls in order:
    (1) SecurityFinding lookup (trigger_fix)
    (2) Workspace lookup (_find_security_workflow pointer check)
    (3) Workflow lookup — pointer path or legacy .first() fallback
    Then execute() → security_config row."""
    db = MagicMock()
    q = db.query.return_value
    q.filter.return_value = q
    if workspace is None:
        workspace = MagicMock(security_automation_project_id=None)
    q.first.side_effect = [finding, workspace, workflow]
    db.execute.return_value.first.return_value = config_row
    return db


def test_trigger_fix_populates_slack_channel_from_config():
    """trigger_fix (autopilot-fix dispatcher) must also set slack_channel — the
    autopilot-fix playbook has NO gate around Slack output, so a missing channel
    sends the literal template to Slack. This is the same #998 bug as the loop.
    """
    finding = _mk_finding()
    row = (True, True, "#sec-fixes")
    db = _mk_db_with_finding_and_workflow(finding, _mk_workflow(), row)

    with patch("app.routers.security.enqueue_run"), \
         patch("app.models.run.Run", side_effect=lambda **kw: MagicMock(**kw, id="run-1")):
        trigger_fix(finding_id=finding.id, db=db, workspace_id="ws-1")

    trg = _captured_state(db)["_trigger"]
    assert trg["event_type"] == "security_finding_fix"
    assert trg["slack_channel"] == "#sec-fixes"
    assert trg["autopilot_enabled"] is True
    assert trg["slack_alerts_enabled"] is True
