# ConductAI repository audit and implementation plan

Repository: `sseshachala/conductai`  
Reviewed branch: `main`  
Baseline commit: `c918c6e051c0718eb7e61659b61fc1b8987fe3d6`  
Review date: 11 September 2026  
Scope: marketing website, authenticated console, FastAPI control plane, Guard, proxy, Lens, workflow runtime, MCP, CLI, local tools, packaging, data, tests, and delivery pipeline.

## 1. Decision

**Modernize the existing repository through bounded replacements. Do not discard it and recreate the entire product in one cutover.**

The core technology choices are suitable: Next.js, React, TypeScript, FastAPI, PostgreSQL, Redis, declarative workflows, and thin integration clients. The repository already contains significant product knowledge: governance outcomes, policy gates, token families, workflow states, approval rules, integrations, schema migrations, compliance packs, API tests, and Figma exports. Recreating that knowledge introduces more risk than extracting and strengthening it.

The problems are serious, but they are concentrated around boundaries: authentication configuration, sandbox failure handling, tool authorization, audit guarantees, mutable client state, dependency compatibility, and release gates. Those boundaries can be repaired in the current codebase. Some large UI and infrastructure modules should then be replaced behind stable routes and contracts.

| Option | Benefits | Costs and risks | Decision |
| --- | --- | --- | --- |
| Incremental patches only | Fast containment; minimal migration | Leaves oversized components and duplicated behavior | Use for urgent repairs only |
| Staged modernization inside this repo | Retains contracts/data; permits focused replacement; each slice is testable and reversible | Requires deliberate compatibility adapters and migration discipline | **Recommended** |
| Entirely new repository and database | Clean starting structure | Recreates 122 pages and hundreds of API declarations; risks lost security semantics, data, clients, and onboarding behavior | Reject as default |
| New console implementation against the existing API | Can substantially improve UX while backend repairs proceed | Still needs real auth, API contracts, route parity, and migration | Use bounded feature replacements, not a separate product fork |

“One-shot” should mean **one complete handoff that an agent can execute without inventing the product**, with sequential validation gates. It must not mean one unreviewed deployment of a rewritten security platform. This document supplies the implementation decisions, module contracts, tasks, and completion criteria. Production credentials, infrastructure configuration, and acceptance of production rollout still come from the owner’s actual environment.

## 2. What was verified

The audit used the pinned checkout, source searches, AST inventory, selected end-to-end code-path review, local web checks, the npm advisory service, GitHub CI metadata, and six offline probes executing selected source functions with synthetic dependencies. No production exploit requests were made. No application source, remote branch, issue, PR, deployment, or customer data was changed.

### 2.1 Inventory

| Item | Observed |
| --- | ---: |
| Git-tracked entries | 1,561 |
| Next.js page files | 122 |
| Pages explicitly starting with `use client` | 66 |
| Next.js route-handler files | 5 |
| Static API route declarations, including WebSockets | 339 |
| Async API declarations | 34 |
| Production API Python files | 300 |
| Production API Python source lines | 62,551 |
| API Python files including tests, migrations, and scripts | 678 |
| API Python lines including those supporting files | 110,691 |
| Web JS/TS source files, including tests/configuration | 296 |
| Web JS/TS lines | 74,523 |
| API test files, recursively | 227 |
| Web unit-test files | 6 |
| Web Playwright spec files | 16 |
| Alembic migration Python files | 120 |

These are inventory counts, not test coverage percentages. AST route declarations are not a claim that all 339 are distinct mounted operations. The handoff includes `repository-inventory.json`; generate a runtime OpenAPI inventory in T00 to resolve mounted prefixes and non-OpenAPI endpoints.

Large files include CLI `main.py` (3,629 lines), CLI `guard.py` (3,339), CLI `paxel.py` (2,704), marketing docs page (2,590), `BlockEditor.tsx` (2,576), `GLensChatPage.tsx` (2,274), API `workflows.py` (2,150), `CanvasEditor.tsx` (1,929), Guard policies page (1,762), packs page (1,753), and `AppShell.tsx` (1,686). Size alone is not a defect; these files combine enough concerns to make safe changes difficult.

### 2.2 Validation results

| Check | Result | Meaning and limit |
| --- | --- | --- |
| Root `npm ci --ignore-scripts --no-fund --no-audit` | Passed | Installed the committed lockfile |
| `npm run typecheck --workspace apps/web` | Passed | TypeScript baseline compiles |
| `npm run lint --workspace apps/web` | Exit 0; **120 warnings** | Warnings are not release blockers |
| `npm run test --workspace apps/web` | **79 passed; 2 failed**, 6 test files | Both failures are GuardShell navigation-label expectations |
| `npm run build --workspace apps/web` | Passed | Compiled and prerendered; no real Clerk keys configured |
| API `python scripts/check_auth_coverage.py` | Passed | Structural coverage/allowlist check; does not prove correct authorization |
| `npm audit --omit=dev --json` | Exit 1; **7 affected dependency entries: 6 high, 1 moderate** | Includes transitive/meta vulnerabilities; not seven independently exploitable product defects |
| Six offline source probes | All confirmed the behaviors listed below | Mocked I/O; no proof of production exposure or exploitation |
| API full pytest / DB migrations / browser auth / load testing | Not run locally | Require Python service dependencies and an isolated Postgres/Redis/Clerk stack |
| GitHub CI at baseline SHA | Main CI and Dependency Security reported success | Security jobs are configured to tolerate failures; web-smoke was still in progress when inspected |

Local web checks used Node `24.19.0` and npm `11.9.0`; repository CI uses Node 20, while root `packageManager` names npm 10.9.0. Reproduce the chosen supported runtime in T00/T03 before treating these checks as release qualification.

Build-reported initial JS: shared 103 kB, Lens 300 kB, workflow editor 267 kB, docs 156 kB, dashboard 152 kB. These are Next build estimates from a no-Clerk-key build, not measured production transfer sizes, Core Web Vitals, or capacity limits.

Offline probes confirmed:

1. Public trial provisioning returns an existing fixture user’s trial agent token and a sign-in ticket.
2. A Modal session dispatch exception invokes the local backend.
3. An E2B session dispatch exception invokes the local backend.
4. The user-auth dependency returns the dev user when Clerk is disabled, without checking the production environment.
5. A Lens policy-evaluation exception still invokes the selected tool implementation.
6. Chain verification reports `valid=true` and counts an event whose hash is absent.

### 2.3 Access and evidence limits

This is a comprehensive engineering audit, not a certification that every line and every deployed behavior is safe. UX findings are based on source, route structure, and committed design references; there was no authenticated usability study. API latency, query plans, production RLS roles, real traffic, secret configuration, restore procedures, and scanner exploitability remain deployment checks.

GitHub returned the main branch as protected, with empty required-check contexts in the branch summary. Ruleset listing was empty. The detailed branch-protection endpoint returned an integration-permission 403. **Actual merge enforcement was not fully verified**; do not report the branch as unprotected.

The repository’s `rtk`, Booster, and ConductGuard agent tools were not available in this execution environment. Ordinary read-only repository tools were used. This did not change repository instructions or enforcement configuration.

### 2.4 Existing work to preserve

- Baseline commit fixes Lens message keys and isolates elapsed-clock updates. Do not reintroduce array-index keys or per-second rerenders of the entire run panel.
- PR #1785 concerns optimistic approval/run status. Reconcile it before rewriting those components; do not duplicate its fix blindly.
- PR #1783 updates LiteLLM event-hook support. Retain its behavior if merged before implementation.
- PR #1466 records a failed Next 16 / React 19 / Clerk upgrade: build passed but sign-in/sign-up returned 500. It is an investigation artifact, not a merge-ready solution.
- Existing real RBAC matrix tests, schema-drift tests, attack/contract/concurrency suites, signed policy configuration, provider circuit breaking, Redis BLMOVE queue handling, and approval substrate are useful starting points.
- Figma exports exist under `docs/design/figma/` and `docs/design/figma-console-2027/`. Preserve the actual Conduct logo and use those committed assets as the design baseline.

## 3. Findings and required improvements

Priorities: **P0** = contain before broad feature work; **P1** = required for a trustworthy modernization release; **P2** = complete during UX/performance migration. Severity expresses possible impact, while evidence indicates what was actually established. “Code” means a traced source behavior; “probe” means the isolated execution above; “opportunity” requires implementation-time measurement or product validation.

### 3.1 Security and governance

| ID / priority | Finding and evidence | Required correction and acceptance |
| --- | --- | --- |
| S01 / P0 / Critical | `modules/guard/routers/trial.py:326–443` accepts email/company without authentication, looks up the Clerk user, returns their existing workspace’s decrypted trial token, and mints a sign-in URL. `modules/onboarding.py` deliberately returns the oldest existing owned workspace. Confirmed with synthetic I/O. Exposure depends on this code being deployed with Clerk and an available trial identity. | Remove credential issuance from unauthenticated email lookup. Use an authenticated browser/device flow or verified email challenge. Existing-user requests must never receive agent tokens or sign-in tickets. Invalid, existing, and new addresses receive the same generic response before verification. T01. |
| S02 / P0 / Critical | `core/auth.py` makes missing Clerk configuration a dev-user/admin path; `core/config.py` defaults `environment` to development. `render.yaml` does not set `ENVIRONMENT` and describes Clerk as optional. The auth dependency has no production check. Confirmed probe; deployed environment is unknown. | Explicit local mode only. Refuse nonlocal startup without valid auth/environment settings. Use explicit service identity for self-hosting; missing keys must never grant admin. Reject externally supplied workspace identifiers without membership/identity binding. T01. |
| S03 / P0 / Critical | `runtime/sandbox_session.py:223–242,420–438` catches remote dispatch failures and constructs `LocalSession` directly. This bypasses the production prohibition in `create_session`. Local tools read/write arbitrary supplied paths and merge the worker environment. Legacy `runtime/sandbox.py` also falls back locally without a production guard. Both provider fallbacks were confirmed offline. | Remove fallback across trust boundaries. Provider failure yields a typed execution failure; no local subprocess/file operation. Gate local backend construction itself, not only its factory. All tool processes get explicit allowlisted environment and a confined filesystem. T01/T07. |
| S04 / P0 / High | `modules/guard/routers/proxy.py:367–383` independently authenticates internal agent tokens, checks expiry, but omits lifecycle rejection applied by `resolve_agent_token`. `agent_run_tokens` has no expiry column, and run-token lookups rely on invalidation. | One principal resolver for every header/transport, with lifecycle, active membership, expiry, token scope, run state, and tenant checks. Add bounded run-token expiry and revocation tests for proxy, HTTP, MCP, hook, WebSocket, Lens, and worker. T01/T02. |
| S05 / P0 / High | `/guard/trial/ops` uses workspace permission `guard.spend.view_all` but queries all trial workspaces and exposes workspace names/IDs and spend. A tenant security/admin role is not a platform operator. Code-confirmed. | Require a separately administered platform-operator principal and audit that access, or make all queries tenant-scoped. Seed two unrelated tenants; each tenant role must be unable to inspect the other through ops. T01/T02. |
| S06 / P0 / High | `mcp/lens_adapter.py` and `mcp/server.py` continue dispatch after policy evaluation throws. They only stop on BLOCK, although the enum also includes APPROVAL. Lens exception behavior was confirmed offline. | Shared enforcement middleware must handle ALLOW, WARN, APPROVAL, BLOCK and engine errors explicitly. APPROVAL creates/resolves a gate; never invoke implementation while pending. Failure policy must be explicit and recorded; protected actions fail closed by default. T01/T04. |
| S07 / P0 / High | `ToolDef.permission` exists, but generic MCP/Lens dispatch does not enforce it. Lens chat supplies `system:lens` instead of the requesting human. Read tools such as `get_recent_events` and `get_spend_summary` can read workspace/org-wide data despite entry permission `guard.activity.view_own`. Some mutating actor tools have additional checks; do not assume all tools are unguarded. | Propagate the real actor plus a separate executing-agent identity. Apply tool permission and row scope before policy evaluation/invocation. Enforce both own/all restrictions and organization membership. Deny unclassified tools. T02/T04. |
| S08 / P1 / High | Proxy audit insertion in `guard/audit.py` omits chain hashes and is best-effort after the response. `verify.py` counts unhashed rows as checked/valid; another verifier filters them away. Hash material includes only timestamp/tool/decision/previous hash, omitting actor, rule, cost, and input metadata. Confirmed null-hash probe. | Implement a versioned append-only decision ledger, complete coverage reporting, canonical full-envelope hashing, and stable per-workspace sequence. Preserve old evidence as legacy/unverified; do not invent historical hashes. Persist enforcement intent durably before effects; append outcome separately. T05. |
| S09 / P1 / High | `chain_hash_for_insert` locks the last event, not a stable workspace chain head. Empty chains have no row to lock; ordering uses timestamp alone. `/guard/verify/chain` combines organization workspaces while carrying one previous hash. | Lock a dedicated chain-head row, use sequence IDs and per-workspace verification, test empty-chain concurrency/tied timestamps/interleaved tenants, and require an external checkpoint for truncation detection. T05. |
| S10 / P1 / High | RLS migration 0004 covers five tables with SELECT policies; the context setter is called manually, and SET LOCAL disappears after transaction commit. Many sensitive tables are outside that migration. DB roles/owner bypass were not inspected. | Adopt a tenant UnitOfWork that establishes context on every transaction. Inventory RLS policies and privileges with a real non-owner role; add USING/WITH CHECK policies per operation and intentional service-role exceptions. Keep explicit application predicates too. T02/T06. |
| S11 / P1 / High | MCP test-connection sends a provided or stored credential to `body.url`; the shared MCP client accepts arbitrary URLs. No shared URL/DNS/egress validator was found on that path. Workflow integration hostname checks exist but do not secure all outbound transports. | Centralize outbound URL validation and credential-to-destination binding. Hosted control plane blocks loopback, link-local, private, metadata, and unsupported schemes, including redirected/rebound destinations. Approved private connections execute in the workspace’s isolated environment. T02/T07/T13. |
| S12 / P1 / High | Trial rate limiting trusts the first `X-Forwarded-For` value and fails open on Redis errors. API Docker startup trusts all forwarded proxies. Real ingress sanitization is unknown. | Trust only configured ingress proxy CIDRs; use validated client IP plus subject/device/global budget limits. Fail closed for anonymous credential/cost provisioning when abuse controls are unavailable. T01/T14. |
| S13 / P1 / Medium | Root web layout loads Narratr scripts in authenticated pages and reports as well as marketing. No application CSP/security-header configuration was found in reviewed web/API sources. Hosting may add headers. | Limit approved marketing scripts to marketing layouts. Add tested route-specific CSP, referrer, frame, MIME, and cache controls; validate actual deployed headers. Keep secrets/reports away from third-party scripts. T08/T12/T14. |
| S14 / P0 / High | `web-smoke.yml` uploads the entire `apps/web/.auth` directory on failure; Playwright uses role storage-state JSON in that directory. This can package session cookies if present at failure. No historical artifact was accessed. | Upload an explicit allowlist of sanitized diagnostics; exclude storage-state files and secrets. Review affected artifact retention/access and revoke exposed test sessions if exposure is established. T01/T03. |
| S15 / P1 / Medium | Provider error handling can log response snippets and upstream URLs and return exception strings. Authentication helpers log email/error details. | Redact structured fields at sink, remove payload/secret logging, use request IDs and typed user-safe errors, and test canary secrets across logs/traces/artifacts. T05/T14. |

