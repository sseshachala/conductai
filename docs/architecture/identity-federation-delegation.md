# Federation delegation (Phase 3)

Phase 3 adds approved external principals, explicit caller bindings and expiring
grants. MCP enforcement is shared by `/mcp` and `/guard/mcp`; no PCAI-specific
authentication branch or feature flag is introduced. Existing unbound callers
retain their service-only behavior. CLI setup and UI components are unchanged.

## Supported scope

The initial delegated capabilities are `mcp.guard_check` and
`mcp.guard_check_prompt`, on the authenticated workspace only. These authorize
policy checks, not tool execution, provider inference, a workflow, or access to
other workspace data. There are no wildcard grants. Other delegated tool calls
are denied pending their resource-specific authorization adapters.

This stage binds dedicated Conduct service (`cond_api_*`) Agent identities.
OAuth/CLI session credentials cannot be bound. Unconfigured OAuth and service
clients continue using normal authentication. Do not reuse the dedicated MCP
credential as a federated Gateway credential: Gateway ingress enforcement is
Phase 5 and is not activated by this MCP implementation.

## Administration

Existing `platform.workspace.edit` authorization protects all configuration.
Trust settings may now be `active`, `draft`, or `disabled`. An active trust alone
does not activate a caller: the administrator must explicitly save its binding.

PUT endpoints below `/workspaces/{workspace_id}/federation`:

- `/principals/{uuid}`: exact issuer + subject, human/workload kind, status,
  approved actions and expected revision.
- `/bindings/{uuid}`: calling service Agent UUID, connection UUID, status,
  approved actions and expected revision.
- `/grants/{uuid}`: binding UUID, principal UUID, status, approved actions,
  expiration and expected revision.

Creation requires revision 0. Updates require the current revision. Identity
keys and binding targets are immutable. Unknown principals are denied; token
claims cannot provision console users, membership or roles. Grant permissions
must be within both caller and principal approvals. Runtime intersects all three
sets again, so reducing an approval immediately constrains existing grants.

Disabled bindings are retained and continue requiring identity. No delete or
service-only downgrade endpoint is provided. Re-enabling requires explicit
administrator action. Disabling a principal, grant, binding or connection denies
new checks. JWT signature validation cannot detect immediate IdP-side revocation
before token expiry; local disabling is the immediate revocation mechanism.

## Request contract

Keep the Conduct service credential in `Authorization: Bearer ...`. Send the
selected connection UUID as `Conduct-Federation-Connection` and a valid access
JWT as `Conduct-Subject-Token` on each JSON-RPC request. Duplicate headers, unknown
selections, unapproved subjects and missing evidence fail closed. Required identity
comes from the authenticated caller's stored binding, not the optional header.

No raw subject token is placed in tool arguments, sessions, policy contexts,
audit records or provider requests. The verified context is immutable and
request-local. The same MCP session ID can carry different principals without
caching one user's authority. Tool use rechecks local state and evidence expiry;
a previously verified or persisted context is not perpetual authorization.

Identity failures at ingress return HTTP 401/403/503 and JSON-RPC error data with
`identity_required: true` plus a stable `code`. A failure at dispatch uses the
MCP `isError` result with the same marker/code in `structuredContent`. Phase 4
must treat both forms as non-bypassable, even if legacy transport fail-open is on.
Generic SSE keepalives and session termination carry no tool execution authority;
every POST is independently checked.

## Persistence and evidence

Migration 0155 adds tenant-composite foreign keys and forced PostgreSQL RLS on
connection/principal/binding/grant rows. Workspace transaction context is set by
trusted code. A unique index supports the Agent composite key without the
exclusive-lock constraint pattern fixed in #2292. Lock waits are bounded and
startup migrations use the shared migration lock.

Version-1 `AuditLog` entries record verified/denied ingress and link Guard decisions
to caller, principal, grant, connection revision, scope and request ID. Raw tokens,
subject strings and mapped claims are excluded. These are a reference-based audit
extension: the existing Guard hash chain remains unchanged and does **not**
authenticate this additional metadata. No stronger integrity claim is made.

Migration downgrade refuses to discard populated authorization records. A binary
rollback to pre-enforcement code also requires stopping federated traffic first;
schema protection alone cannot prevent old code ignoring a required binding.

## Verification and remaining scope

`tools/federation/phase3_harness.py` uses real PostgreSQL, real encrypted service
credentials, production auth dependencies, signed JWTs, both ASGI MCP routes,
actual Guard dispatch and persisted audit records. Only JWKS retrieval is injected.
The restricted-role mode checks RLS is active and tests cross-workspace visibility.
CI runs this outside the permissive unit-suite authorization fixtures.

The harness covers unconfigured/configured clients, two principals, shared-session
concurrency, missing/duplicate evidence, foreign connection, expired/wrong-audience
tokens, unsupported actions, revocation (including an already resolved context),
disabled trust/binding, verification outages and linked attribution.

Phase 4 still needs the real LiteLLM plugin/proxy and fail-open handling tests.
Phase 5 adds direct Gateway/workflow adapters. Phase 6 adds standard Conduct UI
and platform readers. Customer PCAI/IdP connectivity, full third-party OAuth client
acceptance, opaque access tokens and signed integration assertions/replay handling
are not demonstrated by this harness.
