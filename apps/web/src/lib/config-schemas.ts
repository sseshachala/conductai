import { type BlockType } from "./block-types"

// ── Trigger type config map ───────────────────────────────────────────────────

export interface TriggerTypeConfig {
  label: string
  fields: ConfigField[]
}

// Shared field definitions reused across trigger types
const TRIGGER_REPO_FIELD: ConfigField = {
  key: "config.repo",
  label: "Repository",
  type: "text",
  required: true,
  placeholder: "owner/repo",
  hint: "GitHub repository that fires this trigger",
}
const TRIGGER_BRANCH_FIELD: ConfigField = {
  key: "config.branch_filter",
  label: "Branch filter",
  type: "text",
  required: false,
  placeholder: "main",
  hint: "Only fire when the branch matches (leave blank for all branches)",
}
const TRIGGER_BRANCH_PATTERN_FIELD: ConfigField = {
  key: "config.branch_pattern",
  label: "Branch pattern",
  type: "text",
  required: false,
  placeholder: "main",
  hint: "Glob pattern — e.g. release/* (leave blank for all branches)",
}
const TRIGGER_WORKFLOW_NAME_FIELD: ConfigField = {
  key: "config.workflow_name",
  label: "Workflow name",
  type: "text",
  required: false,
  placeholder: "CI",
  hint: "GitHub Actions workflow file name or display name",
}
const TRIGGER_PROJECT_FIELD: ConfigField = {
  key: "config.project_name",
  label: "Project name",
  type: "text",
  required: false,
  placeholder: "my-vercel-project",
  hint: "Vercel project name (leave blank for any project)",
}
const TRIGGER_CRON_FIELD: ConfigField = {
  key: "config.cron",
  label: "Cron expression",
  type: "text",
  required: true,
  placeholder: "0 9 * * 1-5",
  hint: "Standard cron — e.g. 0 9 * * 1-5 for weekdays at 09:00 UTC",
}

export const TRIGGER_CONFIG: Record<string, TriggerTypeConfig> = {
  manual: {
    label: "Manual run",
    fields: [],  // manual inputs rendered separately as badges
  },
  github_issue_labeled: {
    label: "GitHub — issue labeled",
    fields: [
      TRIGGER_REPO_FIELD,
      {
        key: "config.label",
        label: "Label",
        type: "text",
        required: true,
        placeholder: "autopilot-ready",
        hint: "GitHub issue label that fires this trigger",
      },
    ],
  },
  github_issue_opened: {
    label: "GitHub — issue opened",
    fields: [TRIGGER_REPO_FIELD],
  },
  github_pr_opened: {
    label: "GitHub — PR opened",
    fields: [TRIGGER_REPO_FIELD, TRIGGER_BRANCH_FIELD],
  },
  github_pr_updated: {
    label: "GitHub — PR updated",
    fields: [TRIGGER_REPO_FIELD, TRIGGER_BRANCH_FIELD],
  },
  github_pr_merged: {
    label: "GitHub — PR merged",
    fields: [TRIGGER_REPO_FIELD, TRIGGER_BRANCH_FIELD],
  },
  github_pr_review_requested: {
    label: "GitHub — PR review requested",
    fields: [TRIGGER_REPO_FIELD],
  },
  github_push: {
    label: "GitHub — push to branch",
    fields: [TRIGGER_REPO_FIELD, TRIGGER_BRANCH_PATTERN_FIELD],
  },
  github_issue_comment: {
    label: "GitHub — issue commented",
    fields: [TRIGGER_REPO_FIELD],
  },
  github_workflow_run: {
    label: "GitHub — CI run completed",
    fields: [TRIGGER_REPO_FIELD, TRIGGER_WORKFLOW_NAME_FIELD],
  },
  "deployment.succeeded": {
    label: "Vercel — deployment succeeded",
    fields: [TRIGGER_PROJECT_FIELD],
  },
  "deployment.ready": {
    label: "Vercel — deployment ready",
    fields: [TRIGGER_PROJECT_FIELD],
  },
  "deployment.failed": {
    label: "Vercel — deployment failed",
    fields: [TRIGGER_PROJECT_FIELD],
  },
  webhook: {
    label: "Inbound webhook",
    fields: [],  // webhook URL rendered separately
  },
  schedule: {
    label: "Schedule",
    fields: [TRIGGER_CRON_FIELD],
  },
}

