# ConductGuard — Developer Setup

This guide covers how a developer installs ConductGuard on their machine and stays in sync with team policies.

---

## Prerequisites

- Python 3.10+ (Homebrew recommended on macOS — system Python on macOS has network restrictions)
- Claude Code or Codex CLI installed
- A ConductGuard invite code from your team lead or admin

---

## Install the CLI

```bash
pip install conduct-cli
# or
pipx install conduct-cli
```

Verify:

```bash
conduct --version
conductguard-mcp --version   # should print version, not "command not found"
```

---

## Join a Team

Your admin sends you an invite link. The URL contains your invite code. Run:

```bash
conduct guard join <invite-code>
```

This:
1. Registers your machine with the ConductGuard team
2. Writes `~/.conductguard/config.json` with your `member_token` and `clerk_user_id`
3. Installs the PreToolUse and PostToolUse hooks into Claude Code's `~/.claude/settings.json`
4. Pulls the current policy set from the server

---

## Sync Policies

Policies sync automatically every 60 seconds while Claude Code is running. To force a manual sync:

```bash
conduct guard sync
```

You should see output like:

```
[guard] synced 4 policies, 1 budget rule
[guard] hook registered: PreToolUse → /Users/you/.conductguard/hook.py
[guard] hook registered: PostToolUse → /Users/you/.conductguard/hook.py
```

---

## Config File

`~/.conductguard/config.json` stores your local state:

```json
{
  "team_id": "abc123",
  "workspace_id": "ws-uuid",
  "member_token": "grd_...",
  "clerk_user_id": "user_...",
  "policies": [...],
  "budget": {
    "monthly_limit_usd": 50.0,
    "hard_limit_usd": 60.0,
    "alert_threshold_pct": 80
  },
  "last_synced": "2026-06-02T10:30:00Z"
}
```

The `clerk_user_id` is used to enforce per-developer spend caps. If it is missing after an older install, re-run `conduct guard sync` to refresh it.

---

## Hook Location

The hook script lives at `~/.conductguard/hook.py`. It is called by Claude Code before and after every tool execution. Do not edit it manually — `conduct guard sync` overwrites it on each sync.

To verify the hook is registered in Claude Code:

```bash
cat ~/.claude/settings.json | python3 -c "import json,sys; h=json.load(sys.stdin).get('hooks',{}); [print(e.get('command','')) for e in h.get('PreToolUse',[])+h.get('PostToolUse',[])]"
```

You should see `/path/to/python3.11 /Users/you/.conductguard/hook.py` in the output.

---

## Deregister

To remove the hooks from this machine:

```bash
python3 - <<'EOF'
import json, pathlib
p = pathlib.Path.home() / ".claude" / "settings.json"
s = json.loads(p.read_text())
hook_path = str(pathlib.Path.home() / ".conductguard" / "hook.py")
for event in ("PreToolUse", "PostToolUse"):
    s.setdefault("hooks", {}).setdefault(event, [])
    s["hooks"][event] = [e for e in s["hooks"][event] if hook_path not in e.get("command","")]
p.write_text(json.dumps(s, indent=2))
print("hooks removed")
EOF
```

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `conduct: command not found` | Add pip/pipx bin dir to PATH |
| Hook registered with wrong Python | Run `conduct guard sync` — it now auto-detects Homebrew Python |
| `SyntaxError` in hook.py | Run `conduct guard sync` to rewrite the hook |
| Budget check shows old cached data | Delete `~/.conductguard/budget_cache.json` and re-sync |
| Block message not showing in Claude | The message is written to stderr; Claude Code surfaces it in the hook error panel |
