# apps/web/e2e/

Frontend Playwright suite. Everything under here is UI-scoped — no API-only
smokes belong here.

## Suites

| File / dir | What it covers |
|---|---|
| `pages.smoke.spec.ts` | Marketing + auth pages render without console errors. |
| `flows/` | End-to-end user journeys (chat, spend, activity, discovery). |
| `flows-per-role/` | Role-scoped journeys (viewer / developer / admin / security). |
| `auth-setup.ts` | Clerk auth-storage bootstrap. Consumed by the other suites. |
| `roles.ts`, `routes.ts` | Shared role and route maps. |

## Running

```bash
# All Playwright suites
pnpm test:e2e

# Just the smoke spec
pnpm test:e2e pages.smoke.spec.ts

# Headed mode for debugging
pnpm test:e2e:headed
```

## Wiring into the umbrella

`scripts/smoke_all.sh` invokes the smoke spec when `SMOKE_WEB=1` is set
(default off because auth-setup needs Clerk cookies present locally).
