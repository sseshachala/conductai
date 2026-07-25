import argparse
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from conduct_cli.main import _stream_run, cmd_run

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _args(**kw):
    defaults = dict(agent="My-Agent", input=[], project=None, max_turns=None)
    defaults.update(kw)
    return argparse.Namespace(**defaults)


WF = {"id": "wf-id", "name": "My-Agent", "playbook_slug": None, "github_webhook": False}


def _auth_side_effect(*a, **kw):
    return ("https://api.example.com", "ws-1", "key-abc", None)


# ---------------------------------------------------------------------------
# _stream_run — URL construction
# ---------------------------------------------------------------------------

def test_stream_run_url_with_token(capsys):
    events = [{"kind": "run_completed", "payload": {}}]
    with patch("conduct_cli.main.api.stream", return_value=iter(events)) as mock_stream, \
         patch("conduct_cli.main.api.headers", return_value={}):
        result = _stream_run("https://srv", "wf-1", "run-1", "ws-1", token="tok-xyz")
    url = mock_stream.call_args[0][0]
    assert "token=tok-xyz" in url
    assert "workspace_id=ws-1" in url
    assert result is True


# ---------------------------------------------------------------------------
# _stream_run — block_started
# ---------------------------------------------------------------------------

def test_stream_run_block_started_no_prefix(capsys):
    events = [{"kind": "block_started", "payload": {"label": "Run shell"}}]
    with patch("conduct_cli.main.api.stream", return_value=iter(events)), \
         patch("conduct_cli.main.api.headers", return_value={}):
        _stream_run("https://srv", "wf-1", "run-1", "ws-1", token="t")
    out = capsys.readouterr().out
    assert "Run shell" in out
    assert "\033[34m" in out  # BLUE


def test_stream_run_block_started_with_block_id(capsys):
    events = [{"kind": "block_started", "block_id": "b1", "payload": {"label": "Brain"}}]
    with patch("conduct_cli.main.api.stream", return_value=iter(events)), \
         patch("conduct_cli.main.api.headers", return_value={}):
        _stream_run("https://srv", "wf-1", "run-1", "ws-1", token="t")
    out = capsys.readouterr().out
    assert "[b1]" in out
    assert "Brain" in out


# ---------------------------------------------------------------------------
# _stream_run — block_completed
# ---------------------------------------------------------------------------

def test_stream_run_block_completed_prints_green(capsys):
    events = [{"kind": "block_completed", "payload": {"summary": "Done OK"}}]
    with patch("conduct_cli.main.api.stream", return_value=iter(events)), \
         patch("conduct_cli.main.api.headers", return_value={}):
        _stream_run("https://srv", "wf-1", "run-1", "ws-1", token="t")
    out = capsys.readouterr().out
    assert "Done OK" in out
    assert "\033[32m" in out  # GREEN


# ---------------------------------------------------------------------------
# _stream_run — block_failed
# ---------------------------------------------------------------------------

def test_stream_run_block_failed_prints_red(capsys):
    events = [{"kind": "block_failed", "payload": {"error": "Something broke"}}]
    with patch("conduct_cli.main.api.stream", return_value=iter(events)), \
         patch("conduct_cli.main.api.headers", return_value={}):
        _stream_run("https://srv", "wf-1", "run-1", "ws-1", token="t")
    out = capsys.readouterr().out
    assert "Something broke" in out
    assert "\033[31m" in out  # RED


# ---------------------------------------------------------------------------
# _stream_run — brain_tool_call
# ---------------------------------------------------------------------------

def test_stream_run_brain_tool_call_prints_summary(capsys):
    events = [{"kind": "brain_tool_call", "payload": {"summary": "read_file(foo.py)"}}]
    with patch("conduct_cli.main.api.stream", return_value=iter(events)), \
         patch("conduct_cli.main.api.headers", return_value={}):
        _stream_run("https://srv", "wf-1", "run-1", "ws-1", token="t")
    out = capsys.readouterr().out
    assert "read_file(foo.py)" in out


# ---------------------------------------------------------------------------
# _stream_run — guard_check
# ---------------------------------------------------------------------------

def test_stream_run_guard_check_warnings_yellow(capsys):
    events = [{
        "kind": "guard_check",
        "payload": {
            "rules_checked": 3,
            "block_type": "brain",
            "warnings": [{"rule_id": "R1", "message": "token limit near"}],
        },
    }]
    with patch("conduct_cli.main.api.stream", return_value=iter(events)), \
         patch("conduct_cli.main.api.headers", return_value={}):
        _stream_run("https://srv", "wf-1", "run-1", "ws-1", token="t")
    out = capsys.readouterr().out
    assert "R1" in out
    assert "token limit near" in out
    assert "\033[33m" in out  # YELLOW


def test_stream_run_guard_check_audited_blue(capsys):
    events = [{
        "kind": "guard_check",
        "payload": {
            "rules_checked": 2,
            "block_type": "shell",
            "audited": [{"rule_id": "A1", "message": "audit trail recorded"}],
        },
    }]
    with patch("conduct_cli.main.api.stream", return_value=iter(events)), \
         patch("conduct_cli.main.api.headers", return_value={}):
        _stream_run("https://srv", "wf-1", "run-1", "ws-1", token="t")
    out = capsys.readouterr().out
    assert "A1" in out
    assert "audit trail recorded" in out
    assert "\033[34m" in out  # BLUE


