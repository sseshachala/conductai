export const VALID_TABS = ["overview", "guard", "mcp-tools", "getting-started", "blocks", "api", "integrations", "on-prem"] as const

// ── Tab definitions ────────────────────────────────────────────────────────────

export const TABS = [
  { id: "overview",        label: "Overview" },
  { id: "guard",           label: "Guard" },
  { id: "mcp-tools",       label: "MCP & Tools" },
  { id: "getting-started", label: "Automations" },
  { id: "blocks",          label: "Blocks" },
  { id: "api",             label: "API reference" },
  { id: "integrations",    label: "Integrations" },
  { id: "on-prem",         label: "On-Prem" },
] as const

export type TabId = typeof TABS[number]["id"]

// ── Sidebar sections per tab ───────────────────────────────────────────────────

export const TAB_NAV: Record<TabId, { href: string; label: string }[]> = {
  "on-prem": [{ href: "#on-prem-deployment", label: "Installation & acceptance" }],
  "overview": [
    { href: "#try-in-60-seconds", label: "Try in 60 seconds" },
    { href: "#how-it-works",      label: "Architecture" },
    { href: "#threat-model",      label: "Security & threat model" },
    { href: "#action-tools",      label: "Gating agent actions" },
    { href: "#cedar-import",      label: "Cedar policy import" },
  ],
  "getting-started": [
    { href: "#overview",     label: "Overview" },
    { href: "#quick-trial",  label: "Zero-install trial (60s)" },
    { href: "#environments", label: "Environments" },
    { href: "#deployment",   label: "Deployment options" },
    { href: "#cli-install",  label: "CLI. Installation" },
    { href: "#cli-auth",     label: "CLI. Authentication" },
    { href: "#cli-commands", label: "CLI. Commands" },
    { href: "#ci",           label: "CI / GitHub Actions" },
    { href: "#cli-mcp",      label: "MCP Server" },
  ],
  "api": [
    { href: "#api-auth",      label: "Authentication" },
    { href: "#api-workflows", label: "Workflows" },
    { href: "#api-runs",      label: "Runs" },
    { href: "#api-keys",      label: "API Keys" },
  ],
  "blocks": [
    { href: "#memory-block", label: "Memory block" },
  ],
  "guard": [
    { href: "#guard",             label: "Overview" },
    { href: "#guard-agent",       label: "Agent guard" },
    { href: "#guard-user-flow",   label: "Developer setup" },
    { href: "#guard-hook",        label: "Hook & tool coverage" },
    { href: "#guard-sync",        label: "Sync & re-sync" },
    { href: "#guard-mcp",         label: "conductguard-mcp" },
    { href: "#guard-tokens",      label: "Agent tokens" },
    { href: "#guard-okta-tracking", label: "Okta agent tracking" },
    { href: "#guard-spend",       label: "Spend controls" },
    { href: "#guard-savings",     label: "Maximize savings" },
    { href: "#guard-roles",       label: "Roles & permissions" },
    { href: "#guard-onboarding",  label: "Team onboarding" },
    { href: "#guard-scenarios",      label: "Test scenarios" },
    { href: "#guard-token-savings",  label: "RTK + Agent Booster" },
    { href: "#guard-policy-reference", label: "Policy reference" },
  ],
  "mcp-tools": [
    { href: "#mcp-client-acceptance", label: "Client acceptance" },
    { href: "#mcp-overview",     label: "Overview" },
    { href: "#mcp-workspace-url",label: "Workspace URL" },
    { href: "#mcp-claude-web",   label: "Claude.ai (web)" },
    { href: "#mcp-claude-code",  label: "Claude Code (CLI)" },
    { href: "#mcp-claude-desktop", label: "Claude Desktop" },
    { href: "#mcp-claude-work",  label: "Claude for Work" },
    { href: "#mcp-chatgpt",      label: "ChatGPT / Codex" },
    { href: "#mcp-codex",        label: "Codex CLI" },
    { href: "#mcp-cursor",       label: "Cursor" },
    { href: "#mcp-vscode",       label: "VS Code + Copilot" },
    { href: "#mcp-copilot-cli",  label: "Copilot CLI" },
    { href: "#mcp-devin",        label: "Devin" },
    { href: "#mcp-windsurf",     label: "Windsurf" },
    { href: "#mcp-other",        label: "Other clients" },
    { href: "#mcp-enforcement",  label: "What gets enforced" },
    { href: "#mcp-troubleshoot", label: "Troubleshooting" },
  ],
  "integrations": [
    { href: "#oidc", label: "OIDC identity & delegation" },
    { href: "#github", label: "GitHub" },
    { href: "#slack",  label: "Slack" },
    { href: "#linear", label: "Linear" },
    { href: "#email",  label: "Email" },
  ],
}
