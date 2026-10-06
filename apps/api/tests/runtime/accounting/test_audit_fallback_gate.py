"""Deletion must never pass on incomplete windows, tenant mismatches or failures."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import runpy
from unittest.mock import MagicMock, patch

import pytest

from app.runtime.accounting import audit_fallback_gate as gate


@pytest.mark.parametrize("now, expected", [
    (datetime(2026, 10, 2, 12, tzinfo=timezone.utc), datetime(2026, 9, 25, 12, tzinfo=timezone.utc)),
    (datetime(2026, 10, 20, 12, tzinfo=timezone.utc), datetime(2026, 10, 1, tzinfo=timezone.utc)),
    (datetime(2026, 1, 1, tzinfo=timezone.utc), datetime(2025, 12, 25, tzinfo=timezone.utc)),
])
def test_default_window_covers_month_and_last_seven_days(now, expected):
    assert gate.reporting_window_start(now) == expected


def test_window_uses_utc_not_local_month_boundary():
    local = datetime(2026, 10, 1, 1, tzinfo=timezone(timedelta(hours=5)))
    assert gate.reporting_window_start(local) == datetime(2026, 9, 1, tzinfo=timezone.utc)


def test_window_rejects_naive_datetime():
    with pytest.raises(ValueError, match="timezone"):
        gate.reporting_window_start(datetime(2026, 10, 2))


def test_clean_gate_closes_session_and_does_not_alert():
    db = MagicMock()
    with patch.object(gate, "audit_only_by_workspace", return_value=[]), patch.object(gate, "_post_gate_alert") as alert:
        result = gate.run_startup_gate(lambda: db)
    assert result["ready_for_removal"] is True
    assert result["errors"] == result["total_audit_only_rows"] == 0
    db.close.assert_called_once()
    statements = [str(c.args[0]) for c in db.execute.call_args_list]
    assert statements == ["SET TRANSACTION READ ONLY", "SET LOCAL statement_timeout = '20s'"]
    db.commit.assert_not_called()
    alert.assert_not_called()


def test_dirty_gate_closes_db_before_slack_and_logs_critical():
    db = MagicMock()
    entries = [gate.WorkspaceAuditOnlyCount("workspace-1", 3, 1, 0)]

    def alert(message):
        db.close.assert_called_once()
        assert "#2229" in message
        return True

    with patch.object(gate, "audit_only_by_workspace", return_value=entries), \
         patch.object(gate, "_post_gate_alert", side_effect=alert), patch.object(gate, "log") as log:
        result = gate.run_startup_gate(lambda: db)
    assert result["ready_for_removal"] is False
    assert result["slack_alert_sent"] is True
    assert result["total_audit_only_rows"] == 3
    assert result["positive_cost_rows"] == 1
    assert result["request_linked_rows"] == 0
    log.critical.assert_called_once()


def test_no_notify_keeps_dirty_gate_closed_without_slack():
    with patch.object(gate, "audit_only_by_workspace", return_value=[gate.WorkspaceAuditOnlyCount("ws", 1)]), \
         patch.object(gate, "_post_gate_alert") as alert:
        result = gate.run_startup_gate(MagicMock, notify=False)
    assert result["ready_for_removal"] is False
    alert.assert_not_called()


@pytest.mark.parametrize("failure", ["session", "query", "close"])
def test_database_failure_never_passes_or_exposes_credentials(failure):
    db = MagicMock()
    exception = RuntimeError("postgresql://secret@private-database")
    factory = MagicMock(return_value=db)
    if failure == "session":
        factory.side_effect = exception
    elif failure == "query":
        db.execute.side_effect = exception
    else:
        db.close.side_effect = exception

    def alert(message):
        if failure != "session":
            db.close.assert_called_once()
        assert "secret" not in message
        return True

    with patch.object(gate, "audit_only_by_workspace", return_value=[]), \
         patch.object(gate, "_post_gate_alert", side_effect=alert), patch.object(gate, "log") as log:
        result = gate.run_startup_gate(factory)
    assert result["errors"] == 1
    assert result["ready_for_removal"] is False
    assert result["slack_alert_sent"] is True
    assert "secret" not in str(log.method_calls)


def test_slack_failure_does_not_crash_dirty_gate():
    with patch.object(gate, "audit_only_by_workspace", return_value=[gate.WorkspaceAuditOnlyCount("ws", 1)]), \
         patch("app.modules.guard.observability.platform_slack.post_platform_alert", side_effect=RuntimeError("secret")), \
         patch.object(gate, "log") as log:
        result = gate.run_startup_gate(MagicMock)
    assert result["ready_for_removal"] is False
    assert result["slack_alert_sent"] is False
    assert "secret" not in str(log.method_calls)


def test_naive_since_cannot_create_a_clean_gate():
    factory = MagicMock()
    result = gate.run_startup_gate(factory, since=datetime(2026, 10, 2), notify=False)
    assert result["errors"] == 1
    assert result["ready_for_removal"] is False
    factory.assert_not_called()


def test_both_coverage_queries_match_receipts_in_same_workspace():
    db = MagicMock()
    db.execute.return_value.scalar.return_value = 0
    db.execute.return_value.all.return_value = []
    since = gate.reporting_window_start()
    gate.count_audit_only_requests(db, workspace_id="ws", since=since)
    gate.audit_only_by_workspace(db, since=since)
    for call in db.execute.call_args_list:
        assert "r.workspace_id = a.workspace_id" in str(call.args[0])
        assert "r.request_id = a.request_id" in str(call.args[0])


@pytest.mark.parametrize("now, expected_delay", [
    (datetime(2026, 10, 5, 4, tzinfo=timezone.utc), 900),
    (datetime(2026, 10, 5, 5, tzinfo=timezone.utc), 83700),
])
def test_worker_runs_same_gate_at_next_0415_utc(now, expected_delay):
    from app import worker

    class StopLoop(BaseException):
        pass

    with patch.object(worker, "datetime") as clock, \
         patch.object(worker.time, "sleep", side_effect=[None, StopLoop]) as sleep, \
         patch.object(gate, "run_startup_gate", return_value={"ready_for_removal": True}) as check:
        clock.now.return_value = now
        with pytest.raises(StopLoop):
            worker._accounting_gate_loop()
    assert sleep.call_args_list[0].args == (expected_delay,)
    check.assert_called_once()


def _operator_cli():
    return runpy.run_path(str(Path(__file__).resolve().parents[5] / "tools/accounting_gate.py"))


@pytest.mark.parametrize("ready, expected_exit", [(True, 0), (False, 1)])
def test_operator_cli_exit_code_and_no_default_notifications(ready, expected_exit, capsys):
    with patch("sys.argv", ["accounting_gate.py"]), \
         patch.object(gate, "run_startup_gate", return_value={"ready_for_removal": ready}) as check:
        assert _operator_cli()["main"]() == expected_exit
    assert check.call_args.kwargs["notify"] is False
    assert "ready_for_removal" in capsys.readouterr().out


def test_operator_since_cannot_narrow_the_required_window():
    required = datetime(2026, 9, 25, tzinfo=timezone.utc)
    with patch("sys.argv", ["accounting_gate.py", "--since", "2026-10-02T00:00:00Z"]), \
         patch.object(gate, "reporting_window_start", return_value=required), \
         patch.object(gate, "run_startup_gate", return_value={"ready_for_removal": True}) as check:
        assert _operator_cli()["main"]() == 0
    assert check.call_args.kwargs["since"] == required


def test_operator_can_include_older_history_and_opt_in_to_alerts():
    required = datetime(2026, 9, 25, tzinfo=timezone.utc)
    with patch("sys.argv", ["accounting_gate.py", "--since", "2026-09-01T00:00:00Z", "--notify"]), \
         patch.object(gate, "reporting_window_start", return_value=required), \
         patch.object(gate, "run_startup_gate", return_value={"ready_for_removal": False}) as check:
        assert _operator_cli()["main"]() == 1
    assert check.call_args.kwargs["since"] == datetime(2026, 9, 1, tzinfo=timezone.utc)
    assert check.call_args.kwargs["notify"] is True


@pytest.mark.parametrize("value", ["2026-10-02", "not-a-date"])
def test_operator_rejects_invalid_timestamps(value):
    with patch("sys.argv", ["accounting_gate.py", "--since", value]), pytest.raises(SystemExit) as exc:
        _operator_cli()["main"]()
    assert exc.value.code == 2
