export interface Playbook {
  slug: string
  name: string
  icon: string
  description: string
  tags: string[]
  category: string
  featured: boolean
  trigger?: string
  block_count?: number
  install_count?: number
  bundled_with?: string
}

export interface PlaybookScore {
  slug: string
  structural_score: number
  quality_score: number
  grade: string
  status: string
  eval_run_at: string | null
}

export const GRADE_STYLES: Record<string, string> = {
  A: "bg-emerald-100 text-emerald-700",
  B: "bg-blue-100  text-blue-700",
  C: "bg-amber-100  text-amber-700",
  D: "bg-orange-100 text-orange-700",
  F: "bg-red-100    text-red-700",
}

export interface Project {
  id: string
  name: string
  project_type?: string
}

export interface Environment {
  id: string
  name: string
}

export const MODEL_HINTS: Record<string, string> = {
  "claude-haiku-4-5-20251001": "Fastest & cheapest, great for simple fixes and triage tasks",
  "claude-sonnet-4-6": "Balanced speed and capability, recommended for most autopilot tasks",
  "claude-opus-4-7": "Most capable, best for complex multi-file refactors, slower and costlier",
}

export interface PlaybookInput {
  label: string
  default: string
  type: "string" | "select"
  options?: string[]
  hint?: string
}

export interface Repo {
  full_name: string
}

// Playbooks that show the GitHub repo selector on install (webhook registered automatically).
export const GITHUB_WEBHOOK_SLUGS = new Set([
  "pr_reviewer", "copilot_reviewer", "issue_triage",
  "ci_notify", "release_notes", "security_scanner",
  "autopilot_quick", "autopilot_full", "autopilot_approved",
  "security_patch_updater", "dependency_updater", "incident_responder",
  "flaky_test_detective", "release_readiness", "docs_drift_detector",
  "terraform_reviewer", "factory",
])

// Playbooks that need manual webhook setup (show instructions instead).
export const MANUAL_WEBHOOK_SLUGS = new Set(["postmortem_drafter"])

export const CATEGORY_ORDER = [
  "All",
  "Issue to PR",
  "Code Review",
  "Issue Triage",
  "CI/CD",
  "Release Management",
  "Incidents & Ops",
  "Security",
  "Docs",
  "Platform & Infra",
]

// Display labels for category chips, maps internal category to design label
export const CATEGORY_LABELS: Record<string, string> = {
  "Issue to PR": "Issue → PR",
  "Issue Triage": "Triage",
  "Release Management": "Release",
  "Incidents & Ops": "Incidents",
  "Platform & Infra": "Infra",
}

export const CAT_BLOCK: Record<string, string> = {
  "Issue to PR":       "brain",
  "Issue → PR":        "brain",
  "Code Review":       "tool",
  "Issue Triage":      "trigger",
  "Triage":            "trigger",
  "CI/CD":             "logic",
  "Release Management":"output",
  "Release":           "output",
  "Incidents & Ops":   "approval",
  "Incidents":         "approval",
  "Security":          "guard",
  "Docs":              "memory",
  "Platform & Infra":  "mcp",
  "Infra":             "mcp",
  "Testing":           "cleanup",
}


export const FRIENDLY_NAMES: Record<string, string> = {
  autopilot_quick:      "Autopilot Quick",
  autopilot_full:       "Autopilot Full",
  autopilot_approved:   "Autopilot + Approval",
  pr_reviewer:          "PR Reviewer",
  issue_triage:         "Issue Triage",
  release_notes:        "Release Notes",
  ci_notify:            "CI Failure Alert",
  incident_responder:   "Incident Responder",
  dependency_updater:   "Dependency Updater",
  copilot_reviewer:     "Copilot / AI PR Reviewer",
  security_scanner:     "Security Scanner",
  flaky_test_detective: "Flaky Test Detective",
  release_readiness:    "Release Readiness Reviewer",
  postmortem_drafter:   "Postmortem Drafter",
  docs_drift_detector:  "Docs Drift Detector",
  terraform_reviewer:   "Terraform Plan Reviewer",
  factory:              "Software Factory",
}

