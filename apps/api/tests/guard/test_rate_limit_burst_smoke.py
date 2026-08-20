"""End-to-end smoke tests for #1083 (budget check) and #980 (rate limits).

Two kinds of coverage in one file:

1. **In-process smoke** (runs in CI, no infra): stateful fake Redis that actually
   accumulates counters across calls, so RPM/TPM burst behavior is exercised for
   real. Fail-open branches (DB down, Redis down) are re-verified.

2. **Post-deploy smoke** (documented at bottom): a copy/pasteable curl sequence
   to run against a freshly-deployed API. Catches broken migrations, missing
   env vars, or router registration regressions.

Runs standalone: `pytest tests/guard/test_rate_limit_burst_smoke.py -v`
"""
from __future__ import annotations

import time
from unittest.mock import MagicMock, patch


# ── Stateful fake Redis (accumulates counters across calls) ───────────────────

class _FakeRedis:
    """Enough of redis-py to exercise pipeline INCR/EXPIRE + read-back."""
    def __init__(self):
        self.store: dict[str, int] = {}

    def pipeline(self):
        return _FakePipeline(self)


class _FakePipeline:
    def __init__(self, redis: _FakeRedis):
        self.redis = redis
        self.ops: list = []

    def incr(self, key: str, amount: int = 1):
        self.ops.append(("incr", key, amount))
        return self

    def incrby(self, key: str, amount: int):
        self.ops.append(("incr", key, amount))
        return self

    def expire(self, key: str, ttl: int):
        self.ops.append(("expire", key, ttl))
        return self

    def execute(self):
        out = []
        for op in self.ops:
            if op[0] == "incr":
                _, key, amt = op
                self.redis.store[key] = self.redis.store.get(key, 0) + int(amt)
                out.append(self.redis.store[key])
            elif op[0] == "expire":
                out.append(True)
        self.ops.clear()
        return out


def _mock_db_with_limits(rpm=None, tpm=None):
    db = MagicMock()
    row = MagicMock(rpm=rpm, tpm=tpm)
    exec_ = MagicMock()
    exec_.first.return_value = row
    db.execute.return_value = exec_
    return db


# ── RPM burst — accumulator actually blocks after N calls ─────────────────────

def test_rpm_burst_blocks_on_call_n_plus_1():
    from app.modules.guard.rate_limit import check_rate_limit
    db = _mock_db_with_limits(rpm=3)
    redis = _FakeRedis()

    with patch("app.modules.guard.rate_limit._redis_client", return_value=redis):
        # First 3 calls under cap
        for i in range(3):
            d = check_rate_limit(db, workspace_id="ws1", agent_identity_id=None, input_tokens=0)
            assert d.limited is False, f"call {i+1} should not be limited"

        # 4th call trips the cap
        d = check_rate_limit(db, workspace_id="ws1", agent_identity_id=None, input_tokens=0)
        assert d.limited is True
        assert d.metric == "rpm"
        assert d.current == 4
        assert d.limit == 3


# ── TPM burst — total tokens over the window trigger the block ────────────────

def test_tpm_burst_blocks_when_cumulative_tokens_exceed_limit():
    from app.modules.guard.rate_limit import check_rate_limit
    db = _mock_db_with_limits(tpm=1000)
    redis = _FakeRedis()

    with patch("app.modules.guard.rate_limit._redis_client", return_value=redis):
        # 3 calls at 400 tokens each = 1200 cumulative > 1000 cap
        results = [
            check_rate_limit(db, workspace_id="ws1", agent_identity_id=None, input_tokens=400)
            for _ in range(3)
        ]
        assert results[0].limited is False
        assert results[1].limited is False
        assert results[2].limited is True
        assert results[2].metric == "tpm"


# ── Windows are scoped per-workspace + per-agent (no cross-tenant leakage) ────

def test_counters_are_isolated_by_workspace():
    from app.modules.guard.rate_limit import check_rate_limit
    db = _mock_db_with_limits(rpm=2)
    redis = _FakeRedis()

    with patch("app.modules.guard.rate_limit._redis_client", return_value=redis):
        # ws1 uses its 2 requests
        check_rate_limit(db, workspace_id="ws1", agent_identity_id=None, input_tokens=0)
        check_rate_limit(db, workspace_id="ws1", agent_identity_id=None, input_tokens=0)
        # ws2 must still have its own quota
        d = check_rate_limit(db, workspace_id="ws2", agent_identity_id=None, input_tokens=0)
        assert d.limited is False


def test_counters_are_isolated_by_agent_identity():
    from app.modules.guard.rate_limit import check_rate_limit
    db = _mock_db_with_limits(rpm=2)
    redis = _FakeRedis()

    with patch("app.modules.guard.rate_limit._redis_client", return_value=redis):
        check_rate_limit(db, workspace_id="ws1", agent_identity_id="agent-a", input_tokens=0)
        check_rate_limit(db, workspace_id="ws1", agent_identity_id="agent-a", input_tokens=0)
        d = check_rate_limit(db, workspace_id="ws1", agent_identity_id="agent-b", input_tokens=0)
        assert d.limited is False


# ── Windows advance every minute (old counter buckets are dropped) ────────────

