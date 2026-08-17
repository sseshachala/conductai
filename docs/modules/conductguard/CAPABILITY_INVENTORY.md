# ConductGuard Capability Inventory

**Purpose:** ground-truth reference for every Guard capability that has actually shipped, with file:line refs. Prevents "audit drift" where LLM-driven summaries claim gaps for capabilities that already exist. Three prior audits missed live features by grepping too narrowly.

**How to use:** before proposing to build any Guard feature, grep this doc. If it's here, augment; don't rebuild. Regenerate this doc quarterly or on any major Guard merge.

**Note on attack terminology:** this doc deliberately avoids embedding literal attack keywords in prose because Guard's own detectors flag them. See pack JSON files for the full taxonomy.

**Last verified:** 2026-08-17 against `main`.

---

## 1. Skill packs (15 packs, 184 rules)

| Pack | Rules | Path |
|---|---|---|
| conduct-base | 44 | `apps/api/app/modules/guard/skill_packs/conduct-base.json` |
| conduct-prompt-injection | 30 | `apps/api/app/modules/guard/skill_packs/conduct-prompt-injection.json` |
| conduct-owasp | 25 | `apps/api/app/modules/guard/skill_packs/conduct-owasp.json` |
| conduct-endpoint-attacks | 10 | `apps/api/app/modules/guard/skill_packs/conduct-endpoint-attacks.json` |
| conduct-eu-ai-act | 10 | `apps/api/app/modules/guard/skill_packs/conduct-eu-ai-act.json` |
| conduct-iso-42001 | 10 | `apps/api/app/modules/guard/skill_packs/conduct-iso-42001.json` |
| conduct-nist-ai-rmf | 10 | `apps/api/app/modules/guard/skill_packs/conduct-nist-ai-rmf.json` |
| conduct-life-sciences | 9 | `apps/api/app/modules/guard/skill_packs/conduct-life-sciences.json` |
| conduct-financial-services | 8 | `apps/api/app/modules/guard/skill_packs/conduct-financial-services.json` |
| conduct-irs-1075 | 8 | `apps/api/app/modules/guard/skill_packs/conduct-irs-1075.json` |
| surface-aware | 7 | `apps/api/app/modules/guard/skill_packs/surface-aware.json` |
| conduct-hipaa | 4 | `apps/api/app/modules/guard/skill_packs/conduct-hipaa.json` |
| conduct-soc2 | 4 | `apps/api/app/modules/guard/skill_packs/conduct-soc2.json` |
| conduct-pci-dss | 3 | `apps/api/app/modules/guard/skill_packs/conduct-pci-dss.json` |
| meridian-dispatch | 2 | `apps/api/app/modules/guard/skill_packs/meridian-dispatch.json` |

## 2. Guard-related migrations (34 total)

| # | File | Purpose |
|---|---|---|
| 0010 | `0010_backfill_guard_audit_email.py` | Backfill audit user_email |
| 0011 | `0011_guard_policy_match_tokens.py` | Match token limits |
| 0012 | `0012_guard_session_ip_os.py` | Session client_ip + os_info |
| 0013 | `0013_guard_session_hostname.py` | Session hostname |
| 0014 | `0014_security_policy_category.py` | Security policy category |
| 0016 | `0016_guard_personas.py` | Personas on config, member config, policies |
| 0022 | `0022_guard_policy_findings_fields.py` | Findings vocabulary |
| 0024 | `0024_drop_guard_policies.py` | Skill packs become source of truth |
| 0029 | `0029_workflow_guard_settings.py` | Per-workflow Guard toggle + persona overr. |
| 0030 | `0030_backfill_guard_mcp_encrypted_auth.py` | Encrypt Guard MCP auth |
| 0031 | `0031_guard_audit_source_provider_model.py` | Audit source + provider + model |
| 0036 | `0036_guard_rule_override_match_pattern.py` | Per-workspace regex customization |
| 0038 | `0038_guard_audit_workflow_id.py` | Workflow linkage on audit events |
| 0039 | `0039_guard_session_intent.py` | Session intent + tool sequence + parser |
| 0044 | `0044_guard_discovery.py` | Shadow-agent discovery tables |
| 0048 | `0048_remove_env_proxy_config_rows.py` | Remove per-env proxy config |
| 0050 | `0050_drop_proxy_config_rows.py` | Drop proxy_config integration rows |
| **0052** | `0052_guard_audit_hash_chain.py` | **SHA-256 tamper-evident audit chain** |
| 0053 | `0053_guard_audit_policy_hash.py` | Snapshot policy version hash at decision |
| 0054 | `0054_guard_config_deny_on_error.py` | deny_on_error toggle |
| **0055** | `0055_guard_config_advisory_mode.py` | **Shadow / advisory mode** |
| 0056 | `0056_guard_audit_os_info_hostname.py` | os_info + hostname on audit |
| 0057 | `0057_guard_audit_tool_call_len.py` | Widen tool_call column |
| 0059 | `0059_guard_config_fail_closed_default.py` | Default fail_mode = fail_closed |
| 0060 | `0060_policy_certifications.py` | Quarterly review audit table |
| 0062 | `0062_guard_member_config_agent_identity_fk.py` | Link member config to agent_identities |
| 0063 | `0063_discovered_agents_proxy_routed.py` | Mark discovered agents proxy-routed |
| 0079 | `0079_guard_knowledge_index.py` | GLens semantic-search index |
| 0081 | `0081_audit_execution_result.py` | execution_status + result_summary |
| 0083 | `0083_guard_audit_event_goal.py` | Goal linkage on audit events |
| **0084** | `0084_guard_verify_runs.py` | **Guard Verify v2 battery results** |
| 0089 | `0089_guard_override_expiry.py` | Require expiry metadata on exceptions |
| 0092 | `0092_guard_notification_channels.py` | Per-action notification routing |
| 0093 | `0093_guard_approval_requests.py` | HITL approval flow |

