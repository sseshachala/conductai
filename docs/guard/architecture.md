# Guard Architecture

> **One decision engine. Many enforcement points. Additive capability layer. Immutable audit chain.**
>
> Everything else is a call site, a plugin, or a data change.

Locked 2026-09-09 across #1740 / #1750 / #1751 / #1739 / #1737. Reviewer edits 1–5 incorporated.

---

## 1. North star

```
╔══════════════════════════════════════════════════════════════════════════╗
║                        SKILL PACKS + OVERRIDES                           ║
║   (conduct-base, hipaa, soc2, prompt-injection, eu-ai-act, custom...)    ║
║              data, not code. Grows without redeployment.                 ║
╚═════════════════════════════════╤════════════════════════════════════════╝
                                  │ loaded by
                                  ▼
              ┌──────────────────────────────────────────┐
              │      compute_policy(ws_id, context)      │
              │  Inputs:  workspace + PolicyContext      │
              │           { surface, actor_id, tool_name,│
              │             payload,                     │
              │             gate: action|prompt|response}│
              │  Output:  Decision                       │
              │           { verdict: block|approval|     │
              │                      warn|audit|pass,    │
              │             rule_id, pack_slug,          │
              │             obligations: [redact,notify, │
              │                           cosign,record] │
              │           }                              │
              └──────────────────┬───────────────────────┘
                                 │
                     capability pre-check runs at PEP entry
                                 │
     ┌────────────┬─────────────┼─────────────┬────────────┬───────────┐
     ▼            ▼             ▼             ▼            ▼           ▼
   MCP tool   LLM proxy    Runtime block   CLI hook    (future)     (future)
    call       egress      boundary                    webhook       browser
    action    prompt+       action         action                    agent
     gate     response       gate           gate
              gates
                                 │
                                 ▼
                    ┌────────────────────────┐
                    │   Capability Layer     │  Phase 5
                    │  narrows surface       │
                    │  BEFORE PDP call       │
                    │  • task-scoped tokens  │
                    │  • expiring MCP grants │
                    │  • cosign requirements │
                    └────────────┬───────────┘
                                 │
                                 ▼
              ┌──────────────────────────────────┐
              │       AUDIT CHAIN (append-only)  │
              │   hash-linked receipts per task  │
              │   verdict + obligation results   │
              │   raw payloads never persist —   │
              │   all writes route through       │
              │   redact_secrets                 │
              └──────────────────────────────────┘
```

**Locked forever:** evaluator signature, three gates, verdict enum, audit receipt shape, CI-verified PEP capability declarations, raw-payload-never-persists invariant.

**Designed to grow:** skill packs, PEPs, Cedar action names, capability primitives, obligations.

---

## 2. A single request, end to end

Concrete: an agent calls a Postgres MCP tool to run a query.

```
[1] Agent → postgres.query(sql="SELECT * FROM patients")
       │
       ▼
[2] MCP dispatcher (PEP #1)
    ├─ Capability check: does this run hold a handle for postgres.query?
    │  ├─ NO  → 401 refused. PDP never called. Audited as "no capability held."
    │  └─ YES → continue.
       │
       ▼
[3] Build PolicyContext
    { surface: "mcp", gate: "action", actor_id: "agent-42",
      tool_name: "postgres.query",
      payload: { sql: "SELECT * FROM patients" },
      workspace_id: "ws-abc" }
       │
       ▼
[4] compute_policy(ws_id, ctx)
    ├─ Load rules: base + hipaa + custom (all installed packs)
    ├─ Apply workspace overrides
    ├─ Match by gate=action, tool=postgres.query
    ├─ hipaa-phi-no-select-star fires → block
    └─ Decision { verdict: "block",
                  rule_id: "hipaa-phi-no-select-star",
                  pack_slug: "conduct-hipaa",
                  obligations: ["notify:slack:#compliance", "record"] }
       │
       ▼
[5] PEP enforces
    ├─ Refuse call, return structured error to agent
    ├─ Fire obligations (Slack notify)
    └─ Write audit receipt (hash-linked to prev receipt in this task)
       │
       ▼
[6] Audit receipt
    { task_id, seq: 47, prev_hash, this_hash,
      gate: "action", surface: "mcp", tool: "postgres.query",
      verdict: "block", rule_id: "hipaa-phi-no-select-star",
      obligations_completed: ["slack_notified"], ts }
```

