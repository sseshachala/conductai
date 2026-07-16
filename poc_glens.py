#!/usr/bin/env python3
"""
GLens POC — end-to-end conversation loop, terminal only.

Layers tested:
  1. Qwen3 on Modal (intent classifier + param extractor + spec emitter)
  2. Clarifying question loop (terminal)
  3. Render spec generation
  4. Guard API calls (staging or local)
  5. Composed output printed as dashboard summary

Usage:
  cp apps/api/.env .env.glens  # or set vars in shell
  python poc_glens.py
"""

import os
import json
import httpx
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────
import uuid

ENDPOINT_URL   = os.getenv("CONDUCT_INFERENCE_ENDPOINT_URL", "")
MODEL_NAME     = os.getenv("CONDUCT_INFERENCE_MODEL_NAME", "Qwen/Qwen3.6-35B-A3B")
TOKEN_ID       = os.getenv("CONDUCT_INFERENCE_TOKEN_ID", "")
TOKEN_SECRET   = os.getenv("CONDUCT_INFERENCE_TOKEN_SECRET", "")
GUARD_API_BASE = os.getenv("API_BASE_URL", "https://api.conductai.ai")
CLI_API_KEY    = os.getenv("CLI_API_KEY", "")

# Sticky session — all turns in one GLens conversation hit the same warm Modal instance
SESSION_ID = str(uuid.uuid4())

if not ENDPOINT_URL:
    raise SystemExit("CONDUCT_INFERENCE_ENDPOINT_URL not set. Check your .env")

base_url = ENDPOINT_URL if ENDPOINT_URL.endswith("/v1") else f"{ENDPOINT_URL}/v1"

client = OpenAI(
    base_url=base_url,
    api_key="unused",  # Modal ignores api_key, uses Modal-Key/Modal-Secret headers
    default_headers={
        "Modal-Key": TOKEN_ID,
        "Modal-Secret": TOKEN_SECRET,
    },
)

GUARD_ENDPOINTS = {
    "events": {
        "path": "/guard/events",
        "params": ["from", "to", "decision", "severity", "limit"],
        "description": "Guard blocks, warnings, allows — filterable by date, decision (BLOCK/WARN/ALLOW), severity",
    },
    "events_unified": {
        "path": "/guard/events/unified",
        "params": ["from", "to", "limit"],
        "description": "Unified Guard event view with enriched metadata",
    },
    "spend": {
        "path": "/guard/spend",
        "params": ["from", "to", "group_by"],
        "description": "AI spend summary — group_by: model, agent, week, day",
    },
    "spend_sessions": {
        "path": "/guard/spend/sessions",
        "params": ["from", "to", "limit"],
        "description": "Spend broken down by agent session",
    },
}

from datetime import date
TODAY = date.today().isoformat()

CLASSIFIER_SYSTEM = f"""You are GLens, a governance assistant for ConductAI.
Today's date is {TODAY}. Use this to calculate relative dates like "last 30 days", "this month", "H1 2026" etc.
Your job is to help users query their AI governance data (Guard activity, spend, agent inventory, policies).

You have access to these Guard API endpoints:
{json.dumps(GUARD_ENDPOINTS, indent=2)}

Your conversation flow:
1. Understand the user's question
2. If required params are missing (especially time range), ask ONE clarifying question
3. Once you have enough context, emit a render spec JSON

Required params before emitting spec:
- time range (from/to) — always needed unless user says "all time"
- scope (team or all) — ask if ambiguous

When ready to emit the spec, respond with ONLY valid JSON in this format:
{{
  "ready": true,
  "title": "Dashboard title",
  "filters": {{"from": "YYYY-MM-DD", "to": "YYYY-MM-DD", "team": "optional"}},
  "kpis": [
    {{"label": "KPI name", "endpoint": "/guard/activity", "params": {{}}, "highlight": false}}
  ],
  "charts": [
    {{"type": "bar|line", "title": "Chart title", "endpoint": "/guard/spend", "group_by": "model|week|team"}}
  ],
  "tables": [
    {{"title": "Table title", "endpoint": "/guard/activity", "params": {{"severity": "high"}}}}
  ]
}}

If you need more info, respond with:
{{"ready": false, "question": "Your single clarifying question here"}}

Never send governance data to yourself. Only emit specs that reference endpoints.
"""

# ── Guard API caller ──────────────────────────────────────────────────────────
def call_guard_api(path: str, params: dict) -> dict:
    url = f"{GUARD_API_BASE}{path}"
    headers = {"Authorization": f"Bearer {CLI_API_KEY}"} if CLI_API_KEY else {}
    try:
        r = httpx.get(url, params=params, headers=headers, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"error": str(e), "endpoint": path, "params": params}


