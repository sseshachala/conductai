"""Static regression checks for GLens's semantic intent bank (no DB, no LLM).

These enforce the contract described in `glens/intent_bank.py`: every intent
mapped to a tool must resolve to something the runtime can actually execute,
and write intents must line up with the write tools formatters.py expects to
handle as confirm-required drafts. Catches "prompt drift" style regressions
where an intent is added/renamed without updating its wiring.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve()
APPS_API = HERE.parent.parent
if str(APPS_API) not in sys.path:
    sys.path.insert(0, str(APPS_API))

from app.modules.glens.executor import Executor
from app.modules.glens.inference import _KNOWN_DISPATCH_TOOLS
from app.modules.glens.intent_bank import (
    INTENT_EXAMPLES,
    INTENT_TO_TOOL,
    WRITE_INTENTS,
)

# Tools handled directly by formatters.py's confirm-required draft path,
# never executed by Executor against the DB.
_WRITE_ONLY_TOOLS = {"create_guard_rule", "edit_guard_rule", "delete_guard_rule"}


def _executor_tool_names() -> set[str]:
    return {
        name[len("_tool_"):]
        for name in dir(Executor)
        if name.startswith("_tool_") and callable(getattr(Executor, name))
    }


def test_every_intent_has_examples():
    """Every intent must have at least one example phrase for embedding routing."""
    assert INTENT_EXAMPLES, "INTENT_EXAMPLES is empty — no intents registered for semantic routing"
    empty = [intent for intent, examples in INTENT_EXAMPLES.items() if not examples]
    assert not empty, f"Intents with no example phrases: {empty}"


def test_every_intent_has_multiple_paraphrases():
    """Each intent should have several paraphrase examples so routing is robust."""
    thin = {intent: len(examples) for intent, examples in INTENT_EXAMPLES.items() if len(examples) < 2}
    assert not thin, f"Intents with fewer than 2 example phrases: {thin}"


def test_intent_to_tool_covers_every_intent():
    """Every intent in the example bank must have a tool mapping."""
    missing = set(INTENT_EXAMPLES) - set(INTENT_TO_TOOL)
    assert not missing, f"Intents missing from INTENT_TO_TOOL: {missing}"


def test_no_orphan_tool_mappings():
    """INTENT_TO_TOOL must not reference intents that don't exist in the example bank."""
    orphans = set(INTENT_TO_TOOL) - set(INTENT_EXAMPLES)
    assert not orphans, f"INTENT_TO_TOOL has entries with no example phrases: {orphans}"


def test_every_mapped_tool_is_executable():
    """
    Every tool name in INTENT_TO_TOOL must resolve to either:
      - a real `_tool_*` method on Executor (DB-backed read), or
      - a known write-only tool handled by formatters.py's draft/confirm path.
    """
    executable = _executor_tool_names() | _WRITE_ONLY_TOOLS
    unresolvable = {
        intent: tool
        for intent, tool in INTENT_TO_TOOL.items()
        if tool not in executable
    }
    assert not unresolvable, f"Intents mapped to non-existent tools: {unresolvable}"


def test_write_intents_map_to_write_only_tools():
    """Every WRITE_INTENTS entry must map to a tool that needs confirmation before executing."""
    mismatched = {
        intent: INTENT_TO_TOOL.get(intent)
        for intent in WRITE_INTENTS
        if INTENT_TO_TOOL.get(intent) not in _WRITE_ONLY_TOOLS
    }
    assert not mismatched, f"WRITE_INTENTS mapped to non-write tools: {mismatched}"


def test_write_only_tools_are_all_flagged_as_write_intents():
    """No write tool should be reachable via an intent that isn't in WRITE_INTENTS."""
    unflagged = {
        intent: tool
        for intent, tool in INTENT_TO_TOOL.items()
        if tool in _WRITE_ONLY_TOOLS and intent not in WRITE_INTENTS
    }
    assert not unflagged, f"Write-capable intents missing from WRITE_INTENTS: {unflagged}"


def test_known_dispatch_tools_are_reachable_from_some_intent():
    """
    Every tool the fast single-call dispatch path knows about should be
    reachable via at least one semantic intent, so cheap routing can serve it
    without falling through to the LLM dispatch/planner.
    """
    mapped_tools = set(INTENT_TO_TOOL.values())
    unreachable = _KNOWN_DISPATCH_TOOLS - mapped_tools
    assert not unreachable, (
        f"Dispatch tools with no semantic intent mapping (semantic router can "
        f"never route directly to them): {unreachable}"
    )
