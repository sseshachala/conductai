import { type BlockType } from "./block-types"

export interface ConfigField {
  key: string          // dot-path into block.data, e.g. "config.params.owner"
  label: string
  type: "text" | "textarea" | "select" | "toggle" | "number"
  placeholder?: string
  hint?: string
  options?: { value: string; label: string }[]
  defaultValue?: string | boolean | number
}

export interface ConfigSchema {
  fields: ConfigField[]
}

// ── GitHub actions ────────────────────────────────────────────────────────────

const GITHUB_ACTION_FIELDS: Record<string, ConfigField[]> = {
  create_repo: [
    { key: "config.params.name",        label: "Repo name",   type: "text",   placeholder: "delegator" },
    { key: "config.params.description", label: "Description", type: "text",   placeholder: "AI agent orchestration platform" },
    { key: "config.params.private",     label: "Private",     type: "toggle", defaultValue: true },
    { key: "config.params.auto_init",   label: "Add README",  type: "toggle", defaultValue: true },
  ],
  get_repo: [
    { key: "config.params.owner", label: "Owner",     type: "text", placeholder: "sseshachala" },
    { key: "config.params.repo",  label: "Repo name", type: "text", placeholder: "my-repo" },
  ],
  create_branch: [
    { key: "config.params.owner",       label: "Owner",        type: "text", placeholder: "sseshachala" },
    { key: "config.params.repo",        label: "Repo name",    type: "text", placeholder: "my-repo" },
    { key: "config.params.branch",      label: "New branch",   type: "text", placeholder: "feat/{{linear_fetch.identifier}}" },
    { key: "config.params.from_branch", label: "Base branch",  type: "text", placeholder: "main", defaultValue: "main" },
  ],
  open_pull_request: [
    { key: "config.params.owner", label: "Owner",     type: "text", placeholder: "sseshachala" },
    { key: "config.params.repo",  label: "Repo name", type: "text", placeholder: "my-repo" },
    { key: "config.params.title", label: "PR title",  type: "text", placeholder: "feat: {{linear_fetch.title}}" },
    { key: "config.params.head",  label: "Head branch", type: "text", placeholder: "feat/{{linear_fetch.identifier}}" },
    { key: "config.params.base",  label: "Base branch", type: "text", placeholder: "main", defaultValue: "main" },
    { key: "config.params.body",  label: "PR body",   type: "textarea", placeholder: "Auto-generated PR" },
  ],
  list_pull_requests: [
    { key: "config.params.owner", label: "Owner",     type: "text", placeholder: "sseshachala" },
    { key: "config.params.repo",  label: "Repo name", type: "text", placeholder: "my-repo" },
    { key: "config.params.state", label: "State",     type: "select", options: [
      { value: "open", label: "Open" },
      { value: "closed", label: "Closed" },
      { value: "all", label: "All" },
    ], defaultValue: "open" },
  ],
}

// ── Slack actions ─────────────────────────────────────────────────────────────

const SLACK_ACTION_FIELDS: Record<string, ConfigField[]> = {
  post_message: [
    { key: "config.params.channel", label: "Channel", type: "text", placeholder: "#general" },
    { key: "config.params.text",    label: "Message", type: "textarea", placeholder: "Working on {{linear_fetch.identifier}}…" },
  ],
  post_dm: [
    { key: "config.params.user", label: "Slack user ID", type: "text", placeholder: "U0123456", hint: "Find in member profile → ⋮ → Copy member ID" },
    { key: "config.params.text", label: "Message",       type: "textarea", placeholder: "Hey! Your PR is ready for review." },
  ],
  post_approval_message: [
    { key: "config.params.channel", label: "Channel or user ID", type: "text", placeholder: "#eng-approvals" },
    { key: "config.params.text",    label: "Message",            type: "textarea", placeholder: "PR ready: {{github_pr.pr_url}}" },
  ],
}

// ── Linear actions ────────────────────────────────────────────────────────────