### 3.2 Performance and reliability

| ID / priority | Finding and evidence | Required correction and acceptance |
| --- | --- | --- |
| P01 / P1 | Async proxy/MCP handlers run synchronous SQLAlchemy/JWT/helper work directly. Slow DB or key retrieval can block the event loop. `database.py` configures a 5+10 pool per process. | Keep ordinary synchronous REST handlers synchronous. For streaming routes, execute DB/auth units in bounded worker threads with their own sessions; use async HTTP/Redis. Introduce fully async DB only for measured hot paths. Prove event-loop lag and pool budgets under representative concurrency. T06. |
| P02 / P1 | `guard/router.py::_stream_chunks` retains the entire provider output in a bytearray. Proxy response inspection adds another collection path. Large concurrent outputs multiply memory. | Incremental usage parsing and bounded response inspection; no full output retention by default. Define explicit maximum body, chunk, duration, and concurrent-stream limits. Cancel upstream when clients disconnect. T04/T06. |
| P03 / P1 | The provider router creates/closes an AsyncClient per request with a 600-second timeout. Circuit-breaker identity is provider-wide, including different BYO endpoints. | Lifespan-scoped pools; separate connect/read/write/pool/overall deadlines. Breakers and bulkheads keyed by provider+normalized endpoint and safe tenant/account boundary; bounded cardinality. Preserve provider error shape without leaking credentials. T06. |
| P04 / P1 | `routers/insights.py::get_agents` queries workflows, then repeatedly loads their runs and computes aggregates in Python. Other summary paths load whole periods. | Replace N+1 loops with grouped SQL and cursor pagination; use EXPLAIN on seeded volume. Add targeted composite indexes after checking existing indexes. Introduce rollups only when measured necessary. T06. |
| P05 / P2 | Lens initial JS is 300 kB; editor 267 kB; docs page contains a large client-side documentation payload. Large client components eagerly import complex renderers. | Lazy-load charts, inspector, editor panels, and advanced renderers; keep public documentation server-rendered with a small interactive search/navigation island. Measure in comparable builds. T09–T12. |
| P06 / P1 | Marketing layout mounts WorkspaceProvider, whose refresh requests `/projects`; public browsing is coupled to workspace bootstrap. Client fetch/state management is repeated despite an existing API facade. | Public pages must not fetch private workspace data. Use one app bootstrap and tenant-keyed query cache for the console; migrate existing API facade rather than replacing every call independently. T08/T12. |
| R01 / P1 | Redis queue already uses BLMOVE, but claim timestamp is written separately; recovery only scans timestamps. Requeue uses separate Redis mutations; executor accepts limited statuses, while reaper marks old `running` jobs failed based on initial `locked_at`. No progress heartbeat was found on the reviewed path. | DB outbox plus atomic worker lease/heartbeat/fencing. Explicit resumable/ambiguous/terminal states and an external-effect ledger. Recover crashes before/after enqueue, claim, side effect, and acknowledgment. Never promise exactly-once delivery to arbitrary external APIs. T07. |
| R02 / P1 | Lens session replay subscribes before replay, correctly avoiding a gap, but may deliver an event through both replay and pub/sub. Client dispatch has no general dedupe and reconnects every 3 seconds, including auth failures. Its effect excludes auth/workspace dependencies. | Monotonic cursor/dedupe, bounded replay, backoff+jitter, stop on 401/403, visible reconnect state, workspace-bound subscriptions, periodic reauthorization, and transport parser tests. T10. |
| R03 / P1 | Session messages are serialized as one JSON text field; request-bound work and streaming increase the risk of last-writer overwrite and long transactions. Session access is workspace-wide under an own-activity permission. | Normalize messages/events with stable IDs and optimistic concurrency. Explicitly model private/shared sessions; migrate existing sessions as legacy-shared with visible provenance rather than guessing historical ownership. T02/T10. |
| R04 / P1 | API containers run migrations during startup; two Uvicorn workers each run startup threads for seeding/warming. This couples deploy health with mutating initialization. | One migration release job, idempotent versioned seed job, readiness checks, managed lifecycle tasks, graceful worker drain, and backward-compatible deployment order. T14. |
| R05 / P2 | Current load scenario exercises `/health` at 50 rps for 30 seconds. It does not measure Guard, SQL aggregation, queue lag, or SSE. | Add deterministic load fixtures for real principal/policy/audit paths, concurrent streams, and long-running worker recovery. Use test provider stubs, not paid live model calls. T06/T15. |

### 3.3 User experience and frontend maintainability

| ID / priority | Finding and evidence | Required correction and acceptance |
| --- | --- | --- |
| U01 / P1 | WorkspaceProvider can retain the previous workspace when refresh returns no matches; GuardRoleContext keeps previous permissions on some failed/empty/new-workspace paths. Source confirms state is not cleared at transition start. Backend remains the security boundary. | Reset tenant-scoped state synchronously, cancel old requests, discard late responses, show loading with no privileges, and clear caches on sign-out. Test admin A→viewer B→failure→no-membership. T08. |
| U02 / P2 | Console design exports specify dark navigation/light operational canvas, but AppShell uses the light `--surface` sidebar in light mode. Thousands of inline style occurrences make token consistency difficult. | Build five shared screen templates from committed exports; map existing semantic colors and logo into versioned tokens. Migrate routes by template and visually verify desktop/mobile/light/dark. T08/T09. |
| U03 / P1 | Marketing dropdowns use hover-only visibility with `href="#"` triggers. AppShell’s command palette is custom markup rather than a focus-managed dialog. | Accessible menu/dialog primitives with keyboard navigation, focus trap/restore, Escape, ARIA names, reduced motion, and touch support. Test by keyboard and screen-reader-oriented assertions. T08/T12. |
| U04 / P2 | Only one route-local error file was found; no route-local loading files were found. Forms and screens hand-roll loading/error behavior. | Shared page-level skeleton/error/empty/offline/forbidden patterns and per-feature boundaries. Never render network failure as a zero metric or an empty success. T08–T12. |
| U05 / P2 | CanvasEditor/BlockEditor and policies/settings pages combine form rules, transport, and presentation. This makes validation, draft safety, and responsive editing hard to maintain. | Schema-driven forms, field errors, dirty-state confirmation, conflict-aware save, undo/redo for canvas, keyboard-operable node list, and a readable execution preview. Preserve working current behavior where already implemented. T09/T11. |
| U06 / P2 | Lists, activity logs, inspectors, charts, and action status implement separate state patterns. This is an improvement opportunity across the indexed routes, not a claim that every screen lacks pagination. | Standard URL filters, server pagination/sorting, selected-row deep links, named time windows/timezone, last-updated timestamps, safe bulk actions, and query-cache invalidation. T09/T10. |
| U07 / P2 | Shared report views contain their own branding/colors and hand-built Markdown formatting. Existing escaping reduces HTML injection risk; raw HTML presence alone is not an XSS finding. | Shared safe Markdown renderer, report provenance and scope, expiry/revocation controls, accessible tables, export status, and no third-party script on private/shared-report surfaces. T09/T12. |
| U08 / P2 | Root metadata defaults every inheriting page to the homepage canonical and indexing; robots omits some modern private route families. Authenticated visitors are redirected away from `/guard` and `/registry` marketing content. | Route-specific canonicals, explicit noindex/private cache headers on console and shared secrets, complete sitemap policy, and a stable public/product navigation model. Verify links against the full route manifest. T12. |

### 3.4 Code quality, protocols, dependencies, and delivery

| ID / priority | Finding and evidence | Required correction and acceptance |
| --- | --- | --- |
| Q01 / P0 | Web unit tests are not a required CI job; two navigation-label tests fail locally. API lint is `flake8 ... || true`; security scanners use `continue-on-error`. API job title promises typecheck but no Python typecheck step is present. | Add actual blocking web tests/build, meaningful lint/type gates, and severity-based scanner enforcement. Establish a documented legacy-warning baseline, then block additions. Correct tests to intended navigation, not whatever markup happens to exist. T03. |
| Q02 / P1 | API global conftest replaces permission factories with admin noops. The matrix restores checks, which is useful, but many general tests run with synthetic authorization. The matrix permits authorized paths to return statuses other than 403 rather than requiring valid successful behavior. | Separate test app factories/fixtures; real authorization by default for integration tests. Seed valid requests/resources for allowed cases, verify denied cases cause zero effects, and add cross-tenant/own-vs-all tests. Keep the existing matrix as a structural layer. T03. |
| Q03 / P0 | npm scan reports Clerk dependency chains, js-cookie 3.0.5, and nested PostCSS 8.4.31 among affected entries; Next is also a flagged meta dependency. A direct newer PostCSS declaration does not remove nested older copies. Exploitability of each advisory was not established. | Resolve actual dependency graph and patch compatible versions. Do not blindly run `npm audit fix --force`. Complete login, signup, OAuth, tenant switch, and session refresh tests before framework changes; reconcile PR #1466. T03. |
| Q04 / P1 | Python requirements mix runtime/test dependencies and several open version ranges. Web Dockerfile installs from `apps/web/package*.json` using `npm install`, bypassing the authoritative root lockfile. It runs as root; API production image includes build tools. | Reproducible runtime/dev locks, deterministic workspace-aware npm ci image, non-root web runtime, minimal API runtime stage, pinned build inputs, and SBOMs for shipped packages. T03/T14. |
| Q05 / P2 | Large CLI/UI/router files, manually duplicated API types, legacy names, and limited web tests increase coupling. Root npm workspaces excludes the existing `packages/shared`. Static counts include 44 exhaustive-deps suppression occurrences. | Define domain boundaries; generate transport types from OpenAPI; keep domain state typed; either wire shared contracts into workspaces or remove unused package after import proof. Ratchet warning suppression and module complexity. T08–T13. |
| Q06 / P2 | README/contributor/versioning docs and code disagree on framework version, protocol version, product names, and some guarantees. REVIEW.md’s claimed gates do not match workflow behavior. | Generate or verify inventories in CI; document shipped/conditional/advisory capabilities, supported versions, exact commands, and deliberate exceptions. Ensure evidence claims follow the new ledger’s actual guarantees. T12/T15. |
| I01 / P1 | Generic MCP client’s primary path directly posts tools/list or tools/call without initialization/session negotiation. MCP server echoes arbitrary requested protocol versions. This can work for permissive stateless endpoints but is not general interoperability. | Implement supported-version negotiation and lifecycle with pinned SDK/transport adapters, session headers, bounded cleanup, and strict-server contract tests. Preserve existing working clients via explicit compatibility adapters. T13. |
| I02 / P1 | MCP `call_tool(transport="auto")` retries via SSE after general HTTP failure. If a remote mutation completed but its response was lost, the fallback can execute it again. | Negotiate transport with a read-only handshake; never retry a mutation after an ambiguous outcome unless the operation is idempotent under a provider-recognized key. Return unknown/reconcile state otherwise. T07/T13. |
| I03 / P1 | LiteLLM/NeMo compatibility parses text prefixes, including empty/`ok` text as allow. The server’s structured decision contract is richer than client handling. | Introduce versioned typed decisions and strict validation while preserving legacy text in a compatibility adapter. Unknown/malformed decision fails according to explicit policy; never default a malformed modern envelope to allow. Keep policy evaluation central. T04/T13. |
| O01 / P1 | `/health` returns a constant success; `/metrics` is public in source. Worker health and migration/schema readiness are not part of that response. | Separate liveness/readiness, expose internal metrics through controlled ingress, and alert on queue age, stale leases, audit lag/failure, stream errors, and policy latency. T14/T15. |

