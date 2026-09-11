# Modernization progress

Status of each audit finding against **current main**, not the audit baseline
(`c918c6e0`, 2026-09-11). Update when a PR closes a finding — reference the PR
number so future readers can trace it.

## Legend

| Marker | Meaning |
|---|---|
| ✅ Fixed | Closed on main. PR merged. |
| 🚧 In flight | Fix has an open PR. |
| ⚠️ Partial | Some work landed but the finding isn't fully closed. |
| 📋 Filed | Tracker issue exists (public or `conduct-internal`), no code yet. |
| ⏳ Open | Not addressed. |

## 3.1 Security & governance (15)

| ID | Priority | Status | Ref |
|---|---|---|---|
| S01 | P0 Critical | ✅ Fixed | #1794 — unauth trial credential issuance → challenge/redeem flow |
| S02 | P0 Critical | 📋 Filed | conduct-internal #46 — needs `ENVIRONMENT=production` in Render dashboard + code refuse-to-start |
| S03 | P0 Critical | 📋 Filed | conduct-internal #47 — sandbox LocalSession fallback (mitigated by S02 landing) |
| S04 | P0 High | 🚧 In flight | #1795 — proxy internal-agent path through shared resolver + `agent_run_tokens.expires_at` |
| S05 | P0 High | ✅ Fixed | #1794 — `/guard/trial/ops` moved to `require_platform_operator` |
| S06 | P0 High | 📋 Filed | conduct-internal #48 — MCP/Lens dispatch on policy exception + APPROVAL enforcement |
| S07 | P0 High | 📋 Filed | conduct-internal #48 — `ToolDef.permission` not enforced; Lens uses `system:lens` actor |
| S08 | P1 High | ⏳ Open | Audit chain hash material incomplete (missing actor/rule/cost/input) |
| S09 | P1 High | ⏳ Open | Chain-head locking races (no dedicated head row; timestamp-only ordering) |
| S10 | P1 High | ⏳ Open | RLS coverage partial (5 tables of ~30 sensitive) |
| S11 | P1 High | ⏳ Open | No shared outbound URL/SSRF guard |
| S12 | P1 High | ✅ Fixed | #1794 (trial paths) + #1793 (`events.py`) — trusted-proxy CIDR aware XFF, fail-closed Redis |
| S13 | P1 Medium | ⏳ Open | Narratr scripts on authenticated pages; no route-specific CSP |
| S14 | P0 High | ✅ Fixed | #1789 — web-smoke `.auth/` artifact restricted to allowlisted extensions |
| S15 | P1 Medium | ⏳ Open | Logs leak email/error details; no structured redaction |

## 3.2 Performance & reliability (11)

| ID | Priority | Status | Ref |
|---|---|---|---|
| P01 | P1 | ⏳ Open | Sync SQLAlchemy/JWT in async streaming; pool budget analysis |
| P02 | P1 | ⏳ Open | `_stream_chunks` retains full provider output; add bounded response inspection |
| P03 | P1 | ⏳ Open | Per-request AsyncClient with 600s timeout; provider-wide circuit breaker |
| P04 | P1 | ⏳ Open | `insights.get_agents` N+1 |
| P05 | P2 | ⏳ Open | Lens 300kB / editor 267kB / docs client-side — lazy-load + SSR docs |
| P06 | 🚧 In flight | #1796 — `WorkspaceProvider` out of marketing layout |
| R01 | P1 | ⏳ Open | Redis queue heartbeat/fencing + DB outbox |
| R02 | P1 | ⏳ Open | Lens SSE dedupe/backoff/auth-stop |
| R03 | P1 | ⏳ Open | Session messages as monolithic JSON blob; optimistic concurrency |
| R04 | P1 | ⏳ Open | Migrations on API startup |
| R05 | P2 | ⏳ Open | Load scenarios only exercise `/health` |

## 3.3 UX & frontend maintainability (8)

| ID | Priority | Status | Ref |
|---|---|---|---|
| U01 | P1 | ⏳ Open | WorkspaceProvider retains previous workspace on failed refresh |
| U02 | P2 | ⏳ Open | Design tokens diverge from committed exports |
| U03 | P1 | ⏳ Open | Marketing dropdowns hover-only; command palette not focus-managed |
| U04 | P2 | ⏳ Open | No route-local loading/error files |
| U05 | P2 | ⏳ Open | CanvasEditor/BlockEditor combine form + transport + presentation |
| U06 | P2 | ⏳ Open | List/log/inspector state patterns diverge |
| U07 | P2 | ⏳ Open | Shared report views hand-built Markdown formatting |
| U08 | P2 | ⏳ Open | Root metadata defaults every inheriting page to homepage canonical |

## 3.4 Code quality, protocols, dependencies, delivery (10)

| ID | Priority | Status | Ref |
|---|---|---|---|
| Q01 | P0 | ⚠️ Partial | #1789 — API job title corrected (`typecheck` claim removed). Flake8 `\|\| true` + missing typecheck + scanner `continue-on-error` still open. |
| Q02 | P1 | ⏳ Open | Global permissive auth fixtures |
| Q03 | P0 | ⏳ Open | npm dependency graph vulns (6 high, 1 moderate) |
| Q04 | P1 | ⏳ Open | Runtime/dev dep lock separation; Docker build image |
| Q05 | P2 | ⏳ Open | Large CLI/UI files; duplicated API types; `packages/shared` unused |
| Q06 | P2 | ⏳ Open | Docs disagree with code on framework version, protocol version, guarantees |
| I01 | P1 | ⏳ Open | MCP client posts tools/list without initialization/version negotiation |
| I02 | P1 | ⏳ Open | MCP `call_tool` retries mutations after ambiguous responses |
| I03 | P1 | ⏳ Open | LiteLLM/NeMo compat parses text prefixes; treats empty/`ok` as allow |
| O01 | P1 | ⏳ Open | `/health` constant success; `/metrics` public; separate liveness/readiness |

## Score

| Category | Fixed | In flight | Partial | Filed | Open | Total |
|---|---|---|---|---|---|---|
| Security | 4 | 1 | 0 | 4 | 6 | 15 |
| Perf/Reliability | 0 | 1 | 0 | 0 | 10 | 11 |
| UX | 0 | 0 | 0 | 0 | 8 | 8 |
| Code quality | 0 | 0 | 1 | 0 | 9 | 10 |
| **Total** | **4** | **2** | **1** | **4** | **33** | **44** |

## Update protocol

When a PR merges that closes or advances a finding:

1. Move the row's marker (⏳ → 🚧 → ✅ or ⚠️).
2. Append the PR number in the Ref column.
3. Update the score table at the bottom.
4. Commit the change on the same PR when possible so history stays coherent.
