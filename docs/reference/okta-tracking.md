# Tracking Okta-identified agents in Conduct

**Status:** Shipping
**Last updated:** 2026-08-11
**Companion doc:** [okta-plus-conduct.md](./okta-plus-conduct.md) — reference architecture + setup

Once an Okta agent is synced into Conduct it becomes a first-class `AgentIdentity` row and is tracked the same way any Conduct-native agent is. This doc names every field, timestamp, and audit signal that lets you answer common questions about Okta-provisioned agents.

## Where they show up

- **Registry** — `/agent-identity?tab=identities`. Each Okta agent is a row with `source='okta'` and one of the Okta subtypes in `platform_of_origin` (`oidc_client`, `flow`, `okta_flow_sso`, `okta_import`).
- **Source filter chip** — the Okta card's "identities synced" link jumps into the Identities tab with the filter pre-applied (`?tab=identities&source=okta`).
- **Introspection** — `GET /auth/whoami` with any Bearer token echoes the resolved identity (name, source, source_id, tier, lifecycle). Same view Conduct uses internally.

## Fields that identify + describe

| Field | Source | Meaning |
|---|---|---|
| `source` | Sync | `'okta'` for anything provisioned from an Okta tenant |
| `source_id` | Sync | Okta `client_id` — stable across renames, unique per app |
| `platform_of_origin` | Sync | Which Okta surface produced it (`oidc_client`, `flow`, `okta_flow_sso`, `okta_import`) |
| `name` | Sync | Human-readable app name from Okta (`label` field) |
| `owner_user_id` | Sync + manual | Owner enriched from `/api/v1/apps/{id}/users`; can be reassigned via PATCH |
| `risk_tier` | Manual | `tier_1` \| `tier_2` \| `tier_3` — admin-set, drives Cedar policy `match_agent_risk_tier` |
| `agent_role_id` | Manual | Optional role assignment for RBAC-style scoping |

## Timestamps — what each one tells you

| Column | Updated when | Answers |
|---|---|---|
| `created_at` | First sync brought the identity in | "When did we first see this Okta app?" |
| `last_used_at` | Any successful auth (`guard/routers/proxy.py:296`, `mcp.py:1151`, `auth/cli_token.py:68,174`) — same path used for `cond_agt_*` tokens, so Okta JWTs update it too when the verifier resolves them | "Is this agent still calling us? When last?" |
| `last_certified_at` | Manual `Certify` button (POST `/agent-identities/{id}/certify`); auto-clears `pending_review` → `active` | "Has an owner recently attested this agent should still exist?" |
| `deactivated_at` | Set when `lifecycle_state` flips to `deactivated` (manually or via Okta sync when tenant status is `INACTIVE`); cleared on `→active` | "When did this identity get shut down?" |

`last_used_at` is the single most useful signal for detecting drift — an Okta agent that's `active` but hasn't hit `last_used_at` in 90 days is either abandoned or the OAuth flow broke.

## Audit trail

Every Okta JWT verify — success or failure — writes one hash-chained `GuardAuditEvent`:

- `tool_call = 'auth.okta_jwt.verify'`
- payload includes: `agent_identity_id`, `source_id` (Okta client_id), `iss`, `aud`, `outcome` (`ok` / `expired` / `bad_signature` / `wrong_iss` / `wrong_aud` / `identity_deactivated` / `unknown_kid`), and the `jti` if present.

Filter the Guard Activity page by `tool_call:auth.okta_jwt.verify` to see the full verify stream for the workspace. Every subsequent action gated by the same identity carries `agent_identity_id` on its own audit event, so a single agent's session can be reconstructed as: `verify → LLM call → tool call → Cedar decision → response`.

The chain is hash-linked (`prev_hash` per row) so tampering is detectable.

## Common questions, mapped to fields

| "How do I…" | Where to look |
|---|---|
| See all Okta agents in this workspace | `/agent-identity?tab=identities&source=okta` |
| Find an agent by Okta client_id | Same page, `source_id` matches; also `GET /agent-identities?workspace_id=…` |
| Confirm an agent is currently allowed to act | `lifecycle_state == 'active'` in the row |
| See what an agent has done recently | Guard Activity page, filter by `agent_identity_id` |
| Prove we blocked a deactivated agent | Guard Activity, `outcome:identity_deactivated` on `auth.okta_jwt.verify` |
| Find abandoned agents | Sort Identities by `last_used_at` ascending; anything with `never` or an old date is a candidate to review |
| Attest an agent is still owned | `Certify` button on the row |

## Enforcement × tracking

Tracking is not just observability — the same fields drive enforcement:

- `lifecycle_state in ('deactivated','expired')` → `apps/api/app/core/auth.py:222,363,886` hard-blocks the token before any downstream code runs.
- `risk_tier` → `apps/api/app/modules/guard/cedar_adapter/mapper.py:248` exposes it to Cedar as `context.risk_tier`; policies can match on it (e.g. block tier_3 agents from `/refund`).
- `agent_identity_id` → `apps/api/app/core/credentials.py:248` scopes broker-issued run credentials.

The Identity registry is not documentation — it is the enforcement state. Deactivating a row here revokes on the next auth check.

## What we don't track today

- **Real-time Okta revocation.** Deactivate in Okta and Conduct picks it up on the next sync (or when the JWT expires). Absolute freshness is Phase 2 (SCIM/webhook, #1051).
- **Per-tool call chains rolled up per agent.** Available via Guard Activity filter today; a dedicated "agent activity" pane is on the roadmap.
- **Staleness auto-flip.** Cadence-driven `pending_review` transitions when `last_certified_at + cadence_days < now()` are not yet wired — certification is attestation only.