const LINEAR_ACTION_FIELDS: Record<string, ConfigField[]> = {
  fetch_issue: [
    { key: "config.params.issue_id", label: "Issue ID", type: "text", placeholder: "abc123 or ENG-42", hint: "Linear issue UUID or identifier" },
  ],
  list_issues: [
    { key: "config.params.team_id", label: "Team ID",    type: "text", placeholder: "team-uuid" },
    { key: "config.params.label",   label: "Label filter", type: "text", placeholder: "ai-ready" },
  ],
  create_comment: [
    { key: "config.params.issue_id", label: "Issue ID", type: "text", placeholder: "abc123" },
    { key: "config.params.body",     label: "Comment",  type: "textarea", placeholder: "PR opened: {{github_pr.pr_url}}" },
  ],
  update_issue_status: [
    { key: "config.params.issue_id", label: "Issue ID",  type: "text", placeholder: "abc123" },
    { key: "config.params.state_id", label: "State ID",  type: "text", placeholder: "in-progress-state-uuid" },
  ],
}

// ── DigitalOcean actions ──────────────────────────────────────────────────────

const DO_ACTION_FIELDS: Record<string, ConfigField[]> = {
  create_droplet: [
    { key: "config.params.name",   label: "Droplet name", type: "text", placeholder: "sandbox-{{linear_fetch.identifier}}" },
    { key: "config.params.region", label: "Region",       type: "select", options: [
      { value: "nyc3", label: "New York 3" },
      { value: "sfo3", label: "San Francisco 3" },
      { value: "lon1", label: "London 1" },
      { value: "ams3", label: "Amsterdam 3" },
    ], defaultValue: "nyc3" },
    { key: "config.params.size",  label: "Size",  type: "select", options: [
      { value: "s-1vcpu-1gb",  label: "1 vCPU / 1 GB" },
      { value: "s-2vcpu-2gb",  label: "2 vCPU / 2 GB" },
      { value: "s-4vcpu-8gb",  label: "4 vCPU / 8 GB" },
    ], defaultValue: "s-1vcpu-1gb" },
    { key: "config.params.image", label: "Image", type: "text", placeholder: "ubuntu-22-04-x64", defaultValue: "ubuntu-22-04-x64" },
  ],
  get_droplet: [
    { key: "config.params.droplet_id", label: "Droplet ID", type: "text", placeholder: "{{provision_sandbox.droplet_id}}" },
  ],
  destroy_droplet: [
    { key: "config.params.droplet_id", label: "Droplet ID", type: "text", placeholder: "{{provision_sandbox.droplet_id}}" },
  ],
  wait_for_droplet: [
    { key: "config.params.droplet_id",       label: "Droplet ID",      type: "text",   placeholder: "{{provision_sandbox.droplet_id}}" },
    { key: "config.params.timeout_seconds",  label: "Timeout (secs)",  type: "number", placeholder: "300", defaultValue: "300" },
  ],
}

// ── Vercel actions ────────────────────────────────────────────────────────────

const VERCEL_ACTION_FIELDS: Record<string, ConfigField[]> = {
  get_deployment: [
    { key: "config.params.deployment_id", label: "Deployment ID", type: "text", placeholder: "dpl_abc123" },
  ],
  wait_for_deployment: [
    { key: "config.params.deployment_id",      label: "Deployment ID",   type: "text",   placeholder: "dpl_abc123" },
    { key: "config.params.timeout_seconds",    label: "Timeout (secs)",  type: "number", placeholder: "300", defaultValue: "300" },
  ],
  list_deployments: [
    { key: "config.params.project_id", label: "Project ID", type: "text", placeholder: "prj_abc123" },
  ],
  get_latest_deployment: [
    { key: "config.params.project_id", label: "Project ID", type: "text", placeholder: "prj_abc123" },
    { key: "config.params.branch",     label: "Branch",     type: "text", placeholder: "main" },
  ],
  redeploy: [
    { key: "config.params.deployment_id", label: "Deployment ID", type: "text", placeholder: "dpl_abc123 or {{vercel_get.uid}}" },
    { key: "config.params.team_id",       label: "Team ID (optional)", type: "text", placeholder: "team_xyz" },
  ],
  create_deployment_from_git: [
    { key: "config.params.project_id", label: "Project ID", type: "text", placeholder: "prj_abc123" },
    { key: "config.params.ref",        label: "Branch / commit", type: "text", placeholder: "main", defaultValue: "main" },
    { key: "config.params.team_id",    label: "Team ID (optional)", type: "text", placeholder: "team_xyz" },
  ],
}

