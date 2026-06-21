# Conduct AI — Governance Northstar
**v0.2 · June 21, 2026 · Houston**

Sibling to [NORTHSTAR.md](./NORTHSTAR.md) — expands Layer 6 (Trust & Compliance) into the operational spec for the **AI Governance** surface.

> **v0.2 changelog:** Status flags verified against codebase with `file:line` citations. Coverage score revised **22% → ~38%** after audit. Two "Now" items revised: budget hard-stop backend is shipped (UI is the actual gap); fail-open is hardcoded (config flag is the actual gap).

---

## TL;DR

Every enterprise AI deal in 2026 will be won or lost on governance. The competitor of record is TrustLayers (EU-native, async, regulator-buyer). Our wedge is **inline enforcement + US-native + developer install in 10 minutes**. This doc enumerates the full 10-layer governance surface, verified coverage (~38% today), the 90-day target (~60%), and the five immediate items that compound into a defensible position.

The thesis in one line: **TrustLayers tells you what happened. ConductAI stops it before it happens.**

---

## 1. Competitive Frame

| | TrustLayers | ConductAI Guard |
|---|---|---|
| Enforcement | **Async** — logs after execution | **Inline** — blocks before execution |
| Geography | EU-first (France + Lithuania) | US-native |
| Buyer | Legal, compliance, regulators | VP Eng, CISO, CFO |
| Language | EU AI Act Articles | Developer-native, SOC 2 |
| Install | SDK / API | `pip install conduct-cli` |
| Shadow AI detection | No | Yes — passive, zero registration |
| Run-data flywheel | No | Yes — compounding moat |
| MCP-native | No | Yes |

**Decision:** We do not chase EU AI Act Annex IV documentation in v1. We win the US first, then either partner with TrustLayers or build EU coverage at the 12-month mark when a paying EU customer demands it.

---

## 2. Architectural Foundation

Guard is one surface. Three ingestion paths into a single canonical table.

| Path | Source | Code |
|---|---|---|
| 1. Inline hook | PreToolUse from Claude Code / Cursor / Codex / Copilot | `apps/api/app/modules/guard/routers/mcp.py:195` |
| 2. Workflow-driven | `type: guard` block evaluates policies mid-run | `apps/api/app/runtime/blocks/guard_block.py:137` |
| 3. API ingest | `POST /guard/events` for guardctl + external | `apps/api/app/modules/guard/routers/events.py:322` |

**Canonical table:** `guard_audit_events` ([`apps/api/app/modules/guard/models.py:82`](./apps/api/app/modules/guard/models.py)). Columns `conductai_run_id` + `conductai_workflow` exist specifically to link playbook-driven findings to the same audit log used by inline events.

### ❗ Architectural Gap

**Zero of the 10 security playbooks** (`security-scanner`, `security_loop`, `security-autopilot-fix`, `security-patch-updater`, `bughunter-active-scan`, `pr-reviewer`, `copilot-reviewer`, `terraform-reviewer`, `codebase-guard-monitor`, `multi-repo-scanner`) write to `guard_audit_events` today. None use `type: guard`, none POST to `/guard/events`, none reference `GuardAuditEvent`.

They emit findings as PR comments, issues, or Slack messages — none of which flow into the unified audit log. **SOC 2 export today would show inline events only — not security scan results.** The "Guard = single source of governance evidence" narrative is half-built.

**Fix:** Executor-level auto-sync. Any block output containing `findings: [...]` posts to `/guard/events` automatically. One executor change. Every existing + future playbook benefits. No YAML edits required.

---

## 3. The 10-Layer Coverage Surface

Status legend: ✅ have · ⚠️ partial · ❌ gap · *Phase: **Now** = current sprint / **90d** = required for first enterprise deal / **12m** = roadmap*

