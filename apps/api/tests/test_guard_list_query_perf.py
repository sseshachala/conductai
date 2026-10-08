"""Batched / bounded list-endpoint queries return the same results as the N+1 versions."""
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Query, Session

from app.modules.agent_identity.run_token_serialize import serialize_run_tokens
from app.modules.guard.discovery_inventory import workspace_inventory_page
from app.modules.guard.routers import policies_helpers as ph
from app.modules.guard.routers.spend_budgets import _cost_from_groups
from app.routers import team_memory


# ── spend budgets: one GROUP BY == per-budget SUM ─────────────────────────
def test_cost_from_groups_matches_per_budget_filters():
    rows = [
        ("u1", "claude", "a1", 1.0), ("u1", "codex", None, 2.0),
        ("u2", "claude", None, 4.0), (None, "claude", "a1", 8.0), (None, None, None, 16.0),
    ]

    def naive(b):
        return sum(
            c for u, t, a, c in rows
            if (b.clerk_user_id is None or u == b.clerk_user_id)
            and (b.ai_tool is None or t == b.ai_tool)
            and (b.agent_identity_id is None or a == b.agent_identity_id)
        )

    for uid in (None, "u1", "u2"):
        for tool in (None, "claude", "codex"):
            for agent in (None, "a1"):
                b = SimpleNamespace(clerk_user_id=uid, ai_tool=tool, agent_identity_id=agent)
                assert _cost_from_groups(rows, b) == naive(b)
    ws_default = SimpleNamespace(clerk_user_id=None, ai_tool=None, agent_identity_id=None)
    assert _cost_from_groups(rows, ws_default) == 31.0


# ── run tokens: single joined query ───────────────────────────────────────
def test_serialize_run_tokens_uses_one_query_and_matches():
    run_a, run_b = uuid.uuid4(), uuid.uuid4()
    wf = uuid.uuid4()
    now = datetime.now(timezone.utc)

    def tok(run_id, i):
        return SimpleNamespace(id=f"t{i}", run_id=run_id, token_prefix="p", created_at=now,
                               first_used_at=None, invalidated_at=None)

    db = MagicMock()
    db.query.return_value.join.return_value.join.return_value.filter.return_value.all.return_value = [
        (run_a, wf, "My Flow")
    ]
    out = serialize_run_tokens(db, [tok(str(run_a), 1), tok(str(run_b), 2), tok("not-a-uuid", 3)])

    assert db.query.call_count == 1
    assert [(o["workflow_id"], o["workflow_name"]) for o in out] == [
        (str(wf), "My Flow"), (None, None), (None, None)]
    assert out[0]["created_at"] == now.isoformat() and out[0]["first_used_at"] is None
    assert serialize_run_tokens(MagicMock(), []) == []


# ── policies: exception audit does no pack lookup unless a transition is due ──
def _override(**kw):
    base = dict(rule_id="r1", disabled=True, action=None, reason="x", expires_at=None,
                use_audited_at=None, expiry_audited_at=None)
    base.update(kw)
    return SimpleNamespace(**base)


def test_audit_transitions_skips_pack_lookup_when_nothing_pending():
    now = datetime.now(timezone.utc)
    overrides = [
        _override(expires_at=now + timedelta(days=1)),                       # still active
        _override(expires_at=now - timedelta(days=1), expiry_audited_at=now),  # already audited
    ]
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = overrides
    with patch.object(ph, "_pack_rule_map") as pm, patch.object(ph, "_write_audit") as wa:
        ph._audit_exception_transitions(db, uuid.uuid4(), audit_use=False)
    pm.assert_not_called()
    wa.assert_not_called()


def test_audit_transitions_writes_expiry_once_with_single_pack_query():
    now = datetime.now(timezone.utc)
    o1 = _override(rule_id="r1", expires_at=now - timedelta(hours=1))
    o2 = _override(rule_id="r2", expires_at=now - timedelta(hours=2))
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = [o1, o2]
    rules = {"r1": ({"id": "r1", "action": "block"}, None), "r2": ({"id": "r2", "action": "block"}, None)}
    with patch.object(ph, "_pack_rule_map", return_value=rules) as pm, \
            patch.object(ph, "_write_audit") as wa:
        ph._audit_exception_transitions(db, uuid.uuid4(), audit_use=False)
    assert pm.call_count == 1
    assert wa.call_count == 2
    assert o1.expiry_audited_at is not None and o2.expiry_audited_at is not None


def test_pack_rule_map_matches_find_pack_rule():
    ws = uuid.uuid4()
    wp1, wp2 = MagicMock(), MagicMock()
    packs = {wp1: MagicMock(rules=[{"id": "a"}, {"id": "b"}]), wp2: MagicMock(rules=[{"id": "b"}, {"id": "c"}])}
    db = MagicMock()
    db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [wp1, wp2]
    with patch.object(ph, "_resolve_workspace_pack", side_effect=lambda _db, wp: packs[wp]):
        mapping = ph._pack_rule_map(db, ws)
        for rid in ("a", "b", "c", "zzz"):
            assert mapping.get(rid) == ph._find_pack_rule(db, ws, rid)


# ── team memory: synthesis throttled to once per hour per workspace ───────
def test_synth_due_throttles_per_workspace():
    team_memory._synth_last_run.clear()
    assert team_memory._synth_due("ws1") is True
    assert team_memory._synth_due("ws1") is False
    assert team_memory._synth_due("ws2") is True
    team_memory._synth_last_run["ws1"] -= team_memory._SYNTH_INTERVAL_S + 1
    assert team_memory._synth_due("ws1") is True


# ── discovery: filter + paging pushed into SQL ────────────────────────────
def _sql(inventory, under_guard, limit=10, offset=5):
    captured = {}

    def fake_all(self):
        captured["sql"] = str(self.statement.compile(dialect=postgresql.dialect()))
        return []

    with patch.object(Query, "all", fake_all):
        assert workspace_inventory_page(
            Session(), uuid.uuid4(), inventory=inventory, under_guard=under_guard,
            limit=limit, offset=offset) == []
    return captured["sql"]


def test_discovery_page_pushes_filters_and_paging_into_sql():
    sql = _sql("legacy", True)
    assert "LIMIT" in sql and "OFFSET" in sql
    assert "hook_event_id IS NOT NULL" in sql and "coalesce(discovered_agents.detection" in sql
    plain = _sql("all", None)
    assert "hook_event_id" not in plain.split("ORDER BY")[0].split("WHERE")[1]
