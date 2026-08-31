"""Lens regression canon — structural ratchets + coverage manifest.

# Why this file exists

The vibe-code audit (#1482) recommended handcrafted regression tests for
every "must-never-break" behavior. Working through the canon list in #1484
revealed that recent P0 fixes already ship their own regression tests
per-PR — new handcrafted tests would duplicate. Instead this file:

1. Documents the canon as a coverage manifest — which behavior lives in
   which test file, or GAP if uncovered.
2. Adds structural ratchets that catch classes of regression the per-PR
   tests miss (silent de-registration, drift in the open-world set, etc.).

Delete an item from the manifest only after confirming the covering test
still exists and still exercises the behavior end-to-end.

# Coverage manifest

| # | Canon behavior                                                    | Test file                                        |
|---|-------------------------------------------------------------------|--------------------------------------------------|
| 1 | Confirm envelope surfaces on chat/stream `done` event (#1476)     | tests/glens/test_extract_confirm_envelope.py     |
| 2 | Confirm envelope extracts from Anthropic tool_result shape (#1478)| tests/glens/test_extract_confirm_envelope.py     |
| 3 | Any authorized human can decide agent-proposed action (#1479)     | tests/glens/test_actor_chat_confirm.py           |
| 4 | AGENT badge → agent identity page link (#1474)                    | GAP — frontend only, not in pytest scope         |
| 5 | Tool-call pairing under partial streaming (#1343)                 | tests/glens/test_resolve_tools_guarded.py        |
| 6 | "View run" link surfaces post-confirm dispatch (#1475)            | GAP — frontend surface                           |
| 7 | Tool call dispatch → correct handler resolved                     | tests/tools/test_lens_registry_canon.py          |
| 8 | Tool call schema validation rejects malformed input               | GAP — dispatch-layer test not yet written        |
| 9 | Session persistence: reload thread shows history                  | tests/glens/test_chat_feedback_endpoint.py (partial) |
|10 | Multi-provider routing: env-var swap changes provider             | tests/glens/test_gateway_agent_identity.py (partial) |
|11 | Guard integration: per-tool gate blocks correctly                 | tests/glens/test_resolve_tools_guarded.py        |
|12 | Actor substrate: chat → run → HITL → resume                       | tests/glens/test_actor_substrate.py              |
|13 | GLens save-as-metric (semantic layer)                             | GAP — feature parked; #1027                      |
|14 | Agent identity resolution: system:lens → real cond_agt_lens_*     | tests/glens/test_gateway_agent_identity.py       |
|15 | Skill labels render on tool cards                                 | GAP — frontend                                   |
|16 | Attachment upload → downloadable in transcript                    | GAP — frontend                                   |
|17 | Audit event linkage: every tool call has run + agent + user       | GAP — integration test not yet written           |
|18 | Empty state: 0-blocks renders without crash                       | GAP — frontend                                   |
|19 | Long-context handling: >8k tokens doesn't drop tools              | GAP — hard to unit-test                          |
|20 | Registry parametrized: every tool loads + smokes                  | tests/tools/test_lens_registry_canon.py          |

Backend GAPs (#8, #17) are follow-up work — each earns a filed issue when
picked up. Frontend GAPs need Playwright coverage (out of scope for pytest).
"""
from __future__ import annotations

from app.tools.registrations.lens import _TOOLS as LENS_TOOLS
from app.tools.registry import default_registry


# ── Structural ratchets ────────────────────────────────────────────────────
# These catch classes of regression the per-PR tests can't: someone silently
# unregisters a tool, adds a network call to an existing tool, or removes
# actor tagging on a mutating action.

# Snapshot as-of 2026-08-30. Ratchet upward as tools are added, never down.
# A drop = someone removed a tool; investigate before merging.
_LENS_TOOL_COUNT_FLOOR = 70

# Actor-tagged tools must go through require_confirmation() — the substrate
# that lets any authorized human approve. Count floor guards against
# accidental de-tagging that would bypass HITL.
_ACTOR_TOOL_COUNT_FLOOR = 4

# The exact set of tools that hit the network. Adding a new open_world tool
# is a security-review decision — this ratchet forces the discussion.
_KNOWN_OPEN_WORLD_TOOLS = frozenset({
    "get_governance_narrative",
    "search_knowledge",
    "search_memory",
    "search_sessions",
})


def test_lens_tool_count_meets_floor():
    """Silent de-registration of a Lens tool = regression. Update the floor
    when you intentionally add tools; never reduce it."""
    lens_tools = default_registry.list(tag="lens")
    assert len(lens_tools) >= _LENS_TOOL_COUNT_FLOOR, (
        f"Lens tool count dropped to {len(lens_tools)} "
        f"(floor is {_LENS_TOOL_COUNT_FLOOR}) — a tool was silently removed"
    )


def test_actor_tool_count_meets_floor():
    """Every actor tool routes through the confirmation substrate. Fewer
    actor tools than the floor = a mutating action lost its HITL gate."""
    actor_tools = [t for t in LENS_TOOLS if "actor" in t.tags]
    assert len(actor_tools) >= _ACTOR_TOOL_COUNT_FLOOR, (
        f"Actor tool count dropped to {len(actor_tools)} "
        f"(floor is {_ACTOR_TOOL_COUNT_FLOOR}) — HITL coverage regressed"
    )


def test_open_world_set_is_exactly_the_known_four():
    """Every network-calling tool has to be in the reviewed set. Additions
    require a security review. This test fires when someone flips
    open_world=True on a new tool without updating the frozenset."""
    actual = frozenset(t.name for t in LENS_TOOLS if t.annotations.open_world)
    unexpected = actual - _KNOWN_OPEN_WORLD_TOOLS
    missing = _KNOWN_OPEN_WORLD_TOOLS - actual
    assert not unexpected, f"New open_world tools without review: {sorted(unexpected)}"
    assert not missing, f"Expected open_world tools no longer marked: {sorted(missing)}"


def test_every_actor_tool_impl_routes_through_actor_helper():
    """Actor tools use `_actor_impl(name)` which stamps the impl __name__
    with 'actor_impl_'. Two exceptions are the meta-tools introduced in
    #1467 that operate ON approval requests (confirm / cancel) rather than
    propose them — they intentionally skip require_confirmation."""
    META_ACTOR_TOOLS = {"confirm_pending_action", "cancel_pending_action"}
    for t in LENS_TOOLS:
        if "actor" not in t.tags or t.name in META_ACTOR_TOOLS:
            continue
        impl_name = getattr(t.impl, "__name__", "")
        assert impl_name.startswith("actor_impl_"), (
            f"actor tool {t.name!r} impl is {impl_name!r} — must route through _actor_impl()"
        )


def test_no_tool_advertises_both_read_only_and_destructive():
    """A tool cannot be both. Contradictory annotations mislead the model
    into calling destructive tools thinking they're safe."""
    for t in LENS_TOOLS:
        assert not (t.annotations.read_only and t.annotations.destructive), (
            f"{t.name}: annotations declare both read_only AND destructive"
        )


def test_every_tool_declares_input_schema_object():
    """MCP transport expects `inputSchema.type == 'object'` for every tool.
    Non-object schemas break the JSON-RPC tools/list projection."""
    for t in LENS_TOOLS:
        assert t.input_schema.get("type") == "object", (
            f"{t.name}: input_schema.type is {t.input_schema.get('type')!r}, must be 'object'"
        )
