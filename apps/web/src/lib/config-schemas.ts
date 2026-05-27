import { type BlockType } from "./block-types"

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
    },
  ],
  approval: [
    {
      key: "config.message",
      label: "Approval message",
      type: "textarea",
      required: true,
      placeholder: "PR ready for review: {{github_pr.pr_url}} — approve to merge.",
    },
    {
      key: "config.channel",
      label: "Slack channel",
      type: "text",
      required: true,
      placeholder: "#eng-approvals",
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
        { value: "github_issue_labeled",  label: "GitHub — issue labeled" },
        { value: "deployment.succeeded",  label: "Vercel — deployment succeeded" },
        { value: "deployment.ready",      label: "Vercel — deployment ready" },
        { value: "deployment.failed",     label: "Vercel — deployment failed / error" },
        { value: "webhook",               label: "Inbound webhook" },
      ],
    },
    {
      key: "config.labels",
      label: "Labels",
      type: "tags",
      required: true,
      placeholder: "Add a label…",
      hint: "GitHub labels that fire this trigger — any match triggers the workflow",
      suggestions: ["autopilot ready", "ai_pilot_ready", "ai_ready"],
    },
    {
      key: "config.repo_allowlist",
      label: "Repo allowlist",
      type: "text",
      placeholder: "my-org/my-repo",
      hint: "Comma-separated owner/repo — only these repos will fire the trigger",
    },
    {
      key: "config.webhook_secret",
      label: "Signing secret",
      type: "text",
      required: false,
      placeholder: "auto-generated on install",
      hint: "Requires X-Webhook-Signature header when set",
      readOnly: true,
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
    },
    {
      key: "config.channel",
      label: "Slack channel",
      type: "text",
      required: true,
      placeholder: "#general",
    },
    {
      key: "config.to",
      label: "Email address",
      type: "text",
      required: true,
      placeholder: "you@example.com",
    },
    {
      key: "config.webhook_url",
      label: "Webhook URL",
      type: "text",
      required: true,
      placeholder: "https://hooks.example.com/...",
      hint: "Conduct will POST the run result as JSON",
    },
    {
      key: "config.webhook_secret",
      label: "HMAC secret",
      type: "text",
      required: false,
      placeholder: "optional",
      hint: "Signs the payload — receiver checks X-Conduct-Signature: sha256=<hmac>",
    },
  ],
}
