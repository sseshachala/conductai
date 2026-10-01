from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest

from conduct_cli.guard_commands import mcp_review


def args(**kw):
    return SimpleNamespace(**{"action": "list", "server": None, "revision": None, "digest": None, "yes": False, **kw})


@pytest.fixture
def api_mock(monkeypatch):
    cfg = {"workspace_id": str(uuid4()), "api_url": "https://local.example", "agent_token": "test-token"}
    monkeypatch.setattr(mcp_review.guard_shared, "_require_guard_config", lambda: cfg)
    mock = Mock(return_value=[])
    monkeypatch.setattr(mcp_review.guard_shared, "_req", mock)
    return mock, cfg


def test_list_uses_selected_deployment_and_redacts_registration_details(api_mock, capsys):
    mock, cfg = api_mock
    mock.return_value = [{"id": "server", "name": "test", "url": "private-url", "governance": None}]
    mcp_review.run(args())
    assert mock.call_args.args[1] == "https://local.example/mcp-servers?workspace_id=" + cfg["workspace_id"]
    assert "private-url" not in capsys.readouterr().out


@pytest.mark.parametrize("options", [{"action": "quarantine"}, {"action": "approve", "server": str(uuid4()), "revision": 1},
                                     {"action": "revoke", "server": str(uuid4()), "revision": 1}])
def test_mutations_require_explicit_target_revision_and_confirmation(api_mock, options):
    mock, _ = api_mock
    with pytest.raises(SystemExit):
        mcp_review.run(args(**options))
    mock.assert_not_called()


def test_review_sends_exact_reviewed_digest_and_revision(api_mock, capsys):
    mock, _ = api_mock
    mock.return_value = {"id": "server", "governance": {"state": "approved"}}
    mcp_review.run(args(action="approve", server=str(uuid4()), revision=2, digest="a" * 64))
    assert mock.call_args.kwargs["body"] == {"action": "approve", "revision": 2, "digest": "a" * 64}
    assert "test-token" not in capsys.readouterr().out