There are **44 findings/improvement items** above. A finding may require several tasks; related findings are intentionally grouped by the boundary that must be fixed rather than by every matching file.

## 4. Product and compatibility contract

### 4.1 Preserve these capabilities

The replacement must retain marketing/documentation, browser login/signup/invites, multiple workspaces/projects, member roles, agent identities and revocation, Guard configuration/policies/packs, discovery, activity and receipts, approval actions, spend/budgets, compliance/evidence, workflow registry/install/edit/run, canvas configuration, run history and traces, Lens chat/session/report builder, environments/credentials, integrations/MCP servers, notifications/preferences, session reports/share links, governance/security views, CLI login/sync/hooks, local enforcement, and LiteLLM/NeMo adapters.

Keep implemented workflows, policy outcomes, provider request/response compatibility, token prefixes, install paths, public share/receipt expiry semantics, named credentials, and existing identifiers until explicitly migrated. Do not silently delete features because they are obscure or difficult. Every old route must be retained, redirected deliberately, or listed as blocked with a reason in the parity manifest.

### 4.2 Stable boundaries

| Boundary | Rule |
| --- | --- |
| Existing REST endpoints | Preserve successful JSON/status semantics through adapters while introducing new contracts |
| Proxy endpoints | Preserve Anthropic/OpenAI/Perplexity-compatible shape, streaming, headers required by supported clients, and receipt metadata |
| Guard policy | Preserve `BLOCK > APPROVAL > WARN > ALLOW`; policy gate is action/prompt/response; audit-only is a recording mode, not a new permission outcome |
| CLI/MCP | Keep existing commands, flags, token prefixes, legacy tool text, endpoint aliases, and exit-code behavior in a tested compatibility layer |
| Workflows | Keep YAML/graph schema and block semantics; version incompatible fields; import/export round-trip all existing playbooks |
| Data | Preserve workspace, identity, workflow, run, approval, receipt, report, and share IDs; no destructive reset |
| Design | Reuse the logo and exported Figma foundations; no emoji as interface icons; semantic status colors remain consistent |
| Claims | Mockup numbers stay mock data; audit integrity, enforcement coverage, and security statements must reflect tested behavior |

Existing `docs/api-versioning.md` specifies a minimum 90-day notice for production-facing breaking contracts. Preserve this unless the owner explicitly changes it. A direct unsafe credential-disclosure flow must be contained immediately; keep a useful verification-based replacement and a clear client upgrade response rather than retaining insecure behavior for compatibility.

## 5. Target architecture

Keep one repository and the current deployment families. Use a **modular monolith** for the API. Do not add microservices, Kubernetes, Kafka, a new database, or a new identity vendor merely to reorganize the source.

| Layer | Target responsibility | Keep / replace |
| --- | --- | --- |
| Marketing routes | Mostly server-rendered content, metadata, docs, pricing, small client navigation/CTA islands | Keep URLs/assets/copy; replace shared layout and docs delivery |
| Auth route group | Clerk session lifecycle, verified onboarding, invite/device flows | Move out of operational app shell; harden bootstrap |
| Console route group | Bootstrap context, five screen templates, accessible controls, server-state cache | Replace shell and migrate features individually |
| FastAPI transport | Parse/validate inputs, resolve actor/tenant, invoke use case, serialize typed result | Thin current routes behind stable API adapters |
| Domain modules | Identity, workspace, governance, approvals, workflows/runs, Lens/reports, integrations | Extract from existing code; preserve proven algorithms |
| Shared infrastructure | DB UnitOfWork, pooled HTTP/Redis, secrets, telemetry, outbox, clock/IDs | Replace duplicate helpers with narrow interfaces |
| Guard decision service | Consistent context, policy precedence, obligations, enforcement and audit intent | Consolidate existing engines/adapters |
| Worker/runtime | Leased state machine, durable execution checkpoints, isolated tool execution | Harden existing executor and queue |
| External clients | Thin transport/UX adapters with versioned decision contracts | Retain package names; add compatibility tests |

Recommended target directories (create only as needed during a slice):

- `apps/api/app/core/{settings,auth_context,permissions,uow,http_clients,errors,telemetry}.py`
- `apps/api/app/domains/{identity,workspaces,governance,approvals,workflows,runs,lens,integrations}/` with `schemas.py`, `service.py`, `repository.py` where needed.
- `apps/api/app/guard/{policy,policy_types,enforcement,audit,router,gateway}.py` retains the current recognizable policy boundary.
- `apps/api/app/runtime/{executor,leases,outbox,operation_ledger,sandbox_registry}/` or equivalent focused modules; keep compatibility imports during extraction.
- `apps/web/src/features/{workspace,guard,workflows,runs,lens,identity,settings,reports}/`.
- `apps/web/src/components/ui/` for accessible primitives, `components/layout/` for shell/templates, `lib/api/` for generated transport and typed facades.
- `packages/contracts/` for generated OpenAPI client/types and versioned decision/stream/workflow schemas; explicitly declare it in root workspaces.

Do not perform a giant move-only PR. Move code when adding the corresponding behavior/contract tests, and keep temporary compatibility imports identifiable and scheduled for removal in T15.

### 5.1 Identity and authorization contract

Create an immutable `RequestContext` with `request_id`, `workspace_id`, optional authorized `organization_scope`, `principal_id`, `principal_type`, `human_user_id`, `agent_identity_id`, optional `run_id`, `session_id`, `token_id`, `permissions`, and `auth_time`. Values come from validated server-side identity and membership; request headers only select scope, never confer authority.

Keep human authority and executing-agent identity separate. Lens must carry the signed-in user and its Lens agent identity simultaneously. A machine token must use its explicit scopes; it must not inherit the creator’s current admin privileges merely because the creator exists.

Use the sequence: authenticate → resolve requested tenant → verify membership/token binding → check permission → scope resource query → evaluate Guard → satisfy approval/other obligations → record decision intent → execute effect → record outcome. Use the same use case for HTTP, MCP, Lens, worker, and CLI-originated requests. Tool schemas and annotations are not authorization.

New permission classifications: workspace permissions remain in existing RBAC tables; platform-operator permissions live in an independently administered assignment, never in a tenant-editable role. Every tool and endpoint is explicitly public, user-bound, machine-bound, or operator-only. Every “own” query must bind the actual principal, including Lens tools.

### 5.2 API contract

Generate OpenAPI from the runtime application and generate TypeScript types; do not create an independent hand-maintained API model. The source AST inventory is a discovery aid, not the contract authority.

For new console endpoints, use `{data, meta: {request_id, next_cursor?, as_of?}}`. Errors use `{error: {code, message, request_id, field_errors?, retry_after_seconds?}}`. Preserve legacy/provider error shapes at the adapter boundary. Use 401 for missing/expired auth, 403 for denied permission, 404 for tenant-inaccessible resource, 409 for state/version/idempotency conflicts, 422 for validation, 429 for rate limits, and 503 for temporary infrastructure unavailability.

List request defaults: limit 50, maximum 100; validated sort enum; cursor based on stable `(created_at,id)` or sequence, not unbounded offset for high-volume event tables. Validate IDs and time ranges. Do not expose raw DB/provider errors.

Mutations that create runs, issue approval decisions, provision users, rotate keys, install packs, or call external systems require an idempotency key. Persist `(workspace_id, principal_id, operation, key, request_hash, result, status)` with a unique constraint. Same key/same request returns the original result; same key/different body returns 409. Retain records for at least the retry window and the operation’s entire lifecycle; initial default 7 days after terminal state.

### 5.3 Governance decision contract

Keep the existing internal enum and serialize a versioned envelope:

```json
{
  "schema_version": 2,
  "decision_id": "uuid",
  "action": "APPROVAL",
  "code": "approval_required",
  "reason": "Production change requires review",
  "workspace_id": "uuid",
  "principal": {"type": "agent", "id": "uuid", "on_behalf_of": "user-id"},
  "context": {"gate": "action", "surface": "mcp", "operation_id": "uuid"},
  "policy_version": "sha256",
  "matched_rules": [{"id": "rule-id", "version": "version"}],
  "obligations": [{"type": "approval", "approval_id": "uuid", "expires_at": "RFC3339"}],
  "timestamp": "RFC3339",
  "audit": {"recorded": true, "sequence": "integer-as-string"}
}
```

Validate the envelope and rule/source output at every adapter. Unknown actions are errors. APPROVAL is never a synonym for WARN. Approved action digest, workspace, principal, resource version, policy version, and expiry must match the attempted effect. Recheck authorization and policy on resume; fail closed if the approval no longer covers the operation.

For streaming response rules, publish the actual guarantee: passthrough observation cannot retract already-delivered output. For a hard response block, use a bounded hold/release mode or provider-supported intervention, with a tested maximum and explicit failure behavior. Never advertise a streaming observer as complete output prevention.

### 5.4 Audit and execution contracts

Separate immutable enforcement decisions from mutable operational read models. A durable decision record must exist before a protected effect is released. Append a completion/failure/ambiguous-outcome record afterward. This avoids pretending that a single best-effort callback guarantees full evidence.

Audit canonical material includes schema version, tenant, sequence, event ID, operation ID, principal/agent/run, action, gate, policy/rules, normalized redacted input digest, recorded outcome, timestamp, and previous hash. Canonical serialization is versioned and cross-language fixtures prove byte equality. External checkpoint signatures identify a key version; without an independently retained checkpoint, do not claim detection of complete tail truncation or privileged full-chain rewrite.

Worker execution is at-least-once with deduplication. Every claim has `lease_owner`, `lease_expires_at`, and a monotonic fencing token. Heartbeat at 10 seconds with an initial 60-second lease, configurable with maximum-duration limits. These are proposed initial values, not observed capacity guarantees. A stale worker cannot commit new effects after losing its lease. Provider calls with ambiguous completion enter `reconciliation_required`; safe retries require provider idempotency or a queryable outcome.

## 6. Data migration specification

Use **expand → backfill → compare → switch reads → retire**. Hand-write reviewed migrations, following the repository warning against destructive autogeneration. Keep model/index names aligned with migrations. Do not renumber or erase existing migrations.

| Migration family | Additions | Backfill and invariant | Rollback |
| --- | --- | --- | --- |
| Identity | Token hash/version/revocation metadata; run-token expiry/scopes; centralized resolver fields | Hash high-entropy existing opaque tokens in a privileged job without logging plaintext; preserve encrypted integration secrets. Set a bounded expiration for legacy active run tokens, resume with fresh tokens. | Old/new columns coexist; security checks remain enforced on both paths |
| Onboarding | Unique verified-subject/challenge/claim records with status/expiry and default-workspace mapping | Reconcile duplicate onboarding requests, not all workspaces owned by a user; multiple legitimate workspaces remain valid. Serialize provisioning by verified subject. | Disable new provisioning, preserve verified mappings; never restore public credential return |
| Audit v2 | `audit_chain_heads`, immutable `audit_events_v2`, schema version, sequence, full payload digest, checkpoint references | Stable per-tenant head row; unique tenant+sequence and event ID. Old rows remain legacy and report hashed/unhashed counts separately. | Keep v2 history intact; roll back read model only, not evidence |
| Outbox/effects | `outbox_events`, `operation_ledger`, dispatch status/attempts, leases, idempotency records | Create outbox entry in the same DB transaction as run/approval state. Reconcile stranded legacy pending runs explicitly. | Drain one dispatcher generation; old/new workers cannot own the same operation |
| Approvals | Version/action digest, immutable decision actor/time, operation ID, explicit execution status | Map current pending/approved/rejected/timed_out without implying approved means executed. Existing pending approvals retain original payload and timeout. | Read compatibility adapter; security repair remains active |
| Lens | Message rows with stable IDs/order, session version, creator/visibility, stream event sequence | Preserve raw legacy transcript for recovery; deterministic message IDs during migration. Unknown creator becomes legacy-shared, not assigned speculatively. Compare transcript counts/digests. | Session-level read flag can use legacy transcript while retaining new messages through a tested reverse adapter |
| RLS | Roles, tenant settings, policies, indexes/FKs | Test each tenant table with least-privilege app role after every migration. Explicit operator/worker privileges only. | Prefer forward repair; never switch to an unrestricted role just to pass rollout |

For large tables, backfill by primary-key ranges with checkpoints and rate limits. Build necessary indexes concurrently in an Alembic autocommit block where required. Track row counts, nulls, duplicates, FKs, old/new business totals, and sampled content digests. Restore an actual staging snapshot and rehearse the migration before production.

Credential rules: production integration secrets remain encrypted with versioned keys; no generic plaintext-read endpoint. Opaque authentication tokens are hashed with constant-time comparison where applicable; no key rotation may silently invalidate unrelated encryption without a backfill/dual-key read period. Separate runtime DML role from migration owner.

## 7. Console and website specification

### 7.1 App bootstrap and navigation

Put sign-in, sign-up, invite acceptance, CLI authorization, and OAuth authorization outside the operational shell. Fetch authenticated workspaces, active workspace, capabilities, and preferences through a bounded bootstrap endpoint or equivalent coordinated server operation. Only mount tenant queries when bootstrap has resolved a valid workspace.

Use tenant-keyed query state, preferably TanStack Query with a pinned reviewed version, through the existing `lib/api` facade. Keys start with `[workspaceId, principalId, feature, resource, filters]`. Clear old queries, permissions, selected records, and streams on workspace change; ignore stale responses by workspace generation. Cache policy for fast-changing approvals/runs is short and event-invalidated; reference catalogs can be cached longer by version. Keep auth token acquisition centralized and restrict outgoing auth headers to the approved API origin.

