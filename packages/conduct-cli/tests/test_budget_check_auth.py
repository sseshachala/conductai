"""The PreToolUse hook authenticates its budget-check request."""
import io
import json

import pytest

import conduct_cli.hooks.pretooluse as pt


@pytest.fixture
def captured(tmp_path, monkeypatch):
    seen = []

    def fake_urlopen(req, timeout=None):
        seen.append(req)
        return io.BytesIO(json.dumps({"hard_blocked": False, "reason": None}).encode())

    monkeypatch.setattr(pt, "BUDGET_CACHE_PATH", tmp_path / "budget.json")
    monkeypatch.setattr(pt.urllib.request, "urlopen", fake_urlopen)
    return seen


def _config(tmp_path, monkeypatch, cfg):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"api_url": "https://api.test", "workspace_id": "ws", **cfg}))
    monkeypatch.setattr(pt, "CONFIG_PATH", path)


def test_sends_member_token_as_bearer(tmp_path, monkeypatch, captured):
    _config(tmp_path, monkeypatch, {"member_token": "member-tok", "agent_token": "cond_agt_x"})
    assert pt._fetch_budget_status() == (False, None)
    assert captured[0].get_header("Authorization") == "Bearer member-tok"
    assert "/guard/spend/budget-check?workspace_id=ws" in captured[0].full_url


def test_falls_back_to_agent_token(tmp_path, monkeypatch, captured):
    _config(tmp_path, monkeypatch, {"agent_token": "cond_agt_x"})
    pt._fetch_budget_status()
    assert captured[0].get_header("Authorization") == "Bearer cond_agt_x"


def test_no_token_sends_no_header(tmp_path, monkeypatch, captured):
    _config(tmp_path, monkeypatch, {})
    pt._fetch_budget_status()
    assert captured[0].get_header("Authorization") is None
