# CLAUDE.md — [Your Project Name]

## About this project
{{ One paragraph: what this codebase does, who uses it, what problem it solves. }}

**Stack:** {{ e.g. FastAPI + PostgreSQL + Next.js + Redis }}

---

## Before starting any task

1. Read `REVIEW.md` — every task ends with this checklist
2. Check the relevant standard in `standards/` if your change touches auth, security, or the database
3. Run the test suite before and after: `{{ your test command }}`

---

## What agents should never do
- {{ e.g. Never mint tokens outside executor.py }}
- {{ e.g. Never push directly to the main branch }}
- {{ e.g. Never skip the downgrade() step in a migration }}

## The patterns we use
- **Auth:** {{ e.g. require_permission("platform.xyz") — not require_workspace_role() }}
- **DB queries:** {{ e.g. SQLAlchemy ORM, parameterised only — no f-string SQL }}
- **Logging:** {{ e.g. structlog with snake_case keys — no print() in production code }}

---

## Security rules (non-negotiable)
- Every API endpoint requires an auth dependency
- User input is never concatenated into SQL
- Secrets and tokens are never logged or returned in API responses

---

## CI gates (these must pass before merging)
```bash
{{ your test command }}      # Tests — no || true
{{ your lint command }}      # Lint
{{ your typecheck command }} # Types
```

---
<!-- Layer 0: Team OS · conductai.ai/team-os -->