export interface ConfigField {
  key: string          // dot-path into block.data, e.g. "config.params.owner"
  label: string
  type: "text" | "textarea" | "select" | "toggle" | "number" | "tags"
  required?: boolean
  readOnly?: boolean   // show as a non-editable chip — value comes from a previous step
  placeholder?: string
  hint?: string
  options?: { value: string; label: string }[]
  suggestions?: string[]
  defaultValue?: string | boolean | number
  section?: "basic" | "advanced"
}

// ── GitHub ────────────────────────────────────────────────────────────────────

const GITHUB_ACTION_FIELDS: Record<string, ConfigField[]> = {
  fetch_issue: [
    { key: "config.params.owner",        label: "Repo owner",   type: "text", readOnly: true, defaultValue: "{{_trigger.repo_owner}}" },
    { key: "config.params.repo",         label: "Repository",   type: "text", readOnly: true, defaultValue: "{{_trigger.repo_name}}" },
    { key: "config.params.issue_number", label: "Issue number", type: "text", readOnly: true, defaultValue: "{{_trigger.issue_number}}" },
  ],
  create_repo: [
    { key: "config.params.name", label: "Repo name", type: "text", required: true, placeholder: "my-repo" },
  ],
  get_repo: [
    { key: "config.params.owner", label: "Owner", type: "text", required: true, placeholder: "my-org" },
    { key: "config.params.repo",  label: "Repo",  type: "text", required: true, placeholder: "my-repo" },
  ],
  create_branch: [
    { key: "config.params.owner",  label: "Owner",       type: "text", required: true, placeholder: "my-org" },
    { key: "config.params.repo",   label: "Repo",        type: "text", required: true, placeholder: "my-repo" },
    { key: "config.params.branch", label: "Branch name", type: "text", required: true, placeholder: "feat/{{linear_fetch.identifier}}" },
  ],
  open_pull_request: [
    { key: "config.params.owner", label: "Owner",       type: "text", required: true, placeholder: "my-org" },
    { key: "config.params.repo",  label: "Repo",        type: "text", required: true, placeholder: "my-repo" },
    { key: "config.params.title", label: "PR title",    type: "text", required: true, placeholder: "feat: {{linear_fetch.title}}" },
    { key: "config.params.head",  label: "Head branch", type: "text", required: true, placeholder: "feat/{{linear_fetch.identifier}}" },
  ],
  list_pull_requests: [
    { key: "config.params.owner", label: "Owner", type: "text", required: true, placeholder: "my-org" },
    { key: "config.params.repo",  label: "Repo",  type: "text", required: true, placeholder: "my-repo" },
  ],
  fork_repo: [
    { key: "config.params.owner", label: "Owner", type: "text", required: true, placeholder: "my-org" },
    { key: "config.params.repo",  label: "Repo",  type: "text", required: true, placeholder: "my-repo" },
  ],
  list_issues: [
    { key: "config.params.owner", label: "Owner", type: "text",   required: true,  placeholder: "my-org" },
    { key: "config.params.repo",  label: "Repo",  type: "text",   required: true,  placeholder: "my-repo" },
    { key: "config.params.label", label: "Label", type: "text",   required: false, placeholder: "bug", hint: "Filter by label (blank = all)" },
    { key: "config.params.state", label: "State", type: "select", required: false, defaultValue: "open", options: [{ value: "open", label: "Open" }, { value: "closed", label: "Closed" }, { value: "all", label: "All" }] },
  ],
  read_file: [
    { key: "config.params.owner", label: "Owner",  type: "text", required: true,  placeholder: "my-org" },
    { key: "config.params.repo",  label: "Repo",   type: "text", required: true,  placeholder: "my-repo" },
    { key: "config.params.path",  label: "Path",   type: "text", required: true,  placeholder: "src/index.py", hint: "File path relative to repo root" },
    { key: "config.params.ref",   label: "Branch", type: "text", required: false, placeholder: "main", hint: "Branch or commit SHA (blank = default branch)" },
  ],
  update_file: [
    { key: "config.params.owner",   label: "Owner",          type: "text",     required: true,  placeholder: "my-org" },
    { key: "config.params.repo",    label: "Repo",           type: "text",     required: true,  placeholder: "my-repo" },
    { key: "config.params.path",    label: "File path",      type: "text",     required: true,  placeholder: "src/index.py" },
    { key: "config.params.content", label: "Content",        type: "textarea", required: true,  placeholder: "File content..." },
    { key: "config.params.message", label: "Commit message", type: "text",     required: true,  placeholder: "fix: update file" },
    { key: "config.params.branch",  label: "Branch",         type: "text",     required: true,  placeholder: "main" },
    { key: "config.params.sha",     label: "File SHA",       type: "text",     required: false, hint: "Required when updating existing file — use {{read_file.sha}}" },
  ],
  add_repo_secret: [
    { key: "config.params.owner",        label: "Owner",        type: "text", required: true, placeholder: "my-org" },
    { key: "config.params.repo",         label: "Repo",         type: "text", required: true, placeholder: "my-repo" },
    { key: "config.params.secret_name",  label: "Secret name",  type: "text", required: true, placeholder: "MY_API_KEY" },
    { key: "config.params.secret_value", label: "Secret value", type: "text", required: true, placeholder: "{{inputs.api_key}}", hint: "Use a template ref — never hardcode secrets" },
  ],
  search_code: [
    { key: "config.params.query",    label: "Search query", type: "text",   required: true,  placeholder: "{{plan_fix.grep_pattern}} repo:{{fetch_issue.owner}}/{{fetch_issue.repo}}", hint: "GitHub code search — supports repo:, language:, path: filters" },
    { key: "config.params.per_page", label: "Max results",  type: "number", required: false, placeholder: "10", hint: "Maximum file results to return (max 30)" },
  ],
}

