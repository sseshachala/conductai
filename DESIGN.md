# Conduct — Design System Rules

Canonical UI rules. Every module, current and future, must follow these. Drift is debt.

## Color palette — Guard decision / governance states

This is the single source of truth. The Guard policies page (`/guard/policies`) is the canonical reference: the BLOCK/WARN/AUDIT chips there set the tone.

| Decision / state | Color | CSS variable | Tailwind / class |
|---|---|---|---|
| **Block** (blocked, terminal stop) | 🔴 Red | `var(--err)`, `var(--err-bg)`, `var(--err-bd)` | `sbadge err` |
| **Warn** (warned, approval-required, timeout) | 🟡 Yellow | `var(--warn)`, `var(--warn-bg)`, `var(--warn-bd)` | `sbadge warn` |
| **Audit** (recorded only, no action) | 🔵 Blue | `var(--info)`, `var(--info-bg)`, `var(--info-bd)` | `sbadge info` |
| **Allowed / Success / OK** | 🟢 Green | `var(--ok)`, `var(--ok-bg)`, `var(--ok-bd)` | `sbadge ok` |

### Rules

1. **Never hardcode hex colors** for these states. Use the CSS variables. They're defined once in `apps/web/src/app/globals.css`.
2. **Block and Failed share red.** Distinguish by **label text**, not color (`Blocked` vs `Failed`).
3. **Audit is blue, not yellow or green.** A common mistake — `audited` events are observational, not violations.
4. **No fifth color.** If a new decision is added (e.g. `quarantined`, `escalated`), map it to the closest of the four above. Don't invent.

### Where this palette appears (current)

- `apps/web/src/components/guard/ActivityRow.tsx` — `DecisionBadge`
- `apps/web/src/components/runs/StatusBadge.tsx` — `blocked` variant
- `apps/web/src/components/runs/RunTrace.tsx` — failure cards (block-level + run-level)
- `apps/web/src/app/(app)/guard/policies/*` — policy chips (original source of truth)
- `apps/web/src/app/globals.css` — `.sbadge.{ok,warn,err,info}` definitions

### For new components

Before picking a color, check this doc. If you find yourself reaching for orange, purple, or any color outside the four, you're wrong — pick the closest semantic match.

---

## Other rules (extend this doc as patterns crystallize)

- **Add modal, delete confirm-by-typing** — see `feedback_ui_consistency` in memory.
- **Env vars are flat key-value** — no per-provider service cards. See `feedback_env_vars` in memory.

When a UI pattern recurs in 2+ modules, codify it here so the third module doesn't reinvent.