Use four primary navigation groups: Overview; Govern (activity, policies, approvals, identities/discovery, spend); Operate (workflows, runs, Lens, packs/projects); Configure (environments/integrations, members, settings). Preserve existing route paths and feature labels via the manifest. Do not duplicate product pages in several locations without a clear alias.

On small screens, navigation becomes an accessible drawer; critical actions remain usable at 360 CSS pixels. Use a flexible operational canvas and an inspector that becomes a sheet on narrow screens. Use `100dvh`/appropriate fallbacks instead of forcing unusable nested full-height scrolling.

### 7.2 Design foundations

Source assets:

- `docs/design/figma-console-2027/manifest.json`, `tokens.css`, `figma-variables.json`, and the five `mockups/*.png`.
- `docs/design/figma/` marketing exports and existing logo assets.
- `DESIGN.md` semantic states and existing `globals.css` behavior.

Create a documented mapping from Figma tokens to CSS semantic aliases. Keep Allow/Success green, Warn/Approval amber, Block/Failure red, and Audit blue, always with text/icon meaning. Preserve approved logo geometry. Use existing SVG/Lucide system or purpose-built SVGs, not emoji. Do not transplant mock numbers into live pages.

Standard components: Button, IconButton, FormField, Select/Combobox, Dialog, Drawer, ConfirmAction, Toast/StatusRegion, Tooltip, Tabs, StatusBadge, MetricCard, DataTable, FilterBar, DateRange, Pagination, EmptyState, ErrorState, Skeleton, Inspector, CodeBlock, SafeMarkdown, and PageHeader. Use existing Radix dependencies where applicable. New abstractions require two real uses or a clear boundary purpose.

### 7.3 Feature acceptance

| Feature / representative routes | Required behavior |
| --- | --- |
| Overview: `/dashboard`, `/theguard`, `/governance` | Real scope/timezone; totals reconcile with source lists; last updated; distinguish unavailable from zero; cards drill into matching filters |
| Activity: `/logs/guard`, `/theguard/blocks/[id]`, `/audit`, `/secure/activity` | Server cursor/sort/filter; stable selection deep link; principal, rule/version, decision, timestamp, gate/surface, integrity status; redacted payload by permission; export job with progress |
| Policies: `/theguard/policies`, `/theguard/policies/new` | Search/filter; typed rule editor; explicit scope, fail mode and gate coverage; simulate against saved fixtures; show effective policy diff; conflict-aware publish; rollback by version |
| Approvals: `/theguard/approvals` and Lens action cards | Pending/expired/decided/executing/result are distinct; preview exact operation, actor, destination and impact; authorized decisions only; duplicate click safe; display rejection/expiry/conflict; no automatic approval inferred from model text |
| Identities/discovery: `/agent-identity`, `/theguard/discovery` | Show identity source, status, ownership and observed vs enforced coverage; token create-once display; rotate/revoke; expiry; linked runs/activity; discover-to-govern wizard |
| Spend: `/theguard/spend` | Clear actual/estimated/unknown costs; explicit currency, pricing version, time window; budget form with scope; reservation/actual reconciliation; own/all permission correctness |
| Packs: `/packs`, `/packs/[slug]`, public `/registry` | Search/category/compatibility; installed version; verified publisher/integrity status if actually implemented; preview permissions/changes; idempotent install; dry run; upgrade/rollback |
| Workflows: `/workflows`, `/workflows/new`, `/workflows/[id]`, settings | Search/status/project filter; create/import/export; schema validation; versioned save; block forms; graph/list editing; keyboard node operations; undo/redo; missing-credential guidance; deterministic run preview |
| Runs: `/logs/runs`, `/runs/[run_id]`, workflow run routes | Streaming timeline; persistent selection and scroll; outcome vs Guard decision distinction; retry/resume/cancel permissions; costs and limits; artifacts; clear ambiguous/partial failure; linked approval/evidence |
| Lens: `/lens`, `/lens/[sessionId]` | Stable message IDs; private/shared session scope; cancel/reconnect; no lost or duplicate message/action; citations/deep links grounded in data; separate user and agent identity; accessible live-region updates without announcing every token |
| Reports: `/lens/report-builder`, session reports, compliance/SOC2 pages | Typed saved report spec; validated widget allowlist; provenance/as-of/scope; export job; share expiry/revoke; no executable model-generated HTML/JS/SQL |
| Settings: `/settings`, `/theguard/settings`, `/integrations`, `/projects` | Consistent forms and route ownership; capability-based sections; env vars as flat key-value; secret write-only controls; verified endpoint connection test; member/role management; dirty/conflict/error states |
| Setup/trial/auth | Verified identity before credential delivery; resumable setup checklist; copyable client configuration; first known policy verdict and receipt; clear expired/capped/missing-integration guidance |
| Marketing/docs/blog/solutions | Existing positioning/assets; server-rendered content; accessible navigation; accurate capability labels; fast hero/docs; self-canonical URLs; no private workspace fetch; working sign-in/product links |

All remaining routes inherit the closest template. The complete route list is in the handoff inventory and appendix. Template selection does not authorize dropping a route’s unique controls or data.

### 7.4 UX verification

Test keyboard-only onboarding, policy editing, approval, workspace switching, and workflow run inspection. Test 360, 768, and 1440-pixel viewports, light/dark, reduced motion, and long labels/large data. Use automated axe checks plus explicit focus/interaction assertions; zero critical/serious accessibility violations on migrated flows. Visual comparison against Figma references must use fixture data and documented responsive adaptations, not pixel comparison between unrelated live data and mockups.

Form submissions disable duplicate effects while pending, retain user input on error, link errors to fields, and show success only after server acknowledgment. Optimistic state is appropriate for reversible display updates, but approvals/runs must not pretend an external effect has completed.

## 8. Performance targets and measurement

These are **proposed engineering acceptance budgets**, not current production benchmarks or business SLAs. First establish reproducible baselines and record machine, data, concurrency, network, framework flags, auth mode, and warm/cold state.

| Surface | Initial target | Test conditions |
| --- | --- | --- |
| Public page Web Vitals | p75 LCP ≤2.5 s, INP ≤200 ms, CLS ≤0.1 | Field data when available; lab profiles documented separately |
| Common console initial JS | ≤170 kB build-reported; no >5% unexplained regression | Same build/auth/runtime as new baseline |
| Lens initial JS | ≤220 kB | Lazy-load charts/report/editor-only renderers; inspect runtime responsiveness too |
| Workflow editor initial JS | ≤250 kB | Full editor still usable; heavy optional panels deferred |
| Ordinary API list/detail | p95 ≤300 ms; p99 ≤800 ms | Seeded Postgres with 1M audit rows, 10k runs, 1k workflows across tenants; 50 rps for 10 min |
| Guard added request latency | p95 ≤100 ms; p99 ≤250 ms | Warm compiled policy, 50 representative rules, stub upstream; include durable decision write; 50 rps |
| Audit coverage | 100% protected effects have durable decision ID | Includes provider errors, cancelled streams, approvals, and worker crashes |
| SSE | p95 event delivery ≤1 s in local staging network | 200 concurrent streams, replay and reconnect tests; no duplicate UI effects |
| Stream memory | Bounded with output length; no full response accumulation | 100 concurrent synthetic 10 MB output streams; enforce per-stream buffers ≤256 KiB unless explicit bounded inspection mode |
| Query scalability | Workflows/agent summary uses ≤6 SQL queries per request | 1, 10, and 1,000 workflows; no query count proportional to row count |
| Worker progress | Dead worker detected within 2 lease periods | Kill process at each transition; no duplicate provider-recognized operation |

Record RSS, event-loop lag, DB pool wait, query count, upstream time, policy time, audit time, queue age, and stream count separately. If a target cannot be met, profile the bottleneck and document the measured tradeoff; do not change the target silently or claim that a health endpoint proves scalability.

## 9. Ordered implementation work packages

Every task below must produce a small, reviewable commit sequence, update `docs/modernization/progress.json`, and link its validation evidence. Dependency order is mandatory; parallel execution is optional only when the executor is authorized to delegate. No task requires autonomous production deployment.

### T00 — Pin, inventory, and reproduce

Dependencies: none. Inputs: this plan, pinned SHA, existing docs/tests, open PRs.

1. Create an isolated working branch from the current approved base; record differences from the audit SHA. Read applicable AGENTS/REVIEW/ROLES/DESIGN instructions. Reconcile #1785/#1783/#1466 and any subsequent fixes before editing.
2. Add `docs/modernization/{decisions.md,route-parity.json,api-parity.json,progress.json}`. Seed route parity from the handoff; generate runtime OpenAPI including mounted prefixes; enumerate WebSockets, MCP tools, callbacks, CLI entry points, and scheduled jobs separately.
3. Run the actual supported Node/npm and Python/Postgres/Redis development stack. Use isolated Clerk sandbox credentials and fake external provider adapters. Never substitute production data or paid agents for fixtures.
4. Save baseline test/build/scan results, warnings, route bundle report, query counts and key screenshots. Identify fixture test skips explicitly.

Deliverable: reproducible baseline and parity manifests. Gate: every existing page and mounted operation assigned a domain owner/task; expected failing tests recorded, not hidden; production remains untouched. Rollback: delete local branch only if requested; no data migrations yet.

### T01 — Contain critical boundary failures

Dependencies: T00. Addresses S01–S06, S12, S14; mandatory before feature refactoring.

Files: `modules/guard/routers/trial.py`, `modules/onboarding.py`, `core/auth.py`, `core/config.py`, `runtime/sandbox_session.py`, `runtime/sandbox.py`, `modules/guard/routers/proxy.py`, `mcp/{server,lens_adapter}.py`, `.github/workflows/web-smoke.yml`, `render.yaml`, installer/client onboarding code.

1. Introduce an explicit `AUTH_MODE`/environment validation contract. Development bypass requires an explicit local setting; all nonlocal modes enforce authentication. Render API and worker both declare production settings; required secrets are references, never committed values.
2. Disable unauthenticated credential issuance. Replace installer provisioning with verification challenge/device flow: create challenge → browser authenticates or verifies mailbox → server atomically completes subject binding → installer redeems short-lived single-use authorization. Return generic accepted status before verification. Do not reveal existing-user status/tokens.
3. Remove all remote→local execution fallbacks and prohibit direct LocalSession construction outside explicitly local execution. Reject unconfined paths and ambient environment inheritance even in local fixtures.
4. Require centralized lifecycle checks in internal proxy auth; use a temporary conservative run-token lifetime check while the full migration lands in T02.
5. Restrict trial ops to platform operators or tenant scope. Correct anonymous rate-limit failure handling and trusted forwarded IP handling.
6. Make policy errors/APPROVAL stop generic tool invocation. Add fail-mode audit reason, not a silent exception swallow.
7. Remove broad `.auth` uploads and replace with sanitized screenshot/text allowlist.

Tests: actual endpoint requests using mocked Clerk/isolated DB; new/existing email; invalid challenge; replay/expired challenge; startup misconfiguration; all sandbox provider failure modes; deactivated agent over all auth headers; operator/tenant ops; engine exception and APPROVAL cause zero tool calls; artifact manifest contains no cookie storage state.

Gate: all critical regressions pass with real application DI. Safe rollout unit: a containment release independent of UI rewrite. Do not “roll back” by reinstating credential disclosure or local execution fallback; disable affected operations if needed.

### T02 — Unify principals, tenant scope, and secrets

Dependencies: T01. Addresses S04/S05/S07/S10/S11, R03.

1. Extract `RequestContext` and one token/principal resolver; retain existing entry points as adapters. Authenticate once per request, cache only within that request, and avoid repeated token decryption or Clerk queries.
2. Implement permission checks in generic tool dispatch; require every ToolDef to declare its permission/classification. Propagate human actor and executing-agent separately through Lens, MCP, runs, and approvals.
3. Use tenant repositories/UnitOfWork that cannot query tenant resources without authorized scope. Explicitly distinguish one workspace from organization-wide reads; validate membership across every workspace included.
4. Add token expiry/hash/revocation schema and migrations from section 6. Remove plaintext token re-reveal except newly minted values returned once to an authenticated owner; existing trial UX uses rotation or a verified recovery flow.
5. Bind stored credentials to approved endpoints and operation scopes; move secret decryption behind a credential service. Include key-version/rotation read compatibility.
6. Add session visibility/ownership fields. Keep legacy-shared transcripts visibly classified; prohibit own-permission callers from reading another user’s new private session.

Tests: complete endpoint×role×tenant×principal-type matrix with valid resources and bodies; own/all scopes; unknown tool permission denied; role removal during stream and approval; run expiry/revoke; token replay; secret never attached to an unapproved destination. Gate: identical enforcement for HTTP/MCP/Lens/worker, with no system-user promotion of the requesting human.

### T03 — Make quality and dependency gates real

Dependencies: T00/T01. Addresses Q01–Q04, S14.

