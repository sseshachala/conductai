"""#1751 PR 1 — PEP capability registry drift test.

Locks the mapping against docs/guard/architecture.md §8. A PEP silently
changing what it enforces here without also updating the doc fails this
test — deliberate change is required to add or remove a declared gate.
"""
from __future__ import annotations

from app.modules.guard.enforcement import GATES
from app.modules.guard.pep_registry import (
    PEP_CAPABILITIES,
    all_surfaces,
    pep_provides,
)


def test_all_declared_gates_are_in_the_locked_enum():
    """Property 5 / reviewer edit 2: only [action, prompt, response] exist.
    A PEP declaring anything else means either the enum needs to grow (which
    itself requires a schema decision — see architecture.md Property 5) or
    the PEP was miswired."""
    valid = set(GATES)
    for surface, gates in PEP_CAPABILITIES.items():
        assert gates.issubset(valid), (
            f"{surface} declares gates {gates - valid} outside {GATES}"
        )


def test_pep_capabilities_match_architecture_doc_v1():
    """Snapshot of docs/guard/architecture.md §8 as of #1737 merge.
    Changing this table means the doc + this snapshot both update, with
    the reviewer explicitly signing off on the new surface × gate matrix."""
    expected = {
        "mcp":     frozenset({"action"}),
        "proxy":   frozenset({"prompt", "response"}),
        "runtime": frozenset({"action"}),
        "hook":    frozenset({"action"}),
    }
    assert PEP_CAPABILITIES == expected


def test_pep_provides_returns_declared_set():
    assert pep_provides("proxy") == frozenset({"prompt", "response"})
    assert pep_provides("mcp") == frozenset({"action"})


def test_pep_provides_unknown_surface_is_empty_set():
    """Unknown PEP → treated as not_supported for every gate. Downstream
    derive_surface_status relies on this fallback."""
    assert pep_provides("nonexistent") == frozenset()
    assert pep_provides("") == frozenset()


def test_all_surfaces_ordering_is_stable():
    """derive_surface_status callers iterate this list — stable order matters
    for UI badge rendering and audit-row column alignment."""
    surfaces = all_surfaces()
    assert surfaces == ("mcp", "proxy", "runtime", "hook")
    assert set(surfaces) == set(PEP_CAPABILITIES.keys())


def test_every_gate_is_covered_by_at_least_one_pep():
    """Sanity: the locked GATES enum should not contain a gate no PEP
    can enforce. If this fails, either a PEP declaration is missing or
    the enum has a dead value."""
    covered: set[str] = set()
    for gates in PEP_CAPABILITIES.values():
        covered.update(gates)
    missing = set(GATES) - covered
    assert not missing, f"gates {sorted(missing)} have no PEP that provides them"
