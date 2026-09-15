#!/usr/bin/env python3.11
"""Live smoke of conduct-litellm-guard's GuardCheckClient against prod.

Exercises the exact code path LiteLLM invokes at pre_call time when the
guardrail fires — no LiteLLM proxy or LLM upstream keys needed. If this
passes, the LiteLLM plugin will pass end-to-end for any user with a
valid Conduct agent token.

Usage:
  TOKEN=cond_agt_xxx \
  HOSTILE_PROMPT='<block-verb text from /theguard/try>' \
  python3.11 scripts/smoke_plugin_live.py

Exit 0 = plugin client blocks the hostile canary and allows the benign
one. Any other outcome exits 1 with a diff.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "packages/conduct-litellm-guard/src"))

from conduct_litellm_guard._client import GuardCheckClient  # noqa: E402
from conduct_litellm_guard.guardrail import GuardDecision  # noqa: E402


async def _run() -> int:
    token = os.environ.get("TOKEN")
    hostile = os.environ.get("HOSTILE_PROMPT")
    if not token:
        print("ERROR: set TOKEN (paste your trial agent token from /theguard/try)")
        return 2
    if not hostile:
        print("ERROR: set HOSTILE_PROMPT (see /theguard/try 'block' verb text)")
        return 2

    client = GuardCheckClient(
        api_url="https://api.conductai.ai",
        agent_token=token,
        surface="litellm",
    )
    try:
        fail = 0

        raw = await client.guard_check(prompt="Say hi in one short sentence.")
        d = GuardDecision.parse(raw)
        ok = d.verdict == "allow"
        print(f"{'PASS' if ok else 'FAIL'}  benign   verdict={d.verdict:8s} raw={raw!r}")
        fail += 0 if ok else 1

        raw = await client.guard_check(prompt=hostile)
        d = GuardDecision.parse(raw)
        ok = d.verdict == "block"
        print(f"{'PASS' if ok else 'FAIL'}  hostile  verdict={d.verdict:8s} rule={d.rule_id or '-':40s} raw={raw!r}")
        fail += 0 if ok else 1

        print()
        if fail == 0:
            print("OK — plugin's live path returns allow on benign and block on hostile.")
            print("LiteLLM proxy configured per README will behave the same for any user.")
        else:
            print(f"FAIL — {fail} check(s) failed. Fix before handing off.")
        return 0 if fail == 0 else 1
    finally:
        await client.aclose()


if __name__ == "__main__":
    sys.exit(asyncio.run(_run()))
