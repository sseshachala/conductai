export interface McpProvider {
  value: string
  label: string
  serverUrl: string
  transport: "sse" | "http" | "stdio" | "auto"
  credentialKey: string
  description?: string
}

export const MCP_PROVIDERS: McpProvider[] = [
  // Conduct
  { value: "conduct",    label: "Conduct AI",          serverUrl: "https://api.conductai.ai/guard/mcp",          transport: "sse",  credentialKey: "CONDUCT_GUARD_TOKEN",  description: "Conduct AI Guard — policy enforcement and audit" },
  // AI providers
  { value: "openai",     label: "OpenAI",               serverUrl: "https://mcp.openai.com",                      transport: "http", credentialKey: "OPENAI_API_KEY",       description: "OpenAI models and tools" },
  { value: "anthropic",  label: "Claude (Anthropic)",   serverUrl: "https://mcp.anthropic.com",                   transport: "http", credentialKey: "ANTHROPIC_API_KEY",    description: "Claude AI tools" },
  { value: "gemini",     label: "Gemini (Google)",      serverUrl: "https://mcp.googleapis.com",                  transport: "http", credentialKey: "GEMINI_API_KEY",       description: "Google Gemini models" },
  // Dev tools
  { value: "github",     label: "GitHub",               serverUrl: "https://api.githubcopilot.com/mcp",           transport: "http", credentialKey: "GITHUB_TOKEN",         description: "GitHub repos, PRs, issues" },
  { value: "vercel",     label: "Vercel",               serverUrl: "https://mcp.vercel.com",                      transport: "http", credentialKey: "VERCEL_TOKEN",         description: "Vercel deployments and projects" },
  { value: "railway",    label: "Railway",              serverUrl: "https://mcp.railway.com",                     transport: "http", credentialKey: "RAILWAY_TOKEN",        description: "Railway deployments" },
  { value: "sentry",     label: "Sentry",               serverUrl: "https://mcp.sentry.io/mcp",                   transport: "http", credentialKey: "SENTRY_TOKEN",         description: "Error tracking and alerts" },
  { value: "datadog",    label: "Datadog",              serverUrl: "https://mcp.datadoghq.com",                   transport: "http", credentialKey: "DATADOG_API_KEY",      description: "Monitoring and observability" },
  { value: "pagerduty",  label: "PagerDuty",            serverUrl: "https://mcp.pagerduty.com",                   transport: "http", credentialKey: "PAGERDUTY_TOKEN",      description: "Incident management" },
  // Project management
  { value: "linear",     label: "Linear",               serverUrl: "https://mcp.linear.app/mcp",                  transport: "http", credentialKey: "LINEAR_API_KEY",       description: "Issues, projects, cycles" },
  { value: "jira",       label: "Jira",                 serverUrl: "https://mcp.atlassian.com/mcp",               transport: "http", credentialKey: "JIRA_TOKEN",           description: "Atlassian Jira issues" },
  { value: "confluence", label: "Confluence",           serverUrl: "https://mcp.atlassian.com/confluence/mcp",    transport: "http", credentialKey: "CONFLUENCE_TOKEN",     description: "Atlassian Confluence docs" },
  { value: "asana",      label: "Asana",                serverUrl: "https://mcp.asana.com",                       transport: "http", credentialKey: "ASANA_TOKEN",          description: "Tasks and projects" },
  { value: "monday",     label: "Monday.com",           serverUrl: "https://mcp.monday.com",                      transport: "http", credentialKey: "MONDAY_API_KEY",       description: "Work management" },
  { value: "notion",     label: "Notion",               serverUrl: "https://mcp.notion.com",                      transport: "http", credentialKey: "NOTION_TOKEN",         description: "Docs and databases" },
  // Communication
  { value: "slack",      label: "Slack",                serverUrl: "https://mcp.slack.com",                       transport: "sse",  credentialKey: "SLACK_TOKEN",          description: "Channels, messages, users" },
  // Design
  { value: "figma",      label: "Figma",                serverUrl: "https://mcp.figma.com",                       transport: "http", credentialKey: "FIGMA_TOKEN",          description: "Design files and components" },
  // Custom
  { value: "custom",     label: "Custom",               serverUrl: "",                                            transport: "sse",  credentialKey: "",                     description: "Any MCP-compatible server" },
]

export function getProvider(value: string): McpProvider | undefined {
  return MCP_PROVIDERS.find(p => p.value === value)
}