1. Fix GuardShell label tests after establishing intended navigation (`Discovery` vs `Agent Discovery`); assert user behavior as well as exported tab data.
2. Require web typecheck, lint, unit tests, and production build on PRs. Add a small authenticated Playwright gate for sign-in, signup, refresh, workspace switch, and a protected page. Larger cross-browser/visual/load suites can run separately, but failed required smoke blocks release.
3. Replace global permissive auth fixtures with test app factory injection. Keep matrix restoration until migrated; remove it only after equivalent real-auth cases pass. Forbidden cases must assert no DB/outbox/external mutation, not merely a 403.
4. Introduce a Python dev dependency lock, actual Ruff/format/type checks for touched modules, then ratchet remaining debt. Remove `|| true`; scanner exceptions need advisory ID, owner, reason and expiry. Run CLI/adapter tests when those packages change.
5. Resolve the npm graph. Current audit suggests Next 16.3.4 and Clerk 7.9.2 as upgrade candidates, but those are **not validated combinations**. Use PR #1466 to reproduce the login failure, fix provider/layout/session wiring and duplicate SDK versions, then pin a supported patched Next/React/Clerk combination proven by browser auth tests. A tested patched current-major route is preferable if available; do not mix React runtime and type major versions.
6. Generate exact supported runtime locks from official package metadata at implementation time. Record them in an ADR and container/CI config. Do not keep Node/npm disagreement across machines.
7. Enforce high/critical production-dependency and security regression gates after baseline triage; treat scanner graph entries as reachability review inputs, not proof of exploitation. Never auto-force a major upgrade to make the scanner green.

Gate: reproducible clean install/build and valid auth flow; 81 current web tests updated/passing plus meaningful additions; no silently skipped required security tests. Branch-protection enforcement must be checked by an authorized repository administrator because it could not be fully read during this audit.

### T04 — One enforcement contract across surfaces

Dependencies: T02/T03. Addresses S06/S07, P02, I03.

1. Introduce the versioned Decision schema and explicit mapping to legacy text/provider errors. Reuse existing `PolicyAction`, precedence, gates and policy source composition.
2. Consolidate context → permission → policy → obligation → audit intent → dispatch. Remove duplicate decision logic in proxy, Lens, MCP, runtime and adapters. Expose injectable clock/ID/provider interfaces for deterministic tests.
3. Model failure classes independently: auth error, policy unavailable, invalid policy, audit unavailable, approval timeout, provider timeout. Fail-open is an explicit authorized policy mode with evidence and narrow scope, never a catch-all fallback.
4. Carry policy version and input/action digest into approval requests; re-evaluate on resume. Unknown or unsupported obligations block execution with a structured explanation.
5. Define response-inspection modes and bounds; preserve pre-call prevention claims only where enforced.

Tests: rule corpus differential tests old/new for intended unchanged behavior; cross-surface ALLOW/WARN/APPROVAL/BLOCK; combination precedence; invalid/unknown rule; expired exception; response chunks split at sensitive boundaries; pending approval invokes no provider/tool. Gate: all surfaces produce semantically identical decisions on the same normalized input, subject to documented surface capabilities.

### T05 — Durable, verifiable evidence

Dependencies: T02/T04. Addresses S08/S09/S15.

1. Implement audit v2 tables, immutable writer role, canonical serialization, stable chain-head locking, and per-tenant sequence.
2. Move decision persistence ahead of protected effects; outbox outcome recording connects to T07. Return a receipt only after its durable intent exists. Record blocked/failed/cancelled/ambiguous paths too.
3. Implement verifier statuses `complete`, `legacy_partial`, `broken`, `unavailable`; report total events, hashed events, missing ranges, sequence gaps, checkpoint coverage and legacy window separately. Do not label an unhashed history valid in the UI.
4. Add external checkpoint format and signing-key rotation. Keep operational metrics mutable in separate tables; append corrections to evidence rather than overwriting history.
5. Backfill read indexes/metadata without claiming retroactive integrity; make exporters permission-checked async jobs with redacted output and expiry.

Tests: concurrent first append, simultaneous append, tied timestamps, altered actor/rule/cost/payload, missing hash, missing middle/tail with checkpoint, cross-tenant interleaving, crash before/after effect, audit DB outage. Gate: 100% of protected fixture effects link to durable decision/outcome and verifier accurately distinguishes old partial evidence.

### T06 — Bound latency, memory, and database work

Dependencies: T02/T04; final measurements include T05.

1. Add lifespan HTTP/Redis pools and instrument auth, policy, DB, provider, audit and queue latency. Set explicit bounded timeouts and concurrency.
2. Move blocking work out of async streaming/event-loop execution; never share one SQLAlchemy session across concurrent threads. Compute DB pool budget as replicas×processes×pool limit with headroom for workers/migrations.
3. Replace stream-wide accumulation with incremental parser and bounded inspection buffers. Close response/reader on every exit, including client cancellation; do not retry completed/maybe-completed model actions automatically.
4. Rewrite `insights.get_agents` and analogous measured paths to grouped SQL. Add cursor pagination, response limits, bounded report ranges, and matching indexes only after inspecting current indexes/query plans.
5. Cache immutable/versioned catalogs and compiled policies by workspace+policy version+gate. Publish invalidation after committed updates; test revocation/stale cache behavior. Do not cache authorization indefinitely.
6. Add representative load scenarios and publish baselines versus section 8 budgets. Separate unknown token/cost from zero; reconcile estimates to actual usage.

Gate: no N+1 growth in target endpoints, bounded memory with longer streams, acceptable event-loop/pool lag, and no security relaxation to reach performance targets.

### T07 — Durable workflow execution and isolated effects

Dependencies: T01/T02/T04/T05.

1. Add transactional outbox to run creation, approval resume, and webhook-triggered work. Existing Redis list remains transport during migration; DB is authoritative for intent/state.
2. Add fenced worker leases, heartbeat, maximum duration, terminal/retryable/ambiguous errors, and durable node checkpoints. Replace age-only reaper assumptions; healthy long runs must not be marked dead.
3. Define a single operation ID for every external effect. Propagate provider idempotency when available; query outcome or require reconciliation after ambiguous timeout. Never replay an entire DAG to recover one uncertain side effect.
4. Consolidate sandbox provider interface; no fallback to worker host. Enforce resource/time/network/filesystem limits, explicit working root, credential allowlist, and cleanup. SSH destinations require host-key verification and explicit workspace configuration.
5. Preserve pause/resume/cancel/approval semantics and dry-run guarantees. Dry run must not send notifications/create resources; credential availability may be validated without executing effects.

Tests: crash before DB commit, after commit/before enqueue, after queue move/before timestamp, during lease renewal, after provider success/before acknowledgment, Redis outage, provider outage, worker split-brain, concurrent approval clicks, expired approval, cancellation races, and sandbox cleanup. Gate: no lost durable intent or duplicated idempotent effect; uncertain external outcomes remain visible and reconcilable.

### T08 — Shared console foundation

Dependencies: T02/T03.

1. Implement auth group and bootstrap state machine: unknown → authenticating → workspace selection → permissions ready → application, with explicit error/no-membership states.
2. Introduce tenant-scoped query provider and typed API error handling. Adapt `useAuthFetch`, `WorkspaceContext`, `GuardRoleContext`, PreferencesContext and existing API facade in place before deleting old hooks.
3. Create tokens, accessible primitives, shell, command menu, navigation registry, five page templates and responsive inspector.
4. Scope auth/third-party scripts correctly, add loading/error boundaries, and close/cancel tenant state on switch/logout.
5. Seed visual fixtures and initial component interaction tests. Test that denied actions are hidden/disabled appropriately while server checks remain authoritative.

Gate: admin→viewer tenant switch never shows old data/permissions, stale responses are ignored, keyboard and mobile navigation work, and representative shell matches committed design references. Rollback: per-feature read/display flag; authorization fixes are always active.

### T09 — Migrate governance and management features

Dependencies: T04/T05/T06/T08.

Migrate in this order: identities/discovery → activity/receipts → policies → approvals → spend → compliance/reports → settings/integrations/members → packs/projects. Each vertical slice includes typed API facade, query keys, forms, loading/error states, permissions, URL state, live-data behavior, accessible template and tests.

Use the section 7 acceptance table as exact product requirements. Add optimistic-concurrency versions to policy/config editing; do not let stale forms overwrite newer settings. Publish policy updates transactionally with cache invalidation and evidence. Keep declared enforcement coverage separate from observed adoption.

Gate per slice: old URL works; critical action succeeds for the correct role and cannot execute for the wrong one; mutations survive retry correctly; data totals and detail links reconcile; responsive design checked; parity manifest marked migrated with test evidence.

### T10 — Replace Lens state and streaming orchestration

Dependencies: T04/T07/T08; report components from T09 where reused.

1. Split `GLensChatPage.tsx` into session navigation, composer, message store/reducer, stream transport, message renderers, action controller and run inspector. Preserve baseline stable IDs and localized clock components.
2. Persist message/event IDs and normalized message kinds. Use append-only message operations and version checks; retain transcript migration/rollback adapters.
3. Implement shared SSE parser with CRLF, multiple data lines, partial UTF-8, comments, event IDs, reconnect/backoff, cursor dedupe and cancellation. Bind subscription lifetime to workspace+principal+session.
4. Render pending/approved/executing/complete independently. Cancel generation explicitly; reconnect restores server truth. Preserve scroll unless user is following the latest messages; offer a new-events indicator.
5. Propagate real authority through tools, show grounded data source/scope, and never allow model content to select a workspace, bypass permission, approve itself, or run arbitrary rendering code.

Gate: long session + reconnect + concurrent tool events + workspace switch produces no lost/duplicate action or stale data, no feed remount/flicker regression, and no execution on policy/approval error.

### T11 — Replace workflow editing and run inspection

Dependencies: T07/T08/T10 shared stream infrastructure.

1. Split editor state, graph transformations, validation, block catalog, block forms and transport. Retain React Flow/Dagre and existing schemas where suitable.
2. Version graph state; protect against concurrent overwrite; preserve imported YAML and unknown optional fields according to schema compatibility policy. Add draft recovery and safe navigation away from unsaved work.
3. Provide keyboard-accessible graph alternative, reorder/connect validation, readable trigger→environment→guard→brain execution preview, and field-level setup feedback.
4. Lazy-load expensive inspectors/configuration. Use the shared run store/timeline for list, detail, workflow and Lens views; avoid four independent polling systems.

Tests: every bundled playbook import/export, cycles/invalid edges/missing blocks, invalid credential references, dry run, pause/approve/resume, retry/cancel, stale edit conflict, mobile inspection and long-run streaming. Gate: format and runtime parity with current workflows, plus section 8 editor budget.

### T12 — Marketing, docs, sharing, and content truth

Dependencies: T03/T08; audit statements depend on T05.

1. Remove WorkspaceProvider/private queries from public layout. Keep CTA authentication awareness in a small optional island. Replace hover-only menus with accessible controls.
2. Convert docs page into server-rendered content modules with shared heading anchors/search/index. Reuse repository docs as source; do not duplicate them in a 2,590-line client file.
3. Reuse exported logo/tokens/assets and existing copy. Make capability labels reflect release inventory; remove or qualify statements contradicted by actual enforcement/evidence.
4. Correct canonicals, OpenGraph metadata, sitemap, redirects and robots/noindex/cache policy. Preserve inbound links, installation path and provider docs URLs. Shared secret URLs get explicit referrer/noindex/cache controls.
5. Unify Markdown/report rendering without enabling untrusted HTML/JS; retain escaping or an explicitly constrained renderer. Optimize images/fonts and defer approved marketing widgets.

Gate: full public route/link check, keyboard navigation, no private API request on public load, correct metadata per representative route, no third-party widget on console/secret reports, and verified public performance targets.

### T13 — CLI, MCP, adapter and local-tool contracts

Dependencies: T02/T03/T04/T07.

1. Inventory `conduct-cli`, `conduct-daemon`, `conduct-litellm-guard`, `conduct-nemo-guard`, and `tools/booster`: exported APIs, CLI commands, platform support, filesystem outputs, dependencies, release workflows, tests and users. Keep client policy logic thin and central enforcement authoritative.
2. Generate typed Decision parsing and legacy text adapter with unknown/malformed outcomes covered. Keep package names and backward-compatible flags; version protocol behavior deliberately.
3. Implement MCP lifecycle/version negotiation, strict argument schemas, supported capabilities, session binding and resource limits. Negotiate transport before mutations; no mutation fallback/retry on ambiguous response. Test strict HTTP/SSE servers and expired auth.
4. Split large CLI files by commands and services without changing output/exit codes. Store local auth using OS keychain where available or mode-0600 files; atomically update config, preserve user edits, and provide uninstall/rollback.
5. Test wheels/sdists in clean environments, including daemon build-backend validity, optional dependency installation, real supported LiteLLM/NeMo integration bases, and Windows/macOS/Linux CLI paths. Treat unbuilt package metadata as unverified until the build test passes.
6. Add path containment, symlink, ignored-directory and input-size tests to local file indexing/hooks. Scope daemon binding/auth/IPC and prevent logs from containing credentials. Existing tooling must work offline only within the documented fail-mode guarantees.

Gate: clean install/import/command smoke per shipped package; old supported client/server contract tests; new protocol tests; no package publish during this planning/implementation step unless explicitly requested.

### T14 — Reproducible deployment and operations

Dependencies: T03/T05/T06/T07.

1. Build web from root lockfile/workspace manifest with npm ci; non-root runtime. API runtime image omits compilers/test packages; separate locked build/dev dependencies. Scan images and generate SBOMs.
2. Separate migration/seed/release job from API process startup. Set environment/auth/origin/egress settings explicitly in both API and worker. Add graceful shutdown, bounded request/drain times, and queue/lease recovery.
3. Implement `/live` and `/ready`; readiness checks DB/schema and required Redis/policy/audit availability without leaking details. Expose internal metrics via controlled access.
4. Add structured redacted traces, route-specific headers, log retention, request IDs and actionable alerts. Protect operator actions separately from workspace admin.
5. Document restore procedure, backup verification, key rotation, disabled integration behavior, incident containment, and exact feature rollback commands. Verify real ingress forwarded-header trust and actual RLS application role.

