# ConductAI — Full Strategic & Technical Handoff
**Session Date:** June 17, 2026  
**Status:** Pre-launch — targeting Monday June 20, 2026

---

## 1. The Core Insight (Most Important Thing From Today)

**ConductAI has dynamic policy propagation. No competitor does.**

When an admin publishes a policy change in ConductAI, every developer,
every agent, every MCP client gets it on the next tool call. No sync.
No redeployment. No restart. No config drift.

This is not a feature. It is the architecture. It happened to be built
the right way before the market understood what the right way was.

Compare:
- JFrog — update registry, redeploy config, hope devs pull it
- Kiro — admin updates allowlist, developers restart IDE
- Azure API Center — propagates on next client restart
- **ConductAI — enforced at call time, always current**

**One-liner:**
> "Publish once from ConductAI. Enforced instantly across every agent
> and developer without redeployment."

---

## 2. What ConductAI Actually Is (Positioning)

**Not:** An agent scanner  
**Not:** An MCP registry (JFrog, Kong do this)  
**Is:** The live policy enforcement layer above all registries

```
PUBLIC REGISTRIES       ENTERPRISE REGISTRIES
(Glama, MCP.io, npm) + (JFrog, Azure, Kong)
          ↓                      ↓
  ┌───────────────────────────────────┐
  │    ConductAI MCP Control Plane    │
  │  Policy · Enforcement · Audit     │
  └───────────────────────────────────┘
          ↓            ↓           ↓
    Claude Code      Cursor    Windsurf
    (ConductGuard) (Guard ext) (Guard ext)
```

**JFrog tells you which MCP servers are approved.**
**ConductAI enforces it — at every tool call, across every AI client,
with a full audit trail.**

These are complementary. An enterprise can run JFrog as their registry
and ConductAI as their enforcement layer. Partnership angle, not conflict.

---

## 3. Competitive Landscape

| Capability | JFrog | Kong | Kiro | Straiker | ConductAI |
|---|---|---|---|---|---|
| Server allowlist | ✅ | ✅ | ✅ | ✅ | ✅ |
| Tool-level enforcement | ❌ | ❌ | ❌ | ❌ | ✅ |
| Cross-client (CC+Cursor+Windsurf) | ❌ | ❌ | Kiro only | ❌ | ✅ |
| Dynamic policy (no sync) | ❌ | ❌ | ❌ | ❌ | ✅ |
| Structured audit trail | Partial | Partial | ❌ | Partial | ✅ |
| MCP server risk scoring | ❌ | ❌ | ❌ | ❌ | 🔜 |
| Tenant isolation for SaaS | ❌ | ❌ | ❌ | ❌ | 🔜 |
| Developer-native CLI | ❌ | ❌ | ❌ | ❌ | ✅ |
| Free entry point | ❌ | ❌ | ❌ | ❌ | ✅ |

Straiker sells top-down to CISOs. ConductAI lands bottom-up with
developers, surfaces findings to the CISO. Same buyer, lower friction.

---

## 4. The Product Narrative Arc (Three Acts)

### Act 1 — Launch Monday
*"Govern your AI agents in 60 seconds — three policy personas, zero config"*

- `conduct init` → pick persona → Guard active
- Simple, explainable, self-serve
- No demo required

### Act 2 — Week 3-4 Post Launch
*"Now customize — per MCP server, per tool, per team"*

- Users on Standard ask "can I allow github reads but block push?"
- That question IS the MCP governance feature request
- Demand built before feature ships

### Act 3 — Month 2
*"ConductAI MCP Control Plane — tool-level enforcement across every AI client"*

- Full policy.json with server + tool granularity
- Cross-client enforcement
- Audit trail dashboard
- The JFrog comparison lands

---

## 5. The Three Policy Personas (Launch Feature)

The 36 row-based rules in the DB get surfaced as three personas.
Rules don't go away — they get grouped and named.

### 🔴 CONSERVATIVE — Production Safe
*Default deny. Block everything not explicitly allowed.*
Best for: CISOs, regulated industries, production agents.

```json
{
  "persona": "conservative",
  "default_stance": "block",
  "mcp_servers": { "*": { "unknown_tools": "block" } },
  "shell": { "allow": [], "block": ["rm", "curl", "wget", "ssh", "sudo", "chmod"] },
  "file": { "allow": ["read_file"], "block": ["write_file", "delete_file"], "scope": "/workspace/**" },
  "network": { "allowlist": [], "unknown": "block" },
  "audit": "all"
}
```

