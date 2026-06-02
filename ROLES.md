# Conduct Platform — Role & Permission Matrix

## Roles

| Role | Description |
|---|---|
| **admin** | Workspace owner. Full access to everything — platform and Guard. |
| **security** | Security / compliance persona. Full Guard write access. Platform read + credentials/audit. Cannot build or run workflows. |
| **developer** | The builder and AI tool user. Creates and runs workflows. Guard is read-only; sees only own activity and spend. |
| **viewer** | Read-only observer. Cannot write anything. Sees own Guard activity only. |

> **Design principle:** Guard write access (policies, budgets, settings) is restricted to `admin` and `security` only. `developer` and `viewer` are consumers, not managers.

---

## Permission Matrix

| Capability | admin | security | developer | viewer |
|:---|:---:|:---:|:---:|:---:|
| **Platform — Workflows** | | | | |
| View workflows | ✓ | ✓ | ✓ | ✓ |
| Create / edit workflows | ✓ | — | ✓ | — |
| Delete workflows | ✓ (all) | — | ✓ (own only) | — |
| Trigger runs | ✓ | — | ✓ | — |
| View runs | ✓ | ✓ | ✓ | ✓ |
| **Platform — Marketplace & Eval** | | | | |
| Browse marketplace | ✓ | ✓ | ✓ | ✓ |
| Install from marketplace | ✓ | — | ✓ | — |
| View eval / observability | ✓ | ✓ | ✓ | ✓ |
| **Platform — Settings** | | | | |
| Edit workspace (name, plan) | ✓ | — | — | — |
| Manage members (invite, remove, change role) | ✓ | — | — | — |
| View environments (select for playbook install) | ✓ | ✓ | ✓ | — |
| Add / delete credentials | ✓ | ✓ | — | — |
| Audit log | ✓ | ✓ | — | — |
| **Guard — Activity** | | | | |
| View activity dashboard | ✓ | ✓ | own only | own only |
| View activity log | ✓ | ✓ | own only | own only |
| Export activity CSV | ✓ | ✓ | — | — |
| **Guard — Spend** | | | | |
| View spend | ✓ | ✓ | own only | — |
| Set budgets | ✓ | — | — | — |
| **Guard — Policies** | | | | |
| View policies | ✓ | ✓ | ✓ | ✓ |
| Toggle / add / delete policies | ✓ | ✓ | — | — |
| **Guard — Settings** | | | | |
| Edit Slack channel / notifications | ✓ | — | — | — |

---

## UI Contract — Credential Access

Developers can view and select existing environments when installing a playbook, but cannot create or delete credentials. If no environment exists when a developer installs a playbook, the UI must show:

> "No environment available. Ask your admin or security team to create one."

Never show a dead error or a disabled "Add credentials" button with no explanation.

---

## Guard Role Resolution

Guard resolves the effective role in this priority order:

1. **Guard team members** — explicit role set in `guard_members` table (`owner` → `admin`, `security` → `security`, `developer` → `developer`)
2. **Platform workspace members** — fallback via `workspace_users` (`admin` → `admin`, `editor`/`developer` → `developer`)
3. **Default** — `viewer` (safe fallback if user is not found in either)

---

## Naming rationale

`developer` was chosen over `editor` because:
- Conduct's primary users are software developers building and running AI workflows
- Guard monitors *developer* activity — the name closes the loop
- Mirrors usage in Make (Integromat), Temporal, and other developer-facing platforms

---

## Implementation

| Layer | Location |
|---|---|
| Frontend hook | `apps/web/src/hooks/useGuardRole.ts` |
| Permission matrix | `ROLE_PERMISSIONS` constant in `useGuardRole.ts` |
| DB (Guard members) | `guard_members.role` — values: `owner`, `security`, `developer` |
| DB (Platform members) | `workspace_users.role` — values: `admin`, `editor` |
| API auth | `get_guard_org_id` in `apps/api/app/core/auth.py` |

> **Note:** Platform `workspace_users.role` currently uses `editor` — this maps to `developer` in Guard role resolution. A future migration can rename this column value once the frontend is updated.

---

## Future — DB-backed RBAC

Currently roles and the permission matrix live in code (`useGuardRole.ts`). User→role assignments already live in DB (`guard_members`, `workspace_users`). The cycle is broken: changing a permission requires a code deployment.

Target schema to close the cycle:

```sql
-- What roles exist
CREATE TABLE roles (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id UUID REFERENCES workspaces(id) ON DELETE CASCADE,  -- NULL = platform default
  name        TEXT NOT NULL,          -- admin | security | developer | viewer
  description TEXT,
  is_system   BOOLEAN DEFAULT false,  -- system roles cannot be deleted
  created_at  TIMESTAMPTZ DEFAULT now()
);

-- What actions are possible
CREATE TABLE permissions (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name        TEXT UNIQUE NOT NULL,   -- e.g. guard.policies.edit
  description TEXT
);

-- Which roles have which permissions
CREATE TABLE role_permissions (
  role_id       UUID REFERENCES roles(id) ON DELETE CASCADE,
  permission_id UUID REFERENCES permissions(id) ON DELETE CASCADE,
  PRIMARY KEY (role_id, permission_id)
);

-- Which users have which roles (replaces guard_members + workspace_users)
CREATE TABLE user_roles (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id      TEXT NOT NULL,          -- Clerk user ID
  role_id      UUID REFERENCES roles(id) ON DELETE CASCADE,
  workspace_id UUID REFERENCES workspaces(id) ON DELETE CASCADE,
  granted_at   TIMESTAMPTZ DEFAULT now(),
  UNIQUE (user_id, role_id, workspace_id)
);
```

**Permission name convention:** `<module>.<resource>.<action>` — e.g. `guard.policies.edit`, `guard.activity.view_all`, `platform.workflows.create`

**Migration trigger:** When the first customer asks for custom roles per workspace. Until then, the 4 system roles and the code-based matrix are sufficient.