Gate: reproduce image from committed locks, staging restore+migration rehearsal, readiness fails accurately, worker can drain/restart, and no secrets in build artifacts/logs. Production rollout is a separately authorized action against a concrete staged result.

### T15 — Parity, staged cutover, and retirement

Dependencies: all prior tasks.

1. Require every route/API/tool/CLI inventory entry to be migrated, deliberately compatible, or explicitly deferred with retained working implementation. No silent omissions.
2. Shadow-read new query paths where useful. For new policy comparison, execute only one authoritative effect path; shadow policy results must never issue duplicate provider calls or approvals. Redact comparison telemetry.
3. Roll out UI/read changes by workspace: internal fixtures → limited pilot → 25% → all, advancing on agreed observation windows and no P0/P1 regressions. Fix a production security flaw broadly; do not leave the vulnerable implementation selectable by a canary flag.
4. Compare old/new query totals, audit coverage, policy decisions, denied-action counts, queue lag, stream stability, error rates, latency, cost and auth success. Threshold violations stop expansion automatically.
5. After the compatibility period, remove dead code/import shims/flags, update product truth/versioning docs, and ensure no old client or stored graph depends on the removed contract.

Gate: section 11 completion checklist, migration reconciliation, security regression suite, and an implementation report with exact commit/versions/results. A successful build alone never closes modernization.

## 10. Rewrite alternative if explicitly chosen

A full rebuild is justified only by an additional constraint this review did not establish: for example, an incompatible hosting requirement or a genuinely different product scope. It does not remove the urgent security work.

If the owner chooses a new application implementation, use these rules:

1. Complete T01 containment and T00 parity inventory first.
2. Create a new console directory/worktree against the same hardened API contracts and identity provider. Reuse approved design assets. Do not create fake API responses as the final product.
3. Implement the five templates, then all feature rows in section 7, preserving every old route via a route-level proxy/redirect map.
4. Keep existing database IDs and migrations. Rebuild backend modules one bounded domain at a time behind existing endpoints; audit and execution semantics follow sections 5–6.
5. Execute T02–T15 gates. Data migration and parallel code do not authorize dual external effects or dual token issuers.
6. Cut over only after full parity and restoration rehearsal. Maintain old reader compatibility during the notice period, while security fixes stay active.

The staged path is an order-of-magnitude planning effort of several weeks for an experienced small team, not a credible one-day rewrite. As rough, noncommittal planning ranges: containment 2–5 focused engineering days; shared contracts/gates/data foundations 2–4 weeks; feature migrations and operations 4–8 additional weeks with overlap. An entire backend+client+console recreation could take materially longer. These are estimates derived from scope, not measured delivery forecasts; T00 should replace them with task-level estimates.

## 11. Definition of done

- [ ] Every S01–S07/S14 critical boundary regression is fixed and cannot be re-enabled by configuration/feature flag accidents.
- [ ] Every finding has task, commit, test evidence, and status; any deferment names retained behavior and measured risk.
- [ ] Every baseline route, API, MCP tool, workflow/block format and CLI interface has a parity disposition.
- [ ] Real auth tests cover sign-in/signup/refresh/sign-out/invite/OAuth/CLI and tenant switching on the chosen dependency versions.
- [ ] Tenant, role, own/all, machine scope and platform-operator tests exercise valid requests with zero denied side effects.
- [ ] Guard outcomes, approvals and failure classes agree across all surfaces; ambiguous outcomes never become silent success.
- [ ] Protected effects have durable evidence; verifier reports partial/legacy history honestly; sequence/checkpoint tests pass.
- [ ] Migration counts/FKs/digests/business totals reconcile; restore/rollback rehearsal succeeds; no data was reset to satisfy tests.
- [ ] Worker/outbox/lease/crash/duplicate-event tests pass, including long healthy runs and sandbox outages.
- [ ] Web unit/contract/e2e/accessibility checks and API/CLI/adapter suites pass on reproducible runtime versions.
- [ ] Dependency/SAST/container scans are enforced, with only explicit time-limited reviewed exceptions.
- [ ] Performance targets are measured on documented fixtures and comparable builds; no unlimited streams/queries/queues are introduced.
- [ ] Public pages avoid private bootstrap; console uses shared design templates; real logo and copy preserved; no mock metrics presented as real.
- [ ] Staging readiness, observability, header policy, tenant DB roles, secrets, backups and migrations are verified.
- [ ] Production deployment, client package publication, customer messaging, and credential rotation have only occurred under the owner’s actual authorization.

## 12. Instructions for the implementing agent

Use `START-HERE.md` in the handoff package as the task prompt. Keep a machine-readable progress file with task ID, status, dependencies, changed paths, source commit, verification commands/results and unresolved blockers. After each completed task, run only the relevant validation plus mandatory gates; broaden tests to address a concrete risk. Never weaken tests, remove auth checks, set development defaults, or fabricate fixtures to claim success.

When a production secret, inaccessible branch setting or upstream service is needed, complete all local/staging work first and identify the exact remaining operation. Do not invent credentials or substitute a new provider. A blocked deployment does not block completing the implementation and its reviewable artifacts.

## 13. External references used for contract checks

The findings are grounded primarily in repository code. These primary specifications clarify the proposed corrections:

