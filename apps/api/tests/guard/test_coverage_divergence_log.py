"""#1751 PR 4 — workspace_coverage_matrix logs divergence between the
hand-authored enforcement.<surface> string and derive_surface_status.

Purpose: telemetry for the #1750 Phase D cleanup — every divergence points
at a rule whose hand-authored metadata is stale. This test doesn't change
the return schema (that's a follow-up); it only proves the warn-log fires.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from app.modules.guard.coverage import workspace_coverage_matrix


def _installed_pack(slug: str = "conduct-fake", version: str = "1.0.0"):
    p = MagicMock()
    p.pack_slug = slug
    p.pinned_version = None
    return p


def _pack_object(rules, version="1.0.0", slug="conduct-fake"):
    obj = MagicMock()
    obj.slug = slug
    obj.version = version
    obj.rules = rules
    return obj


def _authored(surface_map: dict[str, str]) -> dict:
    """Minimum enforcement metadata dict validate_enforcement_metadata accepts."""
    base = {
        "version": 1,
        "proxy": "not_supported",
        "hook": "not_supported",
        "mcp": "not_supported",
        "runtime": "not_supported",
        "guarantee": "test",
        "requires": [],
        "known_limitations": [],
    }
    base.update(surface_map)
    return base


def _make_db(rules: list[dict]):
    db = MagicMock()
    # installed WorkspaceSkillPack query
    db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [
        _installed_pack(),
    ]
    # custom rules + overrides — return empty for both
    db.query.return_value.filter.return_value.all.return_value = []
    return db


def test_no_divergence_no_warning():
    """Agent-persona action-gate rule with hand-authored surface statuses
    that match derived reality → no warning."""
    rule = {
        "id": "action-only",
        "action": "block",
        "persona": "agent",
        "gates": ["action"],
        # Correct claims: proxy=not_supported (proxy doesn't do action gate),
        # mcp/hook/runtime=hard (they all do action gate).
        "enforcement": _authored({
            "proxy": "not_supported",
            "mcp": "hard",
            "hook": "hard",
            "runtime": "hard",
        }),
    }
    db = _make_db([rule])
    calls = []
    with patch(
        "app.modules.guard.coverage._get_pack",
        return_value=_pack_object([rule]),
    ), patch("app.modules.guard.coverage.validate_enforcement_metadata"), \
       patch("app.modules.guard.coverage.log.warning",
             side_effect=lambda event, **kw: calls.append((event, kw))):
        workspace_coverage_matrix(db, uuid.uuid4())

    assert not any(ev == "guard.coverage.status_divergence" for ev, _ in calls)


def test_hard_authored_but_derived_not_supported_logs():
    """Rule with `enforcement.proxy: 'hard'` but gates=['action'] can't
    actually be enforced on proxy → warn."""
    rule = {
        "id": "stale-hard",
        "action": "block",
        "persona": "agent",
        "gates": ["action"],
        "enforcement": _authored({"proxy": "hard"}),
    }
    db = _make_db([rule])
    calls = []
    with patch(
        "app.modules.guard.coverage._get_pack",
        return_value=_pack_object([rule]),
    ), patch("app.modules.guard.coverage.validate_enforcement_metadata"), \
       patch("app.modules.guard.coverage.log.warning",
             side_effect=lambda event, **kw: calls.append((event, kw))):
        workspace_coverage_matrix(db, uuid.uuid4())

    divergences = [kw for ev, kw in calls if ev == "guard.coverage.status_divergence"]
    proxy_divergence = next(d for d in divergences if d["surface"] == "proxy")
    assert proxy_divergence["rule_id"] == "stale-hard"
    assert proxy_divergence["authored"] == "hard"
    assert proxy_divergence["derived"] == "not_supported"


def test_conditional_authored_never_logs():
    """'conditional' and 'advisory' are deploy-caveat statuses that
    derive_surface_status doesn't model — skip them, don't warn."""
    rule = {
        "id": "conditional-rule",
        "action": "block",
        "persona": "agent",
        "gates": ["action"],
        "enforcement": _authored({
            "mcp": "conditional",   # deploy-caveat, should not trigger warn
            "hook": "hard",
            "runtime": "hard",
            "requires": ["agent calls guard_check"],
        }),
    }
    db = _make_db([rule])
    calls = []
    with patch(
        "app.modules.guard.coverage._get_pack",
        return_value=_pack_object([rule]),
    ), patch("app.modules.guard.coverage.validate_enforcement_metadata"), \
       patch("app.modules.guard.coverage.log.warning",
             side_effect=lambda event, **kw: calls.append((event, kw))):
        workspace_coverage_matrix(db, uuid.uuid4())

    assert not any(ev == "guard.coverage.status_divergence" for ev, _ in calls)


def test_return_shape_unchanged():
    """Non-goal in this PR: change what the API returns. Verify the
    existing keys still land."""
    rule = {
        "id": "shape-check",
        "action": "block",
        "persona": "agent",
        "gates": ["action"],
        "enforcement": _authored({"mcp": "hard"}),
    }
    db = _make_db([rule])
    with patch(
        "app.modules.guard.coverage._get_pack",
        return_value=_pack_object([rule]),
    ), patch("app.modules.guard.coverage.validate_enforcement_metadata"):
        matrix = workspace_coverage_matrix(db, uuid.uuid4())

    row = matrix[0]
    for key in ("proxy", "hook", "mcp", "runtime", "guarantee", "requires", "known_limitations"):
        assert key in row, f"expected key {key} still present"
