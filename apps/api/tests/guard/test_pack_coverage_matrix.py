"""#1751 PR 3 — pack_coverage_matrix.

Aggregates rule counts per PEP surface × gate for a single pack. Feeds the
pack-detail coverage table on the Policies UI (Slice 2 of #1750 Phase B).
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.modules.guard.coverage import pack_coverage_matrix


def _pack(rules: list[dict], version: str = "1.0.0") -> MagicMock:
    p = MagicMock()
    p.rules = rules
    p.version = version
    return p


def test_missing_pack_returns_empty_shape():
    db = MagicMock()
    with patch("app.modules.guard.coverage._get_pack", return_value=None):
        out = pack_coverage_matrix(db, "conduct-fake")
    assert out["pack"] == "conduct-fake"
    assert out["version"] is None
    assert out["total_rules"] == 0
    for surface, counts in out["by_surface"].items():
        assert counts == {"hard": 0, "not_supported": 0}
    for gate, n in out["by_gate"].items():
        assert n == 0


def test_pure_action_pack_covers_mcp_runtime_hook_not_proxy():
    pack = _pack([
        {"id": "r1", "gates": ["action"]},
        {"id": "r2", "gates": ["action"]},
    ])
    with patch("app.modules.guard.coverage._get_pack", return_value=pack):
        out = pack_coverage_matrix(MagicMock(), "conduct-base")

    assert out["total_rules"] == 2
    assert out["by_gate"]["action"] == 2
    assert out["by_gate"]["prompt"] == 0
    assert out["by_gate"]["response"] == 0
    assert out["by_surface"]["mcp"] == {"hard": 2, "not_supported": 0}
    assert out["by_surface"]["runtime"] == {"hard": 2, "not_supported": 0}
    assert out["by_surface"]["hook"] == {"hard": 2, "not_supported": 0}
    assert out["by_surface"]["proxy"] == {"hard": 0, "not_supported": 2}


def test_proxy_gate_pack_covers_only_proxy():
    pack = _pack([
        {"id": "prompt-1", "gates": ["prompt"]},
        {"id": "resp-1",   "gates": ["response"]},
    ])
    with patch("app.modules.guard.coverage._get_pack", return_value=pack):
        out = pack_coverage_matrix(MagicMock(), "conduct-proxy-secrets")

    assert out["by_gate"] == {"action": 0, "prompt": 1, "response": 1}
    assert out["by_surface"]["proxy"] == {"hard": 2, "not_supported": 0}
    assert out["by_surface"]["mcp"] == {"hard": 0, "not_supported": 2}


def test_mixed_dual_gate_rule_counts_toward_every_matching_gate():
    """A rule declaring [action, prompt] counts once per gate in by_gate,
    and shows 'hard' on every surface that provides ANY of its gates."""
    pack = _pack([{"id": "dual", "gates": ["action", "prompt"]}])
    with patch("app.modules.guard.coverage._get_pack", return_value=pack):
        out = pack_coverage_matrix(MagicMock(), "conduct-hipaa")

    assert out["by_gate"] == {"action": 1, "prompt": 1, "response": 0}
    assert out["by_surface"]["mcp"] == {"hard": 1, "not_supported": 0}
    assert out["by_surface"]["proxy"] == {"hard": 1, "not_supported": 0}


def test_version_is_reported_from_the_pack_object():
    pack = _pack([{"id": "r", "gates": ["action"]}], version="2.3.1")
    with patch("app.modules.guard.coverage._get_pack", return_value=pack):
        out = pack_coverage_matrix(MagicMock(), "conduct-hipaa")
    assert out["version"] == "2.3.1"


def test_legacy_rule_without_gates_still_counts():
    """Rules with only persona (not gates) get counted via derive_gates."""
    pack = _pack([
        {"id": "legacy-agent", "persona": "agent"},
        {"id": "legacy-proxy", "persona": "proxy"},
    ])
    with patch("app.modules.guard.coverage._get_pack", return_value=pack):
        out = pack_coverage_matrix(MagicMock(), "conduct-base")

    assert out["total_rules"] == 2
    assert out["by_gate"]["action"] == 1
    assert out["by_gate"]["prompt"] == 1
    assert out["by_surface"]["mcp"]["hard"] == 1
    assert out["by_surface"]["proxy"]["hard"] == 1
