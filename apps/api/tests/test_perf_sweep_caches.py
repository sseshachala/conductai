"""TTL caching + query-shape changes for the app-sweep slow endpoints."""
from app.core.ttl_cache import TTLCache


def test_ttl_cache_hit_expiry_and_per_key(monkeypatch):
    now = [100.0]
    monkeypatch.setattr("app.core.ttl_cache.time.monotonic", lambda: now[0])
    cache, calls = TTLCache(), []

    def compute(k):
        return lambda: calls.append(k) or f"v:{k}"

    assert cache.get_or_compute("a", 10, compute("a")) == "v:a"
    assert cache.get_or_compute("a", 10, compute("a")) == "v:a"
    assert cache.get_or_compute("b", 10, compute("b")) == "v:b"
    now[0] += 11
    cache.get_or_compute("a", 10, compute("a"))
    assert calls == ["a", "b", "a"]


def test_ttl_cache_does_not_cache_exceptions():
    cache, calls = TTLCache(), []

    def boom():
        calls.append(1)
        raise RuntimeError("x")

    for _ in range(2):
        try:
            cache.get_or_compute("k", 10, boom)
        except RuntimeError:
            pass
    assert len(calls) == 2


def test_identity_activity_cached_per_workspace(monkeypatch):
    from app.modules.agent_identity import activity_stats as a

    monkeypatch.setattr(a, "_cache", TTLCache())
    calls = []
    monkeypatch.setattr(a, "_query", lambda db, ws: calls.append(ws) or {ws: a.IdentityActivity(1, None)})

    assert a.identity_activity(None, "ws-a") == {"ws-a": a.IdentityActivity(1, None)}
    a.identity_activity(None, "ws-a")
    a.identity_activity(None, "ws-b")
    assert calls == ["ws-a", "ws-b"]


def test_opener_caches_kpis_and_reuses_request_session(monkeypatch):
    from app.modules.glens.routers import opener as o

    monkeypatch.setattr(o, "_kpi_cache", TTLCache())
    seen = []

    def fake_kpis(ctx, db):
        seen.append((ctx.workspace_id, db))
        return {"blocked_today": 2, "events_today": 5, "blocks_mtd": 0, "active_developers_today": 3}

    monkeypatch.setattr(o, "get_governance_kpis", fake_kpis)
    sentinel = object()
    r1 = o.glens_opener(_="x", workspace_id="ws-a", db=sentinel)
    r2 = o.glens_opener(_="x", workspace_id="ws-a", db=sentinel)
    assert r1 == r2
    assert r1["chips"][0] == "Who was blocked today? (2 blocks)"
    assert seen == [("ws-a", sentinel)]


def test_opener_failure_falls_back_and_is_not_cached(monkeypatch):
    from app.modules.glens.routers import opener as o

    monkeypatch.setattr(o, "_kpi_cache", TTLCache())
    calls = []

    def fail(ctx, db):
        calls.append(1)
        raise RuntimeError("db down")

    monkeypatch.setattr(o, "get_governance_kpis", fail)
    out = o.glens_opener(_="x", workspace_id="ws-a", db=object())
    o.glens_opener(_="x", workspace_id="ws-a", db=object())
    assert out["chips"][0] == "Show me today's Guard activity"
    assert len(calls) == 2


def test_list_policies_last_hits_cached(monkeypatch):
    from app.modules.guard.routers import policies_read as p

    monkeypatch.setattr(p, "_TTL", TTLCache())
    calls = []
    monkeypatch.setattr(p, "_query_last_hits", lambda db, org_ws: calls.append(1) or {"r": 1})
    load = lambda: p._TTL.get_or_compute("ws", p._LAST_HIT_TTL_S, lambda: p._query_last_hits(None, None))
    assert load() == load() == {"r": 1}
    assert calls == [1]


def test_get_pack_unpinned_loads_only_latest_version():
    from app.modules.guard.policy_engine import _get_pack
    from app.modules.guard.models import SkillPack

    got = []

    class Q:
        def filter(self, *_):
            return self

        def all(self):
            return [("2.9.0",), ("2.17.0",), ("2.10.0",)]

    class DB:
        def query(self, col):
            assert col is SkillPack.version  # key column only, never the rules JSONB
            return Q()

        def get(self, model, key):
            got.append(key)
            return "pack"

    assert _get_pack(DB(), "conduct-base", None) == "pack"
    assert got == [("conduct-base", "2.17.0")]


def test_get_pack_unpinned_missing_returns_none():
    from app.modules.guard.policy_engine import _get_pack

    class Q:
        def filter(self, *_):
            return self

        def all(self):
            return []

    class DB:
        def query(self, _):
            return Q()

    assert _get_pack(DB(), "nope", None) is None
