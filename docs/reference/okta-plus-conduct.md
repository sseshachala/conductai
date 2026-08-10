# Okta + Conduct — Reference Architecture

**Status:** Shipping (#1052 Phase 3 complete)
**Last updated:** 2026-08-10

Okta owns identity. Conduct governs authority. This doc explains the split, the flow, and the guarantees.

## The one-line

Your AI builder issues an Okta JWT for its agent. Conduct verifies that JWT, resolves it to a governed identity, and enforces your workspace's rules on every call — without ever holding a copy of your Okta credentials.

## Sequence

```
┌───────────────┐   ┌──────┐   ┌───────────────┐   ┌────────────┐   ┌────────────┐
│ Agent Builder │   │ Okta │   │ Conduct Sync  │   │  Agent JWT │   │  Conduct   │
│  (Claude,     │   │      │   │  (Phase 1)    │   │  Auth      │   │  Cedar     │
│  Gemini,      │   │      │   │               │   │  (Phase 3) │   │  Engine    │
│  Anthropic)   │   │      │   │               │   │            │   │            │
└───────┬───────┘   └───┬──┘   └───────┬───────┘   └─────┬──────┘   └──────┬─────┘
        │               │              │                 │                 │
        │─register app─▶│              │                 │                 │
        │◀──client_id───│              │                 │                 │
        │               │              │                 │                 │
        │               │◀────GET /api/v1/apps───────────│                 │
        │               │                                │                 │
        │               │─sync AgentIdentity rows───────▶│                 │
        │               │  source='okta', source_id=cid  │                 │
        │               │                                │                 │
        │─get JWT─────▶│                                │                 │
        │◀──RS256 JWT──│                                │                 │
        │              │                                │                 │
        │─────────────Bearer <jwt>─────────────────────▶│                 │
        │                                                │─verify──────────│
        │                                                │  (sig + iss +   │
        │                                                │   aud + exp +   │
        │                                                │   lifecycle)    │
        │                                                │                 │
        │◀──────────────200 / 401 with audit event──────│─decide (Cedar)─▶│
```

## Split of concerns

| Concern | Owned by |
|---|---|
| Who is this agent? | **Okta** — issues the client_id, signs the JWT |
| Is this JWT genuine? | **Conduct** — RS256 sig + iss + aud + exp checks |
| Should this agent be allowed to act right now? | **Conduct** — lifecycle_state, workspace scope, Cedar rules |
| Where's the audit trail? | **Conduct** — hash-chained GuardAuditEvent per verify + per action |
| Key rotation | **Okta** — Conduct fetches JWKS on cache miss |
| Deprovisioning | **Okta** (identity plane) + **Conduct** (authority plane) — either can revoke |

## What Conduct verifies (non-negotiable)

- `alg` MUST be RS256. HS256, `none`, and any symmetric alg are rejected outright at the header gate — no signature check runs on a downgraded token.
- `iss` MUST match the issuer configured on the workspace's Okta integration row. There is no trust-by-default for any Okta tenant.
- `aud` MUST match the configured audience. String or list per RFC 7519.
- `exp` MUST be in the future (30 s clock-skew allowance).
- `iat` / `nbf` if present, must be in the past.
- Signature verified against a JWKS-fetched RSA public key matching the token's `kid`. Unknown `kid` triggers one JWKS refresh, then fails cleanly.
- The `sub` claim must match a synced `AgentIdentity` row with `source='okta'`.
- `lifecycle_state` must be `active` — deactivated or expired identities cannot authenticate even with a signature-valid JWT.

Every verify attempt writes one hash-chained audit event (`tool_call='auth.okta_jwt.verify'`) — success or failure. See #1057.

## Failure modes we handle

- **Revocation lag.** When you deactivate an identity in Okta, its already-issued JWTs remain signature-valid until their `exp`. Conduct closes the gap: sync updates `lifecycle_state`, and the lifecycle guard rejects subsequent requests even before Okta's token TTL kicks in. Absolute freshness requires a webhook/SCIM link — that's Phase 2 (#1051).
- **JWKS unreachable.** If Conduct can't reach Okta's JWKS endpoint, verification fails closed (401). Every request is refused on a network partition.

## Setup — 20 minutes

Assumes you already have Conduct installed and a workspace.

1. **Okta admin** — create an OAuth authorization server (or use "default"). Register a service app (client_credentials grant) for your agent. Note the `client_id`, `client_secret`, issuer URL (`https://{domain}/oauth2/{server}`), and audience.
2. **Conduct — sync identities** (Phase 1). On `/agent-identity`, expand the Okta card. Enter your domain and an admin SSWS token. Click **Sync now**. Your service app appears as an AgentIdentity with `source='okta'`.
3. **Conduct — JWT auth config** (Phase 3). On the same card, fill in **Issuer** and **Audience**, toggle **Enabled**, click **Save JWT config**. Feature ships opt-in per-workspace; nothing changes for anyone else until they flip it on.
4. **Test** — from your agent host:
   ```
   curl -s -X POST "https://{domain}/oauth2/{server}/v1/token" \\
     -u "{client_id}:{client_secret}" \\
     -d "grant_type=client_credentials&scope=agent.act"
   ```
   Grab the `access_token`, then simulate:
   ```
   conduct guard simulate --as-okta-agent <jwt>
   ```
   Should print your identity name, source_id, lifecycle_state.
5. **Verify enforcement** — deactivate the identity via the Conduct UI. Re-run the simulate command. Expect a 401 with `Agent identity is deactivated`.

## Identity vs authority

Okta answers "who is this actor?" — that's identity plane.
Conduct answers "what is this actor allowed to do, right now, in this workspace?" — that's authority plane.

The two planes are separable on purpose. Defense in depth — a permissive ruleset can't grant access to an unknown Okta identity, and a revoked Okta identity can't reach a permissive ruleset.

## Related

- Phase 1 (identity sync) — #1036, shipped
- Phase 2 (SCIM/webhook revocation) — #1051, planned
- Phase 3a (JWT verifier) — #1055, shipped as PR #1058
- Phase 3b (bridge + config + lifecycle enforcement) — #1056, shipped as PR #1060
- Phase 3c (E2E tests + CLI + this doc + rollout) — #1057
