# Conduct Platform — Architecture

> How it's built, why decisions were made, and where it's going.

---

## What Conduct Is

Conduct is an **operating layer for AI-assisted engineering teams**. It sits between your developers and their AI coding tools (Claude Code, Codex, Cursor, Windsurf) and provides three compounding capabilities:

```
┌─────────────────────────────────────────────────────────────┐
│                        Developer                            │
│                    Claude Code / Codex / Cursor             │
└───────────────────────────┬─────────────────────────────────┘
                            │  every tool call
                ┌───────────▼───────────┐
                │      ConductGuard     │  ← govern + secure
                │  hook + MCP + policy  │
                └───────────┬───────────┘
                            │  telemetry
                ┌───────────▼───────────┐
                │    Agent Booster      │  ← optimize
                │  symbol index + RTK   │
                └───────────┬───────────┘
                            │  structured output
                ┌───────────▼───────────┐
                │   Conduct Runtime     │  ← automate
                │  YAML playbooks + UI  │
                └───────────────────────┘
```

Each layer works independently but compounds when used together: Guard captures the telemetry that feeds Booster's index, and Booster's token savings fund the budget headroom that Guard enforces.

---

## Tech Stack

| Layer | Choice | Why |
|-------|--------|-----|
| API | FastAPI (Python) | Async-native, Pydantic validation, OpenAPI for free, fast iteration |
| DB | PostgreSQL + SQLAlchemy | RLS for workspace isolation, JSONB for flexible policy fields |
| Migrations | Alembic | Auditable history of every schema change |
| Frontend | Next.js 14 App Router | Server components, good SSE support, Clerk auth integration |
| Auth | Clerk | Handles SSO, org switching, JWT issuance — we verify, not issue |
| CLI | Python (conduct-cli) | Ships as a PyPI package, easy install for all dev machines |
| Workers | Redis + background threads | Lightweight — no Celery overhead for current scale |
| Hosting | Render (API) + Vercel (web) | Zero-ops, scales to zero, preview URLs on every PR |

---

## Layer 1 — ConductGuard

### What it does

Every AI tool call on a developer's machine passes through Guard before it executes. Guard decides: allow, warn, or block. It logs everything.

### How the hook works

```
developer types: Claude Code runs a tool
        ↓
Claude Code fires pre-tool hook
        ↓
conduct hook reads stdin (tool name + input JSON)
        ↓
POST /guard/events  →  API evaluates policies
        ↓
API returns: { decision: "allowed" | "warned" | "blocked", message }
        ↓
hook exits 0 (allow) or 2 (block)
```

The hook is a Python script installed into Claude Code's `settings.json`. It's generated from a template at install time (`conduct install`), which means it's pinned to the workspace token and API URL — no ambient credentials, no global state.

### Why a hook instead of a proxy

A network proxy intercepts traffic but can't understand tool semantics — it sees HTTP, not "this is a Bash tool call with `rm -rf /`". The hook has full access to the structured tool call input, which is what makes pattern matching, path matching, and token-budget checks possible. The tradeoff: the hook must be installed per machine. Guard solves this with `conduct install` and MCP auto-registration.

### Policy engine

Policies are YAML-defined rules stored in PostgreSQL, one set per workspace. Each policy has:

```yaml
rule_id: cmd-injection
match_tool: Bash
match_pattern: "rm\\s+-rf|dd\\s+if=|mkfs\\."
action: block
message: "Destructive shell commands are not allowed."
```

**Matching fields (all optional, ANDed):**
- `match_tool` — exact tool name (`Bash`, `Write`, `Edit`)
- `match_pattern` — regex against the full input JSON string
- `match_path_pattern` — regex against file paths in the input
- `match_tokens_before_gt` — fires when conversation context exceeds N tokens

**Actions:** `block` (exit 2), `warn` (log + continue), `audit` (log silently), `approval` (pause for human review), `inject` (append context to the tool call).

Builtin policies ship as `builtin_policies.yaml` and are auto-seeded to every Guard-enabled workspace on API startup if the file has changed (SHA256-checked). Users can enable/disable individual builtin rules but cannot delete them.

