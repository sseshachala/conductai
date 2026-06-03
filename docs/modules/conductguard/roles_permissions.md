# ConductGuard — Roles & Permissions

ConductGuard uses a 4-role system shared with the Conduct platform. Guard write access (policies, budgets, settings) is restricted to `admin` and `security`. `developer` and `viewer` are consumers — they can see their own activity but cannot modify team settings.

---

## Roles

| Role | Description |
|---|---|
| **admin** | Workspace owner. Full access to everything — platform and Guard. |
| **security** | Security / compliance persona. Full Guard write access. Cannot build or run workflows. |
| **developer** | The AI tool user. Guard is read-only; sees only own activity and spend. |
| **viewer** | Read-only observer. Sees own Guard activity only. Cannot write anything. |

---

## Guard Permission Matrix

| Capability | admin | security | developer | viewer |
|:---|:---:|:---:|:---:|:---:|
| **Activity** | | | | |
| View activity dashboard | ✓ | ✓ | own only | own only |
| View activity log | ✓ | ✓ | own only | own only |
| Export activity CSV | ✓ | ✓ | — | — |
| **Spend** | | | | |
| View spend | ✓ | ✓ | own only | — |
| Set budgets | ✓ | — | — | — |
| **Policies** | | | | |
| View policies | ✓ | ✓ | ✓ | ✓ |
| Toggle / add / delete policies | ✓ | ✓ | — | — |
| **Settings** | | | | |
| Edit Slack channel / notifications | ✓ | — | — | — |
| Manage team members | ✓ | — | — | — |

---

## Role Resolution

Guard resolves the effective role in priority order:

1. **Guard team members** — explicit role set in `guard_members` (`owner` → `admin`, `security` → `security`, `developer` → `developer`)
2. **Platform workspace members** — fallback via `workspace_users` (`admin` → `admin`, `editor`/`developer` → `developer`)
3. **Default** — `viewer` (safe fallback if the user is not found in either table)

This means a developer who joined the Conduct workspace but hasn't been added to the Guard team explicitly will see Guard pages in read-only mode with only their own data.

---

## Frontend Enforcement

The `useGuardRole` hook resolves the current user's effective role client-side and exposes:

```ts
const { role, can } = useGuardRole()

can("edit_policies")   // true for admin, security
can("view_spend")      // true for admin, security, developer (own only)
can("set_budgets")     // true for admin only
```

All write actions (policy toggle, budget save, settings update) are gated behind `can(...)` checks. UI controls are hidden or disabled for roles without access — not just blocked at the API layer.

---

## API Enforcement

Every Guard API endpoint verifies role at the resource layer via `Depends(get_current_user)`. Role checks are not bypassed for MCP callers or internal services. The principle: auth at the resource, every time.

---

## Changing a Member's Role

Admins can change a member's Guard role from **Guard → Team** in the dashboard. Changing a role takes effect on the next policy sync (within 60 seconds).

---

## Full Platform Matrix

See [ROLES.md](../../../../ROLES.md) for the complete platform + Guard permission matrix including workflow, marketplace, credentials, and audit log access.
