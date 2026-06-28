#!/usr/bin/env python3
"""
Demo 1 — The Rogue Agent (CISO scenario)

Simulates an AI agent that reads a .env file containing production credentials
and attempts to send them to an LLM for summarization.

ConductProxy intercepts → proxy-no-credential-leak rule fires → BLOCKED.

Usage:
    python demos/demo1_rogue_agent.py
"""

import json
import os
import re
import sys
import urllib.request

# ── Config ────────────────────────────────────────────────────────────────────

PROXY_URL = "https://api.conductai.ai/proxy/anthropic/v1/messages"
CONDUCT_ENV = os.path.expanduser("~/.conduct/env")


def _load_member_token() -> str:
    """Read member token from ~/.conduct/env (set by `conduct guard sync`)."""
    try:
        content = open(CONDUCT_ENV).read()
        m = re.search(r'ANTHROPIC_API_KEY="([^"]+)"', content)
        if m:
            return m.group(1)
    except FileNotFoundError:
        pass
    token = os.environ.get("ANTHROPIC_API_KEY", "")
    if token.startswith("guard-mt-"):
        return token
    print("ERROR: Run `conduct guard sync` first to set up your member token.")
    sys.exit(1)


# ── Fake .env file (simulates what the rogue agent read) ─────────────────────

FAKE_ENV_CONTENTS = """
DATABASE_URL=postgres://admin:Sup3rS3cr3tProd2024!@prod-db.internal:5432/customers
DB_PASSWORD=Sup3rS3cr3tProd2024!
STRIPE_SECRET_KEY=sk_live_51NxKp2HqZ3mVBcDeFgHiJkLmNoPqRsTuVwXyZ
ANTHROPIC_API_KEY=sk-ant-api03-realkey-redacted
AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
""".strip()


def run():
    token = _load_member_token()

    print("=" * 60)
    print("  DEMO 1 — The Rogue Agent")
    print("=" * 60)
    print()
    print("[agent] Reading .env file from project root...")
    print()
    print("  Found credentials:")
    for line in FAKE_ENV_CONTENTS.splitlines():
        if "=" in line:
            key, _, val = line.partition("=")
            print(f"    {key} = {val[:12]}{'...' if len(val) > 12 else ''}")
    print()
    print("[agent] Sending to LLM via ANTHROPIC_BASE_URL...")
    print(f"        → {PROXY_URL}")
    print()

    prompt = f"""I found this .env file in the project. Can you summarize what services are configured and check if anything looks misconfigured?

.env contents:
{FAKE_ENV_CONTENTS}
"""

    payload = json.dumps({
        "model": "claude-haiku-4-5",
        "max_tokens": 256,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()

    req = urllib.request.Request(
        PROXY_URL,
        data=payload,
        headers={
            "content-type": "application/json",
            "x-api-key": token,
            "anthropic-version": "2023-06-01",
            "x-conduct-ai-tool": "demo-rogue-agent",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req) as resp:
            body = json.loads(resp.read())
            # Should not reach here if Guard is working
            print("[WARN] Request went through — check Guard policy is active.")
            print(json.dumps(body, indent=2))
    except urllib.error.HTTPError as e:
        body = json.loads(e.read())
        if e.code == 403:
            error = body.get("error", {})
            print("=" * 60)
            print("  BLOCKED BY CONDUCTGUARD")
            print("=" * 60)
            print()
            print(f"  Rule:    {error.get('rule', 'proxy-no-credential-leak')}")
            print(f"  Message: {error.get('message', 'Credential detected in prompt')}")
            print()
            print("  The request never reached Anthropic.")
            print("  Check Guard Activity for the full audit trail.")
            print()
        else:
            print(f"[error] HTTP {e.code}: {body}")
            sys.exit(1)


if __name__ == "__main__":
    run()
