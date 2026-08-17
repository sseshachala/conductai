# Audit 05 - Vocabulary

## Section A - Banned terms

Grep of user-facing strings across portal, CLI, API, docs for: playbook, workflow, automation, template, marketplace, skill pack. Rows sorted by file path within severity. All rows are P2 (naming/copy) unless otherwise noted; the pervasive use of these six banned nouns across every surface is by itself a P0 vocabulary problem for the product but is reported here at the individual-string level per spec.

| term | file:line | exact rendered string | surface | severity |
|---|---|---|---|---|
| workflow | apps/web/src/app/(app)/workflows/page.tsx:393 | "Pick a playbook template to create your first agent." (also hits `playbook` + `template`) | portal | P0 |
| playbook | apps/web/src/app/(app)/theguard/policies/page.tsx:1228 | "Install a skill pack to get started." (also hits `skill pack`) | portal | P0 |
| skill pack | apps/web/src/app/(app)/theguard/policies/page.tsx:1228 | "Install a skill pack to get started." | portal | P0 |
| skill packs | apps/web/src/app/(marketing)/docs/page.tsx:2257 | "Policy rules (block / warn / audit) are applied based on your workspace's active skill packs." | portal | P0 |
| automations | apps/web/src/app/(app)/dashboard/page.tsx:1121 | "Successful automations" | portal | P0 |
| automations | apps/web/src/app/(app)/dashboard/page.tsx:1122 | "Failed automations" | portal | P0 |
| automation | apps/web/src/app/page.tsx:81 | "Compliance & automation packs" (hero) | portal | P0 |
| marketplace | apps/web/src/app/(marketing)/security/page.tsx:55 | "Playbooks from the marketplace or imported via YAML" (also `playbooks`) | portal | P0 |
| templates | apps/web/src/app/(app)/workflows/new/page.tsx:80 | template selector labels + "Templates" section header | portal | P1 |
| template | apps/web/src/app/page.tsx:416 | "Get the templates ->" (CTA) | portal | P1 |
| playbooks | apps/web/src/lib/benchmark-editions.ts:37 | "Security and incident playbooks lead the leaderboard" | portal | P1 |
| playbook | apps/web/src/components/AppShell.tsx:114 | breadcrumb `if (pathname.startsWith('/playbooks')) return ['Automations']` (renders "Automations" as breadcrumb; `playbook` in path) | portal | P1 |
| playbook | packages/conduct-cli/src/conduct_cli/main.py:3219 | "List available playbooks or show detail for one" (`--help`) | CLI | P1 |
| playbook | packages/conduct-cli/src/conduct_cli/main.py:3223 | "Install an agent from a playbook" (`--help`) | CLI | P1 |
| playbooks | packages/conduct-cli/src/conduct_cli/main.py:3246 | "Install all playbooks into a project" (`--help`) | CLI | P1 |
| playbook | packages/conduct-cli/src/conduct_cli/mcp_server.py:45 | "List available Conduct playbooks (workflow templates)." (tool description) | CLI | P1 |
| workflow | packages/conduct-cli/src/conduct_cli/mcp_server.py:50 | tool named `conduct_run_workflow` | CLI | P1 |
| skill pack | packages/conduct-cli/src/conduct_cli/main.py:3299 | "Manage Guard skill packs" (`--help`) | CLI | P1 |
| skill packs | packages/conduct-cli/src/conduct_cli/main.py:3122 | "No skill packs available." (echoed user message) | CLI | P1 |
| automation | apps/api/app/modules/guard/routers/config.py:43 | `automation_security_scan` / `automation_workflow_trigger` config fields | API | P1 |
| automations | apps/api/app/routers/insights.py:130 | `successful_automations` / `failed_automations` (response field names) | API | P1 |
| marketplace | apps/api/app/routers/playbooks.py:246 | `platform.marketplace.install` permission | API | P1 |
| marketplace | apps/api/app/core/auth.py:712 | `platform.marketplace.browse` permission docstring | API | P1 |
| playbook | docs/mental-models/08-playbooks.md | dedicated doc titled around playbook mental model | docs | P2 |
| automation | docs/conduct-one-pager.md:161 | "structured multi-step automations" | docs | P2 |
| marketplace | docs/mental-models/08-playbooks.md:171 | "marketplace foundation" section | docs | P2 |

## Section B - Framework display names rendered as slugs

Grepped portal for PCI_DSS, NIST_AI_RMF, OWASP_AGENTIC, IRS_1075, MITRE_ATLAS, SOC2 rendered in user-facing surfaces.