export const PACK_CATALOG = [
  {
    id: "conduct-owasp",
    icon: "🔐",
    name: "OWASP Top 10",
    subtitle: "Guards and scan rules for the 10 most critical web application security risks.",
    description: "Guards and scan rules for the 10 most critical web application security risks, injection, XSS, path traversal, broken crypto, and more.",
    tags: ["Security", "Web"],
    guardRules: 6,
    securityRules: 10,
  },
  {
    id: "conduct-soc2",
    icon: "📋",
    name: "SOC 2",
    subtitle: "Rules aligned to SOC 2 Trust Service Criteria for audit-ready compliance.",
    description: "Rules aligned to SOC 2 Trust Service Criteria, block hardcoded secrets (CC6.1), warn on PII logging (CC7.2), flag debug mode in production.",
    tags: ["Compliance", "Audit"],
    guardRules: 2,
    securityRules: 3,
  },
  {
    id: "conduct-hipaa",
    icon: "🏥",
    name: "HIPAA",
    subtitle: "Block PHI patterns and flag unencrypted health data. §164.312 aligned.",
    description: "Block PHI patterns in source (patient IDs, SSNs, DOBs) and flag unencrypted health data transmission. §164.312 aligned.",
    tags: ["Healthcare", "PII"],
    guardRules: 2,
    securityRules: 3,
  },
  {
    id: "conduct-pci-dss",
    icon: "💳",
    name: "PCI DSS",
    subtitle: "Block PANs and CVVs in source, flag weak TLS. Covers Requirements 3 and 4.",
    description: "Block card numbers (PANs) and CVVs in source, flag weak TLS. Covers PCI DSS Requirements 3 and 4.",
    tags: ["Finance", "Payments"],
    guardRules: 2,
    securityRules: 3,
  },
  {
    id: "conduct-irs-1075",
    icon: "🏛️",
    name: "IRS Publication 1075",
    subtitle: "8 rules protecting Federal Tax Information (FTI) for agencies and contractors under IRC Section 6103.",
    description: "Blocks EINs and tax return data (AGI, W-2, 1099) in AI prompts, prevents FTI from reaching external endpoints or training datasets, enforces encryption and log redaction, and warns on third-party AI processors.",
    tags: ["Government", "Tax", "FTI"],
    guardRules: 8,
  },
  {
    id: "conduct-eu-ai-act",
    icon: "🇪🇺",
    name: "EU AI Act",
    subtitle: "10 rules covering Article 5 prohibited practices, transparency, oversight, and data governance.",
    description: "Blocks social scoring, emotion recognition, biometric categorization, mass surveillance, and subliminal manipulation (Article 5). Covers Article 14 human oversight, Article 13 transparency, Article 10 data governance, and Article 12 logging requirements.",
    tags: ["Compliance", "Regulation", "EU"],
    guardRules: 10,
  },
  {
    id: "conduct-nist-ai-rmf",
    icon: "🏛️",
    name: "NIST AI RMF",
    subtitle: "10 rules across GOVERN, MAP, MEASURE, and MANAGE functions of the NIST AI Risk Management Framework.",
    description: "GOVERN: least privilege, accountability, human oversight, policy bypass. MAP: high-risk domain deployment, unverified data sources. MEASURE: monitoring disable, error swallowing. MANAGE: third-party AI vendors, data retention.",
    tags: ["Compliance", "Risk", "NIST"],
    guardRules: 10,
  },
  {
    id: "conduct-iso-42001",
    icon: "📐",
    name: "ISO 42001",
    subtitle: "10 rules covering operational controls, bias testing, data quality, impact assessment, and incident capture.",
    description: "Covers ISO 42001 Clauses 8.1 (operational controls, human oversight, access control, supplier relationships), 8.2 (bias testing), 8.4 (data quality, data minimisation), 8.5 (impact assessment), 8.6 (responsible use), 9.1 (monitoring), and 10.2 (incident capture).",
    tags: ["Compliance", "AI Governance", "ISO"],
    guardRules: 10,
  },
  {
    id: "conduct-prompt-injection",
    icon: "🧱",
    name: "Prompt Injection Defense",
    subtitle: "30 patterns for override, role-hijack, delimiter-escape, encoded-payload, tool-call-spoof, and system-prompt disclosure attempts.",
    description: "Dedicated pack covering OWASP LLM01, MITRE ATLAS AML.M0031, and ASI06. Includes decoded canaries so base64/hex/ROT13/URL-encoded payloads cannot slip past pattern rules. Rules fire on Bash, Edit, and Write across the hook and MCP surfaces. ML classifier upgrade tracked in #1049.",
    tags: ["Security", "AI", "OWASP LLM"],
    guardRules: 30,
  },
  {
    id: "conduct-endpoint-attacks",
    icon: "🛡️",
    name: "Endpoint Attacks",
    subtitle: "10 rules for reverse shells, credential file reads, cloud metadata recon, persistence, download-pipe-shell, and exfil chains.",
    description: "Detects the same attack techniques an agent-EDR (like Perplexity's Numbat) surfaces, but blocks at the pre-execution layer instead of just logging. Covers MITRE ATT&CK T1059.004, T1552.001/004/005, T1053.003, T1543.002/004, T1546.004, T1105, T1027, and T1041. Ships as blocks (critical/high) plus an audit rule for shell profile writes.",
    tags: ["Security", "MITRE ATT&CK", "Endpoint"],
    guardRules: 10,
  },
  {
    id: "conduct-network-ops",
    icon: "🛰️",
    name: "Network Operations Governance",
    subtitle: "Hook-surface rule blocking autonomous writes to ACL / firewall / routing policy. Companion pack for the network_diagnosis_agent playbook.",
    description: "Bounded-autonomy pack for NetOps agents. Ships one rule (no-network-policy-modify) that blocks agent shell commands matching Junos / Aruba / IOS-style network configuration change verbs — configure terminal, set/delete firewall/security/access-list, write memory, direct writes to *config_changes*.json. Enforcement is hook-only (proxy=not_supported) so LLM prompts about network config flow through untouched; blocks fire only when the agent actually invokes run_shell with a matching command.",
    tags: ["Demo", "Network", "Autonomy", "Bounded"],
    guardRules: 1,
  },
  {
    id: "conduct-base",
    icon: "🚀",
    name: "Startup Baseline",
    subtitle: "Auto-installed. Proxy safety, agent guardrails, and surface-aware policies for every AI tool.",
    description: "Core governance pack — 3 proxy rules (credential leak, prompt injection, PII), 13 agent rules (rm -rf, sudo, .env, secrets in code), and 7 surface rules enforcing per-tool policies across Claude, Codex, ChatGPT, Cursor, and Windsurf.",
    tags: ["Starter", "General"],
    proxyRules: 3,
    agentRules: 13,
    surfaceRules: 7,
  },
]
