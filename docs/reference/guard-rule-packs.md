# Guard rule packs — reference

Every rule that ships in every Guard pack. Auto-generated from the pack JSON at `apps/api/app/modules/guard/skill_packs/`. Rule counts, actions, and framework mappings are the source of truth for compliance evidence.

**Totals:** 15 packs · 183 rules across `block`, `warn`, `audit`, and `approval` actions.

---

## Quick index

| Pack | Rules | Version | Tier |
|---|---:|---|---|
| [conduct-base](#conduct-base) | 46 | 2.15.0 | free |
| [conduct-endpoint-attacks](#conduct-endpoint-attacks) | 10 | 1.1.0 | free |
| [conduct-prompt-injection](#conduct-prompt-injection) | 30 | 1.0.1 | free |
| [conduct-owasp](#conduct-owasp) | 25 | 2.2.3 | paid |
| [conduct-nist-ai-rmf](#conduct-nist-ai-rmf) | 10 | 1.0.1 | paid |
| [conduct-iso-42001](#conduct-iso-42001) | 10 | 1.0.0 | paid |
| [conduct-eu-ai-act](#conduct-eu-ai-act) | 10 | 1.0.0 | paid |
| [conduct-soc2](#conduct-soc2) | 4 | 1.3.0 | paid |
| [conduct-hipaa](#conduct-hipaa) | 4 | 1.4.0 | paid |
| [conduct-irs-1075](#conduct-irs-1075) | 8 | 1.2.0 | paid |
| [conduct-pci-dss](#conduct-pci-dss) | 3 | 1.1.0 | paid |
| [conduct-financial-services](#conduct-financial-services) | 8 | 1.0.0 | demo |
| [conduct-life-sciences](#conduct-life-sciences) | 9 | 1.0.0 | demo |
| [conduct-network-ops](#conduct-network-ops) | 4 | 0.2.1 | demo |
| [conduct-support-ops](#conduct-support-ops) | 2 | 0.1.0 | demo |

---

## Foundation (free tier, auto-installed)

### <a id="conduct-base"></a>conduct-base

**Conduct Base** — v2.15.0 · tier: **free** · 46 rules

Core AI governance rules — proxy interception, agent safety, surface-aware enforcement, workflow governance, and MCP server tool call auditing. 5 proxy + 16 agent + 7 surface + 4 workflow + 2 MCP rules.

**Actions:** `block` ×28 · `warn` ×11 · `audit` ×5 · `approval` ×2  
**Severity:** high ×21 · critical ×16 · medium ×6 · low ×3  
**Source:** [`conduct-base.json`](../../apps/api/app/modules/guard/skill_packs/conduct-base.json)

| Rule ID | Action | Severity | Frameworks | Description |
|---|---|---|---|---|
| `proxy-no-credential-leak` | `block` | critical | SOC2:CC6.1, ISO_42001:6.1 | Block LLM calls containing credentials in the prompt |
| `proxy-no-prompt-injection` | `block` | critical | OWASP:LLM01, ISO_42001:6.1 | Block prompt injection attempts |
| `proxy-no-pii-prompt` | `warn` | high | GDPR:Art32, HIPAA:164.514 | Warn when LLM prompt contains PII |
| `proxy-audit-vision-input` | `audit` | medium | ISO_42001:6.1, NIST_AI_RMF:GOVERN-1.2 | Audit LLM calls that include inline image data — text-based policy rules cannot inspect image contents |
| `audit-image-file-read` | `audit` | low | ISO_42001:6.1 | Audit when agent reads image or scanned document files — content is not inspectable by text-based policy rules |
| `no-path-traversal` | `block` | critical | SOC2:CC6.1, OWASP:A01 | Block reads/writes to system and app-core paths |
| `no-rm-rf` | `block` | critical | SOC2:CC6.1 | Block recursive deletes |
| `no-sudo` | `block` | critical | SOC2:CC6.1 | Block sudo commands |
| `no-env-read` | `block` | high | SOC2:CC6.1 | Block reading .env files |
| `no-env-commits` | `block` | critical | SOC2:CC6.1, GDPR:Art32 | Block committing .env files |
| `no-force-push` | `block` | high | SOC2:CC6.1 | Block force pushes |
| `approve-prod-deploy` | `approval` | high | SOC2:CC8.1 | Gate production deploys behind admin approval |
| `approve-db-migration-prod` | `approval` | high | SOC2:CC8.1 | Gate production DB migrations behind admin approval |
| `no-hardcoded-secrets` | `warn` | high | SOC2:CC6.1 | Warn when AI writes hardcoded secrets into code |
| `no-aws-keys` | `block` | critical | SOC2:CC6.1 | Warn when AI writes AWS access keys into code |
| `secret-stripe` | `block` | critical | PCI_DSS:3.5 | Warn when AI writes Stripe live keys into code |
| `secret-anthropic` | `block` | critical | SOC2:CC6.1 | Block Anthropic API keys written to files |
| `secret-openai-modern` | `block` | critical | SOC2:CC6.1 | Block modern OpenAI project keys (sk-proj-*) |
| `secret-postgres-url` | `block` | high | SOC2:CC6.1 | Block PostgreSQL connection strings with credentials written to files |
| `secret-mysql-url` | `block` | high | SOC2:CC6.1 | Block MySQL connection strings with credentials written to files |
| `secret-gcp-service-account` | `block` | critical | SOC2:CC6.1 | Block Google Cloud service account JSON keys written to files |
| `cmd-injection` | `warn` | high | OWASP:A03 | Warn when AI writes shell execution with user input |
| `sql-injection` | `warn` | high | OWASP:A03 | Warn when AI writes string-formatted SQL |
| `no-secret-in-commit-msg` | `warn` | high | SOC2:CC6.1 | Warn on secrets in git commit messages |
| `surface-chat-no-bash` | `block` | high | SOC2:CC6.1, ISO_42001:6.1, NIST_AI_RMF:GOVERN-1.1 | Block shell execution from chat surfaces — Claude.ai, Claude Desktop, ChatGPT |
| `surface-chat-no-write` | `block` | high | SOC2:CC6.1, ISO_42001:6.1 | Block filesystem writes from chat surfaces |
| `surface-chat-no-network` | `warn` | medium | SOC2:CC6.1 | Warn on outbound network calls from chat surfaces |
| `surface-codex-desktop-warn-exec` | `warn` | medium | SOC2:CC6.1 | Warn on shell execution from Codex Desktop — hybrid surface |
| `surface-codex-desktop-no-delete` | `block` | high | SOC2:CC6.1 | Block destructive deletes from Codex Desktop |
| `surface-dev-audit-prod-write` | `audit` | medium | SOC2:CC7.2, ISO_42001:9.1 | Audit writes to production paths from any dev tool |
| `workflow-audit-all` | `audit` | low | SOC2:CC7.2, ISO_42001:9.1 | Audit every workflow trigger — no pattern required, fires on all workflow tool calls |
| `workflow-warn-prod` | `warn` | high | SOC2:CC8.1, ISO_42001:6.1 | Warn when a production workflow is triggered by an AI agent |
| `workflow-block-destructive` | `block` | critical | SOC2:CC6.1, ISO_42001:6.1 | Block destructive workflows (delete, drop, purge, destroy, wipe) triggered by AI agents |
| `workflow-block-secret-in-payload` | `block` | critical | SOC2:CC6.1, OWASP:LLM02 | Block workflow triggers that pass raw credentials in the payload |
| `surface-unknown-block-exec` | `block` | high | SOC2:CC6.1, ISO_42001:6.1 | Block shell execution from unrecognized surfaces |
| `mcp-audit-all-tool-calls` | `audit` | low | SOC2:CC7.2, ISO_42001:9.1 | Audit all MCP server tool calls |
| `mcp-block-destructive-tools` | `block` | critical | SOC2:CC6.1, ISO_42001:6.1 | Block destructive MCP tool calls |
| `no-slack-token` | `block` | high | — | Block Slack bot/app tokens in agent-written code |
| `no-private-key` | `block` | critical | — | Block private key material in agent-written code |
| `no-conduct-tokens` | `block` | high | OWASP:A02, SOC2:CC6.1 | Block Conduct-issued tokens (cond_agt_*, cond_run_*, cond_cred_*, cond_live_*, cond_api_*) from appearing in tool inp... |
| `no-booster-secrets` | `block` | high | OWASP:A02, SOC2:CC6.1 | Block Agent Booster secret values (BOOSTER_SECRET followed by a 40+ hex value, typically in .mcp.json env blocks) |
| `no-eval` | `block` | high | — | Block use of eval() — arbitrary code execution risk |
| `no-weak-crypto` | `warn` | medium | — | Warn on MD5 or SHA-1 use — broken for security purposes |
| `no-gh-pat-in-code` | `block` | critical | — | Block GitHub Personal Access Token in agent-written code |
| `proxy-fix-this-code-intent` | `warn` | medium | — | Flag prompts using the 'fix this code' framing — dual-use vector for finding vulnerabilities via patch generation |
| `proxy-restricted-model-mythos-fable` | `warn` | high | — | Flag calls to Mythos/Fable-class models — high capability, cybersecurity-restricted per US export controls (2026-06-12) |

### <a id="conduct-endpoint-attacks"></a>conduct-endpoint-attacks

**Conduct Endpoint Attacks** — v1.1.0 · tier: **free** · 10 rules

10 pattern rules for the endpoint-attack techniques Numbat and other agent EDRs surface: reverse shells, SSH/cloud credential file reads, cloud instance metadata recon, persistence via cron/systemd/launchd/shell profiles, encoded-payload shell chains, and secret-read-then-egress chains. Every rule maps to a MITRE ATT&CK sub-technique. Hook and MCP surfaces are covered; the runtime and proxy surfaces are not (these are tool_input-level patterns).

**Actions:** `block` ×9 · `audit` ×1  
**Severity:** critical ×5 · high ×4 · medium ×1  
**Source:** [`conduct-endpoint-attacks.json`](../../apps/api/app/modules/guard/skill_packs/conduct-endpoint-attacks.json)

| Rule ID | Action | Severity | Frameworks | Description |
|---|---|---|---|---|
| `endpoint-attack-reverse-shell` | `block` | critical | MITRE_ATT&CK:T1059.004, OWASP:A04, NIST_AI_RMF:MANAGE-2.3 |  |
| `endpoint-attack-private-key-read` | `block` | critical | MITRE_ATT&CK:T1552.004, OWASP:A02, SOC2:CC6.1, PCI_DSS:3.5 |  |
| `endpoint-attack-cloud-cred-read` | `block` | critical | MITRE_ATT&CK:T1552.001, OWASP:A02, SOC2:CC6.1 |  |
| `endpoint-attack-cloud-metadata-recon` | `block` | high | MITRE_ATT&CK:T1552.005, OWASP:A05 |  |
| `endpoint-attack-persistence-cron` | `block` | high | MITRE_ATT&CK:T1053.003, OWASP:A04 |  |
| `endpoint-attack-persistence-systemd` | `block` | high | MITRE_ATT&CK:T1543.002, OWASP:A04 |  |
| `endpoint-attack-persistence-launchd` | `block` | high | MITRE_ATT&CK:T1543.004, OWASP:A04 |  |
| `endpoint-attack-persistence-shell-profile` | `audit` | medium | MITRE_ATT&CK:T1546.004, OWASP:A04 |  |
| `endpoint-attack-download-pipe-shell` | `block` | critical | MITRE_ATT&CK:T1105, MITRE_ATT&CK:T1027, OWASP:A03, OWASP:A08 |  |
| `endpoint-attack-secret-read-egress-chain` | `block` | critical | MITRE_ATT&CK:T1041, MITRE_ATT&CK:T1552, OWASP:A02, OWASP:A10 |  |

### <a id="conduct-prompt-injection"></a>conduct-prompt-injection

**Conduct Prompt Injection Defense** — v1.0.1 · tier: **free** · 30 rules

Dedicated pack of ~100 patterns for detecting prompt injection, jailbreak, role-hijack, delimiter-escape, and system-prompt disclosure attempts across Bash, Edit, and Write tool inputs. Covers OWASP LLM A01, MITRE ATLAS AML.M0031, ASI06, and common public jailbreak library entries. Complements the base OWASP pack. ML classifier and indirect-injection tracking are on the roadmap.

**Actions:** `block` ×16 · `audit` ×14  
**Severity:** high ×12 · medium ×11 · low ×5 · critical ×2  
**Source:** [`conduct-prompt-injection.json`](../../apps/api/app/modules/guard/skill_packs/conduct-prompt-injection.json)

| Rule ID | Action | Severity | Frameworks | Description |
|---|---|---|---|---|
| `prompt-inject-override-instructions` | `block` | high | OWASP:LLM01, MITRE_ATLAS:AML.M0031 |  |
| `prompt-inject-system-prompt-reveal` | `block` | high | OWASP:LLM01, OWASP:LLM07 |  |
| `prompt-inject-role-hijack` | `block` | high | OWASP:LLM01 |  |
| `prompt-inject-jailbreak-personas` | `block` | high | OWASP:LLM01, MITRE_ATLAS:AML.M0031 |  |
| `prompt-inject-grandma-exploit` | `block` | medium | OWASP:LLM01 |  |
| `prompt-inject-hypothetical-framing` | `audit` | medium | OWASP:LLM01 |  |
| `prompt-inject-suffix-attack` | `block` | high | OWASP:LLM01 |  |
| `prompt-inject-delimiter-escape` | `block` | medium | OWASP:LLM01 |  |
| `prompt-inject-indirect-tool-output` | `audit` | medium | OWASP:LLM01, MITRE_ATLAS:AML.M0031 |  |
| `prompt-inject-context-window-flood` | `audit` | low | OWASP:LLM01, OWASP:LLM04 |  |
| `prompt-inject-encoded-payload-marker` | `audit` | medium | OWASP:LLM01 |  |
| `prompt-inject-encoded-canary-b64-ignore` | `block` | high | OWASP:LLM01 |  |
| `prompt-inject-decoded-override` | `block` | high | OWASP:LLM01 |  |
| `prompt-inject-tool-injection-instruction` | `block` | high | OWASP:LLM01, MITRE_ATLAS:AML.M0031 |  |
| `prompt-inject-fake-conversation` | `audit` | medium | OWASP:LLM01 |  |
| `prompt-inject-payload-in-url` | `audit` | medium | OWASP:LLM01 |  |
| `prompt-inject-markdown-link-instruction` | `audit` | low | OWASP:LLM01 |  |
| `prompt-inject-tool-name-spoof` | `block` | high | OWASP:LLM01 |  |
| `prompt-inject-unicode-tag-smuggle` | `block` | high | OWASP:LLM01 |  |
| `prompt-inject-zero-width-flood` | `audit` | medium | OWASP:LLM01 |  |
| `prompt-inject-homoglyph-instruction` | `audit` | medium | OWASP:LLM01 |  |
| `prompt-inject-credentials-exfil-instruction` | `block` | critical | OWASP:LLM01, OWASP:LLM06, MITRE_ATLAS:AML.T0024 |  |
| `prompt-inject-persistence-write` | `block` | high | OWASP:LLM01, OWASP:ASI06, MITRE_ATLAS:AML.M0031 |  |
| `prompt-inject-tool-disable` | `block` | critical | OWASP:LLM01, NIST_AI_RMF:GOVERN-2.2 |  |
| `prompt-inject-emotional-coercion` | `audit` | low | OWASP:LLM01 |  |
| `prompt-inject-authority-spoof` | `audit` | medium | OWASP:LLM01 |  |
| `prompt-inject-refusal-suppress` | `block` | high | OWASP:LLM01 |  |
| `prompt-inject-payload-splitting` | `audit` | medium | OWASP:LLM01 |  |
| `prompt-inject-code-block-instruction` | `audit` | low | OWASP:LLM01 |  |
| `prompt-inject-language-switch-attack` | `audit` | low | OWASP:LLM01 |  |

---

## Standards & compliance frameworks (paid tier)

### <a id="conduct-owasp"></a>conduct-owasp

**Conduct OWASP** — v2.2.3 · tier: **paid** · 25 rules

OWASP Web Top 10 + Agentic Top 10 enforcement rules for AI coding agents, including ASI06 Memory Poisoning (MITRE ATLAS AML.M0031)

**Actions:** `block` ×14 · `warn` ×11  
**Severity:** high ×10 · critical ×9 · medium ×6  
**Source:** [`conduct-owasp.json`](../../apps/api/app/modules/guard/skill_packs/conduct-owasp.json)

| Rule ID | Action | Severity | Frameworks | Description |
|---|---|---|---|---|
| `owasp_injection_guard` | `block` | high | OWASP:A03, SOC2:CC6.1, ISO_42001:8.4, PCI_DSS:6.5.1 | Block SQL injection patterns — f-string interpolation and string concatenation in SQL statements (OWASP Web A03) |
| `owasp_crypto_guard` | `warn` | medium | OWASP:A02, SOC2:CC6.1, PCI_DSS:3.6, ISO_42001:8.24 | Warn on MD5/SHA1 for passwords (OWASP Web A02) |
| `owasp_weak_session_guard` | `block` | high | OWASP:A07, SOC2:CC6.1, ISO_42001:8.5 | Block weak session token generation (OWASP Web A07) |
| `owasp_ssrf_guard` | `warn` | high | OWASP:A10, SOC2:CC6.1, ISO_42001:8.4 | Warn on unvalidated URL fetch (OWASP Web A10) |
| `owasp_eval_guard` | `block` | critical | OWASP:A03, SOC2:CC6.1, ISO_42001:8.4 | Block eval() calls (OWASP Web A03) |
| `owasp_xss_guard` | `warn` | medium | OWASP:A03, SOC2:CC6.1, ISO_42001:8.4 | Warn on innerHTML assignment (OWASP Web A03 / XSS) |
| `no_prompt_inject` | `block` | critical | OWASP_AGENTIC:A01 | Block prompt injection attempts that try to override agent instructions (OWASP Agentic A01) |
| `no_sensitive_data_exfil` | `block` | critical | OWASP_AGENTIC:A02, SOC2:CC6.1 | Block credential exfiltration via curl or outbound network calls (OWASP Agentic A02) |
| `no_unsigned_package` | `warn` | high | OWASP_AGENTIC:A03 | Warn on packages installed from non-standard or HTTP sources (OWASP Agentic A03 — supply chain) |
| `no_overreach_shell` | `block` | critical | OWASP_AGENTIC:A04 | Block destructive system-wide shell commands that exceed project scope (OWASP Agentic A04 — excessive agency) |
| `no_model_extract` | `block` | high | OWASP_AGENTIC:A05 | Block copying or exfiltrating ML model weights (OWASP Agentic A05 — model theft) |
| `no_covert_channel` | `warn` | high | OWASP_AGENTIC:A06 | Warn on suspicious outbound callbacks or data exfiltration endpoints (OWASP Agentic A06) |
| `no_audit_bypass` | `block` | critical | OWASP_AGENTIC:A07, SOC2:CC7.2 | Block attempts to disable audit logging or monitoring (OWASP Agentic A07 — insufficient monitoring) |
| `no_unverified_deploy` | `warn` | medium | OWASP_AGENTIC:A08 | Warn on force-pushing or deploying without test validation (OWASP Agentic A08 — over-reliance) |
| `no_privilege_escalat` | `block` | critical | OWASP_AGENTIC:A09 | Block privilege escalation beyond sudo (OWASP Agentic A09) |
| `no_budget_bypass` | `block` | high | OWASP_AGENTIC:A10 | Block attempts to override spend limits or rate controls (OWASP Agentic A10 — model DoS) |
| `no_recon_fs` | `block` | critical | OWASP_AGENTIC:A01, SOC2:CC6.1 | Block filesystem reconnaissance targeting credential and system files (Promptware Kill Chain — Reconnaissance) |
| `no_shell_persist` | `block` | critical | OWASP_AGENTIC:A04, SOC2:CC6.1 | Block writes to shell RC files, cron, or systemd units (Promptware Kill Chain — Persistence) |
| `no_dns_exfil` | `warn` | high | OWASP_AGENTIC:A06, SOC2:CC6.7 | Warn on DNS-based exfiltration patterns and encoded outbound data (Promptware Kill Chain — Command & Control) |
| `no_agent_pivot` | `warn` | high | OWASP_AGENTIC:A04, OWASP_AGENTIC:A09 | Warn on cross-agent tool invocation that may indicate lateral movement (Promptware Kill Chain — Lateral Movement) |
| `asi06_memory_write_without_classification` | `warn` | medium | OWASP:ASI06, MITRE_ATLAS:AML.M0031 | Warn when an agent writes to persistent memory without a source or trust classification tag (OWASP ASI06, MITRE ATLAS... |
| `asi06_untrusted_promotion_to_durable` | `block` | high | OWASP:ASI06, MITRE_ATLAS:AML.M0031, NIST_AI_RMF:MAP-2.3 | Block promotion of untrusted content to durable or long-term memory tiers (OWASP ASI06, MITRE ATLAS AML.M0031) |
| `asi06_instruction_shaped_memory_write` | `block` | critical | OWASP:ASI06, OWASP:LLM01, MITRE_ATLAS:AML.M0031 | Block memory writes containing instruction-shaped content that would act as delayed prompt injection (OWASP ASI06, MI... |
| `asi06_cross_tenant_memory_read` | `warn` | medium | OWASP:ASI06, MITRE_ATLAS:AML.M0031, SOC2:CC6.1 | Warn on memory reads that cross tenant or namespace boundaries (OWASP ASI06, MITRE ATLAS AML.M0031) |
| `asi06_memory_integrity_bypass` | `warn` | medium | OWASP:ASI06, MITRE_ATLAS:AML.M0031, SOC2:CC7.1 | Warn when memory writes to a trusted or verified tier omit an integrity claim (OWASP ASI06, MITRE ATLAS AML.M0031) |

### <a id="conduct-nist-ai-rmf"></a>conduct-nist-ai-rmf

**Conduct NIST AI RMF** — v1.0.1 · tier: **paid** · 10 rules

NIST AI Risk Management Framework enforcement rules across GOVERN, MAP, MEASURE, and MANAGE functions

**Actions:** `warn` ×6 · `block` ×4  
**Severity:** critical ×4 · medium ×4 · high ×2  
**Source:** [`conduct-nist-ai-rmf.json`](../../apps/api/app/modules/guard/skill_packs/conduct-nist-ai-rmf.json)

| Rule ID | Action | Severity | Frameworks | Description |
|---|---|---|---|---|
| `nist-govern-policy-bypass` | `block` | critical | NIST_AI_RMF:GOVERN-2.2, EU_AI_ACT:Art9, ISO_42001:8.1 | Block attempts to disable or bypass AI governance controls (NIST AI RMF GOVERN 2.2) |
| `nist-govern-least-privilege` | `block` | critical | NIST_AI_RMF:GOVERN-1.2, OWASP_AGENTIC:A09, ISO_42001:8.1 | Block agents requesting system-wide permissions beyond their defined scope (NIST AI RMF GOVERN 1.2) |
| `nist-govern-human-oversight` | `block` | critical | NIST_AI_RMF:GOVERN-6.1, EU_AI_ACT:Art14, ISO_42001:8.1 | Block autonomous consequential AI decisions without human review gate (NIST AI RMF GOVERN 6.1) |
| `nist-map-high-risk-domain` | `warn` | high | NIST_AI_RMF:MAP-5.1, EU_AI_ACT:Art9, ISO_42001:8.2 | Warn when AI deployed in high-risk domain without documented assessment (NIST AI RMF MAP 5.1) |
| `nist-map-unverified-data-source` | `warn` | high | NIST_AI_RMF:MAP-1.5, OWASP_AGENTIC:A01, ISO_42001:8.4 | Warn on passing unverified external data directly into AI model context (NIST AI RMF MAP 1.5) |
| `nist-measure-audit-disable` | `block` | critical | NIST_AI_RMF:MEASURE-2.5, SOC2:CC7.2, ISO_42001:9.1 | Block disabling monitoring or telemetry on AI systems (NIST AI RMF MEASURE 2.5) |
| `nist-measure-error-swallow` | `warn` | medium | NIST_AI_RMF:MEASURE-2.2, NIST_AI_RMF:MANAGE-1.3, ISO_42001:10.2 | Warn on swallowed exceptions in AI pipeline code (NIST AI RMF MEASURE 2.2) |
| `nist-manage-third-party-ai` | `warn` | medium | NIST_AI_RMF:MANAGE-4.1, ISO_42001:8.1, EU_AI_ACT:Art53 | Warn on use of unapproved third-party AI providers without vendor assessment (NIST AI RMF MANAGE 4.1) |
| `nist-manage-data-retention` | `warn` | medium | NIST_AI_RMF:MANAGE-2.4, GDPR:Art5.1e, ISO_42001:8.4 | Warn on indefinite retention of AI conversation or inference data (NIST AI RMF MANAGE 2.4) |
| `nist-govern-accountability` | `warn` | medium | NIST_AI_RMF:GOVERN-1.7, ISO_42001:8.5 | Warn when AI system deployed without owner/team tag for accountability (NIST AI RMF GOVERN 1.7) |

### <a id="conduct-iso-42001"></a>conduct-iso-42001

**Conduct ISO 42001** — v1.0.0 · tier: **paid** · 10 rules

ISO/IEC 42001:2023 AI Management System enforcement rules — operational controls, data governance, responsible AI use, and continual improvement

**Actions:** `warn` ×6 · `block` ×4  
**Severity:** medium ×4 · high ×3 · critical ×3  
**Source:** [`conduct-iso-42001.json`](../../apps/api/app/modules/guard/skill_packs/conduct-iso-42001.json)

| Rule ID | Action | Severity | Frameworks | Description |
|---|---|---|---|---|
| `iso42001-data-quality` | `warn` | high | ISO_42001:8.4, NIST_AI_RMF:MAP-1.5, EU_AI_ACT:Art10 | Warn on use of unlabeled or unvalidated data in AI training or embedding (ISO 42001 Clause 8.4) |
| `iso42001-responsible-use` | `block` | high | ISO_42001:8.6, EU_AI_ACT:Art9, NIST_AI_RMF:MAP-5.1 | Block agent calling an LLM API with an explicit purpose override intent (ISO 42001 Clause 8.6) |
| `iso42001-human-oversight` | `block` | critical | ISO_42001:8.1, EU_AI_ACT:Art14, NIST_AI_RMF:GOVERN-6.1 | Block autonomous high-impact AI actions without a human review gate (ISO 42001 Clause 8.1) |
| `iso42001-impact-assessment` | `warn` | high | ISO_42001:8.5, EU_AI_ACT:Art9, NIST_AI_RMF:MAP-5.1 | Warn when new AI system or model deployed without documented impact assessment (ISO 42001 Clause 8.5) |
| `iso42001-access-control` | `block` | critical | ISO_42001:8.1, OWASP_AGENTIC:A04, SOC2:CC6.1 | Block AI agents accessing resources or paths outside their designated scope (ISO 42001 Clause 8.1) |
| `iso42001-supplier-ai-control` | `warn` | medium | ISO_42001:8.1, NIST_AI_RMF:MANAGE-4.1, EU_AI_ACT:Art53 | Warn on new third-party AI supplier integration without documented controls (ISO 42001 Clause 8.1 — supplier relation... |
| `iso42001-data-minimisation` | `warn` | medium | ISO_42001:8.4, GDPR:Art5.1c, NIST_AI_RMF:MANAGE-2.4 | Warn on collecting or logging more AI interaction data than necessary (ISO 42001 Clause 8.4) |
| `iso42001-bias-testing` | `warn` | medium | ISO_42001:8.2, NIST_AI_RMF:MEASURE-2.3, EU_AI_ACT:Art10 | Warn when AI model deployed to production without bias or fairness testing evidence (ISO 42001 Clause 8.2) |
| `iso42001-monitoring-required` | `block` | critical | ISO_42001:9.1, NIST_AI_RMF:MEASURE-2.5, SOC2:CC7.2 | Block disabling performance monitoring or observability on AI systems (ISO 42001 Clause 9.1) |
| `iso42001-incident-capture` | `warn` | medium | ISO_42001:10.2, NIST_AI_RMF:MANAGE-1.3, SOC2:CC7.3 | Warn when AI system errors are silently discarded without incident logging (ISO 42001 Clause 10.2) |

### <a id="conduct-eu-ai-act"></a>conduct-eu-ai-act

**Conduct EU AI Act** — v1.0.0 · tier: **paid** · 10 rules

EU AI Act enforcement rules — Article 5 prohibited practices, Article 14 human oversight, Article 13 transparency, Article 10 data governance

**Actions:** `block` ×9 · `warn` ×1  
**Severity:** critical ×7 · high ×3  
**Source:** [`conduct-eu-ai-act.json`](../../apps/api/app/modules/guard/skill_packs/conduct-eu-ai-act.json)

| Rule ID | Action | Severity | Frameworks | Description |
|---|---|---|---|---|
| `eu-ai-no-social-scoring` | `block` | critical | EU_AI_ACT:Art5.1c, ISO_42001:8.6 | Block social scoring systems that rank individuals by behavior (EU AI Act Article 5.1c) |
| `eu-ai-no-emotion-recognition` | `block` | critical | EU_AI_ACT:Art5.1f, ISO_42001:8.6 | Block emotion recognition in workplace or educational contexts (EU AI Act Article 5.1f) |
| `eu-ai-no-biometric-categorization` | `block` | critical | EU_AI_ACT:Art5.1b, GDPR:Art9, ISO_42001:8.6 | Block biometric categorization inferring sensitive attributes (EU AI Act Article 5.1b) |
| `eu-ai-no-mass-surveillance` | `block` | critical | EU_AI_ACT:Art5.1h, ISO_42001:8.6 | Block real-time biometric surveillance in publicly accessible spaces (EU AI Act Article 5.1h) |
| `eu-ai-human-oversight-required` | `block` | critical | EU_AI_ACT:Art14, NIST_AI_RMF:GOVERN-6.1, ISO_42001:8.1 | Block autonomous consequential decisions without human review (EU AI Act Article 14) |
| `eu-ai-transparency-disclosure` | `block` | high | EU_AI_ACT:Art13, EU_AI_ACT:Art50, ISO_42001:8.6 | Warn when AI-generated content or AI interaction is not disclosed to users (EU AI Act Article 13) |
| `eu-ai-pii-training-block` | `block` | high | EU_AI_ACT:Art10, GDPR:Art5.1e, ISO_42001:8.4 | Block writing PII into training datasets without consent markers (EU AI Act Article 10) |
| `eu-ai-gpai-high-risk-use` | `warn` | high | EU_AI_ACT:Art53, EU_AI_ACT:Art9, NIST_AI_RMF:MAP-5.1 | Warn when GPAI model used in high-risk domain without documented assessment (EU AI Act Article 53) |
| `eu-ai-audit-log-required` | `block` | critical | EU_AI_ACT:Art12, SOC2:CC7.2, ISO_42001:9.1 | Block disabling logs on AI systems subject to Article 12 logging obligations (EU AI Act Article 12) |
| `eu-ai-no-manipulation` | `block` | critical | EU_AI_ACT:Art5.1a, ISO_42001:8.6 | Block subliminal manipulation techniques that exploit psychological vulnerabilities (EU AI Act Article 5.1a) |

### <a id="conduct-soc2"></a>conduct-soc2

**Conduct SOC 2** — v1.3.0 · tier: **paid** · 4 rules

SOC 2 compliance rules

**Actions:** `warn` ×3 · `block` ×1  
**Severity:** high ×3 · critical ×1  
**Source:** [`conduct-soc2.json`](../../apps/api/app/modules/guard/skill_packs/conduct-soc2.json)

| Rule ID | Action | Severity | Frameworks | Description |
|---|---|---|---|---|
| `soc2_hardcoded_secret` | `block` | critical | SOC2:CC6.1, ISO_42001:8.4, GDPR:Art32, PCI_DSS:3.5 | Block hardcoded secrets (SOC2 CC6.1) |
| `soc2_log_pii` | `warn` | high | SOC2:CC6.7, GDPR:Art32, HIPAA:164.514, ISO_42001:8.11 | Warn on PII logged to console (SOC2 CC7.2) |
| `soc2_debug_mode` | `warn` | high | SOC2:CC6.6, SOC2:CC8.1, ISO_42001:8.5, OWASP:A05 | Warn on DEBUG=True in production config |
| `soc2_unencrypted_storage` | `warn` | high | SOC2:CC6.1, GDPR:Art32, PCI_DSS:3.4, ISO_42001:8.4 | Warn when sensitive data is written to disk without evident encryption — covers open() with credential-shaped filenam... |

### <a id="conduct-hipaa"></a>conduct-hipaa

**Conduct HIPAA** — v1.4.0 · tier: **paid** · 4 rules

HIPAA PHI protection rules

**Actions:** `block` ×2 · `warn` ×1 · `approval` ×1  
**Severity:** critical ×2 · high ×2  
**Source:** [`conduct-hipaa.json`](../../apps/api/app/modules/guard/skill_packs/conduct-hipaa.json)

| Rule ID | Action | Severity | Frameworks | Description |
|---|---|---|---|---|
| `hipaa_http_phi` | `block` | critical | HIPAA:164.312, SOC2:CC6.1, GDPR:Art32 | Block PHI over unencrypted transit — plain HTTP, FTP, or telnet to endpoints handling patient/medical/PHI/FHIR/HL7/DI... |
| `hipaa_ssn_pattern` | `block` | critical | HIPAA:164.514, GDPR:Art32, PCI_DSS:3.3 | Block SSN patterns in source |
| `hipaa_phi_field` | `warn` | high | HIPAA:164.514, GDPR:Art32, ISO_42001:8.11 | Warn on PHI field access (HIPAA §164.312) |
| `hipaa_phi_export_requires_approval` | `approval` | high | HIPAA:164.308(a)(4), HIPAA:164.312(b), SOC2:CC6.1 | Require compliance-officer approval before exporting PHI-shaped data (SSN, DOB, patient_id, MRN) via bulk write/curl/scp |

### <a id="conduct-irs-1075"></a>conduct-irs-1075

**Conduct IRS 1075** — v1.2.0 · tier: **paid** · 8 rules

IRS Publication 1075 enforcement rules — Federal Tax Information (FTI) protection for government agencies and contractors handling IRS-shared tax data under IRC Section 6103

**Actions:** `block` ×6 · `approval` ×1 · `warn` ×1  
**Severity:** critical ×7 · high ×1  
**Source:** [`conduct-irs-1075.json`](../../apps/api/app/modules/guard/skill_packs/conduct-irs-1075.json)

| Rule ID | Action | Severity | Frameworks | Description |
|---|---|---|---|---|
| `irs1075-no-ein-in-prompt` | `block` | critical | IRS_1075:Sec4, IRS_1075:IRC6103, SOC2:CC6.1 | Block Employer Identification Numbers (EIN) in AI prompts (IRS 1075 Section 4 — FTI Safeguards) |
| `irs1075-no-tax-return-data` | `block` | critical | IRS_1075:Sec4, IRS_1075:IRC6103, HIPAA:164.514 | Block tax return fields (AGI, W-2, 1099 values) in AI model context (IRS 1075 Section 4) |
| `irs1075-no-fti-external-endpoint` | `block` | critical | IRS_1075:Sec4, IRS_1075:IRC6103, NIST_AI_RMF:MANAGE-4.1 | Block FTI from being sent to external AI endpoints not on approved vendor list (IRS 1075 Section 4 — Disclosure Prohi... |
| `irs1075-no-fti-training-data` | `block` | critical | IRS_1075:Sec4, IRS_1075:IRC6103, EU_AI_ACT:Art10 | Block writing FTI into AI training datasets (IRS 1075 Section 4 — Use Restriction) |
| `irs1075-no-fti-unencrypted-write` | `approval` | critical | IRS_1075:Sec9, PCI_DSS:3.4, SOC2:CC6.1 | Require compliance-officer approval for writes of FTI-shaped data to file, disk, or object storage (IRS 1075 Section ... |
| `irs1075-no-fti-plain-log` | `block` | critical | IRS_1075:Sec4, IRS_1075:Sec10, SOC2:CC7.2, GDPR:Art32 | Block FTI appearing unredacted in application logs (IRS 1075 Section 4 — Safeguard Activity) |
| `irs1075-third-party-fti-processor` | `warn` | high | IRS_1075:Sec4, NIST_AI_RMF:MANAGE-4.1, SOC2:CC9.2 | Warn on third-party AI service integration in systems that handle FTI (IRS 1075 Section 4 — Contractor Requirements) |
| `irs1075-fti-purpose-limitation` | `block` | critical | IRS_1075:IRC6103, IRS_1075:Sec4, EU_AI_ACT:Art10 | Block use of FTI beyond the purpose authorised under IRC Section 6103 (IRS 1075 Section 4) |

### <a id="conduct-pci-dss"></a>conduct-pci-dss

**Conduct PCI-DSS** — v1.1.0 · tier: **paid** · 3 rules

PCI-DSS cardholder data rules

**Actions:** `block` ×3  
**Severity:** critical ×2 · high ×1  
**Source:** [`conduct-pci-dss.json`](../../apps/api/app/modules/guard/skill_packs/conduct-pci-dss.json)

| Rule ID | Action | Severity | Frameworks | Description |
|---|---|---|---|---|
| `pci_pan_guard` | `block` | critical | PCI_DSS:3.4, PCI_DSS:3.5, SOC2:CC6.1, GDPR:Art32 | Block card number patterns (PCI DSS Req 3) |
| `pci_cvv_guard` | `block` | critical | PCI_DSS:3.2.1, PCI_DSS:3.2.2, SOC2:CC6.1 | Block CVV storage (PCI DSS Req 3.2) |
| `pci_weak_tls` | `block` | high | PCI_DSS:4.1, SOC2:CC6.7, ISO_42001:8.24 | Block TLS 1.0 usage (PCI DSS Req 4) |

---

## Industry-specific demo packs

### <a id="conduct-financial-services"></a>conduct-financial-services

**Conduct Financial Services** — v1.0.0 · tier: **demo** · 8 rules

Guard controls aligned to US banking model risk management for agentic AI. Interim controls covering SR 11-7 principles while agent-specific guidance is pending.

**Actions:** `block` ×6 · `warn` ×2  
**Severity:** critical ×5 · high ×2 · medium ×1  
**Source:** [`conduct-financial-services.json`](../../apps/api/app/modules/guard/skill_packs/conduct-financial-services.json)

| Rule ID | Action | Severity | Frameworks | Description |
|---|---|---|---|---|
| `fs_tier3_requires_human_oversight` | `block` | critical | SR_11_7:governance, OCC_2021_19, NIST_AI_RMF:MAP-2.3, EU_AI_ACT:Article_26 | Block tier-3 agent action without a recorded human oversight event within the last 24 hours |
| `fs_model_swap_requires_change_record` | `warn` | high | SR_11_7:change_management, FFIEC:change_mgmt, NIST_AI_RMF:GOVERN-1.5 | Warn on model swap mid-workflow without a change control event |
| `fs_lifecycle_promotion_requires_attestation` | `block` | critical | SR_11_7:governance, SR_11_7:change_management, OCC_2021_19, FFIEC:change_mgmt | Block agent lifecycle promotion to production without documented owner attestation |
| `fs_ledger_write_requires_sod` | `block` | critical | SR_11_7:controls, OCC_2021_19, FFIEC:sod, PCI_DSS:7.1 | Block agent write to core banking or ledger systems without segregation-of-duties check |
| `fs_regulated_decisions_require_hitl` | `block` | critical | SR_11_7:high_risk_models, OCC_2021_19, ECOA, FCRA | Block agent decision on credit or lending determinations without human-in-the-loop attestation |
| `fs_customer_data_class_requires_control_mapping` | `block` | high | SR_11_7:data_governance, GLBA, PCI_DSS:7.1, NYDFS_500, SOC2:CC6.1 | Block agent action on customer PII or account data without documented control mapping |
| `fs_cross_tenant_customer_data_blocked` | `block` | critical | SR_11_7:access_controls, GLBA, NYDFS_500, SOC2:CC6.1 | Block agent read across customer tenants or portfolio boundaries without explicit permit |
| `fs_cost_approaching_committee_cap` | `warn` | medium | SR_11_7:monitoring, OCC_2021_19 | Warn on cost accrual approaching per-agent monthly cap set by model risk committee |

### <a id="conduct-life-sciences"></a>conduct-life-sciences

**Conduct Life Sciences** — v1.0.0 · tier: **demo** · 9 rules

Guard controls aligned to life sciences regulatory frameworks for agentic AI. Covers FDA Computer Software Assurance principles, FDA/EMA Good Machine Learning Practice, ICH quality risk management, GAMP AI guidance, and EU AI Act high-risk obligations.

**Actions:** `block` ×5 · `warn` ×3 · `audit` ×1  
**Severity:** critical ×5 · high ×3 · low ×1  
**Source:** [`conduct-life-sciences.json`](../../apps/api/app/modules/guard/skill_packs/conduct-life-sciences.json)

| Rule ID | Action | Severity | Frameworks | Description |
|---|---|---|---|---|
| `ls_clinical_adjacent_requires_human_review` | `block` | critical | FDA_CSA:human_oversight, FDA_EMA_GMLP:P4, EU_AI_ACT:Article_26, ISO_42001:8.5 | Block agent action on clinical decision-adjacent workflows without a recorded human review event (FDA position: AI in... |
| `ls_groundedness_required_for_authoritative_source` | `warn` | high | FDA_CSA:documentation, FDA_EMA_GMLP:P8, ICH_Q9:risk_evidence | Warn on agent proposal lacking provenance chain back to an authoritative source (groundedness gate) |
| `ls_regulated_system_write_requires_two_person` | `block` | critical | FDA_CSA:integrity, GAMP_5:data_integrity, ICH_Q9:controls, ISO_42001:8.4 | Block agent write to LIMS, EDC, MES, or other GxP systems without two-person integrity check |
| `ls_intended_use_scope_check` | `warn` | high | FDA_CSA:intended_use, FDA_EMA_GMLP:P1, GAMP_5:validation | Warn on agent action outside the validated intended-use scope (FDA CSA intended-use principle) |
| `ls_credibility_assessment_freshness` | `block` | critical | FDA_AI_CREDIBILITY:continuous_assessment, FDA_EMA_GMLP:P5, GAMP_5:periodic_review | Block agent action if credibility assessment is expired (FDA 2025 draft guidance on AI credibility) |
| `ls_lifecycle_traceability_log` | `audit` | low | FDA_CSA:traceability, GAMP_5:lifecycle, ISO_42001:9.2 | Audit every agent-touched artifact for CSA lifecycle traceability (records event even without intervention) |
| `ls_model_swap_requires_revalidation` | `warn` | high | FDA_CSA:change_control, FDA_EMA_GMLP:P6, GAMP_5:change_mgmt | Warn on model swap in regulated pathway without accompanying revalidation event |
| `ls_patient_safety_action_requires_hitl` | `block` | critical | FDA_CSA:patient_safety, FDA_EMA_GMLP:P4, ICH_Q9:risk_management, EU_AI_ACT:Article_26 | Block agent decision on patient-safety-adjacent actions without human-in-the-loop attestation |
| `ls_phi_scope_check_required` | `block` | critical | HIPAA:Privacy_Rule, HIPAA:Security_Rule, FDA_CSA:data_governance, ISO_42001:8.4 | Block agent action on PHI-classified data without documented HIPAA scope check |

### <a id="conduct-network-ops"></a>conduct-network-ops

**Conduct — Network Operations Governance** — v0.2.1 · tier: **demo** · 4 rules

Hook-surface rules for governing autonomous NetOps agents. Blocks writes to security-sensitive network configuration (ACL, firewall, routing policy) while allowing reversible operational actions (QoS, service restart, logging). Companion pack for the network_diagnosis_agent playbook.

**Actions:** `block` ×4  
**Severity:** high ×4  
**Source:** [`conduct-network-ops.json`](../../apps/api/app/modules/guard/skill_packs/conduct-network-ops.json)

| Rule ID | Action | Severity | Frameworks | Description |
|---|---|---|---|---|
| `no-network-policy-modify` | `block` | high | SOC2:CC6.1, ISO_42001:6.1 | Block agent shell commands that modify security-sensitive network configuration (ACL, firewall, routing policy, RADIU... |
| `no-radius-policy-modify` | `block` | high | SOC2:CC6.1, SOC2:CC6.6, ISO_42001:6.1 | Block agent shell / API actions that mutate RADIUS / AAA / ClearPass identity policy — service enforcement, role mapp... |
| `no-firmware-downgrade` | `block` | high | SOC2:CC6.1, SOC2:CC7.1, ISO_42001:6.1 | Block agent shell actions that install, load, or activate a network device firmware / OS image (Junos, ArubaOS, Aruba... |
| `no-mass-vlan-reassignment` | `block` | high | SOC2:CC6.1, SOC2:CC7.2, ISO_42001:6.1 | Block agent shell actions that reassign VLAN membership across many ports at once — interface ranges, port-access rol... |

### <a id="conduct-support-ops"></a>conduct-support-ops

**Conduct — Support Operations Governance** — v0.1.0 · tier: **demo** · 2 rules

Hook-surface rules for autonomous support agents. Blocks credential harvest, data exfiltration, and DNS tunneling attempts that arise when agents ingest untrusted customer input (prompt injection). Companion pack for the compromised_support_agent playbook.

**Actions:** `block` ×2  
**Severity:** high ×2  
**Source:** [`conduct-support-ops.json`](../../apps/api/app/modules/guard/skill_packs/conduct-support-ops.json)

| Rule ID | Action | Severity | Frameworks | Description |
|---|---|---|---|---|
| `no-external-post-with-body` | `block` | high | SOC2:CC6.7, ISO_42001:6.1, OWASP_LLM:LLM01 | Block agent HTTP POST/PUT with body via curl or wget. Prompt injection through customer input frequently uses this pa... |
| `no-dns-exfil` | `block` | high | SOC2:CC6.7, ISO_42001:6.1 | Block DNS lookups with unusually long encoded subdomain labels (base64 or hex shape). DNS tunneling is the standard f... |

---

## Adding a rule to a pack

Rules are plain JSON objects. Each rule declares `id`, `persona` (surface), `action` (block/warn/audit/approval), `severity`, optional `match_pattern` (regex) or `match_semantics` (LLM classifier), `frameworks` (compliance tags), and an `enforcement` block that maps the rule to each surface (proxy/hook/mcp/runtime) with `hard`/`conditional`/`soft`/`not_supported`.

Full schema reference: [Policy pack schema (ADR-0002)](../adr/ADR-0002-policy-pack-schema-and-applicability-contract.md).

Enforcement coverage matrix (auto-generated): [enforcement_coverage.generated.md](../modules/conductguard/enforcement_coverage.generated.md).