- A Clerk sign-in token is created for a specific user; it is an authentication capability, not proof that the caller owns an email. [Clerk createSignInToken](https://clerk.com/docs/reference/backend/sign-in-tokens/create-sign-in-token).
- Resource/data access still needs authorization even when a route or middleware checks authentication. [Next.js authentication guide](https://nextjs.org/docs/app/guides/authentication).
- Outbound destination validation must account for private addresses, redirects and DNS behavior. [OWASP SSRF prevention](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html).
- Strict MCP interoperability needs protocol/capability negotiation and initialization; implement a documented supported version set rather than echoing arbitrary versions. [MCP lifecycle](https://modelcontextprotocol.io/specification/2025-11-25/basic/lifecycle).
- The npm advisory data is retained in the handoff. Scanner severity is not proof of a reachable exploit in Conduct. Review upstream advisories and actual usage before selecting mitigation; the Clerk combined-authorization advisory does not itself imply compromised sessions. [Clerk’s published advisory](https://github.com/clerk/javascript/security/advisories/GHSA-w24r-5266-9c3c).

## Appendix A. Source index and complete web route inventory

The following appendix is generated from the pinned checkout. Repository-relative paths in the plan are implementation targets; source links point to the audit SHA, not a moving branch.

### A.1 Finding-to-source links

Some findings are cross-file or measurements. The files below are the relevant implementations; local validation evidence is in the handoff. Absence findings remain scoped to reviewed source and require deployment verification.

| Finding | Primary source files at the reviewed commit |
| --- | --- |
| S01 | [`apps/api/app/modules/guard/routers/trial.py`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/api/app/modules/guard/routers/trial.py); [`apps/api/app/modules/onboarding.py`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/api/app/modules/onboarding.py); [`apps/api/app/core/clerk.py`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/api/app/core/clerk.py) |
| S02 | [`apps/api/app/core/auth.py`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/api/app/core/auth.py); [`apps/api/app/core/config.py`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/api/app/core/config.py); [`render.yaml`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/render.yaml); [`apps/web/src/middleware.ts`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/middleware.ts) |
| S03 | [`apps/api/app/runtime/sandbox_session.py`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/api/app/runtime/sandbox_session.py); [`apps/api/app/runtime/sandbox.py`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/api/app/runtime/sandbox.py) |
| S04 | [`apps/api/app/modules/guard/routers/proxy.py`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/api/app/modules/guard/routers/proxy.py); [`apps/api/app/core/auth.py`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/api/app/core/auth.py); [`apps/api/app/modules/agent_identity/run_token_model.py`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/api/app/modules/agent_identity/run_token_model.py) |
| S05 | [`apps/api/app/modules/guard/routers/trial.py`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/api/app/modules/guard/routers/trial.py) |
| S06 | [`apps/api/app/mcp/server.py`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/api/app/mcp/server.py); [`apps/api/app/mcp/lens_adapter.py`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/api/app/mcp/lens_adapter.py) |
| S07 | [`apps/api/app/tools/registry.py`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/api/app/tools/registry.py); [`apps/api/app/tools/registrations/lens/guard_core.py`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/api/app/tools/registrations/lens/guard_core.py); [`apps/api/app/modules/glens/routers/chat.py`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/api/app/modules/glens/routers/chat.py); [`apps/api/app/mcp/lens_adapter.py`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/api/app/mcp/lens_adapter.py) |
| S08 | [`apps/api/app/guard/audit.py`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/api/app/guard/audit.py); [`apps/api/app/modules/guard/routers/verify.py`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/api/app/modules/guard/routers/verify.py); [`apps/api/app/modules/guard/routers/events.py`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/api/app/modules/guard/routers/events.py) |
| S09 | [`apps/api/app/modules/guard/models.py`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/api/app/modules/guard/models.py); [`apps/api/app/modules/guard/routers/verify.py`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/api/app/modules/guard/routers/verify.py) |
| S10 | [`apps/api/alembic/versions/0004_rls_workspace_isolation.py`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/api/alembic/versions/0004_rls_workspace_isolation.py); [`apps/api/app/core/database.py`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/api/app/core/database.py) |
| S11 | [`apps/api/app/routers/mcp_servers.py`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/api/app/routers/mcp_servers.py); [`apps/api/app/runtime/integrations/mcp_client.py`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/api/app/runtime/integrations/mcp_client.py) |
| S12 | [`apps/api/app/modules/guard/routers/trial.py`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/api/app/modules/guard/routers/trial.py); [`apps/api/Dockerfile`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/api/Dockerfile) |
| S13 | [`apps/web/src/app/layout.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/layout.tsx); [`apps/web/next.config.js`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/next.config.js) |
| S14 | [`.github/workflows/web-smoke.yml`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/.github/workflows/web-smoke.yml); [`apps/web/e2e/auth-setup.ts`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/e2e/auth-setup.ts) |
| S15 | [`apps/api/app/guard/router.py`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/api/app/guard/router.py); [`apps/api/app/core/clerk.py`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/api/app/core/clerk.py); [`apps/api/app/runtime/integrations/mcp_client.py`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/api/app/runtime/integrations/mcp_client.py) |
| P01 | [`apps/api/app/modules/guard/routers/proxy.py`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/api/app/modules/guard/routers/proxy.py); [`apps/api/app/mcp/server.py`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/api/app/mcp/server.py); [`apps/api/app/core/database.py`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/api/app/core/database.py) |
| P02 | [`apps/api/app/guard/router.py`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/api/app/guard/router.py); [`apps/api/app/modules/guard/routers/proxy.py`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/api/app/modules/guard/routers/proxy.py) |
| P03 | [`apps/api/app/guard/router.py`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/api/app/guard/router.py); [`apps/api/app/modules/guard/circuit_breaker.py`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/api/app/modules/guard/circuit_breaker.py) |
| P04 | [`apps/api/app/routers/insights.py`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/api/app/routers/insights.py) |
| P05 | [`apps/web/src/components/glens/GLensChatPage.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/components/glens/GLensChatPage.tsx); [`apps/web/src/components/canvas/CanvasEditor.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/components/canvas/CanvasEditor.tsx); [`apps/web/src/app/(marketing)/docs/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28marketing%29/docs/page.tsx) |
| P06 | [`apps/web/src/app/(marketing)/layout.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28marketing%29/layout.tsx); [`apps/web/src/lib/WorkspaceContext.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/lib/WorkspaceContext.tsx) |
| R01 | [`apps/api/app/core/queue.py`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/api/app/core/queue.py); [`apps/api/app/runtime/executor.py`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/api/app/runtime/executor.py); [`apps/api/app/worker.py`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/api/app/worker.py) |
| R02 | [`apps/api/app/modules/glens/routers/session_stream.py`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/api/app/modules/glens/routers/session_stream.py); [`apps/web/src/hooks/useLensSessionStream.ts`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/hooks/useLensSessionStream.ts) |
| R03 | [`apps/api/app/modules/glens/models.py`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/api/app/modules/glens/models.py); [`apps/api/app/modules/glens/routers/lens_sessions.py`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/api/app/modules/glens/routers/lens_sessions.py); [`apps/api/app/modules/glens/routers/chat.py`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/api/app/modules/glens/routers/chat.py) |
| R04 | [`apps/api/Dockerfile`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/api/Dockerfile); [`apps/api/app/main.py`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/api/app/main.py); [`apps/api/app/worker.py`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/api/app/worker.py) |
| R05 | [`load/health-baseline.js`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/load/health-baseline.js); [`.github/workflows/load-baseline.yml`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/.github/workflows/load-baseline.yml) |
| U01 | [`apps/web/src/lib/WorkspaceContext.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/lib/WorkspaceContext.tsx); [`apps/web/src/lib/GuardRoleContext.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/lib/GuardRoleContext.tsx) |
| U02 | [`apps/web/src/components/AppShell.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/components/AppShell.tsx); [`apps/web/src/app/globals.css`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/globals.css); [`docs/design/figma-console-2027/manifest.json`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/docs/design/figma-console-2027/manifest.json); [`docs/design/figma-console-2027/tokens.css`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/docs/design/figma-console-2027/tokens.css) |
| U03 | [`apps/web/src/app/(marketing)/layout.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28marketing%29/layout.tsx); [`apps/web/src/components/AppShell.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/components/AppShell.tsx) |
| U04 | [`apps/web/src/app/(app)/layout.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28app%29/layout.tsx); [`apps/web/src/app/(app)/workflows/[id]/error.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28app%29/workflows/%5Bid%5D/error.tsx) |
| U05 | [`apps/web/src/components/canvas/BlockEditor.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/components/canvas/BlockEditor.tsx); [`apps/web/src/components/canvas/CanvasEditor.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/components/canvas/CanvasEditor.tsx); [`apps/web/src/app/(app)/theguard/policies/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28app%29/theguard/policies/page.tsx) |
| U06 | [`apps/web/src/app/(app)/logs/guard/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28app%29/logs/guard/page.tsx); [`apps/web/src/app/(app)/theguard/spend/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28app%29/theguard/spend/page.tsx) |
| U07 | [`apps/web/src/app/share/[token]/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/share/%5Btoken%5D/page.tsx); [`apps/web/src/app/(app)/lens/report-builder/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28app%29/lens/report-builder/page.tsx) |
| U08 | [`apps/web/src/app/layout.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/layout.tsx); [`apps/web/src/app/robots.ts`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/robots.ts); [`apps/web/src/middleware.ts`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/middleware.ts) |
| Q01 | [`.github/workflows/ci.yml`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/.github/workflows/ci.yml); [`.github/workflows/dependency-security.yml`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/.github/workflows/dependency-security.yml); [`apps/web/src/components/guard/__tests__/GuardShell.test.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/components/guard/__tests__/GuardShell.test.tsx) |
| Q02 | [`apps/api/tests/conftest.py`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/api/tests/conftest.py); [`apps/api/tests/test_endpoint_matrix.py`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/api/tests/test_endpoint_matrix.py) |
| Q03 | [`package-lock.json`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/package-lock.json); [`apps/web/package.json`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/package.json) |
| Q04 | [`apps/api/requirements.txt`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/api/requirements.txt); [`apps/api/Dockerfile`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/api/Dockerfile); [`apps/web/Dockerfile`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/Dockerfile); [`package.json`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/package.json) |
| Q05 | [`packages/conduct-cli/src/conduct_cli/main.py`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/packages/conduct-cli/src/conduct_cli/main.py); [`apps/api/app/routers/workflows.py`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/api/app/routers/workflows.py); [`apps/web/src/components/glens/GLensChatPage.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/components/glens/GLensChatPage.tsx); [`package.json`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/package.json); [`packages/shared/package.json`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/packages/shared/package.json) |
| Q06 | [`README.md`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/README.md); [`REVIEW.md`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/REVIEW.md); [`docs/api-versioning.md`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/docs/api-versioning.md); [`docs/design/figma-console-2027/README.md`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/docs/design/figma-console-2027/README.md) |
| I01 | [`apps/api/app/runtime/integrations/mcp_client.py`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/api/app/runtime/integrations/mcp_client.py); [`apps/api/app/mcp/server.py`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/api/app/mcp/server.py) |
| I02 | [`apps/api/app/runtime/integrations/mcp_client.py`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/api/app/runtime/integrations/mcp_client.py) |
| I03 | [`packages/conduct-litellm-guard/src/conduct_litellm_guard/_client.py`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/packages/conduct-litellm-guard/src/conduct_litellm_guard/_client.py); [`packages/conduct-nemo-guard/src/conduct_nemo_guard/_decisions.py`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/packages/conduct-nemo-guard/src/conduct_nemo_guard/_decisions.py) |
| O01 | [`apps/api/app/main.py`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/api/app/main.py); [`apps/api/app/worker.py`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/api/app/worker.py) |

### A.2 Related GitHub work

| Item | Implementation relevance |
| --- | --- |
| [Baseline commit](https://github.com/sseshachala/conductai/commit/c918c6e051c0718eb7e61659b61fc1b8987fe3d6) | Preserve Lens stable message keys and localized elapsed-clock rendering |
| [PR #1785](https://github.com/sseshachala/conductai/pull/1785) | Reconcile approval/run optimistic-status changes |
| [PR #1783](https://github.com/sseshachala/conductai/pull/1783) | Reconcile LiteLLM event-hook support |
| [PR #1466](https://github.com/sseshachala/conductai/pull/1466) | Blocked framework/auth upgrade; reproduce sign-in failure before choosing dependency versions |
| [Main CI run](https://github.com/sseshachala/conductai/actions/runs/34553539516) | Baseline repository CI success does not imply all proposed gates exist |
| [Dependency Security run](https://github.com/sseshachala/conductai/actions/runs/34553539351) | Inspect tolerated failures in workflow configuration |

PR and workflow statuses are observations from the review, not promises of their state at implementation time.

### A.3 Complete web page inventory

122 page files. Task assignment below identifies the primary migration package; shared security/design tasks also apply. Client means the page file itself declares `use client`; a server page may still render client children. Bracketed segments retain their exact source names.

| Route pattern | Page mode | Primary task | Source |
| --- | --- | --- | --- |
| `/` | Client | T12 | [`apps/web/src/app/(marketing)/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28marketing%29/page.tsx) |
| `/about` | Server | T12 | [`apps/web/src/app/(marketing)/about/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28marketing%29/about/page.tsx) |
| `/accept-invite` | Client | T01 | [`apps/web/src/app/(app)/accept-invite/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28app%29/accept-invite/page.tsx) |
| `/agent-identity` | Client | T09 | [`apps/web/src/app/(app)/agent-identity/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28app%29/agent-identity/page.tsx) |
| `/audit` | Client | T09 | [`apps/web/src/app/(app)/audit/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28app%29/audit/page.tsx) |
| `/b/[id]/[token]` | Client | T12 | [`apps/web/src/app/(marketing)/b/[id]/[token]/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28marketing%29/b/%5Bid%5D/%5Btoken%5D/page.tsx) |
| `/benchmark` | Server | T12 | [`apps/web/src/app/(marketing)/benchmark/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28marketing%29/benchmark/page.tsx) |
| `/benchmark/[edition]` | Client | T12 | [`apps/web/src/app/(marketing)/benchmark/[edition]/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28marketing%29/benchmark/%5Bedition%5D/page.tsx) |
| `/benchmark/[edition]/[slug]` | Client | T12 | [`apps/web/src/app/(marketing)/benchmark/[edition]/[slug]/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28marketing%29/benchmark/%5Bedition%5D/%5Bslug%5D/page.tsx) |
| `/blog` | Server | T12 | [`apps/web/src/app/(marketing)/blog/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28marketing%29/blog/page.tsx) |
| `/blog/autonomous-agents-need-an-autonomous-guard` | Server | T12 | [`apps/web/src/app/(marketing)/blog/autonomous-agents-need-an-autonomous-guard/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28marketing%29/blog/autonomous-agents-need-an-autonomous-guard/page.tsx) |
| `/blog/cedar-cant-say-warn` | Server | T12 | [`apps/web/src/app/(marketing)/blog/cedar-cant-say-warn/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28marketing%29/blog/cedar-cant-say-warn/page.tsx) |
| `/blog/conduct-is-open-today` | Server | T12 | [`apps/web/src/app/(marketing)/blog/conduct-is-open-today/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28marketing%29/blog/conduct-is-open-today/page.tsx) |
| `/blog/fix-this-code` | Server | T12 | [`apps/web/src/app/(marketing)/blog/fix-this-code/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28marketing%29/blog/fix-this-code/page.tsx) |
| `/blog/governing-37-ai-agents-in-production` | Server | T12 | [`apps/web/src/app/(marketing)/blog/governing-37-ai-agents-in-production/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28marketing%29/blog/governing-37-ai-agents-in-production/page.tsx) |
| `/blog/guard-and-security-loop` | Server | T12 | [`apps/web/src/app/(marketing)/blog/guard-and-security-loop/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28marketing%29/blog/guard-and-security-loop/page.tsx) |
| `/blog/guard-on-agentic-governance-benchmark` | Server | T12 | [`apps/web/src/app/(marketing)/blog/guard-on-agentic-governance-benchmark/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28marketing%29/blog/guard-on-agentic-governance-benchmark/page.tsx) |
| `/blog/launch-hero` | Server | T12 | [`apps/web/src/app/(marketing)/blog/launch-hero/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28marketing%29/blog/launch-hero/page.tsx) |
| `/blog/mcp-enterprise-ready-what-the-spec-doesnt-solve` | Server | T12 | [`apps/web/src/app/(marketing)/blog/mcp-enterprise-ready-what-the-spec-doesnt-solve/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28marketing%29/blog/mcp-enterprise-ready-what-the-spec-doesnt-solve/page.tsx) |
| `/blog/mcp-gateway-launch` | Server | T12 | [`apps/web/src/app/(marketing)/blog/mcp-gateway-launch/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28marketing%29/blog/mcp-gateway-launch/page.tsx) |
| `/blog/one-policy-every-llm-call` | Server | T12 | [`apps/web/src/app/(marketing)/blog/one-policy-every-llm-call/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28marketing%29/blog/one-policy-every-llm-call/page.tsx) |
| `/blog/openrouter-one-policy-every-model` | Server | T12 | [`apps/web/src/app/(marketing)/blog/openrouter-one-policy-every-model/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28marketing%29/blog/openrouter-one-policy-every-model/page.tsx) |
| `/blog/rtk-how-we-cut-93-percent-of-cli-tokens` | Client | T12 | [`apps/web/src/app/(marketing)/blog/rtk-how-we-cut-93-percent-of-cli-tokens/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28marketing%29/blog/rtk-how-we-cut-93-percent-of-cli-tokens/page.tsx) |
| `/blog/stop-paying-opus-prices-for-haiku-work` | Client | T12 | [`apps/web/src/app/(marketing)/blog/stop-paying-opus-prices-for-haiku-work/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28marketing%29/blog/stop-paying-opus-prices-for-haiku-work/page.tsx) |
| `/blog/threat-modeling-is-a-playbook` | Server | T12 | [`apps/web/src/app/(marketing)/blog/threat-modeling-is-a-playbook/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28marketing%29/blog/threat-modeling-is-a-playbook/page.tsx) |
| `/blog/which-ai-model-for-which-task` | Client | T12 | [`apps/web/src/app/(marketing)/blog/which-ai-model-for-which-task/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28marketing%29/blog/which-ai-model-for-which-task/page.tsx) |
| `/blog/why-ai-reads-your-whole-file-when-it-only-needs-three-functions` | Client | T12 | [`apps/web/src/app/(marketing)/blog/why-ai-reads-your-whole-file-when-it-only-needs-three-functions/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28marketing%29/blog/why-ai-reads-your-whole-file-when-it-only-needs-three-functions/page.tsx) |
| `/book-demo` | Server | T12 | [`apps/web/src/app/(marketing)/book-demo/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28marketing%29/book-demo/page.tsx) |
| `/cli-auth` | Client | T01 | [`apps/web/src/app/(app)/cli-auth/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28app%29/cli-auth/page.tsx) |
| `/cli-login-success` | Server | T12 | [`apps/web/src/app/(marketing)/cli-login-success/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28marketing%29/cli-login-success/page.tsx) |
| `/compare` | Server | T12 | [`apps/web/src/app/(marketing)/compare/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28marketing%29/compare/page.tsx) |
| `/dashboard` | Client | T09 | [`apps/web/src/app/(app)/dashboard/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28app%29/dashboard/page.tsx) |
| `/deployment` | Server | T12 | [`apps/web/src/app/(marketing)/deployment/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28marketing%29/deployment/page.tsx) |
| `/discovery` | Server | T12 | [`apps/web/src/app/(marketing)/discovery/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28marketing%29/discovery/page.tsx) |
| `/docs` | Client | T12 | [`apps/web/src/app/(marketing)/docs/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28marketing%29/docs/page.tsx) |
| `/docs/discovery` | Server | T12 | [`apps/web/src/app/(marketing)/docs/discovery/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28marketing%29/docs/discovery/page.tsx) |
| `/docs/lens` | Server | T12 | [`apps/web/src/app/(marketing)/docs/lens/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28marketing%29/docs/lens/page.tsx) |
| `/docs/mcp-setup` | Server | T12 | [`apps/web/src/app/(marketing)/docs/mcp-setup/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28marketing%29/docs/mcp-setup/page.tsx) |
| `/docs/schema` | Server | T12 | [`apps/web/src/app/(marketing)/docs/schema/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28marketing%29/docs/schema/page.tsx) |
| `/eval` | Client | T12 | [`apps/web/src/app/(marketing)/eval/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28marketing%29/eval/page.tsx) |
| `/eval/[slug]` | Client | T12 | [`apps/web/src/app/(marketing)/eval/[slug]/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28marketing%29/eval/%5Bslug%5D/page.tsx) |
| `/evidence` | Server | T12 | [`apps/web/src/app/(marketing)/evidence/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28marketing%29/evidence/page.tsx) |
| `/frameworks` | Server | T12 | [`apps/web/src/app/(marketing)/frameworks/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28marketing%29/frameworks/page.tsx) |
| `/governance` | Client | T09 | [`apps/web/src/app/(app)/governance/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28app%29/governance/page.tsx) |
| `/guard` | Server | T12 | [`apps/web/src/app/(marketing)/guard/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28marketing%29/guard/page.tsx) |
| `/integrations` | Client | T09 | [`apps/web/src/app/(app)/integrations/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28app%29/integrations/page.tsx) |
| `/lens` | Client | T10 | [`apps/web/src/app/(app)/lens/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28app%29/lens/page.tsx) |
| `/lens/[sessionId]` | Client | T10 | [`apps/web/src/app/(app)/lens/[sessionId]/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28app%29/lens/%5BsessionId%5D/page.tsx) |
| `/lens/report-builder` | Client | T10 | [`apps/web/src/app/(app)/lens/report-builder/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28app%29/lens/report-builder/page.tsx) |
| `/logs` | Server | T09 | [`apps/web/src/app/(app)/logs/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28app%29/logs/page.tsx) |
| `/logs/guard` | Client | T09 | [`apps/web/src/app/(app)/logs/guard/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28app%29/logs/guard/page.tsx) |
| `/logs/observability` | Client | T09 | [`apps/web/src/app/(app)/logs/observability/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28app%29/logs/observability/page.tsx) |
| `/logs/runs` | Client | T11 | [`apps/web/src/app/(app)/logs/runs/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28app%29/logs/runs/page.tsx) |
| `/mcp-gateway` | Server | T12 | [`apps/web/src/app/(marketing)/mcp-gateway/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28marketing%29/mcp-gateway/page.tsx) |
| `/oauth-authorize` | Client | T01 | [`apps/web/src/app/(app)/oauth-authorize/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28app%29/oauth-authorize/page.tsx) |
| `/observability` | Server | T09 | [`apps/web/src/app/(app)/observability/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28app%29/observability/page.tsx) |
| `/observability/alerts` | Client | T09 | [`apps/web/src/app/(app)/observability/alerts/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28app%29/observability/alerts/page.tsx) |
| `/open-source` | Server | T12 | [`apps/web/src/app/(marketing)/open-source/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28marketing%29/open-source/page.tsx) |
| `/packs` | Client | T09 | [`apps/web/src/app/(app)/packs/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28app%29/packs/page.tsx) |
| `/packs/[slug]` | Client | T09 | [`apps/web/src/app/(app)/packs/[slug]/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28app%29/packs/%5Bslug%5D/page.tsx) |
| `/partners` | Client | T12 | [`apps/web/src/app/(marketing)/partners/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28marketing%29/partners/page.tsx) |
| `/playbooks/submit` | Client | T09 | [`apps/web/src/app/(app)/playbooks/submit/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28app%29/playbooks/submit/page.tsx) |
| `/pricing` | Server | T12 | [`apps/web/src/app/(marketing)/pricing/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28marketing%29/pricing/page.tsx) |
| `/privacy` | Server | T12 | [`apps/web/src/app/(marketing)/privacy/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28marketing%29/privacy/page.tsx) |
| `/projects` | Client | T09 | [`apps/web/src/app/(app)/projects/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28app%29/projects/page.tsx) |
| `/projects/[id]` | Client | T09 | [`apps/web/src/app/(app)/projects/[id]/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28app%29/projects/%5Bid%5D/page.tsx) |
| `/registry` | Server | T12 | [`apps/web/src/app/(marketing)/registry/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28marketing%29/registry/page.tsx) |
| `/router` | Client | T12 | [`apps/web/src/app/(marketing)/router/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28marketing%29/router/page.tsx) |
| `/runs` | Server | T09 | [`apps/web/src/app/(app)/runs/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28app%29/runs/page.tsx) |
| `/runs/[run_id]` | Client | T11 | [`apps/web/src/app/(app)/runs/[run_id]/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28app%29/runs/%5Brun_id%5D/page.tsx) |
| `/sdd` | Client | T12 | [`apps/web/src/app/(marketing)/sdd/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28marketing%29/sdd/page.tsx) |
| `/secure` | Client | T09 | [`apps/web/src/app/(app)/secure/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28app%29/secure/page.tsx) |
| `/secure/activity` | Client | T09 | [`apps/web/src/app/(app)/secure/activity/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28app%29/secure/activity/page.tsx) |
| `/security` | Server | T12 | [`apps/web/src/app/(marketing)/security/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28marketing%29/security/page.tsx) |
| `/settings` | Client | T09 | [`apps/web/src/app/(app)/settings/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28app%29/settings/page.tsx) |
| `/settings/modules` | Client | T09 | [`apps/web/src/app/(app)/settings/modules/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28app%29/settings/modules/page.tsx) |
| `/setup` | Client | T01 | [`apps/web/src/app/(app)/setup/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28app%29/setup/page.tsx) |
| `/share/[token]` | Client | T12 | [`apps/web/src/app/share/[token]/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/share/%5Btoken%5D/page.tsx) |
| `/sign-in/[[...sign-in]]` | Server | T01 | [`apps/web/src/app/(app)/sign-in/[[...sign-in]]/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28app%29/sign-in/%5B%5B...sign-in%5D%5D/page.tsx) |
| `/sign-up/[[...sign-up]]` | Server | T01 | [`apps/web/src/app/(app)/sign-up/[[...sign-up]]/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28app%29/sign-up/%5B%5B...sign-up%5D%5D/page.tsx) |
| `/solutions` | Server | T12 | [`apps/web/src/app/(marketing)/solutions/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28marketing%29/solutions/page.tsx) |
| `/solutions/action-governance` | Server | T12 | [`apps/web/src/app/(marketing)/solutions/action-governance/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28marketing%29/solutions/action-governance/page.tsx) |
| `/solutions/engineering-leaders` | Server | T12 | [`apps/web/src/app/(marketing)/solutions/engineering-leaders/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28marketing%29/solutions/engineering-leaders/page.tsx) |
| `/solutions/financial-services` | Server | T12 | [`apps/web/src/app/(marketing)/solutions/financial-services/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28marketing%29/solutions/financial-services/page.tsx) |
| `/solutions/life-sciences` | Server | T12 | [`apps/web/src/app/(marketing)/solutions/life-sciences/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28marketing%29/solutions/life-sciences/page.tsx) |
| `/solutions/memory-hardening` | Server | T12 | [`apps/web/src/app/(marketing)/solutions/memory-hardening/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28marketing%29/solutions/memory-hardening/page.tsx) |
| `/solutions/nemo-guardrails` | Server | T12 | [`apps/web/src/app/(marketing)/solutions/nemo-guardrails/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28marketing%29/solutions/nemo-guardrails/page.tsx) |
| `/solutions/okta-plus-conduct` | Server | T12 | [`apps/web/src/app/(marketing)/solutions/okta-plus-conduct/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28marketing%29/solutions/okta-plus-conduct/page.tsx) |
| `/solutions/security-compliance` | Server | T12 | [`apps/web/src/app/(marketing)/solutions/security-compliance/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28marketing%29/solutions/security-compliance/page.tsx) |
| `/solutions/security-loop` | Server | T12 | [`apps/web/src/app/(marketing)/solutions/security-loop/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28marketing%29/solutions/security-loop/page.tsx) |
| `/team-os` | Client | T12 | [`apps/web/src/app/(marketing)/team-os/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28marketing%29/team-os/page.tsx) |
| `/team-os/license` | Client | T12 | [`apps/web/src/app/(marketing)/team-os/license/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28marketing%29/team-os/license/page.tsx) |
| `/terms` | Server | T12 | [`apps/web/src/app/(marketing)/terms/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28marketing%29/terms/page.tsx) |
| `/theguard` | Client | T09 | [`apps/web/src/app/(app)/theguard/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28app%29/theguard/page.tsx) |
| `/theguard/activity` | Server | T09 | [`apps/web/src/app/(app)/theguard/activity/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28app%29/theguard/activity/page.tsx) |
| `/theguard/approvals` | Client | T09 | [`apps/web/src/app/(app)/theguard/approvals/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28app%29/theguard/approvals/page.tsx) |
| `/theguard/blocks/[id]` | Client | T09 | [`apps/web/src/app/(app)/theguard/blocks/[id]/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28app%29/theguard/blocks/%5Bid%5D/page.tsx) |
| `/theguard/compliance` | Client | T09 | [`apps/web/src/app/(app)/theguard/compliance/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28app%29/theguard/compliance/page.tsx) |
| `/theguard/discovery` | Client | T09 | [`apps/web/src/app/(app)/theguard/discovery/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28app%29/theguard/discovery/page.tsx) |
| `/theguard/policies` | Client | T09 | [`apps/web/src/app/(app)/theguard/policies/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28app%29/theguard/policies/page.tsx) |
| `/theguard/policies/new` | Client | T09 | [`apps/web/src/app/(app)/theguard/policies/new/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28app%29/theguard/policies/new/page.tsx) |
| `/theguard/reports/soc2` | Client | T09 | [`apps/web/src/app/(app)/theguard/reports/soc2/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28app%29/theguard/reports/soc2/page.tsx) |
| `/theguard/session-reports` | Client | T09 | [`apps/web/src/app/(app)/theguard/session-reports/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28app%29/theguard/session-reports/page.tsx) |
| `/theguard/session-reports/[id]` | Client | T09 | [`apps/web/src/app/(app)/theguard/session-reports/[id]/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28app%29/theguard/session-reports/%5Bid%5D/page.tsx) |
| `/theguard/settings` | Client | T09 | [`apps/web/src/app/(app)/theguard/settings/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28app%29/theguard/settings/page.tsx) |
| `/theguard/spend` | Client | T09 | [`apps/web/src/app/(app)/theguard/spend/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28app%29/theguard/spend/page.tsx) |
| `/theguard/team-memory` | Client | T09 | [`apps/web/src/app/(app)/theguard/team-memory/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28app%29/theguard/team-memory/page.tsx) |
| `/theguard/team-os` | Client | T09 | [`apps/web/src/app/(app)/theguard/team-os/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28app%29/theguard/team-os/page.tsx) |
| `/theguard/team-os/ai-rollout` | Client | T09 | [`apps/web/src/app/(app)/theguard/team-os/ai-rollout/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28app%29/theguard/team-os/ai-rollout/page.tsx) |
| `/theguard/try` | Client | T09 | [`apps/web/src/app/(app)/theguard/try/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28app%29/theguard/try/page.tsx) |
| `/token-guardrails` | Server | T12 | [`apps/web/src/app/(marketing)/token-guardrails/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28marketing%29/token-guardrails/page.tsx) |
| `/tools` | Client | T12 | [`apps/web/src/app/(marketing)/tools/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28marketing%29/tools/page.tsx) |
| `/tools/agent-booster` | Server | T12 | [`apps/web/src/app/(marketing)/tools/agent-booster/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28marketing%29/tools/agent-booster/page.tsx) |
| `/tools/conduct-cli` | Client | T12 | [`apps/web/src/app/(marketing)/tools/conduct-cli/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28marketing%29/tools/conduct-cli/page.tsx) |
| `/use-cases` | Server | T12 | [`apps/web/src/app/(marketing)/use-cases/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28marketing%29/use-cases/page.tsx) |
| `/what-is-conduct-ai` | Server | T12 | [`apps/web/src/app/(marketing)/what-is-conduct-ai/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28marketing%29/what-is-conduct-ai/page.tsx) |
| `/workflows` | Client | T11 | [`apps/web/src/app/(app)/workflows/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28app%29/workflows/page.tsx) |
| `/workflows/[id]` | Server | T11 | [`apps/web/src/app/(app)/workflows/[id]/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28app%29/workflows/%5Bid%5D/page.tsx) |
| `/workflows/[id]/runs` | Client | T11 | [`apps/web/src/app/(app)/workflows/[id]/runs/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28app%29/workflows/%5Bid%5D/runs/page.tsx) |
| `/workflows/[id]/runs/[run_id]` | Client | T11 | [`apps/web/src/app/(app)/workflows/[id]/runs/[run_id]/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28app%29/workflows/%5Bid%5D/runs/%5Brun_id%5D/page.tsx) |
| `/workflows/[id]/settings` | Client | T11 | [`apps/web/src/app/(app)/workflows/[id]/settings/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28app%29/workflows/%5Bid%5D/settings/page.tsx) |
| `/workflows/new` | Client | T11 | [`apps/web/src/app/(app)/workflows/new/page.tsx`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/%28app%29/workflows/new/page.tsx) |

### A.4 Next.js route handlers

| Route | Primary task | Source |
| --- | --- | --- |
| `/.well-known/oauth-authorization-server` | T13 | [`apps/web/src/app/.well-known/oauth-authorization-server/route.ts`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/.well-known/oauth-authorization-server/route.ts) |
| `/api/mcp/guard/oauth/authorize` | T13 | [`apps/web/src/app/api/mcp/guard/oauth/authorize/route.ts`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/api/mcp/guard/oauth/authorize/route.ts) |
| `/api/mcp/guard/oauth/callback` | T13 | [`apps/web/src/app/api/mcp/guard/oauth/callback/route.ts`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/api/mcp/guard/oauth/callback/route.ts) |
| `/api/mcp/guard/oauth/complete` | T13 | [`apps/web/src/app/api/mcp/guard/oauth/complete/route.ts`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/api/mcp/guard/oauth/complete/route.ts) |
| `/api/mcp/guard/oauth/register` | T13 | [`apps/web/src/app/api/mcp/guard/oauth/register/route.ts`](https://github.com/sseshachala/conductai/blob/c918c6e051c0718eb7e61659b61fc1b8987fe3d6/apps/web/src/app/api/mcp/guard/oauth/register/route.ts) |

### A.5 API and implementation manifests

The package includes all 339 static API declarations with method, path expression, handler, source line, sync/async status, and signature in `repository-inventory.json`. `api-parity-seed.json` adds task ownership and runtime-mount verification fields. Prefix composition, dynamic registration, WebSockets, MCP tools, and non-OpenAPI callbacks require the runtime inventory step in T00.

`findings.json` maps all 44 items to source and work packages. `task-plan.json` contains all 16 task specifications, dependencies, and empty evidence/status fields for implementation tracking. `route-parity.json` preserves all 127 page/handler files. None of these manifests marks implementation complete.