// ── Slack ─────────────────────────────────────────────────────────────────────

const SLACK_ACTION_FIELDS: Record<string, ConfigField[]> = {
  post_message: [
    { key: "config.params.channel", label: "Channel", type: "text",     required: true, placeholder: "#general" },
    { key: "config.params.text",    label: "Message", type: "textarea", required: true, placeholder: "{{previous_block.summary}}" },
  ],
  post_dm: [
    { key: "config.params.user", label: "User ID", type: "text",     required: true, placeholder: "U0123456", hint: "Profile → ⋮ → Copy member ID" },
    { key: "config.params.text", label: "Message", type: "textarea", required: true, placeholder: "Your PR is ready for review." },
  ],
  post_approval_message: [
    { key: "config.params.channel", label: "Channel", type: "text",     required: true, placeholder: "#eng-approvals" },
    { key: "config.params.text",    label: "Message", type: "textarea", required: true, placeholder: "PR ready: {{github_pr.pr_url}}" },
  ],
}

// ── Linear ────────────────────────────────────────────────────────────────────

const LINEAR_ACTION_FIELDS: Record<string, ConfigField[]> = {
  fetch_issue: [
    { key: "config.params.issue_id", label: "Issue ID", type: "text", required: true, placeholder: "ENG-42 or uuid", hint: "Linear identifier or UUID" },
  ],
  list_issues: [
    { key: "config.params.team_id", label: "Team ID", type: "text", required: true, placeholder: "team-uuid" },
    { key: "config.params.label",   label: "Label",   type: "text", placeholder: "ai-ready" },
  ],
  create_comment: [
    { key: "config.params.issue_id", label: "Issue ID", type: "text",     required: true, placeholder: "ENG-42" },
    { key: "config.params.body",     label: "Comment",  type: "textarea", required: true, placeholder: "PR opened: {{github_pr.pr_url}}" },
  ],
  update_issue_status: [
    { key: "config.params.issue_id", label: "Issue ID", type: "text", required: true, placeholder: "ENG-42" },
    { key: "config.params.state_id", label: "State ID", type: "text", required: true, placeholder: "in-progress-uuid" },
  ],
}

