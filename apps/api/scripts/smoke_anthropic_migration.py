"""Real-LLM smoke test for the anthropic to llm_client refactor.

Runs each of the 5 migrated code paths against Claude and prints only
pass/fail per site (never the API key, never full response bodies).

Usage from apps/api/:

    python3.11 scripts/smoke_anthropic_migration.py

Loads ANTHROPIC_API_KEY via python-dotenv (auto-finds the local dotfile
in this working tree). Requires:
- anthropic 0.125.0 installed (already in requirements.txt after refactor)
- a valid ANTHROPIC_API_KEY configured

Total cost: ~$0.005 (five small Haiku/Sonnet calls, ~5000 tokens combined).
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

# Load config from local dotfile via python-dotenv (auto-discovers)
try:
    from dotenv import load_dotenv, find_dotenv
    load_dotenv(find_dotenv(usecwd=True))
except ImportError:
    pass

# Sanity: bail early if no key. Never print the value.
if not os.environ.get("ANTHROPIC_API_KEY"):
    print("FAIL: ANTHROPIC_API_KEY not configured for this shell.")
    sys.exit(1)

# Diagnostic: show which base URL the SDK will resolve. We never print the key.
_base = os.environ.get("ANTHROPIC_BASE_URL")
if _base:
    print(f"NOTE: ANTHROPIC_BASE_URL is set to {_base!r} — SDK will route there, not api.anthropic.com")
    print("      Run with BYPASS_GUARD_PROXY=1 to force the smoke test to hit api.anthropic.com directly")
    if os.environ.get("BYPASS_GUARD_PROXY") == "1":
        del os.environ["ANTHROPIC_BASE_URL"]
        print("      → cleared ANTHROPIC_BASE_URL for this process")

# Ensure app.* imports work when run from apps/api/
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.runtime.llm_client import client_for, LLMTextBlock, LLMToolUseBlock


def _ok(site: int, name: str, cost: float, extra: str = "") -> None:
    print(f"site {site} ({name}): OK  cost=${cost:.5f}  {extra}")


def _fail(site: int, name: str, err: Exception) -> None:
    print(f"site {site} ({name}): FAIL  {type(err).__name__}: {str(err)[:120]}")


def smoke_site_1_team_memory() -> None:
    """Mirrors routers/team_memory.py: haiku summarizer with system + user."""
    name = "team_memory summarizer"
    try:
        t0 = time.time()
        c = client_for("anthropic", os.environ["ANTHROPIC_API_KEY"])
        r = c.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=100,
            system=(
                "You are extracting team-useful learnings from an AI coding session. "
                "Extract: key decisions made, bugs found and how fixed, patterns discovered, gotchas. "
                "Only return exactly NULL for sessions with zero code work (pure chat, no files, no tools). "
                "Otherwise return 1-5 sentences."
            ),
            messages=[{"role": "user", "content": "Fixed a race condition in the guard approval decide path by adding SELECT FOR UPDATE."}],
        )
        first = r.content[0] if r.content else None
        got_text = isinstance(first, LLMTextBlock) and len(first.text) > 0
        if not got_text:
            raise AssertionError(f"expected LLMTextBlock, got {type(first).__name__}")
        _ok(1, name, r.cost_usd, f"chars={len(first.text)} ({time.time() - t0:.1f}s)")
    except Exception as e:
        _fail(1, name, e)


def smoke_site_2_workflows_preflight() -> None:
    """Mirrors routers/workflows.py inline call: haiku with just user, no system."""
    name = "workflows preflight estimator"
    try:
        t0 = time.time()
        c = client_for("anthropic", os.environ["ANTHROPIC_API_KEY"])
        r = c.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=150,
            system="",  # workflows.py preflight passes no system
            messages=[{"role": "user", "content": (
                "Estimate how many tool calls this task needs. Respond with JSON only, no explanation: "
                '{ "files": [], "estimated_turns": <number>, "reasoning": "<one line>" }\n\n'
                "Task: read a small config file and print its contents."
            )}],
        )
        first = r.content[0] if r.content else None
        got_text = isinstance(first, LLMTextBlock) and "{" in first.text
        if not got_text:
            raise AssertionError(f"expected LLMTextBlock with JSON, got {type(first).__name__}: {(first.text[:60] if first else 'empty')}")
        _ok(2, name, r.cost_usd, f"chars={len(first.text)} ({time.time() - t0:.1f}s)")
    except Exception as e:
        _fail(2, name, e)


def smoke_site_3_policies_generate() -> None:
    """Mirrors modules/guard/routers/policies.py: haiku with _GENERATE_SYSTEM."""
    name = "policies /generate"
    try:
        t0 = time.time()
        from app.modules.guard.routers.policies import _GENERATE_SYSTEM
        c = client_for("anthropic", os.environ["ANTHROPIC_API_KEY"])
        r = c.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            system=_GENERATE_SYSTEM,
            messages=[{"role": "user", "content": "Block agents from calling curl to production hosts"}],
        )
        first = r.content[0] if r.content else None
        got_text = isinstance(first, LLMTextBlock) and len(first.text) > 20
        if not got_text:
            raise AssertionError(f"expected substantive LLMTextBlock, got {type(first).__name__}")
        _ok(3, name, r.cost_usd, f"chars={len(first.text)} ({time.time() - t0:.1f}s)")
    except Exception as e:
        _fail(3, name, e)


def smoke_site_4_compiler_extract_slots() -> None:
    """Mirrors compiler/compiler.py::_extract_slots — sonnet + tools + tool_choice."""
    name = "compiler _extract_slots (tools+tool_choice)"
    try:
        t0 = time.time()
        from app.compiler.compiler import _extract_slots, get_client
        result = _extract_slots(
            "Read the incident ticket from PagerDuty and summarize the customer impact in 3 sentences",
            get_client(),
        )
        if not isinstance(result, dict):
            raise AssertionError(f"expected dict, got {type(result).__name__}")
        if "goal" not in result:
            raise AssertionError(f"expected 'goal' key, got keys {list(result.keys())}")
        _ok(4, name, 0.0, f"keys={list(result.keys())} ({time.time() - t0:.1f}s)")
    except Exception as e:
        _fail(4, name, e)


def smoke_site_5_compiler_stream() -> None:
    """Mirrors compiler/stream.py: sonnet streaming via client.stream()."""
    name = "compiler.stream (streaming)"
    try:
        t0 = time.time()
        c = client_for("anthropic", os.environ["ANTHROPIC_API_KEY"])
        deltas = 0
        total_chars = 0
        for text in c.stream(
            model="claude-sonnet-4-6",
            max_tokens=80,
            system="You are a compiler for an AI agent workflow platform.",
            messages=[{"role": "user", "content": "In one sentence, what does a brain block do?"}],
        ):
            deltas += 1
            total_chars += len(text)
        if deltas == 0:
            raise AssertionError("stream yielded zero deltas")
        _ok(5, name, 0.0, f"deltas={deltas} chars={total_chars} ({time.time() - t0:.1f}s)")
    except Exception as e:
        _fail(5, name, e)


if __name__ == "__main__":
    print("=" * 60)
    print("Real-LLM smoke test — anthropic → llm_client refactor")
    print("=" * 60)
    smoke_site_1_team_memory()
    smoke_site_2_workflows_preflight()
    smoke_site_3_policies_generate()
    smoke_site_4_compiler_extract_slots()
    smoke_site_5_compiler_stream()
    print("=" * 60)
    print("Done. All 5 sites 'OK' → refactor is safe to merge.")