# ── Render spec executor ──────────────────────────────────────────────────────
def execute_spec(spec: dict):
    print("\n" + "═" * 60)
    print(f"  ✦ GLens — {spec.get('title', 'Governance Report')}")
    print("═" * 60)

    filters = spec.get("filters", {})
    print(f"  Period: {filters.get('from', '?')} → {filters.get('to', '?')}")
    if filters.get("team"):
        print(f"  Scope:  {filters['team']}")

    print("\n  KPIs")
    print("  " + "─" * 40)
    for kpi in spec.get("kpis", []):
        params = {**filters, **kpi.get("params", {})}
        data = call_guard_api(kpi["endpoint"], params)
        highlight = " ◀ HIGHLIGHT" if kpi.get("highlight") else ""
        if isinstance(data, dict) and "error" in data:
            print(f"  {kpi['label']}: [API error — {data['error']}]{highlight}")
        elif isinstance(data, list):
            print(f"  {kpi['label']}: {len(data)}{highlight}")
        else:
            count = data.get("total") or data.get("count") or len(data.get("items", []))
            print(f"  {kpi['label']}: {count}{highlight}")

    print("\n  Charts")
    print("  " + "─" * 40)
    for chart in spec.get("charts", []):
        params = {**filters, "group_by": chart.get("group_by", "")}
        data = call_guard_api(chart["endpoint"], params)
        if isinstance(data, dict) and "error" in data:
            print(f"  [{chart['type']}] {chart['title']}: [API error — {data['error']}]")
        elif isinstance(data, list):
            print(f"  [{chart['type']}] {chart['title']}: {len(data)} data points")
        else:
            print(f"  [{chart['type']}] {chart['title']}: {len(data.get('items', data.get('groups', [])))} data points")

    print("\n  Tables")
    print("  " + "─" * 40)
    for table in spec.get("tables", []):
        params = {**filters, **table.get("params", {})}
        data = call_guard_api(table["endpoint"], params)
        if isinstance(data, dict) and "error" in data:
            print(f"  {table['title']}: [API error — {data['error']}]")
        elif isinstance(data, list):
            print(f"  {table['title']}: {len(data)} rows")
            for item in data[:5]:
                print(f"    · {item.get('tool_name','?')} — {item.get('decision','?')} — {item.get('created_at','?')}")
        else:
            items = data.get("items", [])
            print(f"  {table['title']}: {len(items)} rows")
            for item in items[:5]:
                print(f"    · {item}")

    print("\n" + "═" * 60)
    print("  [↗] Pin as page  [⬇] Export PDF  [?] Ask follow-up")
    print("═" * 60 + "\n")


# ── Qwen3 conversation loop ───────────────────────────────────────────────────
def run_glens():
    print("\n✦ GLens — Governance Assistant (POC)")
    print("  Type your question. Ctrl+C to exit.\n")

    messages = [{"role": "system", "content": CLASSIFIER_SYSTEM}]

    while True:
        user_input = input("You: ").strip()
        if not user_input:
            continue

        messages.append({"role": "user", "content": user_input})

        print("GLens: processing... (cold start may take 30-60s)", end="\r", flush=True)
        response = None
        for attempt in range(3):
            try:
                response = client.chat.completions.create(
                    model=MODEL_NAME,
                    messages=messages,
                    response_format={"type": "json_object"},
                    temperature=0.2,
                    max_tokens=1024,
                    extra_headers={"Modal-Session-ID": SESSION_ID},
                    extra_body={"chat_template_kwargs": {"enable_thinking": False}},
                    timeout=90,
                )
                break
            except Exception as e:
                if attempt < 2:
                    print(f"GLens: retrying... (attempt {attempt + 2}/3)", end="\r", flush=True)
                    import time; time.sleep(10)
                else:
                    raise
        if response is None:
            print("GLens: model unavailable, try again.\n")
            continue

        raw = response.choices[0].message.content.strip()
        messages.append({"role": "assistant", "content": raw})

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            print(f"GLens: {raw}\n")
            continue

        if parsed.get("ready"):
            print(f"GLens: Building your dashboard...\n")
            execute_spec(parsed)
            # allow follow-up
            print("GLens: Dashboard ready. Ask a follow-up or press Ctrl+C to exit.\n")
        else:
            question = parsed.get("question", raw)
            print(f"GLens: {question}\n")


if __name__ == "__main__":
    try:
        run_glens()
    except KeyboardInterrupt:
        print("\n\nGLens session ended.\n")