| slug | file:line | route where rendered | severity |
|---|---|---|---|
| MITRE_ATLAS | apps/web/src/app/(marketing)/solutions/memory-hardening/page.tsx:172 | /solutions/memory-hardening ("OWASP:ASI06 and MITRE_ATLAS:AML.M0031") | P0 |
| OWASP_AGENTIC | apps/web/src/app/(marketing)/solutions/memory-hardening/page.tsx:172 | /solutions/memory-hardening (same line, appears as tag reference) | P0 |
| PCI_DSS | apps/web/src/app/(app)/governance/page.tsx:115 | /governance (mapped through display-name map `PCI_DSS: "PCI DSS"`, so slug is not rendered raw to end user - keys are consumed only for lookup) | P2 |
| SOC2 | apps/web/src/app/(app)/governance/page.tsx:109 | /governance (mapped through display-name map `SOC2: "SOC 2"`, keys are used only for lookup) | P2 |
| SOC2 | apps/web/src/app/(app)/theguard/reports/soc2/page.tsx:116 | /theguard/reports/soc2 (`.find(f => f.framework.toUpperCase().startsWith("SOC2"))` - used in comparison, not rendered raw) | P2 |
| NIST_AI_RMF | (not found in user-facing portal strings) | UNKNOWN | (no findings) |
| IRS_1075 | (not found in user-facing portal strings) | UNKNOWN | (no findings) |


## Section C - Cross-surface parity

For each core noun: portal term, CLI term, API field, docs term, mismatch (Y/N). Portal = JSX children under apps/web/src/app/(app)/**. CLI = click help strings in packages/conduct-cli/src/conduct_cli/**. API = pydantic model / response field name. Docs = docs/**.md.

| object | portal term | CLI term | API field | docs term | mismatch (Y/N) |
|---|---|---|---|---|---|
| agent | "agent" (workflows/page.tsx labels "agents"); breadcrumb for `/workflows` renders "Agents" (AppShell.tsx:123) | `conduct run` doc string uses "agent" and "workflow" interchangeably (mcp_server.py:45,50) | model class `Workflow` (models/workflow.py) - API field is `workflow_id`, never `agent_id` | "AI agent blocks", "agent playbook" | Y - portal says "Agents"; API says `workflow`; CLI mixes both |
| developer | "developer" / "developers" (theguard/page.tsx `active_developers`, dashboard) | "this machine"; DeveloperToolCoverage post | model classes `DeveloperToolCoverage`, `DeveloperSavings` | "developers and their AI coding tools" | N |
| event | "Events today" / "Flight Recorder" (logs/guard) | not surfaced in help text | model class `GuardAuditEvent`; endpoint `POST /guard/events` | "POST /guard/events" | N |
| machine | "machine" (Sessions and Machines toggle, logs/guard/page.tsx:432) | "this machine" in help copy | no dedicated model; `hostname`/`client_ip`/`os_info` on GuardSession | "developer machine" | N |
| pack | "pack" ("View rules ->" on pack cards); "skill pack" in some copy | `--pack-slug`, `--pack-name` args (main.py) | model classes `SkillPack`, `WorkspaceSkillPack` | "installed skill packs", "policy pack schema" | Y - portal alternates "pack" and "skill pack"; CLI says "skill pack"; API says `SkillPack` (both terms present, informal drift) |
| policy | "policy" / "policies" (theguard/policies UI) | `_save_policy()` internal; `--help` uses "policy" | rules stored inside SkillPack; no dedicated `Policy` model; policies-list endpoint returns rows named `policy` in response | "policies are YAML-defined rules stored in PostgreSQL" | Y - portal says "rule" AND "policy" for the same object (policies/page.tsx:1180 "N active" refers to `policies.filter(p => p.enabled)`, tab shows "Custom rule" form); ambiguity is API-side too |
| rule | "rule" ("Custom rule" form, "Rule ID", rule counts) | rule_id parsed from output | field `rule_id` on GuardAuditEvent, WorkspaceCustomRule, GuardRuleOverride | "Each policy has: rule_id" | Y - portal + docs both alternate "rule" and "policy" for the same entity |
| run | "run" (RunMeta type, "Run not found") | `cmd_run()`, `_stream_run()`, `_poll_run()` | model class `Run` in models/run.py | "execution run", "playbook run" | N |
| session | "session" (GuardSession, "Sessions today") | `cmd_sessions()`, `_session_stats()` | model classes `GuardSession`, `SessionReport` | "every developer session (a continuous Claude Code run) is tracked" | N |

Three of nine core nouns (agent, pack, policy/rule) show cross-surface mismatch. The `agent` mismatch (portal says "Agents", API says `workflow_id`) is the most visible: URLs at `/workflows/[id]`, sidebar breadcrumbs at "Agents", CLI at `conduct_run_workflow` MCP tool. The `rule` vs `policy` conflation exists inside a single page.