Every PEP produces the same receipt shape. Every receipt is chained. Any auditor can replay the chain and verify nothing was inserted, removed, or reordered.

---

## 3. The three gates (locked)

Per #1739 ADR. Three values, from day one, no growth.

| Gate | Cedar action | Fires when | Context |
|---|---|---|---|
| `action` | `Action::"Shell"`, `"Write"`, `"Read"`, `"Network"`, `"MCPCall"` | agent invokes a structured tool call | `tool_name`, `tool_input` |
| `prompt` | `Action::"LLMPrompt"` | outbound prompt sent to a model | `text`, `model`, `provider` |
| `response` | `Action::"LLMResponse"` | model response returned to caller | `text`, `model`, `finish_reason` |

**Why exactly three:**
- **Two** (action + prompt) misses response — attacker doesn't need injection if they can exfil via output.
- **Four** (splitting action into shell / write / read) is a rule-matcher concern, not a gate concern. Cedar handles it.
- **Five+** overlaps with PEPs. Gates describe *what kind of thing* is being decided; PEPs describe *where* the decision is enforced.

`LLMStream` (drafted in #1739) is deferred. Streaming semantics route through obligations on `LLMResponse`, not a fourth gate. Extending the gate enum requires schema migration on every workspace — obligations extend without one.

### Rule field → gate mapping

Not every rule field applies at every gate. Ratchet locked here so a new rule field can't silently pick up cross-gate semantics without a doc update:

| Rule field | Fires at gate | Notes |
|---|---|---|
| `match_tool` | action | expanded through `expand_match_tool` (families like `bash`/`shell`) |
| `match_ai_tool` | action | matches the caller surface (`claude-code`, `cursor`, …) |
| `match_path_pattern` | action | regex against `file_path` / `path` / `command` |
| `match_pattern` | action **or** prompt | evaluated against the caller-provided text at each gate (`json.dumps(tool_input)` for action; prompt body for prompt) |
| `match_prompt` | prompt | regex against outbound prompt text |
| `match_provider` | prompt | exact match against upstream provider name |
| `match_model` | prompt | regex against model id |

Property 8 corollary: both matchers — the MCP-side `_match_policy` and the proxy-side `_rule_matches` — must honour the same field-to-gate mapping. #1771 caught the MCP-side matcher up on `match_prompt / match_provider / match_model` after #1770's `guard_check_prompt` verb made MCP a valid transport into the proxy PEP.

---

## 4. Use cases

### 4.1 HIPAA hospital agent (today)

Agent has: MCP access to Epic EHR, LLM proxy, filesystem.

| Gate | Rule | Verdict | Obligation |
|---|---|---|---|
| action | `hipaa-phi-no-select-star` | block | slack:#compliance-team |
| action | `hipaa-audit-all-phi-reads` | audit | record with actor + patient_id |
| prompt | `hipaa-no-phi-in-prompt` | block | redact and re-prompt |
| response | `hipaa-no-ssn-in-response` | warn | redact SSN pattern before send |

Compliance team ships one pack. Every agent in the org enforces it. Adding a new HIPAA rule = data change, no code change.

### 4.2 Financial trading agent with cosign (Phase 5)

```
Agent → execute_trade(size=$50M)
    │
    ▼
Capability layer: cosign-required handle held for execute_trade
    ├─ attribute: requires cosign for size > $10M
    ▼
Returns pending_cosign envelope. Trade does NOT execute.
    │
    ▼
Cosign request → Bloomberg terminal of head trader
    ├─ WebAuthn touch on hardware key → signed payload
    ▼
Verify signature vs runtime keypair + run_id + payload hash
    ├─ Valid + fresh → capability narrowed to "this exact trade"
    ▼
Trade executes. Audit chain records: request, cosign artifact, execution, receipt.
```

Cosign is a capability primitive, not a new PDP rule. New requirement mandating cosign for wire transfers = one attribute flip on the payment capability, no code deploy.

### 4.3 Multi-tenant SaaS (future)

Each tenant's workspace has its own pack precedence, capability grants, audit chain. Tenancy is a `workspace_id` parameter to `compute_policy`. Zero architectural change to add multi-tenant — the design assumed workspace scoping from day one.

### 4.4 New attack class discovered tomorrow

Zero-day: "steganographic instruction hiding in unicode homoglyphs."

**With this design:**
1. Write one skill pack rule: `pattern: <regex>, gate: prompt, action: block`.
2. Publish pack version bump.
3. Every workspace with that pack installed enforces it at every LLM proxy egress — without redeploying Guard.

**Without this design (per-surface rules):** update MCP guard, update proxy guard, update runtime guard, update CLI hook, test drift across 4 code paths, deploy, discover a 5th surface you forgot.

---

## 5. Immutable properties (9)

Do not touch these without a schema migration.

1. **Evaluator signature** — `compute_policy(workspace_id, PolicyContext) -> Decision`.
2. **PolicyContext shape** — `{ surface, actor_id, gate, tool_name, payload, ... }`.
3. **Decision shape** — `{ verdict, rule_id, pack_slug, obligations[] }`.
4. **Verdict enum** — `{ block, approval, warn, audit, pass }`. `inject` retired → audit + obligation. Precedence: `block > approval > warn > audit > pass`.
5. **Gate enum** — `{ action, prompt, response }`. Locked from day one.
6. **Audit receipt shape** — `{ task_id, seq, prev_hash, this_hash, gate, surface, tool, verdict, rule_id, obligations_completed, ts }`.
7. **Precedence** — most-restrictive action wins; `non_overridable: True` rules bypass workspace overrides; pack precedence is one admin dial.
8. **PEP capability declarations are machine-verified.** Every PEP registers `provides_capabilities: {gate_types}` in `apps/api/app/modules/guard/pep_registry.py`. Snapshot test in `tests/guard/test_pep_registry.py` locks the mapping against this doc — a PEP silently changing what it enforces fails CI. Per-rule surface status is derived on read via `derive_surface_status(rule, surface)`; hand-authored `enforcement.<surface>` values are compared against derived and divergence is warn-logged for #1750 Phase D cleanup. Full CI-run conformance test per capability is a follow-up.
9. **Raw payload never persists outside ephemeral scope.** All log writes — divergence logs, debug tables, audit rows — route through `redact_secrets` at `apps/api/app/core/pii.py:86`. Matched-span + hash + size only. P0 security invariant.

## 6. Extension points (5)

Add here without migration.

- **New skill pack** — ship JSON/YAML with rules → workspace installs → live. Zero code change.
- **New PEP surface** — register with `provides_capabilities`, call `compute_policy`, emit audit receipt. Conformance test proves declaration matches behavior.
- **New Cedar action name** — add to #1739 ADR + mapper entry in `cedar_adapter/`. Existing rules unaffected.
- **New capability primitive** (Phase 5 pattern) — additive to PDP. Registers as pre-check before `compute_policy` call. Emits its own audit shape variant.
- **New obligation** — registry entry. Verdicts stay fixed; side effects grow.

---

## 7. Design principles

1. **Delete only what can be regenerated from primary sources.** Derived metadata (like `status`) is safe to delete. Hand-authored prose (`guarantee`, `known_limitations`) is primary source itself — retain.
2. **Data changes and code changes always ticket separately.** Different reviewers, different review paths.
3. **Verdicts describe yes/no/hold. Obligations describe side effects.** Never grow the verdict enum; always grow obligations.
4. **Capability check happens before PDP consultation.** Both must permit. Capability refusal short-circuits (no PDP call). Both refusals audited, distinguished by receipt type.

---

## 8. PEPs in production

| PEP | Provides gates | Location |
|---|---|---|
| MCP | action | `apps/api/app/modules/guard/routers/mcp_impls.py` |
| LLM proxy | prompt, response | `apps/api/app/routers/proxy.py` |
| Runtime | action (via PreBlock) | `apps/api/app/runtime/blocks/` |
| CLI hook | action | `packages/conduct-cli/` PreToolUse |
| Lens | action, prompt, response | `apps/api/app/modules/glens/routers/chat.py` + `tools/registrations/lens/` |
| LiteLLM plugin | prompt (response deferred) | `packages/conduct-litellm-guard/` |

Lens is a well-behaved caller — no special path. LLM calls route through `guarded_completion` → `LLMClient` → proxy. Tool calls route through Lens tool registry → `guard_check` → MCP PEP.

The LiteLLM plugin is also a well-behaved caller: it sits at the LiteLLM `pre_call` boundary — a prompt-gate concern — and dispatches through the new `guard_check_prompt` MCP verb. Transport = MCP; enforcement point = the LLM proxy PEP (proxy-persona rules, `gate="prompt"`, audit `source="proxy"`). `PEP_CAPABILITIES["mcp"]` stays `{action}`; the plugin's row above documents the effective gate the caller reaches, not a new MCP capability.

The four rows above (excluding Lens) are the source of truth for `PEP_CAPABILITIES` in `apps/api/app/modules/guard/pep_registry.py`. `derive_surface_status(rule, surface)` reads this table + the rule's `gates` to compute per-rule enforcement status. `pack_coverage_matrix(db, pack_slug)` aggregates across a pack; the Policies UI reads it via `GET /guard/policies/packs/{slug}/coverage-matrix`.

`PolicyOut` and `EnforcementCoverageOut` both carry `derived_<surface>` fields alongside the hand-authored `enforcement.<surface>` values. The Coverage tab renders both side-by-side; when they disagree, a ⚠ marker flags the rule as stale metadata (#1750 Phase D signal). Once Phase D retires the hand-authored fields, the derived subtext becomes the sole source of truth without any UI change.

### Smoke test

`scripts/smoke_1755.sh` verifies the end-to-end wiring against a running API:

```bash
API=http://localhost:8000 CONDUCT_TOKEN=cond_agt_xxx bash scripts/smoke_1755.sh
```

Checks: coverage endpoint returns `derived_<surface>` fields; pack coverage matrix populated for `conduct-base`; rule-fires endpoint redacts `input_summary`; count of authored↔derived divergences (Phase D readiness signal).

---

## 9. Failure modes prevented

**Evaluator drift.** Each surface has its own rule loader → same rule applied by MCP but not proxy. Prevention: one `compute_policy`; Property 8 (CI-verified declarations) prevents PEP declarations from drifting from behavior.

**Schema fossilization.** Enum chosen too narrow → future migration on production rows. Prevention: gate enum is `[action, prompt, response]` from Phase 0. Extensions go through obligations, not gates.

**Audit chain data poisoning.** Divergence or debug logs capture raw payloads including secrets → seven days of production traffic logs contain API keys and PII. Prevention: Property 9 (raw payload never persists). Every log path routes through `redact_secrets`. Backed by hard invariant, not by convention.

---

## 10. Deck-ready frame

> Guard is a Policy Decision Point for AI agents.
>
> One evaluator sees every action, prompt, and response an agent produces, against a workspace's full policy — compliance packs, custom rules, overrides. Every enforcement point in the stack — MCP tool calls, LLM proxy, runtime blocks, CLI hooks — calls the same evaluator, gets the same decision, writes the same tamper-evident audit receipt.
>
> Capability primitives narrow what the agent can reach; the evaluator authorizes what it does with what it holds; the audit chain records what actually happened.
>
> **Filter today. Capability tomorrow. Receipt always.**

Nothing left to move — everything that could change is either data (packs), a plug-in (PEPs), an obligation, or an additive layer (capabilities).

---

## Related

- #1737 — single evaluator mandate
- #1740 — parent unification epic (reviewer edits 1–4)
- #1739 — Cedar action-name ADR (gate enum lock)
- #1750 — Policies page rollout (Phases A–D)
- #1751 — derived enforcement status
- #1752 — `_project_rule` projection fix (reviewer edit 5)
- #1193 — Cedar interchange
- #663 — skill-pack model + `compute_policy` foundation
- conduct-internal #42 — 2nd provisional patent (unification + Phase 5)