// ── DigitalOcean ──────────────────────────────────────────────────────────────

const DO_ACTION_FIELDS: Record<string, ConfigField[]> = {
  create_droplet: [
    { key: "config.params.name",   label: "Droplet name", type: "text",   required: true, placeholder: "sandbox-{{linear_fetch.identifier}}" },
    { key: "config.params.region", label: "Region",       type: "select", defaultValue: "nyc3", options: [
      { value: "nyc3", label: "New York 3" },
      { value: "sfo3", label: "San Francisco 3" },
      { value: "lon1", label: "London 1" },
      { value: "ams3", label: "Amsterdam 3" },
    ]},
  ],
  get_droplet: [
    { key: "config.params.droplet_id", label: "Droplet ID", type: "text", required: true, placeholder: "{{create_droplet.droplet_id}}" },
  ],
  destroy_droplet: [
    { key: "config.params.droplet_id", label: "Droplet ID", type: "text", required: true, placeholder: "{{create_droplet.droplet_id}}" },
  ],
  wait_for_droplet: [
    { key: "config.params.droplet_id", label: "Droplet ID", type: "text", required: true, placeholder: "{{create_droplet.droplet_id}}" },
  ],
}

// ── Vercel ────────────────────────────────────────────────────────────────────

const VERCEL_ACTION_FIELDS: Record<string, ConfigField[]> = {
  get_deployment: [
    { key: "config.params.deployment_id", label: "Deployment ID", type: "text", required: true, placeholder: "dpl_abc123" },
  ],
  wait_for_deployment: [
    { key: "config.params.deployment_id", label: "Deployment ID", type: "text", required: true, placeholder: "dpl_abc123" },
  ],
  list_deployments: [
    { key: "config.params.project_id", label: "Project ID", type: "text", required: true, placeholder: "prj_abc123" },
  ],
  get_latest_deployment: [
    { key: "config.params.project_id", label: "Project ID", type: "text", required: true, placeholder: "prj_abc123" },
    { key: "config.params.branch",     label: "Branch",     type: "text", placeholder: "main" },
  ],
  redeploy: [
    { key: "config.params.deployment_id", label: "Deployment ID", type: "text", required: true, placeholder: "dpl_abc123 or {{vercel_get.uid}}" },
  ],
  create_deployment_from_git: [
    { key: "config.params.project_id", label: "Project ID", type: "text", required: true, placeholder: "prj_abc123" },
    { key: "config.params.ref",        label: "Branch",     type: "text", placeholder: "main", defaultValue: "main" },
  ],
}

// ── Railway ───────────────────────────────────────────────────────────────────

const RAILWAY_ACTION_FIELDS: Record<string, ConfigField[]> = {
  trigger_deployment: [
    { key: "config.params.service_id",     label: "Service ID",     type: "text", required: true, placeholder: "service-uuid" },
    { key: "config.params.environment_id", label: "Environment ID", type: "text", required: true, placeholder: "environment-uuid" },
  ],
  list_services: [
    { key: "config.params.project_id", label: "Project ID", type: "text", required: true, placeholder: "project-uuid" },
  ],
  get_deployment: [
    { key: "config.params.deployment_id", label: "Deployment ID", type: "text", required: true, placeholder: "deployment-uuid" },
  ],
  get_service_deployments: [
    { key: "config.params.service_id",     label: "Service ID",     type: "text", required: true, placeholder: "service-uuid" },
    { key: "config.params.environment_id", label: "Environment ID", type: "text", required: true, placeholder: "environment-uuid" },
  ],
  wait_for_deployment: [
    { key: "config.params.deployment_id", label: "Deployment ID", type: "text", required: true, placeholder: "{{railway_deploy.id}}" },
  ],
}

