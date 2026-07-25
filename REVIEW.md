# REVIEW.md — Conduct Quality Gate

This file encodes what a senior engineer holds in their head before shipping.
Agents read this before declaring any task complete. Humans read this before opening a PR.

**Rule:** if a PR passes this checklist, it is safe to merge regardless of who wrote it.

---

## The Standard

Done means: the next engineer can read this in 6 months without needing to ask you anything.
Not done means: it works today but leaves a trap for someone later.

---

## Pre-Ship Checklist

### 1. Auth (non-negotiable)
- [ ] Every new `@router.{method}` endpoint has an auth `Depends()` in its signature
- [ ] New endpoints use `require_permission("platform.xyz")`, not `require_workspace_role()`
- [ ] Intentionally public endpoints are added to the ALLOWLIST in `apps/api/scripts/check_auth_coverage.py` with a documented reason
- [ ] `python scripts/check_auth_coverage.py` passes clean

### 2. Token architecture
- [ ] `cond_run_*` tokens are minted ONLY in `executor.py` — never in webhooks, triggers, or routers
- [ ] `cond_cred_*` tokens are minted ONLY by `mint_cred_token()` in `executor.py`
- [ ] No endpoint or background task mints a token and also validates it (separation of concerns)
- [ ] `CONDUCT_RUN_TOKEN`, `CONDUCT_RUN_ID`, `CONDUCT_API_URL` are injected via env vars on both mint paths (Layer 1 + Layer 3)

### 3. Migrations
- [ ] One migration file per change — no bundling unrelated schema changes
- [ ] SQL verified locally before push: `alembic upgrade head` on a local DB
- [ ] `downgrade()` is defined and tested
- [ ] No `DROP COLUMN` without a preceding deploy that stops writing to the column

### 4. Tests
- [ ] `pytest tests/ -x -q` passes — no `|| true`, no skipped tests hiding failures
- [ ] New logic has at least one test that will fail if the logic breaks
- [ ] Mocks match the real interface they replace (mock drift = silent bugs)

### 5. Security
- [ ] No user input concatenated into SQL — parameterised queries only
- [ ] File paths resolved and verified to stay within project root before reading
- [ ] No secrets, tokens, or PII in logs, error messages, or API responses
- [ ] No `verify=False` on HTTPS calls, no `rejectUnauthorized: false`

### 6. Impact analysis — all 4 layers, every time
- [ ] **CLI** — did this change a command, env var, config key, or output format the CLI reads?
- [ ] **Frontend** — did this change a route path, response field name, or shape the UI depends on?
- [ ] **API** — is this a breaking change for existing callers (webhooks, MCP, external integrations)?
- [ ] **DB** — does this add, drop, or rename schema in a way that requires a migration?

### 7. Self-review
- [ ] Read your own diff as if reviewing a stranger's PR
- [ ] Delete everything added "just in case" — YAGNI
- [ ] Remove all debugging artifacts: `print()`, commented-out blocks, TODO without a ticket number
- [ ] Every name (variable, function, endpoint) describes what it does — no comment needed to explain it
- [ ] No backwards-compatibility shims for things that have no callers

---

## What CI Catches Automatically

These run on every push and fail the build:

| Check | Command |
|---|---|
| Auth coverage | `python scripts/check_auth_coverage.py` |
| Tests | `pytest tests/ -x -q` |
| Migrations | `alembic upgrade head` |
| Web typecheck | `npm run typecheck` |
| Web lint | `npm run lint` |

If any of these fail, the PR cannot merge. Fix the gate, not the gate-check.

---

## What Only Humans Can Check

CI catches structure. These require judgement:

- **Right abstraction?** Did I build for a problem that doesn't exist yet, or the one that does?
- **Readable?** Will the next engineer understand why this was done, not just what it does?
- **Blast radius?** Is this change scoped to what was asked, or does it touch things it shouldn't?
- **Simpler version?** Is there a 20-line version that handles 95% of cases before reaching for the 200-line version?
- **Reversible?** If this turns out to be wrong, can we undo it without a data migration or a customer call?

---

## Principles

**The gate is the work.**
Agents can make production-ready changes. What makes that safe is not the prompting — it's the gate. A PR that passes this checklist from a non-engineer is safe to merge. A PR that skips it is unsafe regardless of who wrote it.

**Write it down, not down-ish.**
"Use your judgement" is not a standard. This document is the standard. Ambiguity in a review checklist means the bar gets lower every PR.

**The ALLOWLIST is a decision, not a shortcut.**
Every intentionally-public endpoint in `check_auth_coverage.py` was a deliberate call with a documented reason. Adding to it requires the same rigour as adding a public API.

**One source of truth.**
If the standard lives in three places, it lives in zero places. This file is it. When the standard changes, update it here.

---

## Related files
- `CLAUDE.md` — project memory and architecture context
- `DESIGN.md` — colour palette and UI consistency rules
- `ROLES.md` — permission matrix (use before any auth/RBAC work)
- `apps/api/scripts/check_auth_coverage.py` — machine-enforced auth gate
- `.github/workflows/ci.yml` — full CI definition
