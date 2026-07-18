"""Test the 1-call dispatch path. Run from apps/api/:
   python3 test_dispatch.py
"""
import time, json, sys
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

import os, sys
sys.path.insert(0, str(Path(__file__).parent))

from app.modules.glens.inference import dispatch_tool
from app.modules.glens.formatters import format_tool_result

CASES = [
    "Show me today's Guard activity",
    "Who was blocked today?",
    "Show governance KPIs",
    "What's our spend this month?",
    "List all Guard rules",
]

print("Testing 1-call dispatch path\n")
for msg in CASES:
    t0 = time.perf_counter()
    tool, args = dispatch_tool(msg)
    t1 = time.perf_counter()

    # Simulate executor result
    fake_results = {
        "get_recent_governance_events": [{"ts": "2026-07-18T03:00:00Z", "decision": "allowed", "rule_id": None, "ai_tool": "claude-code", "user_email": "sudhi@b2bsphere.com"}],
        "get_governance_kpis": {"events_today": 42, "blocked_today": 2, "active_developers_today": 1, "blocks_mtd": 5, "risk_avoided_usd_mtd": 12.50},
        "get_spend_summary": {"total_cost_usd": 3.14, "by_developer": [{"email": "sudhi@b2bsphere.com", "cost_usd": 3.14}]},
        "list_policies": [{"rule_id": "no-rm-rf", "description": "Block rm -rf", "decision": "blocked", "enabled": True}],
    }
    result = fake_results.get(tool, {})
    formatted = format_tool_result(tool, result)

    status = "✓" if formatted else "✗ (no formatter)"
    print(f"{status}  [{t1-t0:.2f}s]  {msg!r}")
    print(f"     → tool={tool} args={args}")
    if formatted:
        print(f"     → answer={formatted['answer']!r}")
    print()