// ── Integration → action options ──────────────────────────────────────────────

export const INTEGRATION_ACTIONS: Record<string, { value: string; label: string }[]> = {
  github: [
    { value: "fetch_issue",        label: "Fetch issue" },
    { value: "get_repo",           label: "Get repo" },
    { value: "create_repo",        label: "Create repo" },
    { value: "create_branch",      label: "Create branch" },
    { value: "open_pull_request",  label: "Open pull request" },
    { value: "list_pull_requests", label: "List pull requests" },
    { value: "fork_repo",          label: "Fork repo" },
    { value: "list_issues",        label: "List issues" },
    { value: "read_file",          label: "Read file" },
    { value: "update_file",        label: "Update file" },
    { value: "add_repo_secret",    label: "Add repo secret" },
    { value: "search_code",        label: "Search code" },
  ],
  slack: [
    { value: "post_message",          label: "Post message" },
    { value: "post_dm",               label: "Send DM" },
    { value: "post_approval_message", label: "Send approval request" },
  ],
  linear: [
    { value: "fetch_issue",         label: "Fetch issue" },
    { value: "list_issues",         label: "List issues" },
    { value: "create_comment",      label: "Create comment" },
    { value: "update_issue_status", label: "Update status" },
  ],
  digitalocean: [
    { value: "create_droplet",   label: "Create droplet" },
    { value: "get_droplet",      label: "Get droplet" },
    { value: "destroy_droplet",  label: "Destroy droplet" },
    { value: "wait_for_droplet", label: "Wait until active" },
  ],
  vercel: [
    { value: "get_deployment",             label: "Get deployment" },
    { value: "wait_for_deployment",        label: "Wait until ready" },
    { value: "list_deployments",           label: "List deployments" },
    { value: "get_latest_deployment",      label: "Get latest deployment" },
    { value: "redeploy",                   label: "Redeploy" },
    { value: "create_deployment_from_git", label: "Deploy from git" },
  ],
  railway: [
    { value: "trigger_deployment",      label: "Trigger deployment" },
    { value: "list_services",           label: "List services" },
    { value: "get_deployment",          label: "Get deployment" },
    { value: "get_service_deployments", label: "Get service deployments" },
    { value: "wait_for_deployment",     label: "Wait until success" },
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

// ── Per-block type schemas (non-tool blocks) ──────────────────────────────────

export const BLOCK_CONFIG_SCHEMAS: Partial<Record<BlockType, ConfigField[]>> = {
  brain: [
    {
      key: "isAgentic",
      label: "Can use tools",
      type: "toggle",
      hint: "AI loops autonomously — reads files, writes code, runs commands",
      defaultValue: false,
      section: "basic",
    },
    {
      key: "routingPreference",
      label: "Model routing",
      type: "select",
      defaultValue: "balanced",
      hint: "Conduct picks the best model for this step based on your preference",
      options: [
        { value: "balanced", label: "Balanced — best default" },
        { value: "quality",  label: "Quality — strongest model" },
        { value: "speed",    label: "Speed — faster response" },
        { value: "cost",     label: "Cost — efficient model" },
      ],
      section: "advanced",
    },
  ],
  logic: [
    {
      key: "config.condition",
      label: "Condition",
      type: "text",
      required: true,
      placeholder: "exit_code == 0",
      hint: "Expression evaluated against the previous block's output",
      section: "basic",
    },
  ],
  approval: [
    {
      key: "config.message",
      label: "Approval message",
      type: "textarea",
      required: false,
      placeholder: "This run requires your approval — please review and respond.",
      section: "basic",
    },
    {
      key: "config.channel",
      label: "Slack channel",
      type: "text",
      required: false,
      placeholder: "#eng-approvals",
      section: "basic",
    },
  ],
  trigger: [
    {
      key: "config.event_type",
      label: "Trigger type",
      type: "select",
      required: true,
      defaultValue: "github_issue_labeled",
      options: [
        { value: "github_issue_labeled",       label: "GitHub — issue labeled" },
        { value: "github_issue_opened",        label: "GitHub — issue opened" },
        { value: "github_pr_opened",           label: "GitHub — PR opened / updated" },
        { value: "github_pr_merged",           label: "GitHub — PR merged" },
        { value: "github_pr_review_requested", label: "GitHub — PR review requested" },
        { value: "github_push",                label: "GitHub — push to branch" },
        { value: "github_issue_comment",       label: "GitHub — issue commented" },
        { value: "github_workflow_run",        label: "GitHub — CI run completed" },
        { value: "deployment.succeeded",       label: "Vercel — deployment succeeded" },
        { value: "deployment.ready",           label: "Vercel — deployment ready" },
        { value: "deployment.failed",          label: "Vercel — deployment failed / error" },
        { value: "webhook",                    label: "Inbound webhook" },
      ],
      section: "basic",
    },
    {
      key: "config.labels",
      label: "Labels",
      type: "tags",
      required: true,
      placeholder: "Add a label…",
      hint: "GitHub labels that fire this trigger — any match triggers the workflow",
      suggestions: ["autopilot ready", "ai_pilot_ready", "ai_ready"],
      section: "basic",
    },
    {
      key: "config.repo_allowlist",
      label: "Repo allowlist",
      type: "text",
      placeholder: "my-org/my-repo",
      hint: "Comma-separated owner/repo — only these repos will fire the trigger",
      section: "basic",
    },
    {
      key: "config.webhook_secret",
      label: "Signing secret",
      type: "text",
      required: false,
      placeholder: "auto-generated on install",
      hint: "Requires X-Webhook-Signature header when set",
      readOnly: true,
      section: "advanced",
    },
  ],
  mcp: [
    {
      key: "config.credential_key",
      label: "MCP Credential Handle",
      type: "text",
      required: true,
      placeholder: "mcp-vercel",
      hint: "Handle saved in Settings → Credentials",
      section: "basic",
    },
    {
      key: "config.tool_name",
      label: "Tool name",
      type: "text",
      required: true,
      placeholder: "get_logs",
      section: "basic",
    },
    {
      key: "config.transport",
      label: "Transport",
      type: "select",
      defaultValue: "auto",
      options: [
        { value: "auto", label: "Auto (HTTP → SSE fallback)" },
        { value: "http", label: "HTTP (Streamable)" },
        { value: "sse",  label: "SSE" },
      ],
      section: "advanced",
    },
  ],
  output: [
    {
      key: "integration",
      label: "Send via",
      type: "select",
      required: true,
      defaultValue: "slack",
      options: [
        { value: "slack",   label: "Slack" },
        { value: "email",   label: "Email" },
        { value: "both",    label: "Slack + Email" },
        { value: "webhook", label: "Outbound webhook" },
      ],
      section: "basic",
    },
    {
      key: "config.channel",
      label: "Slack channel",
      type: "text",
      required: true,
      placeholder: "#general",
      section: "basic",
    },
    {
      key: "config.to",
      label: "Email address",
      type: "text",
      required: true,
      placeholder: "you@example.com",
      section: "basic",
    },
    {
      key: "config.webhook_url",
      label: "Webhook URL",
      type: "text",
      required: true,
      placeholder: "https://hooks.example.com/...",
      hint: "Conduct will POST the run result as JSON",
      section: "basic",
    },
    {
      key: "config.webhook_secret",
      label: "HMAC secret",
      type: "text",
      required: false,
      placeholder: "optional",
      hint: "Signs the payload — receiver checks X-Conduct-Signature: sha256=<hmac>",
      section: "advanced",
    },
  ],
}
