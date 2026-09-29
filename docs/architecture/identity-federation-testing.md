# Identity federation: real harness acceptance matrix

Epic #2283. Companion to [the contract](identity-federation.md).
This matrix is not a claim that federated runtime support is implemented.

## Reuse and isolation

Reuse `tools/security-e2e/compose.yml` and `local.py`: running API/web, PostgreSQL
with applied migrations, Redis, real Clerk sandbox accounts, and Playwright.
Keep production auth/RBAC enabled. Never import `apps/api/tests/conftest.py`
into the black-box harness: that unit suite replaces permission dependencies.
Run with a dedicated disposable database, synthetic users and cleanup.

Reuse the existing sandbox signup/login and token-exchange journey helpers.
The shared `apps/web/e2e-security/support/mcp.ts` probe exercises real HTTP
initialize, initialized notification, tools/list and guard_status invocation
without federation evidence. It handles JSON/SSE envelopes and session IDs.
It does not claim to exercise PKCE consent or delegated identity.

The existing `expectUsableToken` now invokes this probe instead of only listing
tools through the legacy endpoint. It uses real OAuth token exchange to obtain
an Agent credential. That overlap is not two independent authentication tests.
Add a separately provisioned integration Agent-token case and full OAuth
authorization-code/PKCE case in subsequent harness work.

## Release gates

| Case | Setup and observable outcome | Delivery |
| --- | --- | --- |
| Existing exchange / no federation | Real login and exchange, initialize/list/call succeeds without federation headers. | Phase 1 baseline enhancement |
| MCP OAuth / no federation | Register client, authorization/consent, PKCE exchange, initialize/list/call, invalid verifier and code replay rejection. | Before shared auth integration |
| Service Agent token / no federation | Provision caller independently of OAuth; initialize/list/call succeeds, foreign workspace denied. | Before shared auth integration |
| LiteLLM / required federation | Actual plugin and proxy, two signed identities, different Guard decisions and correctly persisted attribution. No Conduct Gateway inference dependency. | Phase 4 |
| Second application / federation | Independent MCP client uses identical contract, with no PCAI branches. | Phase 4 |
| Failure matrix | Missing, expired, wrong-purpose/audience/signature evidence; wrong tenant, revoked grant, disabled connection; no inference or silent downgrade. | Phases 2-5 |
| Mixed clients | Concurrent OAuth/service/federated calls, different users/tenants on shared transports, no cached-context leakage. | Phases 3-5 |
| Gateway ingress | Repeat configured/unconfigured and failure cases through Gateway; inspect provider stub requests for stripped identity evidence. | Phase 5 |
| UI and audit | Tenant-scoped Flight Recorder/Lens displays caller/principal separately and distinguishes policy checks from receipts. | Phases 5-6 |

Use a local signing identity-provider fixture and deterministic provider stub for
federated tests. Do not stub Conduct verification, delegation, policy or database
persistence. Test assertion replay across concurrent workers and key rotation.
Assert positive and negative records via tenant-authorized API plus database
queries where appropriate, and assert zero provider invocations for denied calls.
No raw tokens in test output, screenshots, traces, fixtures or retained artifacts.

## Commands and evidence

For the existing unfederated local baseline (requires the dedicated Clerk test
configuration described in `tools/security-e2e/README.md`):

```sh
rtk proxy python3.11 tools/security-e2e/local.py test \
  --credentials-file /path/to/sandbox-credentials --allow-test-users \
  --grep 'owner token lists MCP tools only for its workspace'
```

Rebuild the isolated application stack from the candidate revision before claiming
release compatibility; a passing probe against an old running stack is only a
baseline observation. Do not reset or reuse production databases.

CI must record revision, client/protocol/LiteLLM versions, migrations, pass/fail
counts and skipped cases. Missing prerequisites must fail the required harness
job, not silently turn it green. Existing unit tests supplement, not replace,
these gates. Live PCAI and third-party UI client acceptance is separately tracked;
local fixture success does not prove those external clients work.

## Phase 1 verification record (2026-09-29)

- 119 schema/authentication/MCP unit regression tests passed. These are not the
  black-box authorization gate because of the unit-suite permission overrides.
- The new shared MCP probe passed standalone TypeScript checking.
- One real browser baseline passed against the existing local stack in its
  table-owner mode: synthetic Clerk login, OAuth token exchange, MCP initialization,
  initialized notification, tool listing and guard_status invocation. The harness
  cleaned up its synthetic user and organization.
- The restricted-role attempt failed its prerequisite check: the running API
  reports the table-owner role and inactive audit RLS. No auth bypass was added;
  the functional retry explicitly used owner mode. Restricted-role RLS remains
  unverified and required for release acceptance.
- The local stack was not rebuilt from this revision. This is existing-client
  baseline evidence, not candidate deployment or federated-flow acceptance.
- Full PKCE, independent service credentials, configured federation, mixed-client
  isolation and direct Gateway cases remain required implementation-phase gates.

## Phase 2 verification record (2026-09-29)

- 174 targeted tests passed: federation contracts/verifier/network controls and
  existing Agent-token, Okta, OAuth and MCP regression paths.
- Full migrations through 0154 passed on a fresh disposable PostgreSQL instance.
- The standalone [Phase 2 harness](../../tools/federation/README.md) passed with
  actual persisted synthetic credentials and production auth dependencies, without
  the unit-suite permission overrides. It verified admin saves, developer denial,
  tenant boundaries, optimistic revisions, audit persistence and composite FK
  isolation using ASGI requests and real PostgreSQL.
- Populated migration rollback correctly refused to discard configuration.
- Signed fixtures cover two independent issuers, rotation, expiry, outages and
  cache isolation. JWKS/network responses are injected in these unit tests;
  customer IdP connectivity and live HTTPS deployment remain unverified.
- Configuration is draft/disabled only. This phase does not enable delegated
  authentication on MCP or Gateway; that requires Phase 3 enforcement. Existing
  clients do not need configuration changes. No new feature flag was added.
- The disposable database runs as its table owner. Restricted-role RLS and the
  full configured/unconfigured MCP/Gateway release gates above remain pending.

## Phase 3 verification record (2026-09-29)

- 241 targeted federation, migration, Agent-token, Okta, OAuth, MCP and Guard
  regression tests passed; 10 existing database-fixture tests were skipped.
  The endpoint authentication coverage check passed.
- Fresh migrations through 0155 passed on disposable PostgreSQL. The Phase 3
  ASGI harness passed with a restricted runtime role and active forced RLS,
  real persisted service credentials, signed JWTs and actual Guard dispatch.
  Only JWKS retrieval was injected; this is not live customer IdP acceptance.
- Both MCP POST transports passed configured/unconfigured cases, concurrent
  subjects sharing a transport session, scope denial, missing/expired evidence,
  wrong audience/connection, revocation of an already verified context, JWKS
  outage, audit attribution and cross-workspace database isolation.
- CI now runs this restricted-role harness. Its hosted execution remains pending
  until this branch is pushed. Direct Gateway and LiteLLM plugin acceptance are
  later-phase work; Phase 3 grants only the two supported MCP policy checks.
- No production configuration or deployment was changed by this harness.

## Configuration UI requirement

The later UI phase must reuse Conduct's existing Integrations and Agent Identity
settings patterns and shared form, button, dropdown, validation, loading and
permission components. Do not introduce a separate design system. Phase 2 has
no UI changes.
