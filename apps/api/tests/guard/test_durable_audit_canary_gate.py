"""#1995 canary rollout — deterministic per-workspace enable check.

Locks the three properties the rollout process depends on:

- Global kill switch overrides everything below.
- Allowlist wins over pct (dark-launch works at pct=0).
- Bucketing is deterministic (same workspace, same pct → same answer)
  so a workspace never flaps between the durable and legacy writer.
"""
from __future__ import annotations

import pytest

from app.core.config import Settings


def _s(**overrides) -> Settings:
    """Build a Settings snapshot without importing the app singleton so
    each test starts from a clean slate. All fields default to whatever
    the class declares; only the fields under test are overridden."""
    return Settings(**overrides)


def test_global_flag_off_disables_everything():
    """Kill switch beats allowlist + pct=100."""
    s = _s(
        guard_use_durable_audit=False,
        guard_durable_audit_rollout_pct=100,
        guard_durable_audit_allowlist="ws-1,ws-2",
    )
    assert s.durable_audit_enabled_for("ws-1") is False
    assert s.durable_audit_enabled_for("ws-anything") is False


def test_allowlist_wins_over_zero_pct():
    """Dark-launch: pct=0 but allowlisted workspace still gets the
    durable path. This is how internal test workspaces get the feature
    before any percentage rollout starts."""
    s = _s(
        guard_use_durable_audit=True,
        guard_durable_audit_rollout_pct=0,
        guard_durable_audit_allowlist="ws-canary",
    )
    assert s.durable_audit_enabled_for("ws-canary") is True
    assert s.durable_audit_enabled_for("ws-not-listed") is False


def test_full_rollout_enables_all_workspaces():
    """pct=100 always returns True (no hash roundtrip needed)."""
    s = _s(
        guard_use_durable_audit=True,
        guard_durable_audit_rollout_pct=100,
    )
    for ws in ("a", "b", "c", "d", "e"):
        assert s.durable_audit_enabled_for(ws) is True


def test_bucketing_is_deterministic():
    """Same workspace + same pct MUST return the same answer across
    repeated calls — this is the invariant that stops a workspace from
    flapping between the two writer paths mid-session."""
    s = _s(guard_use_durable_audit=True, guard_durable_audit_rollout_pct=25)
    ws = "550e8400-e29b-41d4-a716-446655440000"
    first = s.durable_audit_enabled_for(ws)
    for _ in range(20):
        assert s.durable_audit_enabled_for(ws) is first


def test_bumping_pct_only_moves_workspaces_across_the_line():
    """A workspace enabled at pct=10 must stay enabled at pct=20, 30, ...,
    100. Bumping pct never *removes* workspaces from the durable path."""
    ws = "workspace-under-test"
    prior = False
    for pct in (0, 1, 5, 10, 25, 50, 75, 100):
        s = _s(guard_use_durable_audit=True, guard_durable_audit_rollout_pct=pct)
        enabled = s.durable_audit_enabled_for(ws)
        if prior:
            assert enabled is True, (
                f"workspace at pct={pct} regressed to disabled after being enabled "
                f"at a lower pct — bucketing is not monotonic"
            )
        prior = enabled or prior


def test_pct_approximately_matches_proportion_at_scale():
    """Loose sanity: bucketing should distribute roughly evenly. Not a
    statistical test — just catches a broken hash or an off-by-one that
    lands everyone in the same bucket.

    Uses 1000 workspace ids and asserts pct=50 enables 40–60% of them.
    """
    s = _s(guard_use_durable_audit=True, guard_durable_audit_rollout_pct=50)
    ids = [f"ws-{i:08d}" for i in range(1000)]
    enabled = sum(1 for w in ids if s.durable_audit_enabled_for(w))
    assert 400 <= enabled <= 600, (
        f"pct=50 enabled {enabled}/1000 workspaces — hash bucketing "
        f"looks skewed or broken"
    )


def test_allowlist_trims_whitespace_and_ignores_empty_entries():
    """Env var strings often arrive with stray whitespace or an extra
    trailing comma. Don't turn ``",ws-1, ws-2,"`` into three
    slightly-wrong lookups — normalize on parse."""
    s = _s(
        guard_use_durable_audit=True,
        guard_durable_audit_allowlist=" , ws-1 , ws-2,",
        guard_durable_audit_rollout_pct=0,
    )
    ids = s.durable_audit_allowlist_ids()
    assert ids == frozenset({"ws-1", "ws-2"})
    assert s.durable_audit_enabled_for("ws-1") is True
    assert s.durable_audit_enabled_for("") is False


def test_empty_allowlist_is_empty_set():
    s = _s(guard_use_durable_audit=True, guard_durable_audit_allowlist="")
    assert s.durable_audit_allowlist_ids() == frozenset()