// ── Railway actions ───────────────────────────────────────────────────────────

const RAILWAY_ACTION_FIELDS: Record<string, ConfigField[]> = {
  trigger_deployment: [
    { key: "config.params.service_id",     label: "Service ID",     type: "text", placeholder: "service-uuid" },
    { key: "config.params.environment_id", label: "Environment ID", type: "text", placeholder: "environment-uuid" },
  ],
  list_services: [
    { key: "config.params.project_id", label: "Project ID", type: "text", placeholder: "project-uuid" },
  ],
  get_deployment: [
    { key: "config.params.deployment_id", label: "Deployment ID", type: "text", placeholder: "deployment-uuid" },
  ],
  get_service_deployments: [
    { key: "config.params.service_id",     label: "Service ID",     type: "text", placeholder: "service-uuid" },
    { key: "config.params.environment_id", label: "Environment ID", type: "text", placeholder: "environment-uuid" },
  ],
  wait_for_deployment: [
    { key: "config.params.deployment_id",     label: "Deployment ID",   type: "text",   placeholder: "deployment-uuid or {{railway_deploy.id}}" },
    { key: "config.params.timeout_seconds",   label: "Timeout (secs)",  type: "number", placeholder: "300", defaultValue: "300" },
  ],
}

// ── Integration → action options ──────────────────────────────────────────────

export const INTEGRATION_ACTIONS: Record<string, { value: string; label: string }[]> = {
  github: [
    { value: "create_repo",        label: "Create repo" },
    { value: "get_repo",           label: "Get repo" },
    { value: "create_branch",      label: "Create branch" },
    { value: "open_pull_request",  label: "Open pull request" },
    { value: "list_pull_requests", label: "List pull requests" },
  ],
  slack: [
    { value: "post_message",          label: "Post message" },
    { value: "post_dm",               label: "Send DM" },
    { value: "post_approval_message", label: "Send approval request" },
  ],
  linear: [
    { value: "fetch_issue",          label: "Fetch issue" },
    { value: "list_issues",          label: "List issues" },
    { value: "create_comment",       label: "Create comment" },
    { value: "update_issue_status",  label: "Update status" },
  ],
  digitalocean: [
    { value: "create_droplet",   label: "Create droplet" },
    { value: "get_droplet",      label: "Get droplet" },
    { value: "destroy_droplet",  label: "Destroy droplet" },
    { value: "wait_for_droplet", label: "Wait until active" },
  ],
  vercel: [
    { value: "get_deployment",            label: "Get deployment" },
    { value: "wait_for_deployment",       label: "Wait until ready" },
    { value: "list_deployments",          label: "List deployments" },
    { value: "get_latest_deployment",     label: "Get latest deployment" },
    { value: "redeploy",                  label: "Redeploy" },
    { value: "create_deployment_from_git", label: "Deploy from git branch" },
  ],
  railway: [
    { value: "trigger_deployment",     label: "Trigger deployment" },
    { value: "list_services",          label: "List services" },
    { value: "get_deployment",         label: "Get deployment" },
    { value: "get_service_deployments", label: "Get service deployments" },
    { value: "wait_for_deployment",    label: "Wait until success" },
  ],
}

export const ACTION_FIELDS: Record<string, Record<string, ConfigField[]>> = {
  github:       GITHUB_ACTION_FIELDS,
  slack:        SLACK_ACTION_FIELDS,
  linear:       LINEAR_ACTION_FIELDS,
  digitalocean: DO_ACTION_FIELDS,
  vercel:       VERCEL_ACTION_FIELDS,
  railway:      RAILWAY_ACTION_FIELDS,
}

export const INTEGRATIONS = [
  { value: "github",       label: "GitHub" },
  { value: "slack",        label: "Slack" },
  { value: "linear",       label: "Linear" },
  { value: "digitalocean", label: "DigitalOcean" },
  { value: "vercel",       label: "Vercel" },
  { value: "railway",      label: "Railway" },
]

// ── Per-block type schemas (non-tool fields) ──────────────────────────────────

