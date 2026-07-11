#!/usr/bin/env python3
"""
Demo 3 — Unauthorized Credential Access Outside Business Hours (PCI-DSS scenario)

An AI agent running a finance automation workflow attempts to read production
credential stores at 11:47 PM — outside the approved access window.

Policy: no agent may access production credential paths outside 09:00–18:00 local time.

ConductGuard pre-tool hook fires — Read tool blocked, event logged with rule name.

Usage:
    python3 demos/demo3_credential_access.py
"""

import json
import os
import sys
import time
import urllib.request
from datetime import datetime

CONDUCT_CFG = os.path.expanduser("~/.conduct/config.json")

RED    = "\033[91m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
RESET  = "\033[0m"


def _load_conduct_cfg() -> dict:
    try:
        return json.load(open(CONDUCT_CFG))
    except FileNotFoundError:
        print("ERROR: Run `conduct guard sync` first.")
        sys.exit(1)


def _print_banner():
    print()
    print(f"{BOLD}{'═' * 62}{RESET}")
    print(f"{BOLD}  DEMO 3 — Credential Access Outside Business Hours{RESET}")
    print(f"{BOLD}  PCI-DSS · Time-Window Policy Enforcement{RESET}")
    print(f"{BOLD}{'═' * 62}{RESET}")
    print()


def _step(n: int, label: str):
    print(f"{CYAN}{BOLD}[step {n}]{RESET} {label}")


def _pause(secs: float = 0.8):
    time.sleep(secs)


def run():
    cfg          = _load_conduct_cfg()
    workspace_id = cfg["workspace"]
    api_key      = cfg["api_key"]
    user_email   = cfg.get("user_email", "demo@conductai.ai")
    api_url      = cfg.get("server", "https://api.conductai.ai").rstrip("/")

    _print_banner()

    # ── Step 1: context ───────────────────────────────────────────────────────
    _step(1, "Finance automation agent — end-of-day reconciliation workflow")
    _pause(0.5)
    print(f"  {DIM}Workflow: invoice-reconciliation · triggered at 11:47 PM{RESET}")
    print(f"  {DIM}Agent: finance-bot · model: claude-haiku-4-5{RESET}")
    _pause(1.0)
    print()

    # ── Step 2: show the policy ───────────────────────────────────────────────
    _step(2, "Active Guard policy — PCI-DSS credential access window")
    _pause(0.5)
    print(f"  {DIM}┌─────────────────────────────────────────────────────┐{RESET}")
    print(f"  {DIM}│ Rule: pci-credential-access-hours                   │{RESET}")
    print(f"  {DIM}│ Tool: Read                                          │{RESET}")
    print(f"  {DIM}│ Path match: */.aws/*, */vault/*, *credential*       │{RESET}")
    print(f"  {DIM}│ Allowed window: 09:00 – 18:00 local time            │{RESET}")
    print(f"  {DIM}│ Outside window: BLOCK                               │{RESET}")
    print(f"  {DIM}└─────────────────────────────────────────────────────┘{RESET}")
    _pause(1.2)
    print()

    # ── Step 3: agent action ──────────────────────────────────────────────────
    target_path = "/run/secrets/prod-vault/stripe_credentials.json"
    _step(3, f"Agent reads credential store for payment processor keys")
    _pause(0.5)
    print(f"  {YELLOW}  tool: Read{RESET}")
    print(f"  {YELLOW}  path: {target_path}{RESET}")
    _pause(0.8)
    print(f"  {DIM}→ ConductGuard pre-tool hook fires{RESET}")
    _pause(1.0)
    print()

    # ── Step 4: post real block event ─────────────────────────────────────────
    now = datetime.now()
    rule_id      = "pci-credential-access-hours"
    rule_message = (
        f"Credential access blocked outside business hours "
        f"(attempted {now.strftime('%I:%M %p')} — allowed window 09:00–18:00). "
        f"PCI-DSS Req 7: restrict access to system components."
    )

    event_payload = json.dumps({
        "workspace_id": workspace_id,
        "user_email":   user_email,
        "ai_tool":      "demo",
        "tool_call":    "Read",
        "input_summary": target_path,
        "decision":     "blocked",
        "rule_id":      rule_id,
        "rule_message": rule_message,
        "source":       "hook",
    }).encode()

    guard_req = urllib.request.Request(
        f"{api_url}/guard/events",
        data=event_payload,
        headers={
            "Content-Type":  "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    try:
        with urllib.request.urlopen(guard_req, timeout=10) as resp:
            resp.read()
    except Exception as e:
        print(f"  {YELLOW}(dashboard log failed: {e}){RESET}")

    # ── Step 5: show result ───────────────────────────────────────────────────
    print(f"  {RED}{BOLD}{'─' * 50}{RESET}")
    print(f"  {RED}{BOLD}  ✗  BLOCKED by ConductGuard{RESET}")
    print(f"  {RED}{BOLD}{'─' * 50}{RESET}")
    print(f"  {RED}  Rule   : {rule_id}{RESET}")
    print(f"  {RED}  Tool   : Read{RESET}")
    print(f"  {RED}  Path   : {target_path}{RESET}")
    print(f"  {RED}  Time   : {now.strftime('%I:%M %p')} (outside 09:00–18:00){RESET}")
    print(f"  {RED}  Control: PCI-DSS Req 7 — restrict access to system components{RESET}")
    print(f"  {RED}{BOLD}{'─' * 50}{RESET}")
    print()
    print(f"  {DIM}Event logged → ConductGuard dashboard → /theguard/activity{RESET}")
    print()
    print(f"{BOLD}{'═' * 62}{RESET}")
    print(f"{GREEN}{BOLD}  Credentials read: 0     Audit entries: 1     Controls: PCI-DSS Req 7{RESET}")
    print(f"{BOLD}{'═' * 62}{RESET}")
    print()


if __name__ == "__main__":
    run()