### MCP server (second surface)

Guard also runs as an MCP server. This surfaces `guard_check` and `guard_status` tools directly inside the LLM's tool loop — useful for agents running in agentic mode where hooks fire on every sub-call. The MCP server evaluates the same policy set as the hook.

### Session capture

Every developer session (a continuous Claude Code run) is tracked:
- Machine fingerprint: `hostname`, `client_ip`, `os_info`
- Cumulative token spend and cost
- Event count and violation count

This is how Guard can alert when a developer's machine appears on a new IP or hostname — useful for detecting unauthorized access or machine migration.

### Why we built PII detection as 3 layers

A single regex for "secrets" produces too many false positives on source code. The three-layer approach:

1. **Structural** — formats that are unmistakably secrets (UUIDs in specific positions, base64 blocks, PEM headers). Near-zero false positives.
2. **Bare-in-text** — known vendor prefixes (`sk_live_`, `ghp_`, `xoxb-`). Prefix-locked, high precision.
3. **Context-aware** — keyword (`password`, `api_key`, `secret`) + separator (`=` or `:`) + value. The separator is `[=:]` only — not `"` — to avoid matching dict key closing quotes in source code.

Each layer is independent. A match at any layer triggers the rule.

---

## Layer 2 — Agent Booster

### What it does

Agent Booster reduces the tokens Claude reads per task by giving it a smarter search interface than raw `grep`. Instead of reading entire files, the LLM queries for relevant symbols and gets back only the slices it needs.

### Architecture

```
codebase
    ↓
tree-sitter parser  →  symbol index (functions, classes, methods)
    ↓
MiniLM embeddings   →  vector store (local, ~/.booster/)
    ↓
MCP tools exposed to LLM:
  search_context   — semantic search, returns ranked symbol slices
  smart_read       — read only the relevant parts of a file
  get_symbols      — survey a file's structure before reading
  route_model      — pick the right model tier for the task
```

**Why local embeddings instead of an API?** Zero latency, no cost per query, works offline, no data leaves the machine. The MiniLM model is small enough to run in-process. The tradeoff: index quality is lower than OpenAI embeddings, but for code symbols the structured tree-sitter index compensates.

**Why tree-sitter?** It produces a language-aware symbol graph, not a line-by-line index. This means `search_context("how does auth work")` returns the `require_permission` function body, not every file that contains the word "auth".

**RTK (Rust Token Killer)** works at the shell level — it's a CLI wrapper that strips noise from build output, test results, and git diffs before they reach Claude. Typically 60-90% reduction. It's separate from Booster: Booster reduces what Claude reads, RTK reduces what Claude sees in command output.

---

## Layer 3 — Conduct Runtime

### What it does

The Runtime executes YAML playbooks — structured multi-step automations that combine AI agent blocks, shell blocks, API calls, and conditional logic. Think: "run the incident-responder playbook" instead of writing a prompt every time.

### Compiler + Executor

```
playbook.yaml
     ↓
Compiler  →  validated DAG (blocks + edges)
     ↓
Executor  →  runs blocks in order, passes state between them
     ↓
Run record (stored in DB, streamed to UI via SSE)
```

Each block has a type:
- `brain` — LLM call with a system prompt and tools (agentic or single-turn)
- `run_shell` — shell command in a sandbox (E2B or Modal)
- `api_call` — HTTP request to an external service
- `condition` — branch logic based on previous block output
- `memory` — recall or record context from the workspace knowledge base

**Turn budgets** prevent runaway agent loops. Every `brain` block has a `max_turns` derived from complexity (`small=25`, `medium=50`, `large=100`). The executor enforces this — a block that hits its budget returns what it has, rather than spinning indefinitely.

**Why YAML and not a visual builder as the source of truth?** YAML is versionable, diffable, and reviewable in a PR. The canvas UI is a viewer/editor that reads from YAML — the YAML is the artifact. This means playbooks can be shipped as packages, reviewed like code, and rolled back with git.

### Sandbox execution