### Layer 1 — Identity & Access
| Item | Status | Citation | Phase |
|---|---|---|---|
| Developer identity (Clerk SSO) | ✅ | `apps/api/app/core/auth.py:142,242,342` | — |
| Agent identity (Claude Code / Cursor / Codex / Copilot detect) | ✅ | `packages/conduct-cli/src/conduct_cli/hook_template.py:224` (`_detect_ai_tool`) | — |
| Model identity (which model fired) | ⚠️ logged not enforced | `guard_audit_events.tool_call` column | 90d |
| Service-account vs human distinction | ❌ | — | 90d |
| RBAC for governance config (4 roles) | ✅ | `apps/api/app/core/auth.py:516` (`{admin, developer, security, viewer}`) | — |
| `require_permission()` dependency for endpoints | ✅ | `apps/api/app/core/auth.py:547` | — |
| Break-glass override with audit | ❌ | — | 90d |
| Per-team / per-department policies | ⚠️ workspace-level only | `apps/api/app/modules/guard/models.py:10` (`guard_config`) | 90d |

### Layer 2 — Policy & Decision
| Item | Status | Citation | Phase |
|---|---|---|---|
| Inline block/warn/allow | ✅ | `apps/api/app/modules/guard/policy_engine.py` + `routers/mcp.py:195` | — |
| Persona JSON (Conservative/Standard/Developer) | ✅ | migration `0016_guard_personas.py`; `guard_config.persona`, `guard_member_config.persona`, rule-level `persona_affinity` | — |
| Skill packs (versioned rule bundles) | ✅ | `apps/api/app/modules/guard/skill_packs/conduct-base.json`; `models.py:204` (`SkillPack`) | — |
| Per-workspace rule overrides | ✅ | `apps/api/app/modules/guard/models.py:247` (`GuardRuleOverride`) | — |
| Workspace custom rules | ✅ | `apps/api/app/modules/guard/models.py:231` (`WorkspaceCustomRule`) | — |
| Pre-computed policy cache (perf) | ✅ | `apps/api/app/modules/guard/models.py:261` (`GuardPolicyCache` with `version_hash`) | — |
| Dynamic propagation (no restart) | ✅ | policy cache invalidated on pack/override change | — |
| Policy versioning + rollback UI | ⚠️ versioned in DB, no UI rollback | — | 90d |
| Policy simulation / dry-run | ❌ | — | 90d |
| Per-repo / per-project overrides | ❌ | — | 90d |
| Rule precedence + conflict resolution | ⚠️ implicit (last-write-wins) | `policy_engine.compute_policy` | 90d |
| Time-bound policies (after-hours stricter) | ❌ | — | 12m |
| Geo-aware policies (EU vs US) | ❌ | — | 12m |

### Layer 3 — Action Enforcement
| Item | Status | Citation | Phase |
|---|---|---|---|
| PreToolUse interception | ✅ | `packages/conduct-cli/src/conduct_cli/hook_template.py:2` | — |
| PostToolUse outcome log | ✅ | `hook_template.py:608` | — |
| Tool whitelist / blacklist (via skill pack rules) | ✅ | `skill_packs/conduct-base.json` rules with `match_tool` | — |
| Destructive command detection (`rm -rf`, `git reset --hard`, etc.) | ✅ | `skill_packs/conduct-base.json:9` (`no-rm-rf`, `no-git-reset-hard`) | — |
| Production system block (prod deploy gate) | ⚠️ rule-based, not explicit "prod" concept | — | 90d |
| Network egress control (allowed domains) | ❌ | — | 12m |
| Resource / time quotas | ❌ | — | 12m |
| Approval block (workflow-level) | ✅ | `apps/api/app/runtime/blocks/approval_block.py:14` (`_execute_approval`) | — |
| **Approval in PreToolUse hook** | ❌ | — | **Now** |
| Multi-party approval | ❌ | — | 90d |

