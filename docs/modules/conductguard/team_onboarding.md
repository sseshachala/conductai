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

### 5. Get the invite code

Go to **Guard → Team → Invite**. Copy the invite code. Send it to developers via Slack, email, or your onboarding docs.

---

## Developer: Join the Team

Developers need the `conduct-cli` package and the invite code from their admin.

```bash
# Install
pip install conduct-cli

# Join
conduct guard join <invite-code>
```

On join, the CLI:
1. Authenticates with the ConductGuard API
2. Writes `~/.conductguard/config.json` with team credentials and policies
3. Registers PreToolUse and PostToolUse hooks in `~/.claude/settings.json`
4. Prints confirmation with the registered hook path

The developer is now covered. No further configuration is needed.

---

## What Happens on First Sync

`conduct guard sync` (runs automatically after join, and every 60 seconds thereafter):

1. Fetches current policies from `/guard/config/policies`
2. Fetches current budget rules from `/guard/spend/budgets`
3. Fetches the developer's `clerk_user_id` for per-user budget enforcement
4. Writes the hook script to `~/.conductguard/hook.py`
5. Registers or updates the hook entries in `~/.claude/settings.json`
6. Validates the hook compiles correctly (py_compile check)

---

## Invite Code Mechanics

| Field | Detail |
|---|---|
| Format | Short alphanumeric string, e.g. `grd_a1b2c3` |
| Scope | Workspace-scoped — one code per Guard team |
| Expiry | No expiry by default; admin can rotate at Guard → Settings |
| Role assigned | All new joiners get `developer` role; admin promotes as needed |

---

## Adding an Existing Workspace Member

If a developer is already in the Conduct workspace (appears in `workspace_users`), they can still join Guard explicitly via the invite code. Explicit Guard membership takes priority over the workspace fallback for role resolution.

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
- [ ] Invite code sent to all developers

**Per developer:**
- [ ] `pip install conduct-cli`
- [ ] `conduct guard join <invite-code>`
- [ ] Confirm hook registered: `cat ~/.claude/settings.json | grep conductguard`
- [ ] Run one Claude Code session — verify activity appears in Guard dashboard
