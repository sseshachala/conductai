"""Measure GLens latency per phase. Run from apps/api/:
   python3 test_glens_perf.py

Also tests the Python shortcut path (no LLM calls).
"""
import time
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

from openai import OpenAI
import os, json

endpoint = os.environ["CONDUCT_INFERENCE_ENDPOINT_URL"].rstrip("/")
model    = os.environ["CONDUCT_INFERENCE_MODEL_NAME"]
api_key  = os.environ["CONDUCT_INFERENCE_TOKEN_ID"]

base_url = endpoint if endpoint.endswith("/v1") else f"{endpoint}/v1"
client = OpenAI(base_url=base_url, api_key=api_key)

EXTRA = {"thinking": {"type": "disabled"}}

TOOLS = [{
    "type": "function",
    "function": {
        "name": "get_recent_governance_events",
        "description": "Fetch recent Guard audit events",
        "parameters": {
            "type": "object",
            "properties": {
                "limit":    {"type": "integer"},
                "since":    {"type": "string"},
                "decision": {"type": "string"},
            },
            "required": [],
        },
    }
}]

SYSTEM = "You are a governance assistant. Call get_recent_governance_events for activity questions. Today is 2026-07-18."

def call(messages, **kw):
    return client.chat.completions.create(
        model=model, messages=messages, temperature=0, max_tokens=512,
        extra_body=EXTRA, **kw
    )

print(f"Model: {model}\n")

# Phase 1: LLM decides which tool to call
t0 = time.perf_counter()
resp1 = call(
    [
        {"role": "system",  "content": SYSTEM},
        {"role": "user",    "content": "Show me today's Guard activity"},
    ],
    tools=TOOLS, tool_choice="auto",
)
t1 = time.perf_counter()
phase1 = t1 - t0

msg = resp1.choices[0].message
tool_called = bool(msg.tool_calls)
tc = msg.tool_calls[0] if tool_called else None
args = json.loads(tc.function.arguments) if tc else {}
print(f"Phase 1 — LLM picks tool:   {phase1:.2f}s   tool={tc.function.name if tc else 'none'}  args={args}")

# Phase 2: DB / executor (simulated — just measure JSON serialization time locally)
t0 = time.perf_counter()
# Simulate what the executor returns (20 rows of fake data)
fake_events = [
    {"id": str(i), "ts": "2026-07-18T02:57:00Z", "decision": "allowed",
     "rule_id": None, "ai_tool": "claude-code", "user_email": "sudhi@b2bsphere.com"}
    for i in range(20)
]
tool_result = json.dumps(fake_events)
t1 = time.perf_counter()
phase2 = t1 - t0
print(f"Phase 2 — DB query (simul): {phase2*1000:.1f}ms  ({len(fake_events)} rows, {len(tool_result)} bytes)")

# Phase 3: LLM formats the tool result into final JSON
messages2 = [
    {"role": "system",    "content": SYSTEM},
    {"role": "user",      "content": "Show me today's Guard activity"},
    {"role": "assistant", "content": msg.content or "", "tool_calls": [tc.model_dump()]},
    {"role": "tool",      "tool_call_id": tc.id, "content": tool_result},
]
t0 = time.perf_counter()
resp2 = call(messages2, tools=TOOLS, tool_choice="auto")
t1 = time.perf_counter()
phase3 = t1 - t0

final = resp2.choices[0].message
print(f"Phase 3 — LLM formats JSON: {phase3:.2f}s   finish={resp2.choices[0].finish_reason}")
print(f"\nTotal (phases 1+3):         {phase1+phase3:.2f}s  (DB is negligible)")

try:
    parsed = json.loads(final.content or "{}")
    print(f"\nResponse shape: skill={parsed.get('skill')} rows={len(parsed.get('rows', []))} columns={len(parsed.get('columns', []))}")
except Exception as e:
    print(f"\nParse failed: {e}\nRaw: {repr(final.content[:200])}")

print("\n" + "─"*60)
print("Shortcut path (no LLM calls):")
from collections import Counter
from datetime import datetime, timezone

fake_events2 = [
    {"id": str(i), "ts": "2026-07-18T02:57:00Z", "decision": "allowed" if i < 18 else "warned",
     "rule_id": None, "ai_tool": "claude-code", "user_email": "sudhi@b2bsphere.com"}
    for i in range(20)
]
t0 = time.perf_counter()
counts = Counter(r.get("decision", "allowed") for r in fake_events2)
parts = [f"{v} {k}" for k, v in counts.most_common()]
result = {
    "skill": "governance", "ready": False,
    "answer": f"{len(fake_events2)} events today — {', '.join(parts)}.",
    "columns": [
        {"key": "ts", "label": "Time", "type": "date"},
        {"key": "decision", "label": "Decision", "type": "badge"},
        {"key": "rule_id",  "label": "Rule",     "type": "text"},
        {"key": "ai_tool",  "label": "AI Tool",  "type": "text"},
        {"key": "user_email","label": "User",    "type": "text"},
    ],
    "rows": fake_events2,
}
t1 = time.perf_counter()
print(f"  Time: {(t1-t0)*1000:.2f}ms   rows={len(result['rows'])}")
print(f"  Answer: {result['answer']}")
print(f"\nSpeedup: {phase1+phase3:.2f}s → ~{(t1-t0)*1000:.0f}ms  ({(phase1+phase3)/max(t1-t0,0.0001):.0f}x faster)")
