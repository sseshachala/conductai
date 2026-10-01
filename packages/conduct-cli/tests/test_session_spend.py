from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest

from conduct_cli.guard_commands import session_spend


def test_selected_deployment_and_workspace(monkeypatch, capsys):
    ws, event = str(uuid4()), str(uuid4())
    monkeypatch.setattr(session_spend.shared, "_require_guard_config", lambda: {"workspace_id": ws, "agent_token": "test"})
    monkeypatch.setattr(session_spend.shared, "_api_url", lambda _: "https://local.example")
    req = Mock(return_value={"link_status": "unlinked", "combined_cost_microdollars": None})
    monkeypatch.setattr(session_spend.shared, "_req", req)
    session_spend.run(SimpleNamespace(event=event))
    req.assert_called_once_with("GET", f"https://local.example/guard/events/session-usage/{event}/reconciliation?workspace_id={ws}", token="test")
    assert '"combined_cost_microdollars": null' in capsys.readouterr().out


def test_invalid_id_does_not_contact_api(monkeypatch):
    req = Mock()
    monkeypatch.setattr(session_spend.shared, "_req", req)
    with pytest.raises(SystemExit, match="UUID"):
        session_spend.run(SimpleNamespace(event="../other"))
    req.assert_not_called()
