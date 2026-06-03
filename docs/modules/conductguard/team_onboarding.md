# ConductGuard — Team Onboarding

This guide covers how an admin sets up a ConductGuard team and onboards developers. The entire process takes about 5 minutes for the admin, and under 2 minutes per developer.

---

## Admin: One-Time Setup

### 1. Create the team

In the Conduct dashboard, go to **Guard → Settings**. If this is your first Guard team, you'll be prompted to create one. The team is linked to your Conduct workspace automatically.

### 2. Set up Slack alerts (optional but recommended)

Go to **Guard → Settings → Alert channel**. Enter the Slack channel name (e.g. `#ai-governance`). Alerts fire when spend thresholds are crossed or when tool calls are blocked.

### 3. Configure spend budgets

Go to **Guard → Spend**. Set:
- **Monthly limit** — triggers a Slack alert at `alert_threshold_pct` (default 80%)
- **Hard cap** — blocks all tool calls when reached
- **Default per developer** — applies a per-developer monthly cap to everyone

### 4. Create policies

Go to **Guard → Policies**. Built-in policies are enabled by default (e.g. block `rm -rf`, warn on force push). Add custom rules for your team's specific needs.

### 5. Verify workspace members

Go to **Guard → Team**. All workspace members appear automatically — no invite code or explicit join step required. Promote any developer to `security` or `admin` role from this view as needed.

---

## Developer: Set Up Guard

Developers need the `conduct-cli` package. Guard is available automatically to all workspace members.

```bash
# Install
pip install conduct-cli

# Authenticate (already done if you use Conduct)
conduct login --server https://api.conductai.ai --api-key <api-key>

# Sync Guard — installs hook + MCP, pulls policies
conduct guard sync
```

`sync`:
1. Fetches current policies from `/guard/config/policies`
2. Fetches current budget rules from `/guard/spend/budgets`
3. Fetches the developer's `clerk_user_id` for per-user budget enforcement
4. Writes the hook script to `~/.conductguard/hook.py`
5. Registers the hook entries in `~/.claude/settings.json` and Codex
6. Registers the `conductguard-mcp` server in `~/.claude/settings.json`
7. Validates the hook compiles correctly (py_compile check)

The developer is now covered. No further configuration is needed.

---

## What Happens on Each Sync

Policies sync automatically every 60 seconds while Claude Code is running. On each sync:

1. Fetches current policies from `/guard/config/policies`
2. Fetches current budget rules from `/guard/spend/budgets`
3. Rewrites `~/.conductguard/hook.py` with the latest hook script
4. Registers or updates hook entries in `~/.claude/settings.json`
5. Validates the hook compiles correctly (py_compile check)

---

## Verifying a Developer is Enrolled

As admin, go to **Guard → Team**. Active members have a green status indicator. If a developer appears as inactive, ask them to re-run `conduct guard sync`.

You can also check the **Guard → Activity** dashboard — developers start appearing as soon as their first tool call is logged.

---

## Removing a Developer

Go to **Guard → Team → [developer name] → Remove**. Their hooks will stop reporting on the next sync. Their historical audit events are retained.

To remove the hooks from the developer's machine manually:

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

## Onboarding Checklist

**Admin (one-time):**
- [ ] Guard team created and linked to workspace
- [ ] Slack alert channel configured
- [ ] Workspace monthly limit and hard cap set
- [ ] Per-developer default cap set (optional)
- [ ] Policies reviewed and customized
- [ ] Verify all workspace members appear in Guard → Team

**Per developer:**
- [ ] `pip install conduct-cli`
- [ ] `conduct login --server https://api.conductai.ai --api-key <api-key>`
- [ ] `conduct guard sync`
- [ ] Confirm hook registered: `cat ~/.claude/settings.json | grep conductguard`
- [ ] Run one Claude Code session — verify activity appears in Guard dashboard
