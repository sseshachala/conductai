"""PEP capability registry (#1751 PR 1).

Each Policy Enforcement Point (MCP tool call, LLM proxy egress, runtime
block boundary, CLI hook) declares which enforcement gates it can evaluate.
This registry is the source of truth Property 8 (of the pinnable Guard
architecture doc, §5) refers to as "PEP `provides_capabilities` declarations
machine-verified in CI."

The drift test in tests/guard/test_pep_registry.py locks the shape against
the architecture doc — a PEP silently changing what it enforces will fail
the test until either the code or the doc is updated deliberately.

Downstream consumers:
    derive_surface_status(rule, surface)     — #1751 PR 2
    pack_coverage_matrix(pack_slug)          — #1751 PR 3
    Policies UI verified badges              — #1750 Phase B Slice 2 (#1755)
"""
from __future__ import annotations

from app.modules.guard.enforcement import GATES

# The four surfaces documented today in apps/api/app/modules/guard/routers/
# and packages/conduct-cli/. Lens is a well-behaved caller through MCP + proxy
# per docs/guard/architecture.md §8 — no separate row.
Surface = str  # one of PEP_CAPABILITIES.keys()

PEP_CAPABILITIES: dict[Surface, frozenset[str]] = {
    "mcp":     frozenset({"action"}),
    "proxy":   frozenset({"prompt", "response"}),
    "runtime": frozenset({"action"}),
    "hook":    frozenset({"action"}),  # CLI pre-tool-use hook
}


def pep_provides(surface: str) -> frozenset[str]:
    """Return the gates a PEP declares it can evaluate. Unknown surfaces
    return the empty set — treat as `not_supported`."""
    return PEP_CAPABILITIES.get(surface, frozenset())


def all_surfaces() -> tuple[str, ...]:
    """Ordered surface list — stable projection order for coverage matrices."""
    return ("mcp", "proxy", "runtime", "hook")


# Every declared gate must be a member of the locked GATES enum. Ratchet
# enforced at import: adding a new value to a PEP set that isn't in GATES
# fails fast at process start, not at run time.
for _surface, _gates in PEP_CAPABILITIES.items():
    _unknown = _gates - set(GATES)
    if _unknown:
        raise ValueError(
            f"PEP_CAPABILITIES['{_surface}'] declares unknown gates {sorted(_unknown)} "
            f"outside the locked GATES enum {GATES}"
        )