### Layer 4 — Data Governance
| Item | Status | Citation | Phase |
|---|---|---|---|
| PII screening (EMAIL/PHONE/SSN/CARD/IP) | ✅ | `apps/api/app/core/pii.py:17-26` | — |
| Secrets detection — Layer 1 structural (AWS/GitHub/PEM) | ✅ | `apps/api/app/core/pii.py:27-39` (`_STRUCTURAL`) | — |
| Secrets detection — Layer 2 bare-in-text (sk-, xox*, Bearer) | ✅ | `apps/api/app/core/pii.py:40+` (`_BARE`) | — |
| Secrets detection — Layer 3 context-aware catch-all | ✅ | `apps/api/app/core/pii.py:5-8` (3-layer doc) | — |
| Secrets pattern matching in hook (sk-, OpenAI keys) | ✅ | `packages/conduct-cli/src/conduct_cli/hook_template.py:344` (`SECRET_PATTERNS`) | — |
| PII redaction in logs | ✅ | `pii.py` substitutes `[EMAIL]`, `[SSN]`, etc. | — |
| Prompt injection detection | ❌ | — | 90d |
| Output governance (block model emitting customer PII) | ❌ | — | 90d |
| Data classification (PHI/PCI/GDPR labels) | ❌ | — | 12m |
| Data lineage (data → model → output) | ❌ | — | 12m |
| Cross-tenant isolation (RLS) | ✅ | `apps/api/app/core/workspace_context.py:16` (`set_workspace_rls`) | — |
| Data residency enforcement | ❌ | — | 12m |
| Right-to-be-forgotten (GDPR Article 17) | ❌ | — | 12m |
| Retention policy (configurable) | ❌ | — | 90d |

### Layer 5 — Spend / FinOps
| Item | Status | Citation | Phase |
|---|---|---|---|
| Per-developer / per-tool / per-day spend tracking | ✅ | `apps/api/app/modules/guard/routers/spend.py` | — |
| `GuardSpendBudget` model (monthly + hard cap + per-dev) | ✅ | `apps/api/app/modules/guard/models.py:150` | — |
| Hard-cap enforcement endpoint | ✅ | `apps/api/app/modules/guard/routers/spend.py:500` (`/budget-check`) | — |
| Hook calls budget-check + blocks at cap | ✅ | `packages/conduct-cli/src/conduct_cli/hook_template.py:688-699` (`rule_id="budget-hard-cap"`) | — |
| Soft warning at % threshold (5% buckets, anti-spam) | ✅ | `apps/api/app/modules/guard/routers/events.py:157` (`_check_spend_budget`) | — |
| Slack alert on threshold | ✅ | `events.py` (Slack notification path) | — |
| **Budget management UI** (set/show limits per dev) | ❌ | — | **Now** |
| Per-project cost-center allocation | ❌ | — | 90d |
| Anomaly detection (spend spike) | ⚠️ playbook only | `apps/api/playbooks/ai-drift-detector.yaml` | 90d |
| Model-selection economy (auto-downgrade) | ⚠️ routing exists | — | 90d |
| Cache hit-rate tracking (RTK + Booster) | ✅ | `models.py:114` (`GuardSavings`) | — |

### Layer 6 — Reporting & Audit
| Item | Status | Citation | Phase |
|---|---|---|---|
| Full event log + search | ✅ | `apps/api/app/modules/guard/routers/events.py` | — |
| **Security playbook findings → unified audit log** | ❌ | playbooks don't write to `guard_audit_events` | **Now** |
| Framework coverage API (SOC2 / ISO 42001 / OWASP / PCI / GDPR) | ✅ | `apps/api/app/routers/governance.py:124` (`/governance/frameworks`); rules tagged `frameworks: [...]` in skill packs | — |
| Plain-English narrative endpoint | ⚠️ template-based, LLM upgrade planned | `apps/api/app/routers/governance.py:134` (`/governance/narrative`) | 90d |
| **SOC 2 export PDF** (rendered, board-ready) | ❌ | no PDF lib (reportlab/weasyprint) anywhere | **Now** |
| ISO 42001 export PDF | ❌ rules tagged, render missing | rules carry `frameworks: ["ISO_42001:8.4"]` | 90d |
| NIST AI RMF mapping | ❌ | — | 90d |
| EU AI Act Annex IV docs | ❌ | — | 12m (concede or partner) |
| GDPR Article 30 records | ❌ | — | 12m |
| Tamper-evident logs (hash chain or signed) | ❌ | — | 90d |
| Scheduled reports (weekly/monthly email) | ❌ | — | 90d |
| SIEM export (Splunk/Datadog/Elastic) | ❌ | — | 90d |
| Custom report builder | ❌ | — | 12m |
| Long-term immutable storage (S3 cold) | ⚠️ Postgres only | — | 90d |

