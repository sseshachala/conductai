"""GET /guard/spend caches per (workspace, month) and never across workspaces."""
from app.core.ttl_cache import TTLCache
from app.modules.guard.routers import spend_summary as ss


def test_spend_summary_cached_per_workspace(monkeypatch):
    calls = []
    monkeypatch.setattr(ss, "_summary_cache", TTLCache())
    monkeypatch.setattr(ss, "_get_spend_summary_inner", lambda db, ws, month: calls.append(ws) or f"summary:{ws}")

    assert ss.get_spend_summary(db=None, workspace_id="ws-a", month=None) == "summary:ws-a"
    assert ss.get_spend_summary(db=None, workspace_id="ws-a", month=None) == "summary:ws-a"
    assert ss.get_spend_summary(db=None, workspace_id="ws-b", month=None) == "summary:ws-b"
    assert calls == ["ws-a", "ws-b"]


def test_spend_summary_cache_expires(monkeypatch):
    calls = []
    now = [1000.0]
    monkeypatch.setattr(ss, "_summary_cache", TTLCache())
    monkeypatch.setattr(ss.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(ss, "_get_spend_summary_inner", lambda db, ws, month: calls.append(ws) or "s")

    ss.get_spend_summary(db=None, workspace_id="ws-a", month=None)
    now[0] += ss._SUMMARY_TTL_S + 1
    ss.get_spend_summary(db=None, workspace_id="ws-a", month=None)
    assert calls == ["ws-a", "ws-a"]
