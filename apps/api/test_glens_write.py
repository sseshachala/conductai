"""
GLens write-action smoke tests.
Usage:
  python test_glens_write.py                          # hits localhost:8000
  python test_glens_write.py https://api.conductai.ai # hits prod

Requires:
  CONDUCT_TEST_TOKEN  — Bearer token for a workspace with guard.policies.edit permission
  CONDUCT_WORKSPACE   — workspace_id (UUID)
"""
import json
import os
import sys

import httpx

BASE = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://localhost:8000"
TOKEN = os.environ.get("CONDUCT_TEST_TOKEN", "")
WORKSPACE = os.environ.get("CONDUCT_WORKSPACE", "")

if not TOKEN or not WORKSPACE:
    print("Set CONDUCT_TEST_TOKEN and CONDUCT_WORKSPACE env vars")
    sys.exit(1)

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "X-Workspace-ID": WORKSPACE,
    "Content-Type": "application/json",
}


def stream(message: str) -> dict:
    """Send a GLens chat message and return the final 'done' payload."""
    with httpx.Client(timeout=60) as client:
        with client.stream(
            "POST",
            f"{BASE}/glens/chat/stream",
            headers=HEADERS,
            json={"message": message},
        ) as resp:
            resp.raise_for_status()
            last = {}
            for line in resp.iter_lines():
                if line.startswith("data: "):
                    evt = json.loads(line[6:])
                    if evt.get("type") == "thinking":
                        print(f"  ··· {evt.get('label', '')}")
                    elif evt.get("type") == "done":
                        last = evt
                    elif evt.get("type") == "error":
                        return {"error": evt.get("message")}
            return last


def check(label: str, payload: dict, *, expect_confirm=False, expect_clarify=False, expect_action=None):
    print(f"\n{'='*60}")
    print(f"TEST: {label}")
    if "error" in payload:
        print(f"  ❌ Error: {payload['error']}")
        return
    confirm = payload.get("confirm_required", False)
    clarify = payload.get("clarification_required", False)
    action = payload.get("action")
    answer = payload.get("answer", "")
    followups = payload.get("followups", [])

    if expect_clarify:
        if clarify:
            print(f"  ✅ clarification_required — {answer[:80]}")
            if followups:
                print(f"     chips: {followups}")
        else:
            print(f"  ❌ Expected clarification_required, got: confirm={confirm} answer={answer[:80]}")
    elif expect_confirm:
        if confirm:
            print(f"  ✅ confirm_required action={action}")
            draft = payload.get("draft", {})
            print(f"     draft: {json.dumps(draft, indent=6)}")
            if expect_action and action != expect_action:
                print(f"  ⚠️  Expected action={expect_action}, got action={action}")
            warning = payload.get("warning")
            if warning:
                print(f"  ⚠️  warning: {warning}")
        else:
            print(f"  ❌ Expected confirm_required, got: clarify={clarify} answer={answer[:80]}")
    else:
        print(f"  answer: {answer[:120]}")
        print(f"  confirm={confirm} clarify={clarify}")


# ── Clarification cases ────────────────────────────────────────────────────────

print("\n" + "="*60)
print("SECTION: Vague inputs — should trigger clarification_required")

check("Vague: 'block it'",
      stream("create a guard rule to block it"),
      expect_clarify=True)

check("Vague: 'add a strict rule'",
      stream("add a strict rule"),
      expect_clarify=True)

check("Vague: 'add a rule for Claude'",
      stream("add a rule for Claude"),
      expect_clarify=True)

check("Edit: no rule mentioned",
      stream("make the rule stricter"),
      expect_clarify=True)

check("Delete: no rule mentioned",
      stream("delete that rule"),
      expect_clarify=True)


# ── Generate path (good desc, no pattern) ─────────────────────────────────────

print("\n" + "="*60)
print("SECTION: Good description, no pattern — should call generate endpoint")

check("Create: 'Block access to .env files'",
      stream("create a rule that blocks access to .env files"),
      expect_confirm=True, expect_action="create")

check("Create: 'Warn when secrets are pasted into Claude'",
      stream("add a rule to warn when secrets are pasted into Claude"),
      expect_confirm=True, expect_action="create")


# ── Full args (pattern + tool present) ────────────────────────────────────────

print("\n" + "="*60)
print("SECTION: Full args — should go straight to confirm_required")

check("Create: explicit pattern and tool",
      stream("create a guard rule to block cursor from reading files matching \\.env$"),
      expect_confirm=True, expect_action="create")


# ── Edit / Delete with rule resolution ────────────────────────────────────────

print("\n" + "="*60)
print("SECTION: Edit and delete — rule_id resolution")

check("List rules first (to know what IDs exist)",
      stream("list my guard rules"))

check("Edit: named rule",
      stream("disable rule cursor-block-env"),
      expect_confirm=True, expect_action="patch")

check("Delete: named rule",
      stream("delete rule test-custom-rule"),
      expect_confirm=True, expect_action="delete")

print("\n" + "="*60)
print("Done.")