### Layer 7 — Detection & Monitoring
| Item | Status | Citation | Phase |
|---|---|---|---|
| Shadow AI tool detection | ✅ | `packages/conduct-cli/src/conduct_cli/main.py:236` (`_detect_ai_tools`) | — |
| Guard self-status MCP tool | ✅ | `apps/api/app/modules/guard/routers/mcp.py:38,342` (`guard_status`) | — |
| AI drift / behavioral anomaly | ⚠️ playbook only | `apps/api/playbooks/ai-drift-detector.yaml:105` (budget burn, policy spikes, shadow usage, quality drops, over-reliance) | 90d |
| Compromised agent / jailbreak detection | ❌ | — | 12m |
| Real-time alerts (Slack/PagerDuty/email) | ⚠️ Slack only | — | 90d |

### Layer 8 — Integration Surface
| Item | Status | Citation | Phase |
|---|---|---|---|
| CLI install (`conduct-cli`) | ✅ | `packages/conduct-cli/src/conduct_cli/guard.py` | — |
| MCP-native | ✅ | `apps/api/app/modules/guard/routers/mcp.py` | — |
| Cursor MCP registration | ✅ | `guard.py:261` (`~/.cursor/mcp.json`) | — |
| VS Code MCP registration | ✅ | `guard.py:248` (`_vscode_mcp_paths`) | — |
| Codex hook install | ✅ | `guard.py:306` (`_install_codex_hook`) | — |
| Claude Code hook install | ✅ | `guard.py` (primary install path) | — |
| JetBrains / Windsurf / Zed | ❌ | — | 90d |
| CI/CD enforcement (GH Actions / GitLab / Jenkins) | ⚠️ via playbooks + webhooks | — | 90d |
| Programmatic API for policy config | ✅ | `apps/api/app/modules/guard/routers/policies.py` | — |
| Webhook ingress for non-MCP tools | ❌ | — | 12m |

### Layer 9 — Vendor / Supply Chain
| Item | Status | Citation | Phase |
|---|---|---|---|
| Skill pack provenance (versioned rule bundles) | ✅ | `models.py:204` (`SkillPack` + `WorkspaceSkillPack`) | — |
| Vendor risk per AI provider (DPA tracking) | ❌ | — | 12m |
| Model provenance tracking | ❌ | — | 12m |
| Third-party MCP server vetting | ❌ | — | 90d |
| Marketplace governance (approved plugins list) | ❌ | — | 90d |

### Layer 10 — Operations
| Item | Status | Citation | Phase |
|---|---|---|---|
| Fail-open behavior when Guard is down | ✅ DECIDED (hardcoded) | `packages/conduct-cli/src/conduct_cli/hook_template.py:90,125` (try/except → return False; "Never block a tool call due to sync failure") | — |
| **Config flag for fail-closed mode** (opt-in) | ❌ | — | **Now** |
| Local policy cache (offline survival) | ✅ | `hook_template.py:36,92` (POLICY_PATH + BUDGET_CACHE_PATH, 5-min TTL) | — |
| Multi-region failover | ❌ | — | 12m |
| Policy A/B testing | ❌ | — | 12m |
| Sandbox env for testing new policies | ❌ | — | 90d |

---

## 4. Coverage Score

| | Today (v0.2 verified) | 90-day target | 12-month target |
|---|---|---|---|
| **Total surface coverage** | **~38%** | **~60%** | **~80%** |

90-day adds: budget management UI, SOC 2 PDF render, security-playbook auto-sync, approval-in-hook, fail-closed config flag, prompt-injection detection, JetBrains/Windsurf/Zed integrations, tamper-evident logs, SIEM export, scheduled reports, retention policy UI, per-repo overrides, policy dry-run, multi-party approval, anomaly detection in core (not just playbook).