Shell blocks run in isolated sandboxes (E2B or Modal) rather than on the API server. This was a deliberate security boundary decision — arbitrary shell execution must never run on the same process as the API. The sandbox backend is configurable per playbook.

---

## Security Principles

### Auth at the resource layer

Every API endpoint has an explicit auth dependency. We don't rely on "the caller is trusted" — even internal MCP tools and block executors hit the same auth checks as external HTTP clients.

### RBAC via DB-seeded permissions

Four roles: `admin`, `security`, `developer`, `viewer`. Permissions are seeded into the DB (`roles → role_permissions → permissions`) and checked via `require_permission("guard.policies.edit")`. Role names are never hardcoded in endpoint logic — only permission strings, which the DB matrix resolves.

### Workspace isolation via RLS

Every Guard table has a `workspace_id` column. PostgreSQL Row-Level Security policies enforce that queries only return rows for the active workspace. This is a belt-and-suspenders measure on top of application-layer filtering.

### MCP is not a security boundary

MCP tools are transport, not auth. If a Conduct API is exposed via MCP, the underlying API endpoint still enforces auth. The MCP hop adds zero security — it's a convenience interface.

---

## Key Design Decisions

| Decision | Rationale | Trade-off |
|----------|-----------|-----------|
| Hook over proxy | Tool-semantic awareness, no MITM TLS complexity | Per-machine install required |
| Policies in DB not files | Per-workspace customization, runtime updates without deploy | YAML is the source of truth, DB is the working copy |
| Async telemetry (Slack + scan) | Tool call latency was blocking on HTTP calls to Slack | Rare: if API dies between commit and background task, one notification is lost |
| Local MiniLM embeddings | Zero cost, zero latency, offline-capable | Lower recall than hosted embeddings on ambiguous queries |
| YAML playbooks as source | Git-versionable, PR-reviewable, packageable | Canvas UI must stay in sync with YAML parser |
| Sequential Alembic migrations | Simple to reason about, clear history | Two devs writing simultaneously must coordinate revision IDs |
| Builtin policy auto-seed | No manual "refresh" button needed after deploys | Seed runs across all workspaces on startup — slow if many workspaces |

---

## Architecture Backlog (known gaps)

- **Local CLI policy cache** — currently every tool call makes an API round trip. A local `~/.conductguard/policy_cache.json` with 60s TTL would make Guard invisible when the API is slow or unreachable.
- **Webhook delivery** — violations trigger Slack alerts but there's no generic webhook for enterprise customers to integrate into their own systems.
- **Alembic timestamp IDs** — sequential integer revision IDs require coordination between developers. Timestamp-based IDs are conflict-free.
- **Per-developer policy overrides** — workspace policies apply to everyone. Power users may need exceptions.

---

## End-to-End Flow

```
Developer runs: claude "fix the auth bug"
                    │
         Claude Code starts a session
                    │
         Guard hook registers session
         POST /guard/events (tool=guard_activity)
                    │
         Claude Code calls Bash("grep -r auth src/")
                    │
         Hook fires → POST /guard/events
                    │
         API checks policies:
           - match_tool: Bash ✓
           - match_pattern: no match
           → decision: allowed
                    │
         [background] write GuardAuditEvent
         [background] update GuardSession totals
                    │
         Claude Code calls Write("src/auth.py", ...)
                    │
         Hook fires → POST /guard/events
         API checks: match_path_pattern: "prod/" — no match
         → decision: allowed
                    │
         Session ends → GuardSession.ended_at set
         Final totals: tokens, cost, savings written
```

---

## Contributing

The platform is organized as a monorepo:

```
apps/
  api/          FastAPI backend (Python)
  web/          Next.js frontend (TypeScript)
packages/
  conduct-cli/  CLI + hook installer (Python, ships to PyPI)
tools/
  booster/      Agent Booster MCP server (Python)
```

Before adding a new API endpoint: check `CLAUDE.md` for the permission string to use (`require_permission()`), never `require_workspace_role()`. Every endpoint needs an explicit auth `Depends`.

Before adding a new Guard policy: add it to `builtin_policies.yaml` — it will auto-seed to all workspaces on next deploy.
