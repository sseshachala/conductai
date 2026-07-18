"""Quick smoke test for Together AI inference — run from apps/api/:
   CONDUCT_INFERENCE_ENDPOINT_URL=https://api.together.xyz/v1 \
   CONDUCT_INFERENCE_MODEL_NAME=Qwen/Qwen3.5-9B \
   CONDUCT_INFERENCE_TOKEN_ID=<your_key> \
   python test_together.py
"""
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

from openai import OpenAI

endpoint = os.environ.get("CONDUCT_INFERENCE_ENDPOINT_URL", "").rstrip("/")
model    = os.environ.get("CONDUCT_INFERENCE_MODEL_NAME", "")
api_key  = os.environ.get("CONDUCT_INFERENCE_TOKEN_ID", "")

if not all([endpoint, model, api_key]):
    sys.exit("Set CONDUCT_INFERENCE_ENDPOINT_URL, CONDUCT_INFERENCE_MODEL_NAME, CONDUCT_INFERENCE_TOKEN_ID")

client = OpenAI(base_url=f"{endpoint}/v1" if not endpoint.endswith("/v1") else endpoint, api_key=api_key)

print(f"Endpoint : {endpoint}")
print(f"Model    : {model}")
print()

# ── Test 1: plain chat ────────────────────────────────────────────────────────
print("Test 1: plain chat + JSON mode")
resp = client.chat.completions.create(
    model=model,
    messages=[
        {"role": "system", "content": "Reply with valid JSON only."},
        {"role": "user",   "content": 'Return {"status": "ok", "model": "<model_name>"}'},
    ],
    response_format={"type": "json_object"},
    temperature=0,
    max_tokens=512,
    extra_body={"thinking": {"type": "disabled"}},
)
content = resp.choices[0].message.content
print(f"  raw: {repr(content)}")
print(f"  finish_reason: {resp.choices[0].finish_reason}")
parsed = json.loads(content)
assert parsed.get("status") == "ok", f"Unexpected: {parsed}"
print(f"  PASS — {parsed}")

# ── Test 2: tool calling ──────────────────────────────────────────────────────
print("Test 2: tool calling")
tools = [{
    "type": "function",
    "function": {
        "name": "get_governance_kpis",
        "description": "Get governance KPIs",
        "parameters": {"type": "object", "properties": {}, "required": []},
    }
}]
resp = client.chat.completions.create(
    model=model,
    messages=[
        {"role": "system", "content": "You are a governance assistant. Call tools when asked."},
        {"role": "user",   "content": "How many events happened today? Call get_governance_kpis."},
    ],
    tools=tools,
    tool_choice="auto",
    temperature=0,
    max_tokens=256,
    extra_body={"thinking": {"type": "disabled"}},
)
msg = resp.choices[0].message
assert msg.tool_calls, f"Expected tool call, got: {msg.content}"
tc = msg.tool_calls[0]
assert tc.function.name == "get_governance_kpis", f"Wrong tool: {tc.function.name}"
print(f"  PASS — called {tc.function.name}()")

# ── Test 3: tool result → final answer ───────────────────────────────────────
print("Test 3: tool result → final JSON answer")
messages = [
    {"role": "system", "content": 'Reply with JSON: {"answer": "..."}'},
    {"role": "user",   "content": "How many events today?"},
    {"role": "assistant", "content": "", "tool_calls": [tc.model_dump()]},
    {"role": "tool", "tool_call_id": tc.id, "content": '{"events_today": 42, "blocked_today": 3}'},
]
resp = client.chat.completions.create(
    model=model,
    messages=messages,
    tools=tools,
    tool_choice="auto",
    temperature=0,
    max_tokens=256,
    extra_body={"thinking": {"type": "disabled"}},
)
final = resp.choices[0].message
assert not final.tool_calls, "Expected final answer, got another tool call"
result = json.loads(final.content or "{}")
assert "answer" in result, f"No answer key: {result}"
print(f"  PASS — {result}")

print()
print("All tests passed. Together AI is wired correctly.")