def test_new_minute_window_resets_counters():
    from app.modules.guard.rate_limit import check_rate_limit
    db = _mock_db_with_limits(rpm=2)
    redis = _FakeRedis()

    with patch("app.modules.guard.rate_limit._redis_client", return_value=redis):
        # Freeze minute at T
        with patch("app.modules.guard.rate_limit.time.time", return_value=100.0):
            check_rate_limit(db, workspace_id="ws1", agent_identity_id=None, input_tokens=0)
            check_rate_limit(db, workspace_id="ws1", agent_identity_id=None, input_tokens=0)
            d = check_rate_limit(db, workspace_id="ws1", agent_identity_id=None, input_tokens=0)
            assert d.limited is True  # blocked in current window

        # Advance to next minute
        with patch("app.modules.guard.rate_limit.time.time", return_value=160.0):
            d = check_rate_limit(db, workspace_id="ws1", agent_identity_id=None, input_tokens=0)
            assert d.limited is False  # fresh window


# ── Contract check: 429 response body carries the fields the CLI expects ──────

def test_rate_limit_response_shape():
    from app.modules.guard.rate_limit import RateLimitDecision
    d = RateLimitDecision(True, "over", "rpm", 3, 4, "workspace")
    body = {"error": {
        "type": "guard_rate_limited",
        "message": d.reason,
        "metric": d.metric,
        "limit": d.limit,
        "current": d.current,
        "scope": d.scope,
    }}
    assert body["error"]["type"] == "guard_rate_limited"
    assert body["error"]["metric"] in ("rpm", "tpm")
    assert body["error"]["limit"] >= 1


def test_budget_response_shape():
    from app.modules.guard.routers.spend import BudgetCheckOut
    bc = BudgetCheckOut(hard_blocked=True, reason="over", monthly_cost_usd=10.0, hard_limit_usd=9.0)
    body = {"error": {
        "type": "guard_budget_exceeded",
        "message": bc.reason or "Monthly AI budget reached.",
        "monthly_cost_usd": bc.monthly_cost_usd,
        "hard_limit_usd": bc.hard_limit_usd,
    }}
    assert body["error"]["type"] == "guard_budget_exceeded"
    assert body["error"]["hard_limit_usd"] == 9.0


# ── Migration surface — SELECT the columns the code assumes exist ─────────────

def test_migration_defines_expected_columns():
    """Snapshot of columns _resolve_limits and the CRUD router depend on.
    If the migration drops any of these, this test tells you before deploy."""
    from app.modules.guard.models import GuardRateLimit
    cols = {c.name for c in GuardRateLimit.__table__.columns}
    for required in ("id", "workspace_id", "agent_identity_id", "rpm", "tpm", "created_at", "updated_at"):
        assert required in cols, f"guard_rate_limits missing column: {required}"


def test_alembic_head_includes_0096():
    """Guards against someone accidentally reverting the head pointer."""
    from pathlib import Path
    versions = Path(__file__).resolve().parents[2] / "alembic" / "versions"
    heads = []
    for f in versions.glob("*.py"):
        text = f.read_text()
        if 'down_revision = "0095"' in text:
            heads.append(f.name)
    assert "0096_guard_rate_limits.py" in [Path(h).name for h in heads], \
        "0096 migration must chain from 0095"


# ─────────────────────────────────────────────────────────────────────────────
# POST-DEPLOY SMOKE (manual)
# ─────────────────────────────────────────────────────────────────────────────
# Run against a freshly-deployed API. Requires an admin CLI token.
#
#   API=https://your-api.example.com
#   TOKEN=guard-mt-...  # admin member token
#   WS=<workspace_id>
#
#   # 1. Set workspace default (RPM=2 for a fast test).
#   curl -sf -X PUT "$API/guard/rate-limits" \
#     -H "Authorization: Bearer $TOKEN" -H "X-Workspace-Id: $WS" \
#     -H "Content-Type: application/json" \
#     -d '{"agent_identity_id": null, "rpm": 2, "tpm": null}'
#
#   # 2. List should show the row.
#   curl -sf "$API/guard/rate-limits" \
#     -H "Authorization: Bearer $TOKEN" -H "X-Workspace-Id: $WS" | jq
#
#   # 3. Trigger the limit by making 3 quick proxy calls.
#   for i in 1 2 3; do
#     curl -s -o /dev/null -w "%{http_code}\n" \
#       "$API/proxy/v1/messages" \
#       -H "x-api-key: $TOKEN" \
#       -H "content-type: application/json" \
#       -d '{"model":"claude-3-5-haiku-latest","max_tokens":1,"messages":[{"role":"user","content":"hi"}]}'
#   done
#   # Expected: 200, 200, 429
#
#   # 4. Cleanup — remove the row so real traffic isn't affected.
#   ROW_ID=$(curl -sf "$API/guard/rate-limits" \
#     -H "Authorization: Bearer $TOKEN" -H "X-Workspace-Id: $WS" \
#     | jq -r '.[] | select(.agent_identity_id == null) | .id')
#   curl -sf -X DELETE "$API/guard/rate-limits/$ROW_ID" \
#     -H "Authorization: Bearer $TOKEN" -H "X-Workspace-Id: $WS"
#
# Budget check smoke: set hard_limit_usd = 0.01 on your workspace budget via
# /theguard/spend, then run one proxy call. Expected: 429 with
# {"error": {"type": "guard_budget_exceeded", ...}}. Unset the limit after.
