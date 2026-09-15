# apps/api/scripts/

API-only smokes and one-off tools. These run against a **local API** —
they need `DATABASE_URL`, KMS material, or seeded workspaces to work.

If you want a prod smoke, use `scripts/smoke_all.sh` at the repo root
(which invokes the API smokes only when `DATABASE_URL` is set).

## Smokes

| File | What it verifies |
|---|---|
| `proxy_smoke.sh` | 3-provider Gateway HTTP round-trip; asserts `guard_audit_events.agent_identity_id` (#1971 Phase 0) and `guard_audit_events.route` (#1973) both populate. |
| `smoke_api.sh` | Tier-2 curl smoke covering non-Guard API endpoints. |
| `smoke_anthropic_migration.py` | One-off Anthropic model-catalog migration verify. |

## Tools (seeding / codegen)

- `seed_e2e_workspace.py`, `seed_anthropic_key.py`, `seed_guard.py`, `seed_skill_packs.py`
- `check_auth_coverage.py`, `check_sys_modules_ratchet.py`
- `generate_schema.py`, `generate_guard_enforcement_coverage.py`
- `normalize_env_var_keys.py`, `validate_all_skill_packs.py`

Run: `bash apps/api/scripts/proxy_smoke.sh` (local DB required).
