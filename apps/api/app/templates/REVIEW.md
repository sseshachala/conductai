# REVIEW.md — Quality Gate

Before any agent declares work done, every applicable item here must be checked.
Before any human opens a PR, run through this list.

## The standard
Done means: the next engineer reads this in 6 months with no questions.

---

## Pre-ship checklist

### Auth
- [ ] Every new endpoint has an auth dependency in its signature
- [ ] New endpoints use permission names, not hardcoded role strings
- [ ] Intentionally public endpoints are in the allowlist with a documented reason
- [ ] Auth coverage CI gate passes

### Tests
- [ ] Test suite passes — no `|| true`, no unexplained skips
- [ ] New logic has a test that fails if the logic breaks
- [ ] Mocks match the real interface they replace

### Security
- [ ] No user input concatenated into SQL
- [ ] File paths from user input are bounded to the project root
- [ ] No secrets in logs, error messages, or API responses

### Database
- [ ] One migration per change
- [ ] Migration tested locally before push
- [ ] `downgrade()` defined
- [ ] Destructive changes staged: stop writing first, then drop

### Impact — all layers, every change
- [ ] CLI / SDK — any command, config key, or output format changed?
- [ ] Frontend — any route, field name, or response shape changed?
- [ ] API — breaking change for existing callers?
- [ ] DB — migration needed?

### Self-review
- [ ] Read your diff as if reviewing a stranger's PR
- [ ] Delete everything added "just in case"
- [ ] Remove all debugging artifacts
- [ ] Every name describes what it does — no comment needed

---

## What machines should check (automate these)
| Check | Command |
|---|---|
| Auth coverage | `python scripts/check_auth_coverage.py` |
| Tests | `pytest tests/ -x -q` |
| Type check | `npm run typecheck` |
| Lint | `npm run lint` |

---

## Principle
The gate is the work. A PR that passes this list from a non-engineer is safe to merge.
A PR that skips it is unsafe regardless of who wrote it.

<!-- Layer 0: Team OS · conductai.ai/team-os -->