def test_stream_run_guard_check_clean_green(capsys):
    events = [{
        "kind": "guard_check",
        "payload": {"rules_checked": 5, "block_type": "brain"},
    }]
    with patch("conduct_cli.main.api.stream", return_value=iter(events)), \
         patch("conduct_cli.main.api.headers", return_value={}):
        _stream_run("https://srv", "wf-1", "run-1", "ws-1", token="t")
    out = capsys.readouterr().out
    assert "5 rules checked" in out
    assert "passed" in out
    assert "\033[32m" in out  # GREEN


# ---------------------------------------------------------------------------
# _stream_run — terminal events
# ---------------------------------------------------------------------------

def test_stream_run_returns_true_on_run_completed():
    events = [{"kind": "run_completed", "payload": {}}]
    with patch("conduct_cli.main.api.stream", return_value=iter(events)), \
         patch("conduct_cli.main.api.headers", return_value={}):
        result = _stream_run("https://srv", "wf-1", "run-1", "ws-1", token="t")
    assert result is True


def test_stream_run_returns_false_on_run_failed():
    events = [{"kind": "run_failed", "payload": {"error": "executor crashed"}}]
    with patch("conduct_cli.main.api.stream", return_value=iter(events)), \
         patch("conduct_cli.main.api.headers", return_value={}):
        result = _stream_run("https://srv", "wf-1", "run-1", "ws-1", token="t")
    assert result is False


def test_stream_run_returns_false_on_empty_stream():
    with patch("conduct_cli.main.api.stream", return_value=iter([])), \
         patch("conduct_cli.main.api.headers", return_value={}):
        result = _stream_run("https://srv", "wf-1", "run-1", "ws-1", token="t")
    assert result is False


def test_stream_run_unknown_kind_prints_gray(capsys):
    events = [{"kind": "some_unknown_event", "payload": {"info": "x"}}]
    with patch("conduct_cli.main.api.stream", return_value=iter(events)), \
         patch("conduct_cli.main.api.headers", return_value={}):
        _stream_run("https://srv", "wf-1", "run-1", "ws-1", token="t")
    out = capsys.readouterr().out
    assert "\033[90m" in out  # GRAY


# ---------------------------------------------------------------------------
# cmd_run
# ---------------------------------------------------------------------------

def _make_req_side_effect(workflows, trigger_resp=None, **extras):
    """Return a side-effect for api.req that handles the common GET/POST calls."""
    trigger_resp = trigger_resp or {"run_id": "run-abc"}

    def _req(method, url, hdrs, body=None):
        if method == "GET" and "/workflows" in url and "runs" not in url:
            return workflows
        if method == "POST" and "/preflight" in url:
            return {"suggested_max_turns": 20, "total_files": []}
        if method == "POST" and "/validate-inputs" in url:
            return extras.get("validate_inputs", {"missing": []})
        if method == "POST" and "/validate" in url:
            return extras.get("validate", {"errors": []})
        if method == "POST" and "/trigger" in url:
            return trigger_resp
        return {}

    return _req


def test_cmd_run_agent_not_found(capsys):
    with patch("conduct_cli.main._require_auth", return_value=("https://srv", "ws-1", "key")), \
         patch("conduct_cli.main.api.req", side_effect=_make_req_side_effect([])), \
         patch("conduct_cli.main.api.headers", return_value={}):
        with pytest.raises(SystemExit) as exc:
            cmd_run(_args(agent="Ghost-Agent"))
    assert exc.value.code == 1
    assert "Ghost-Agent" in capsys.readouterr().out


def test_cmd_run_bad_input_format(capsys):
    with patch("conduct_cli.main._require_auth", return_value=("https://srv", "ws-1", "key")), \
         patch("conduct_cli.main.api.req", side_effect=_make_req_side_effect([WF])), \
         patch("conduct_cli.main.api.headers", return_value={}):
        with pytest.raises(SystemExit) as exc:
            cmd_run(_args(input=["badformat"]))
    assert exc.value.code == 1
    out = capsys.readouterr().out
    assert "key=value" in out


def test_cmd_run_happy_path():
    with patch("conduct_cli.main._require_auth", return_value=("https://srv", "ws-1", "key")), \
         patch("conduct_cli.main.api.req", side_effect=_make_req_side_effect([WF])), \
         patch("conduct_cli.main.api.headers", return_value={}), \
         patch("conduct_cli.main._stream_run", return_value=True) as mock_stream:
        cmd_run(_args())
    mock_stream.assert_called_once_with("https://srv", "wf-id", "run-abc", "ws-1", "key")


def test_cmd_run_project_not_found(capsys):
    def _req(method, url, hdrs, body=None):
        if method == "GET" and "/workflows" in url:
            return [WF]
        if method == "GET" and "/projects" in url:
            return [{"id": "p-1", "name": "Proj-A"}]
        return {}

    with patch("conduct_cli.main._require_auth", return_value=("https://srv", "ws-1", "key")), \
         patch("conduct_cli.main.api.req", side_effect=_req), \
         patch("conduct_cli.main.api.headers", return_value={}):
        with pytest.raises(SystemExit) as exc:
            cmd_run(_args(project="NonExistent"))
    assert exc.value.code == 1
    assert "NonExistent" in capsys.readouterr().out


def test_cmd_run_missing_required_inputs(capsys):
    missing = [{"label": "Issue URL", "key": "issue_url"}]
    with patch("conduct_cli.main._require_auth", return_value=("https://srv", "ws-1", "key")), \
         patch("conduct_cli.main.api.req", side_effect=_make_req_side_effect([WF], validate_inputs={"missing": missing})), \
         patch("conduct_cli.main.api.headers", return_value={}), \
         patch("conduct_cli.main._stream_run", return_value=True):
        with pytest.raises(SystemExit) as exc:
            cmd_run(_args())
    assert exc.value.code == 2
    out = capsys.readouterr().out
    assert "issue_url" in out