## 3. Routers (20 files, 81 endpoints)

| Router | Endpoints |
|---|---|
| `routers/proxy.py` | POST /call, POST /vendor-key, POST /health |
| `routers/events.py` | POST, POST /usage, GET, GET /cost-trend, GET /stream, POST /batch, GET /unified, GET /audit/verify |
| `routers/verify.py` | GET /evidence, GET /chain, POST /run, GET /history |
| `routers/policies.py` | POST, GET, GET /{id}, GET /by-slug/{slug}, POST /{id}/rules, PATCH /{id}, DELETE /{id}, POST /{id}/override, POST /{id}/exception |
| `routers/config.py` | GET /installed, GET, PATCH, DELETE, GET /persona, PATCH /persona, PATCH /runtime-persona, POST /resync, POST /invite/regenerate |
| `routers/approvals.py` | POST, GET, GET /{id}, POST /{id}/decide, GET /{id}/stream |
| `routers/discovery.py` | POST /scan, GET /scans, GET /agents, POST /agents/{id}/register, GET /summary |
| `routers/mcp.py` | GET, DELETE, POST, POST |
| `routers/members.py` | GET, PATCH, DELETE, GET |
| `routers/spend.py` | GET /budget, GET /current, POST /configure, GET /trend, GET /breakdown |
| `routers/notifications.py` | GET, POST, PATCH, DELETE, POST |
| `routers/token_guardrails.py` | GET, PATCH |
| `routers/signing_key.py` | POST, GET, DELETE |
| `routers/session_reports.py` | GET /summary, GET /timeline, GET /violations, POST /export, GET /{id} |
| `routers/sessions.py` | PATCH |
| `routers/savings.py` | POST /report, GET /summary, GET /distribution |
| `routers/developer_tools.py` | POST, GET, GET /me |
| `routers/knowledge_search.py` | GET |
| `routers/memory_search.py` | GET |
| `routers/ws.py` | WebSocket handler |

## 4. Test files (22)

`test_guard.py`, `test_guard_policy_engine.py`, `test_guard_proxy.py`, `test_guard_test_battery.py`, `test_chain_verify.py`, `test_guard_pack_matrix.py`, `test_guard_enforcement_coverage.py`, `test_guard_approval.py`, `test_guard_cedar_inject_guidance.py`, `test_guard_events_api.py`, `test_guard_mcp_auth.py`, `test_guard_notifications.py`, `test_guard_override_expiry_migration.py`, `test_guard_policy_exceptions.py`, `test_guard_savings.py`, `test_guard_spend_month_window.py`, `test_okta_jwt.py`, `test_okta_jwt_bridge.py`, `test_okta_jwt_bridge_multi.py`, `test_okta_sync.py`, `test_mcp_autoprovision_guardconfig.py`, `test_asi_controls.py`