### 🟡 STANDARD — Engineering Teams
*Allow common read ops. Block destructive actions. Warn on unknowns.*
Best for: Most engineering teams.

```json
{
  "persona": "standard",
  "default_stance": "warn",
  "mcp_servers": {
    "github": { "allow": ["read_file", "list_issues", "search_code"], "block": ["delete_branch", "force_push"] },
    "filesystem": { "allow": ["read_file", "list_directory"], "block": ["delete_file"], "scope": "/workspace/**" },
    "*": { "unknown_tools": "warn" }
  },
  "shell": { "allow": ["git", "npm", "python"], "block": ["rm -rf", "sudo", "ssh"] },
  "network": { "allowlist": ["api.github.com", "api.anthropic.com"], "unknown": "warn" },
  "audit": "all"
}
```

### 🟢 DEVELOPER — Local Dev
*Audit everything. Block only catastrophic risks. Stay out of the way.*
Best for: Individual developers, local experimentation.

```json
{
  "persona": "developer",
  "default_stance": "audit",
  "mcp_servers": { "*": { "unknown_tools": "audit" } },
  "shell": { "block": ["rm -rf /", "sudo rm", "dd if="] },
  "file": { "block": ["/etc/*", "/usr/*", "~/.ssh/*"] },
  "network": { "unknown": "audit" },
  "audit": "all"
}
```

---

## 6. System Architecture

### How MCP Works (Critical Clarification)

MCP is NOT a JSON file that makes API calls. The settings JSON is just a pointer telling Claude Code where to find the MCP server **process**. When Claude Code starts, it launches that process. The MCP server speaks MCP protocol over stdio.

```
Claude Code starts
  → reads ~/.claude/settings.json  ← pointer only
  → launches: python conductguard_mcp.py  ← RUNNING PROCESS (stdio)
  → agent attempts tool call
  → PreToolUse fires → MCP server → GET conductai.ai/api/v1/policy → allow/block
  → PostToolUse fires → MCP server → POST conductai.ai/api/v1/audit → logged
```

### Two Components

**1. MCP Server** — Python process on developer's machine. Ships in `conduct-cli`. Calls ConductAI API for policy + logging. Developer never edits this.

**2. Policy API** — `GET /api/v1/policy` on conductai.ai. Returns persona JSON. Secured by org session token. This is where dynamic propagation happens.

### Policy API Contract

```
GET /api/v1/policy
Authorization: Bearer sess_xyz

Response: {
  "org": "acme-corp",
  "persona": "standard",
  "assigned_by": "user",
  "version": "2026-06-17T10:00:00Z",
  "pre_tool_use": {
    "github:delete_branch": "block",
    "github:read_file": "allow",
    "*:*": "audit"
  },
  "post_tool_use": { "audit_all": true }
}
```

### Minimal MCP Server

```python
# conductguard/mcp_server.py
import httpx, keyring
from mcp.server import Server
from mcp.types import BlockResult, AllowResult

server = Server("conductguard")
POLICY_API = "https://conductai.ai/api/v1/policy"

async def fetch_policy():
    token = keyring.get_password("conductai", "session_token")
    try:
        async with httpx.AsyncClient(timeout=0.5) as client:
            r = await client.get(POLICY_API, headers={"Authorization": f"Bearer {token}"})
            return r.json()
    except:
        return PERSONAS["developer"]  # ponytail: fail-open, add local cache Week 2

@server.pre_tool_use()
async def enforce(tool_name: str, server_name: str, params: dict):
    policy = await fetch_policy()
    rules = policy.get("pre_tool_use", {})
    key = f"{server_name}:{tool_name}"
    decision = rules.get(key) or rules.get(f"{server_name}:*") or rules.get("*:*") or "audit"
    if decision == "block":
        return BlockResult(reason=f"ConductGuard: {key} blocked by policy")
    return AllowResult()

@server.post_tool_use()
async def audit(tool_name: str, server_name: str, result: dict):
    policy = await fetch_policy()
    if policy.get("post_tool_use", {}).get("audit_all"):
        await log_event(tool_name, server_name, result)
    return result
```

---

## 7. Security — API Key & Token Handling

**Three rules, non-negotiable:**

1. Raw API key → exchanged immediately for session token at `POST /api/auth/exchange`, **never stored anywhere**
2. Session token → OS keychain only (`keyring`), never flat files or env vars
3. All output → masked (`sk_live_abc...xyz`), never full key printed

