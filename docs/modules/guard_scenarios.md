# Guard Test Scenarios

A runbook for reproducing every ConductGuard integration test. Pick this up cold and follow each scenario in order — each one is self-contained.

---

## Table of Contents

1. [Environment Setup](#environment-setup)
2. [Verification Commands (Run Anytime)](#verification-commands-run-anytime)
3. [Scenario 1 — Workspace Hard Cap Blocks All Tool Calls](#scenario-1--workspace-hard-cap-blocks-all-tool-calls)
4. [Scenario 2 — Per-User Hard Cap](#scenario-2--per-user-hard-cap)
5. [Scenario 3 — Policy Rule Blocks a Specific Tool Call](#scenario-3--policy-rule-blocks-a-specific-tool-call)
6. [Scenario 4 — Alert Threshold Fires Slack Notification](#scenario-4--alert-threshold-fires-slack-notification)
7. [Known Issues and Gotchas](#known-issues-and-gotchas)
8. [Teardown / Deregister Hooks](#teardown--deregister-hooks)

---

## Environment Setup

Before running any scenario, verify the environment is wired correctly.

| Component | Location |
|-----------|----------|
| CLI source | `/Users/sudhiseshachala/projects/marshal/packages/conduct-cli` |
| Config file | `~/.conductguard/config.json` |
| Policy file | `~/.conductguard/policy.json` |
| Hook script | `~/.conductguard/hook.py` |
| Hook registration | `~/.claude/settings.json` |
| Budget cache | `~/.conductguard/budget_cache.json` (5-min TTL) |
| Python binary | `/opt/homebrew/bin/python3.11` |
| API base URL | `https://api.conductai.ai` |
| UI | Guard → Spend page, Guard → Policies page |

### Config file structure

`~/.conductguard/config.json` must contain at minimum:

```json
{
  "workspace_id": "<your-workspace-id>",
  "api_url": "https://api.conductai.ai",
  "user_email": "<your-email>",
  "clerk_user_id": "<your-clerk-user-id>"
}
```

> `clerk_user_id` was added in v0.4.16. If missing, run `conduct guard sync` to refresh the config.

### Hook registration check

```bash
cat ~/.claude/settings.json | /opt/homebrew/bin/python3.11 -m json.tool | grep conductguard
```

Expected output: one or more lines referencing `.conductguard/hook.py`.

### Policy rule count check

```bash
/opt/homebrew/bin/python3.11 -c "import json; p=json.load(open('/Users/sudhiseshachala/.conductguard/policy.json')); print(f'{len(p[\"rules\"])} rules')"
```

Expected: a non-zero number (18 rules in the baseline policy).

---

## Verification Commands (Run Anytime)

These commands can be used at any point to inspect the live state of Guard on the local machine.

```bash
# Check registered hooks
cat ~/.claude/settings.json | /opt/homebrew/bin/python3.11 -m json.tool | grep conductguard

# Inspect full config
cat ~/.conductguard/config.json

# Count policy rules
/opt/homebrew/bin/python3.11 -c "import json; p=json.load(open('/Users/sudhiseshachala/.conductguard/policy.json')); print(f'{len(p[\"rules\"])} rules')"

# Inspect budget cache
cat ~/.conductguard/budget_cache.json

# Manual hook test — passes through (expect exit 0 when not blocked)
echo '{"tool_name":"bash","tool_input":{"command":"ls"},"session_id":"test"}' | /opt/homebrew/bin/python3.11 ~/.conductguard/hook.py; echo "exit: $?"

# Manual hook test — triggers rm policy block (expect exit 2 when no-rm rule is active)
echo '{"tool_name":"bash","tool_input":{"command":"rm -rf /tmp"},"session_id":"test"}' | /opt/homebrew/bin/python3.11 ~/.conductguard/hook.py; echo "exit: $?"
```

---

## Scenario 1 — Workspace Hard Cap Blocks All Tool Calls

**Purpose:** Verify that setting a workspace-level monthly budget below current spend blocks every subsequent tool call for all users in the workspace.

### Prerequisites

- Guard hook is registered in `~/.claude/settings.json`
- `conduct guard sync` has been run at least once
- You know the current workspace monthly spend (visible on Guard → Spend)

---

### Step 1 — Set the workspace budget below current spend

1. Open the UI: Guard → Spend
2. Find **Team monthly budget**
3. Set it to a value strictly below the current monthly spend
   - If current spend is `$0.00`, set it to `$0.00` exactly (or any value at or below actual spend)
   - If current spend is `$12.50`, set it to `$10.00` or any value ≤ `$12.50`
4. Check the box: **Block new AI sessions when budget is exhausted**
5. Click **Save**

---

### Step 2 — Sync and clear the local cache

```bash
conduct guard sync
rm ~/.conductguard/budget_cache.json
```

`sync` pulls the updated budget config from the API. Deleting the cache forces an immediate re-check on the next hook call (bypassing the 5-min TTL).

---

### Step 3 — Verify the API response directly

```bash
/opt/homebrew/bin/python3.11 -c "
import json, urllib.request
cfg = json.load(open('/Users/sudhiseshachala/.conductguard/config.json'))
url = cfg['api_url'] + '/guard/spend/budget-check?workspace_id=' + cfg['workspace_id']
resp = urllib.request.urlopen(url, timeout=5)
print(resp.read().decode())
"
```

**Expected response:**

```json
{
  "hard_blocked": true,
  "reason": "Your team's monthly AI budget of $X.XX has been reached. New tool calls are paused until the budget is raised or the month resets.",
  "monthly_cost_usd": X,
  "hard_limit_usd": X
}
```

If `hard_blocked` is `false`, the budget was not set below the current spend — go back to Step 1.

---

### Step 4 — Verify the hook blocks tool calls

```bash
echo '{"tool_name":"bash","tool_input":{"command":"ls"},"session_id":"test"}' | /opt/homebrew/bin/python3.11 ~/.conductguard/hook.py; echo "exit: $?"
```

**Expected output:**

```
[ConductGuard] Your team's monthly AI budget of $X.XX has been reached. New tool calls are paused...
exit: 2
```

Exit code `2` is the signal to Claude Code that the tool call is blocked.

---

### Step 5 — Verify in Claude Code

Open a Claude Code session and trigger any tool call (e.g., ask it to list files). The response in the session should show:

```
PreToolUse hook error: [...]: [ConductGuard] Your team's monthly AI budget of $X.XX has been reached. New tool calls are paused...
```

No tool output will be returned — the call is fully blocked before execution.

---

### Teardown — Restore normal operation

```bash
# 1. Raise the budget above current spend in the UI (Guard → Spend → Save)
# 2. Sync and clear cache
conduct guard sync
rm ~/.conductguard/budget_cache.json
```

Verify the hook now passes through:

```bash
echo '{"tool_name":"bash","tool_input":{"command":"ls"},"session_id":"test"}' | /opt/homebrew/bin/python3.11 ~/.conductguard/hook.py; echo "exit: $?"
```

Expected: `exit: 0` (no block message).

---

## Scenario 2 — Per-User Hard Cap

**Purpose:** Verify that a per-developer spend limit blocks tool calls for a specific user without affecting others.

### Prerequisites

- `clerk_user_id` is present in `~/.conductguard/config.json` (v0.4.16+)
- You know the current monthly spend for the test user (visible on Guard → Spend, per-user breakdown)

---

### Step 1 — Set the per-developer limit below the user's spend

1. Open the UI: Guard → Spend
2. Find **Default per-developer limit**
3. Set it to a value strictly below the test user's current monthly spend
4. Click **Save**

---

### Step 2 — Sync and clear cache

```bash
conduct guard sync
rm ~/.conductguard/budget_cache.json
```

---

### Step 3 — Verify the API response for the specific user

```bash
/opt/homebrew/bin/python3.11 -c "
import json, urllib.request
cfg = json.load(open('/Users/sudhiseshachala/.conductguard/config.json'))
url = (
    cfg['api_url']
    + '/guard/spend/budget-check?workspace_id='
    + cfg['workspace_id']
    + '&clerk_user_id='
    + cfg.get('clerk_user_id', '')
)
resp = urllib.request.urlopen(url, timeout=5)
print(resp.read().decode())
"
```

**Expected response:**

```json
{
  "hard_blocked": true,
  "reason": "You've reached your monthly AI spend limit of $X.XX. New tool calls are paused until your limit is raised or the month resets."
}
```

> If `clerk_user_id` is empty in config, run `conduct guard sync` to refresh it. This field was added in v0.4.16.

---

### Step 4 — Verify hook blocks tool calls (same as Scenario 1, Step 4)

```bash
echo '{"tool_name":"bash","tool_input":{"command":"ls"},"session_id":"test"}' | /opt/homebrew/bin/python3.11 ~/.conductguard/hook.py; echo "exit: $?"
```

**Expected:** block message with `exit: 2`.

---

### Teardown

```bash
# 1. Raise the per-developer limit above the user's spend in the UI → Save
conduct guard sync
rm ~/.conductguard/budget_cache.json
```

---

## Scenario 3 — Policy Rule Blocks a Specific Tool Call

**Purpose:** Verify that a Guard policy rule matches a pattern in a tool call and blocks it with a custom message, logs it to the activity feed, and fires a Slack notification.

### Prerequisites

- Guard hook is registered and `conduct guard sync` has been run
- A Slack webhook is configured (required to verify the Slack notification)

---

### Step 1 — Create the policy rule in the UI

1. Open the UI: Guard → Policies
2. Click **Add rule**
3. Fill in:

   | Field | Value |
   |-------|-------|
   | Rule ID | `no-rm` |
   | Match tool | `bash` |
   | Match pattern | `rm` |
   | Action | `block` |
   | Message | `Deleting files is not allowed. Use git to revert changes instead.` |

4. Click **Save**

---

### Step 2 — Sync the policy locally

```bash
conduct guard sync
```

This pulls the updated policy from the API to `~/.conductguard/policy.json`.

---

### Step 3 — Confirm the rule is in the local policy file

```bash
/opt/homebrew/bin/python3.11 -c "
import json
p = json.load(open('/Users/sudhiseshachala/.conductguard/policy.json'))
matches = [r for r in p['rules'] if r.get('rule_id') == 'no-rm']
for r in matches:
    print(r)
print(f'Found {len(matches)} matching rule(s)')
"
```

**Expected:** one rule printed with `rule_id: no-rm` and the correct message.

---

### Step 4 — Test the hook directly

```bash
echo '{"tool_name":"bash","tool_input":{"command":"rm -rf /tmp/test"},"session_id":"test"}' | /opt/homebrew/bin/python3.11 ~/.conductguard/hook.py; echo "exit: $?"
```

**Expected output:**

```
[ConductGuard] Deleting files is not allowed. Use git to revert changes instead.
exit: 2
```

---

### Step 5 — Verify in Claude Code

In a Claude Code session, ask:

```
run bash -c 'rm -rf /tmp/test'
```

The tool call should be blocked inline:

```
PreToolUse hook error: [...]: [ConductGuard] Deleting files is not allowed. Use git to revert changes instead.
```

---

### Step 6 — Verify Slack notification

Check the configured Slack channel. You will see two messages — one for the block, one for the spend alert (if threshold is crossed):

**Block notification:**
```
🚫 salessupport@organicsphere.com blocked by no-rm in claude-code
Deleting files is not allowed. Use git to revert changes instead.
```

**Spend alert (fires if current spend has crossed the alert threshold):**
```
⚠️ Guard spend alert (workspace-wide): $30.23 of $30.00 used (101%) — alert threshold 80% reached
```

> Both messages appear in the same Slack channel. The block notification fires on every blocked tool call. The spend alert fires once per 5% spend increment (deduped since v0.4.21).

**Real example from a live session (2026-06-02):**
```
[7:45 PM] 🚫 salessupport@organicsphere.com blocked by no-rm in claude-code
          Deleting files is not allowed. Use git to revert changes instead.
[7:45 PM] ⚠️ Guard spend alert (workspace-wide): $25.05 of $30.00 used (83%) — alert threshold 80% reached
[7:52 PM] 🚫 salessupport@organicsphere.com blocked by no-rm in claude-code
          Deleting files is not allowed. Use git to revert changes instead.
[7:52 PM] ⚠️ Guard spend alert (workspace-wide): $28.60 of $30.00 used (95%) — alert threshold 80% reached
[8:07 PM] 🚫 salessupport@organicsphere.com blocked by no-rm in claude-code
          Deleting files is not allowed. Use git to revert changes instead.
```

---

### Step 7 — Verify activity log

1. Open the UI: Guard → Activity (or equivalent activity log view)
2. Find the event for this tool call
3. Confirm:
   - `decision` = `blocked`
   - `rule_id` = `no-rm`
   - `tool_name` = `bash`
   - `user_email` matches the test user

---

### Teardown

To remove the `no-rm` rule:

1. Go to Guard → Policies
2. Delete the `no-rm` rule
3. Run `conduct guard sync` to pull the updated policy

Verify the rule is gone:

```bash
/opt/homebrew/bin/python3.11 -c "
import json
p = json.load(open('/Users/sudhiseshachala/.conductguard/policy.json'))
matches = [r for r in p['rules'] if r.get('rule_id') == 'no-rm']
print(f'Found {len(matches)} matching rule(s) — expect 0')
"
```

Then confirm `rm` commands pass through:

```bash
echo '{"tool_name":"bash","tool_input":{"command":"rm -rf /tmp/test"},"session_id":"test"}' | /opt/homebrew/bin/python3.11 ~/.conductguard/hook.py; echo "exit: $?"
```

Expected: `exit: 0`.

---

## Scenario 4 — Alert Threshold Fires Slack Notification

**Purpose:** Verify that when workspace spend exceeds the configured alert threshold, a Slack notification is sent. Alerts are deduped — they fire once per 5% spend increment, not on every tool call.

### Prerequisites

- A Slack webhook is configured in Guard → Settings
- You know the current workspace monthly spend percentage (e.g. spend is 85% of budget)

---

### Step 1 — Set the alert threshold below current spend percentage

1. Open the UI: Guard → Spend
2. Find **Alert threshold** (expressed as a percentage)
3. Set it to a value already exceeded by current spend
   - Example: if spend is at 85% of budget, set threshold to 80%
4. Click **Save**

---

### Step 2 — Trigger a tool call

In a Claude Code session, trigger any tool call that passes through the hook (e.g., ask it to list files or read a file). The hook checks spend on every tool call and fires the alert if the threshold is newly crossed.

---

### Step 3 — Verify Slack notification

Check the configured Slack channel. Expected message:

```
⚠️ Guard spend alert (workspace-wide): $X.XX of $Y.YY used (Z%) — alert threshold 80% reached
```

**Real example from a live session (2026-06-02), spend progressing from 83% → 101%:**
```
[7:45 PM] ⚠️ Guard spend alert (workspace-wide): $25.05 of $30.00 used (83%) — alert threshold 80% reached
[7:50 PM] ⚠️ Guard spend alert (workspace-wide): $27.39 of $30.00 used (91%) — alert threshold 80% reached
[7:52 PM] ⚠️ Guard spend alert (workspace-wide): $28.60 of $30.00 used (95%) — alert threshold 80% reached
[7:53 PM] ⚠️ Guard spend alert (workspace-wide): $30.23 of $30.00 used (101%) — alert threshold 80% reached
```

> Alerts are deduplicated since v0.4.21 — fires once per 5% spend increment, not on every tool call. Each line above represents a distinct 5% crossing.

---

### Teardown

Adjust the alert threshold back to your preferred operational value (e.g., 80%) and save.

---

## Known Issues and Gotchas

| Issue | Detail | Fix |
|-------|--------|-----|
| Budget cache TTL | Cache is valid for 5 minutes — changes to spend limits are not reflected until the cache expires or is deleted | `rm ~/.conductguard/budget_cache.json` |
| Wrong Python binary | Hook must run under Python 3.11+ from Homebrew. Apple system Python at `/usr/bin/python3` or `/Library/Developer/CommandLineTools/usr/bin/python3` has network restrictions that break the API call | Verify hook registration uses `/opt/homebrew/bin/python3.11` |
| Python auto-detection | `conduct guard sync` auto-detects best available Python (prefers 3.11 > 3.10 > sys.executable) since v0.4.20. If hook is registered under the wrong binary, re-run `conduct guard sync` | Run `conduct guard sync` |
| Missing `clerk_user_id` | Per-user budget checks require `clerk_user_id` in config. Field was added in v0.4.16 — older installs have it missing | Run `conduct guard sync` to refresh config |
| Block message format in Claude Code | Block messages appear as `PreToolUse hook error: [...]: [ConductGuard] <message>`. This is the expected display format — the prefix is added by Claude Code's hook error handler, not by Guard | Expected behaviour, not a bug |
| Alert deduplication | Spend alerts fire once per 5% increment (since v0.4.21). If you are testing alerts repeatedly, you may need to adjust spend or threshold to move into a new increment | Adjust budget or threshold to cross a new 5% boundary |

---

## Teardown / Deregister Hooks

To fully remove Guard hooks from the local Claude Code installation:

```bash
/opt/homebrew/bin/python3.11 -c "
import json, pathlib
p = pathlib.Path('/Users/sudhiseshachala/.claude/settings.json')
s = json.loads(p.read_text())
for v in s.get('hooks', {}).values():
    for h in v:
        h['hooks'] = [
            e for e in h.get('hooks', [])
            if '.conductguard' not in e.get('command', '')
        ]
p.write_text(json.dumps(s, indent=2))
print('done')
"
```

After running this, verify hooks are removed:

```bash
cat ~/.claude/settings.json | /opt/homebrew/bin/python3.11 -m json.tool | grep conductguard
```

Expected: no output.

To re-register hooks after deregistration, run:

```bash
conduct guard sync
```

---

*Last updated: 2026-06-02. Covers CLI v0.4.21+, API at `https://api.conductai.ai`.*