## 5. Capability audit — Conduct vs Pooja Kira's MCP gateway

Legend: **SHIPPED** = fully in production. **PARTIAL** = present but narrower than compared alternative. **GAP** = not shipped.

Attack-family details are intentionally not listed in this table — see the referenced pack files for the taxonomy.

| # | Capability | Status | Evidence |
|---|---|---|---|
| 1 | Machine-readable evidence policy / coverage doc | SHIPPED | `apps/api/scripts/generate_guard_enforcement_coverage.py`; `docs/modules/conductguard/enforcement_coverage.generated.md`; `app/modules/guard/coverage.py:28` |
| 2 | Prompt-injection detector | SHIPPED | `conduct-prompt-injection.json` — 30 rules across the OWASP LLM01 family; plus `conduct-base.json:38` as required baseline rule |
| 3 | Input normalization pipeline (zero-width strip / homoglyph map / Base64 decode / ROT13) | SHIPPED | `app/modules/guard/detectors/normalizer.py` — `normalize()` returns `list[Variant]` (raw first so anomaly rules still fire); wired into `routers/proxy.py:_rule_matches`; tests at `tests/test_guard_normalizer.py`. Ported (MIT) from `poojakira/mcp-agent-security-gateway`. Shipped in #1148 |
| 4 | Field-weighted risk scoring | PARTIAL | `models.py:417` `risk_score` column at session level; no per-field weighting |
| 5 | Suspicious URL heuristics | PARTIAL | `conduct-owasp.json:429` covers known exfil callback domains; `:284` covers credential exfil via outbound calls; `:692` covers DNS-tunnel patterns. Missing: raw-IP detection, TLD heuristics |
| 6 | Shadow mode (observe-without-enforce) | SHIPPED | Migration `0055_guard_config_advisory_mode.py`; `routers/config.py:52` `ConfigPatch.advisory_mode` |
| 7 | Kernel behavioral pre-check | PARTIAL | `conduct-endpoint-attacks.json` catches shell tool args. Missing: in-argument spawn-token detection across arbitrary tools |
| 8 | Server registry / shadow-server detection | SHIPPED | Migration `0044_guard_discovery.py`; `routers/discovery.py`; migration `0063_discovered_agents_proxy_routed.py` |
| 9 | CloudEvent-style verdict structure | GAP | Verified absent. Our verdict is single-rule attribution (`GuardVerdict` in `models.py`); no layered envelope |
| 10 | Multi-layer orchestrator | GAP | Verified absent. `policy_engine.py` is single-pass rule evaluation across surfaces, not layered |
| 11 | Adversarial test harness | SHIPPED | `app/modules/guard/test_battery.py` — 11+ ASI-tagged attack cases; `routers/verify.py` POST /run executes; migration `0084_guard_verify_runs.py` persists results; `test_guard_test_battery.py` |
| 12 | CI hardening (SHA-pinned actions, Trivy, Grype, CodeQL, Bandit, pip-audit, SBOM) | SHIPPED | 36 refs SHA-pinned across `.github/workflows/*.yml`; `.github/dependabot.yml` (github-actions/pip/npm); `codeql.yml`, `dependency-security.yml` (bandit + pip-audit + npm audit), `container-security.yml` (trivy + grype), `sbom.yml` (Syft CycloneDX + SPDX on release). Shipped in #1152. Baseline triage and hard-fail flip tracked in #1153 |
| 13 | RUNBOOK.md + QUICKSTART.md split | GAP | Verified absent from repo root, `docs/`, `docs/modules/conductguard/` |
| 14 | Anonymous mode toggle for dev | GAP (intentional) | Verified absent; not aligned with security model |
| 15 | W3C traceparent propagation | PARTIAL | Sentry OTel propagator only; no explicit W3C traceparent in Guard log emission |
| 16 | Circuit breaker with auto-recovery | PARTIAL | `models.py:45` `fail_mode` toggle; migrations `0054`, `0059`. Missing: closed / open / half-open state machine, failure_threshold, recovery_timeout |
| 17 | K8s deployment templates | GAP | Verified absent. Docker Compose exists for local dev only |
| 18 | Hash-chained audit log | SHIPPED | Migration `0052_guard_audit_hash_chain.py`; `models.py:18` `chain_hash_for_insert()` (SHA-256, per-workspace scoped, row-locked for race safety); `models.py:187` `entry_hash` column; `routers/verify.py:240` `verify_chain()` endpoint; `test_chain_verify.py` |
| 19 | BCC / exfil semantic analyzer (synonym map + intent) | GAP | Verified absent |