```python
# cli/login.py
import keyring, getpass, httpx

def login():
    api_key = getpass.getpass("Enter your API key: ")  # interactive only, never as CLI arg
    r = httpx.post("https://conductai.ai/api/auth/exchange", json={"api_key": api_key})
    if r.status_code != 200:
        print("✗ Invalid API key"); return
    data = r.json()
    keyring.set_password("conductai", "session_token", data["session_token"])
    api_key = None  # wipe from memory
    print(f"✓ Logged in as {data['email']} ({data['org']})")
    print(f"✓ Credentials stored securely in system keychain")
```

API side: store `hash(session_token)` in DB, not plaintext.

---

## 8. Developer Install Flow

```bash
pip install conduct-cli
conduct login      # interactive prompt → keychain storage
conduct init       # three persona picker → sets org persona via API
conduct install    # writes ~/.claude/settings.json → MCP registered
# Done. Every tool call now governed by live policy.
```

---

## 9. RBAC Roles vs Agent Personas — Two Independent Axes

```
RBAC Roles   →  govern humans inside ConductAI dashboard
Personas     →  govern AI agents in the field
```

These are independent. A Developer (RBAC) can run an agent with persona Conservative.

**RBAC permissions:**
- Admin: create/edit/delete/assign personas, publish policy, all logs, manage members
- Security: create/edit/assign personas, publish policy, all logs
- Developer: view their assigned persona, view own audit logs only
- Viewer: read only

**`assigned_by` field:**
- `"assigned_by": "user"` — developer picked via `conduct init`, can change
- `"assigned_by": "admin"` — centrally locked, developer cannot override

**Flow A (launch):** User picks persona via `conduct init`.  
**Flow B (Month 2):** Admin assigns personas centrally.

**Enterprise pitch:** "Your RBAC controls who sets the policy. Your persona controls what the agent can do. Neither can be bypassed by a developer in the field."

---

## 10. One JSON, Two Sections (MCP + Security)

Same runtime evaluator handles both. Admin publishes once — both update together. No drift.

```json
{
  "persona": "standard",
  "assigned_by": "user",
  "mcp": {
    "github": { "allow": ["read_file", "list_issues"], "block": ["delete_branch", "push"] },
    "*": { "unknown_tools": "audit" }
  },
  "security": {
    "shell": { "block": ["rm -rf", "sudo"] },
    "file": { "block": ["/etc/*", "~/.ssh/*"] },
    "network": { "allowlist": ["api.github.com"], "unknown": "warn" },
    "secrets": { "scan_output": true }
  },
  "audit": { "all": true }
}
```

Generic evaluator:
```python
async def evaluate(policy, context):
    if context.type == "mcp_tool":
        return check_rules(policy.get("mcp", {}), context.server, context.tool)
    if context.type == "shell":
        return check_rules(policy.get("security", {}).get("shell", {}), context.command)
    if context.type == "file":
        return check_rules(policy.get("security", {}).get("file", {}), context.path)
    if context.type == "network":
        return check_rules(policy.get("security", {}).get("network", {}), context.host)
    return policy.get("default_stance", "audit")
```

---

## 11. Monday Launch Checklist

### Must Have
- [ ] Homepage live at conductai.ai
- [ ] `/signup` works via Clerk
- [ ] `pip install conduct-cli` works
- [ ] `conduct login` — interactive, keychain storage
- [ ] `conduct init` — three persona picker
- [ ] `conduct install` — writes Claude Code settings
- [ ] Basic tool call blocked by policy end to end
- [ ] Docs page — install + quickstart

### Explicitly Deferred
- [ ] MCP Control Plane (Month 2)
- [ ] Cross-client Cursor/Windsurf (Week 3-4)
- [ ] Admin-assigned personas / Flow B (Month 2)
- [ ] MCP server risk scoring (Month 2)
- [ ] Tenant isolation for SaaS (Month 2)

---

## 12. Key Decisions

1. **Rows → Personas** — 36 DB rules surfaced as 3 named profiles
2. **No guard_sync** — policy is live API, dynamic by design
3. **One MCP server** — pre/post handlers, calls policy API
4. **One JSON, two sections** — MCP + security in same response
5. **Keychain not files** — session token in OS keychain
6. **MCP governance is post-launch** — personas are the on-ramp
7. **Tease MCP Control Plane on launch** — waitlist CTA below fold
8. **RBAC ≠ Personas** — independent axes
9. **Personas are agent-level** — not user-level
10. **Flow A only at launch** — user picks, admin assignment is Month 2
11. **`assigned_by` field** — separates self-serve from enterprise-locked
12. **Same architecture for security + MCP policies** — one evaluator, one JSON