export const BLOCK_CONFIG_SCHEMAS: Partial<Record<BlockType, ConfigField[]>> = {
  brain: [
    {
      key: "isAgentic",
      label: "Agentic mode",
      type: "toggle",
      hint: "AI runs in a loop — reads files, writes code, runs commands",
      defaultValue: false,
    },
    {
      key: "config.max_turns",
      label: "Max turns",
      type: "number",
      placeholder: "20",
      hint: "Maximum tool-use iterations (agentic mode only)",
      defaultValue: "20",
    },
  ],
  logic: [
    {
      key: "config.condition",
      label: "Condition",
      type: "text",
      placeholder: "exit_code == 0",
      hint: "Expression evaluated against the previous block's output. e.g. exit_code == 0",
    },
  ],
  approval: [
    {
      key: "config.message",
      label: "Approval message",
      type: "textarea",
      placeholder: "PR ready for review: {{github_pr.pr_url}} — approve to merge.",
    },
    {
      key: "config.slack_user",
      label: "Slack user ID (for DM)",
      type: "text",
      placeholder: "U0123456",
      hint: "If set, sends a DM. Otherwise posts to channel below.",
    },
    {
      key: "config.channel",
      label: "Fallback channel",
      type: "text",
      placeholder: "#eng-approvals",
    },
  ],
  trigger: [
    {
      key: "config.event_type",
      label: "Trigger type",
      type: "select",
      options: [
        { value: "manual",  label: "Manual (Test run button)" },
        { value: "webhook", label: "Webhook" },
        { value: "schedule", label: "Schedule (cron)" },
        { value: "github_issue_labeled", label: "GitHub issue labeled" },
      ],
      defaultValue: "manual",
    },
    {
      key: "config.enforcement",
      label: "Enforcement mode",
      type: "select",
      options: [
        { value: "strict", label: "Strict (require config)" },
        { value: "permissive", label: "Permissive (fallback)" },
      ],
      defaultValue: "strict",
      hint: "When strict, missing label/allowlist config will block trigger matches.",
    },
    {
      key: "config.label_mode",
      label: "Label match mode",
      type: "select",
      options: [
        { value: "exact", label: "Exact label" },
        { value: "one_of", label: "Any of labels" },
        { value: "all_of", label: "All labels required" },
      ],
      defaultValue: "exact",
      hint: "Used for GitHub issue labeled triggers.",
    },
    {
      key: "config.label",
      label: "Label (exact mode)",
      type: "text",
      placeholder: "autopilot-ready",
      hint: "Required when label mode = exact.",
    },
    {
      key: "config.labels",
      label: "Labels (comma-separated)",
      type: "text",
      placeholder: "bug,autopilot-ready",
      hint: "Used for one_of/all_of modes.",
    },
    {
      key: "config.repo_scope",
      label: "Repo scope",
      type: "select",
      options: [
        { value: "allowlist", label: "Allowlist only" },
        { value: "allow_all", label: "Allow all repos" },
        { value: "denylist", label: "Denylist" },
      ],
      defaultValue: "allowlist",
    },
    {
      key: "config.repo_allowlist",
      label: "Repo allowlist",
      type: "text",
      placeholder: "your-org/narratr-website,your-org/narratr-social",
      hint: "Comma-separated owner/repo values.",
    },
    {
      key: "config.repo_denylist",
      label: "Repo denylist",
      type: "text",
      placeholder: "your-org/experimental-repo",
      hint: "Used only when repo scope = denylist.",
    },
    {
      key: "config.cron",
      label: "Cron expression",
      type: "text",
      placeholder: "0 9 * * 1-5",
      hint: "Only used when type = schedule",
    },
  ],
  output: [
    {
      key: "integration",
      label: "Send via",
      type: "select",
      options: [
        { value: "slack", label: "Slack" },
        { value: "email", label: "Email" },
        { value: "both",  label: "Slack + Email" },
      ],
      defaultValue: "slack",
    },
    {
      key: "config.channel",
      label: "Slack channel",
      type: "text",
      placeholder: "#general",
      hint: "Required when sending via Slack",
    },
    {
      key: "config.to",
      label: "To (email address)",
      type: "text",
      placeholder: "you@example.com",
      hint: "Required when sending via Email",
    },
    {
      key: "config.from_address",
      label: "From (optional)",
      type: "text",
      placeholder: "Delegator <notifications@delegator.dev>",
      hint: "Defaults to system sender",
    },
  ],
}