12-month concedes: EU AI Act Annex IV (TrustLayers' specialty), data residency, GDPR right-to-be-forgotten, multi-region failover — unless a paying EU customer demands sooner.

---

## 5. The Five Now Items

In priority order (revised after audit — backend gaps were smaller than expected):

1. **Budget Management UI** — backend is fully shipped (`GuardSpendBudget` model + `/budget-check` endpoint + hook integration). Only the page to set/visualize per-developer limits is missing. ~1 sprint.
2. **SOC 2 Export PDF** — framework mapping API and rule tagging are done (`/governance/frameworks` + skill pack `frameworks: [...]` arrays). PDF render layer is the gap. ~1 sprint.
3. **Approval in PreToolUse hook** — `_execute_approval` block exists at workflow layer; lift the same contract into a `PENDING` decision returned from the hook, with Slack/email release link and 5-min auto-deny. ~1 sprint.
4. **Config flag for fail-closed mode** — fail-open is already the hardcoded default (and the right one for most customers). Add a config flag `guard.enforcement.on_outage = fail_open | fail_closed` so security-critical buyers can opt into fail-closed. ~2 days.
5. **Security playbook findings → `guard_audit_events`** — executor auto-sync any block output with `findings: [...]` to `POST /guard/events`. Zero playbook YAML changes. Closes the unified-surface gap. ~1 sprint.

---

## 6. Buyer Mapping

| Buyer | Owns layers | First conversation hook |
|---|---|---|
| **VP Eng / CTO** | 1, 2, 3, 5, 8 | "Install in 10 min. Block bad commands before they run. See every AI tool your team is actually using." |
| **CISO** | 3, 4, 6, 7 | "589 PII events screened, 6 prod deploys intercepted, in 18 days. One-click SOC 2." |
| **CFO** | 5 | "$381/day in AI spend you didn't see. Hard-cap by developer. $4,700/yr already saved per dev." |
| **Compliance / Legal** | 6 + parts of 4 | "Every AI action mapped to SOC 2 controls. Audit trail is tamper-evident." |
| **DPO (EU)** | — | Concede or partner with TrustLayers until a paying EU customer demands native EU coverage. |

---

## 7. Anti-Patterns

- **Don't build EU AI Act Annex IV docs ahead of a paying EU customer.** Engineering opportunity cost is too high. Partner with TrustLayers if needed.
- **Don't market the 10-layer coverage as a feature claim.** Buyers will check. Only surface layers we score ≥80% on.
- **Don't fork Guard into a separate "secure" module.** The unified surface (one audit table, one policy engine, one UI) IS the moat. Forking destroys it.
- **Don't ship SOC 2 export without the security-playbook auto-sync first.** A PDF that doesn't include scan findings undersells the product.
- **Don't build human-in-the-loop as a new system.** Reuse the existing `_execute_approval` contract — just expose it at the hook layer.
- **Don't flip the default to fail-closed.** Hook-down should never break developer flow. Make fail-closed an opt-in for security-critical workloads only.

---

## 8. Tied To

- **Epic:** _(to be created — link will be added here once filed)_
- **Code anchors:** [`apps/api/app/modules/guard/models.py:82`](./apps/api/app/modules/guard/models.py), [`runtime/blocks/guard_block.py:137`](./apps/api/app/runtime/blocks/guard_block.py), [`routers/mcp.py:195`](./apps/api/app/modules/guard/routers/mcp.py), [`routers/events.py:322`](./apps/api/app/modules/guard/routers/events.py), [`core/pii.py:17`](./apps/api/app/core/pii.py), [`routers/governance.py:124`](./apps/api/app/routers/governance.py), [`hook_template.py:344,688`](./packages/conduct-cli/src/conduct_cli/hook_template.py)
- **Related epics:** #748 (TrustLayers competitive response), #750 (Governance Dashboard), #756 (Conduct Compliance), #758 (MCP surface expansion)
- **Parent doc:** [NORTHSTAR.md](./NORTHSTAR.md) (Layer 6 — Trust & Compliance)

---

*This document iterates weekly. Each row in the 10-layer matrix maps to a child issue under the epic. Status moves with code reality, not aspiration.*