## 6. Capabilities we ship that Pooja does NOT have

| Capability | Evidence | Why it matters |
|---|---|---|
| Multi-tenant policy scoping (per-workspace) | Workspace-scoped `GuardConfig`, per-workspace rules, per-workspace audit chain | She's single-tenant; we scale to many customers on one deployment |
| Cross-surface enforcement contract | Every rule declares `enforcement.{proxy, hook, mcp, runtime}` with hard / conditional / advisory / not_supported guarantees | One rule declares behavior on 4 surfaces; hers is MCP-wire only |
| Compliance framework tagging | Every rule declares `frameworks` (OWASP, ISO 42001, GDPR, NIST, HIPAA, PCI-DSS, SOC2); ASI taxonomy in `asi_controls.py` | Auditors get direct rule-to-control mapping |
| Human-in-the-loop approval flow | Migration `0093_guard_approval_requests.py`; `routers/approvals.py`; `approval.py`; `test_guard_approval.py` | Blocked actions become approval requests |
| Notification channels per action | Migration `0092_guard_notification_channels.py`; `routers/notifications.py` (Slack, email, webhook) | Per-action routing |
| Token / turn / cost guardrails | `routers/token_guardrails.py`; migration `0060_policy_certifications.py`; ASI-03 excessive-agency control | Per-run budgets |
| Policy exception with expiry | Migration `0089_guard_override_expiry.py`; `test_guard_policy_exceptions.py` | Time-bounded exceptions |
| Shadow-agent discovery | Migration `0044_guard_discovery.py`; `routers/discovery.py` | Find unenrolled agents |
| Guard Verify v2 (evidence + chain + run + history) | Migration `0084_guard_verify_runs.py`; `routers/verify.py`; `test_battery.py` | Live "does Guard actually work?" endpoint suite |
| Cedar-based policy engine | `app/modules/guard/cedar_adapter/`; `test_guard_cedar_inject_guidance.py` | Declarative policy language |
| Per-workspace policy customization | Migration `0036_guard_rule_override_match_pattern.py` | Per-tenant regex tuning |
| Policy certifications (quarterly review) | Migration `0060_policy_certifications.py` | Compliance-audit primitive |
| Per-workflow Guard settings | Migration `0029_workflow_guard_settings.py` | Guard toggle + persona override per workflow |
| Guard Knowledge index (GLens) | Migration `0079_guard_knowledge_index.py`; `routers/knowledge_search.py` | Semantic search across Guard state |
| Agent identity linkage | Migration `0062_guard_member_config_agent_identity_fk.py` | Guard config bound to agent_identities table |
| Session-level intent + tool sequence | Migration `0039_guard_session_intent.py` | Per-session parser + tool sequence tracking |
| deny_on_error toggle | Migration `0054_guard_config_deny_on_error.py` | Hard-deny on evaluator errors |
| Audit-to-workflow linkage | Migrations `0038_guard_audit_workflow_id.py`, `0083_guard_audit_event_goal.py` | Deep-link audit to runs + goals |

## 7. What to check before proposing new Guard work

Before opening any "let's build X in Guard" issue, run this sequence:

1. Grep skill packs — is it already a rule?
2. List guard-related migrations — is there a migration for it?
3. List routers — is there an endpoint for it?
4. List guard tests — is there a test for it?
5. Check section 5 of this doc — is it marked SHIPPED or PARTIAL?

If any step 1–5 hits, the proposal should be "augment" not "build."

## 8. Regeneration

Run the enforcement-coverage generator and commit:

```
python3 apps/api/scripts/generate_guard_enforcement_coverage.py
```

Then re-run the systematic capability audit protocol (to be authored at `docs/modules/conductguard/AUDIT_PROTOCOL.md`).

Regenerate this doc on any of:

- New migration under `alembic/versions/` matching guard, audit, policy, proxy, hook, chain, approval, or verify
- New file under `app/modules/guard/routers/`
- New skill pack under `app/modules/guard/skill_packs/`
- Any change to `app/modules/guard/models.py`, `policy_engine.py`, `coverage.py`, `test_battery.py`, `approval.py`, or `asi_controls.py`
