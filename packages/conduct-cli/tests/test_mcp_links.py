from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest

from conduct_cli.guard_commands import mcp_links


def args(**kw):
    return SimpleNamespace(**{"action": "list", "installation": None, "reference": None,
                              "server": None, "revision": None, "offset": 0, **kw})


@pytest.fixture
def api(monkeypatch):
    cfg = {"workspace_id": str(uuid4()), "api_url": "https://onprem.example", "agent_token": "synthetic"}
    monkeypatch.setattr(mcp_links.guard_shared, "_require_guard_config", lambda: cfg)
    request = Mock(return_value={"installations": [], "registrations": [], "next_offset": None})
    monkeypatch.setattr(mcp_links.guard_shared, "_req", request)
    return request, cfg


def test_selected_deployment_workspace_and_pagination(api):
    request, cfg = api
    mcp_links.run(args(offset=100))
    assert request.call_args.args == ("GET", f"https://onprem.example/guard/discover/mcp-reconciliation?workspace_id={cfg['workspace_id']}&offset=100")


def test_negative_offset_rejected_before_network(api):
    request, _ = api
    with pytest.raises(SystemExit):
        mcp_links.run(args(offset=-1))
    request.assert_not_called()


@pytest.mark.parametrize("action", ["link", "unlink"])
def test_explicit_link_revision(api, action):
    request, _ = api
    server = str(uuid4())
    mcp_links.run(args(action=action, installation=str(uuid4()), reference="b" * 64, server=server, revision=4))
    assert request.call_args.args[0] == "PUT"
    assert request.call_args.kwargs["body"] == {"server_id": server if action == "link" else None, "revision": 4}


@pytest.mark.parametrize("options", [{}, {"installation": "bad", "reference": "b" * 64},
    {"installation": str(uuid4()), "reference": "bad"},
    {"installation": str(uuid4()), "reference": "b" * 64},
    {"installation": str(uuid4()), "reference": "b" * 64, "server": str(uuid4())}])
def test_rejects_incomplete_mutation_before_network(api, options):
    request, _ = api
    with pytest.raises(SystemExit):
        mcp_links.run(args(action="link", **options))
    request.assert_not_called()
