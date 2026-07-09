import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";

const root = process.cwd();
const docsDir = path.join(root, "docs", "mental-models");
const imagesDir = path.join(docsDir, "images");

const colors = {
  bg: "#f8fafc",
  ink: "#111827",
  muted: "#64748b",
  line: "#cbd5e1",
  panel: "#ffffff",
  blue: "#2563eb",
  sky: "#0ea5e9",
  teal: "#0f766e",
  green: "#16a34a",
  amber: "#d97706",
  orange: "#ea580c",
  red: "#dc2626",
  purple: "#7c3aed",
  pink: "#db2777",
  slate: "#475569",
};

const diagrams = [
  {
    file: "01-execution-engine.md",
    image: "01-execution-engine.svg",
    alt: "Execution engine mental model",
    title: "Execution Engine",
    subtitle: "A leased worker turns a compiled workflow graph into ordered block execution with durable state.",
    nodes: [
      {
        id: "entry",
        x: 60,
        y: 170,
        w: 250,
        h: 150,
        accent: colors.blue,
        title: "execute_run(run_id)",
        lines: ["Run row", "WorkflowVersion", "Workspace context"],
      },
      {
        id: "prep",
        x: 370,
        y: 130,
        w: 300,
        h: 230,
        accent: colors.teal,
        title: "Prepare runtime",
        lines: [
          "Load graph nodes + edges",
          "Resolve environment credentials",
          "Mint cond_run_* token",
          "Restore Redis checkpoint",
          "Freeze pricing snapshot",
        ],
      },
      {
        id: "dag",
        x: 750,
        y: 115,
        w: 360,
        h: 260,
        accent: colors.purple,
        title: "_execute_dag()",
        lines: [
          "Topological sort",
          "Check cancellation",
          "Skip completed blocks",
          "Compute logic route skip-set",
          "Dispatch one block at a time",
        ],
      },
      {
        id: "blocks",
        x: 1190,
        y: 110,
        w: 330,
        h: 285,
        accent: colors.orange,
        title: "Block executors",
        lines: [
          "brain: LLM/tool loop",
          "tool: integration API",
          "logic: route pass/fail",
          "memory: recall/record",
          "approval: pause",
          "guard/output/mcp",
        ],
      },
      {
        id: "state",
        x: 355,
        y: 515,
        w: 365,
        h: 205,
        accent: colors.green,
        title: "State + events",
        lines: [
          "state[block_id] stores output",
          "RunEvent records transitions",
          "Redis checkpoint after each block",
          "{{block.field}} resolves downstream",
        ],
      },
      {
        id: "failure",
        x: 835,
        y: 515,
        w: 360,
        h: 205,
        accent: colors.red,
        title: "Failure / resume",
        lines: [
          "Block error -> run cleanup",
          "Budget exhausted -> failed",
          "Worker crash -> replay checkpoint",
          "Stale lease -> retry",
        ],
      },
    ],
    arrows: [
      ["entry", "prep"],
      ["prep", "dag"],
      ["dag", "blocks"],
      ["blocks", "state"],
      ["blocks", "failure"],
      ["state", "dag", "next block"],
    ],
    callouts: [
      { x: 70, y: 780, text: "Core invariant: one run owns a lease, every completed block becomes durable state.", color: colors.slate },
    ],
  },
  {
    file: "02-brain-block.md",
    image: "02-brain-block.svg",
    alt: "Brain block mental model",
    title: "Brain Block",
    subtitle: "A bounded LLM reasoning loop that can stay single-turn or run tools inside an isolated session.",
    nodes: [
      {
        id: "block",
        x: 60,
        y: 170,
        w: 260,
        h: 155,
        accent: colors.blue,
        title: "_execute_brain()",
        lines: ["Block config", "State context", "Compiled prompt"],
      },
      {
        id: "router",
        x: 385,
        y: 115,
        w: 310,
        h: 215,
        accent: colors.purple,
        title: "Model router",
        lines: [
          "Explicit YAML model wins",
          "inputs.model override",
          "Playbook default",
          "Complexity -> model",
        ],
      },
      {
        id: "session",
        x: 385,
        y: 405,
        w: 310,
        h: 210,
        accent: colors.teal,
        title: "Execution session",
        lines: [
          "managed: no shell/files",
          "e2b: ephemeral workspace",
          "modal: container",
          "ssh: persistent remote",
        ],
      },
      {
        id: "loop",
        x: 775,
        y: 145,
        w: 380,
        h: 345,
        accent: colors.orange,
        title: "Agentic loop",
        lines: [
          "Turn 1 sufficiency check",
          "POST via Guard proxy",
          "Parse stop_reason/tool calls",
          "Dispatch tools to session",
          "Accumulate turns + cost",
          "Stop on answer or budget",
        ],
      },
      {
        id: "guard",
        x: 1235,
        y: 145,
        w: 300,
        h: 185,
        accent: colors.red,
        title: "Guard proxy",
        lines: ["Conduct URL only", "Policy before vendor", "Audit every call"],
      },
      {
        id: "output",
        x: 1235,
        y: 405,
        w: 300,
        h: 225,
        accent: colors.green,
        title: "Output shape",
        lines: [
          "output text",
          "model + provider",
          "turns + tokens",
          "cost_usd",
          "extracted PR/branch JSON",
        ],
      },
    ],
    arrows: [
      ["block", "router"],
      ["block", "session"],
      ["router", "loop"],
      ["session", "loop"],
      ["loop", "guard"],
      ["guard", "loop", "LLM response"],
      ["loop", "output"],
    ],
    callouts: [
      { x: 70, y: 760, text: "Critical rule: agentic blocks need runs_on=e2b/modal/ssh for real file or shell access.", color: colors.red },
    ],
  },
  {
    file: "03-guard-proxy.md",
    image: "03-guard-proxy.svg",
    alt: "Guard proxy mental model",
    title: "Guard Proxy",
    subtitle: "A universal LLM gateway that authenticates, enforces policy, selects upstream, forwards, and audits.",
    nodes: [
      {
        id: "incoming",
        x: 55,
        y: 205,
        w: 235,
        h: 145,
        accent: colors.blue,
        title: "Incoming SDK call",
        lines: ["Anthropic", "OpenAI", "Perplexity"],
      },
      {
        id: "auth",
        x: 345,
        y: 135,
        w: 270,
        h: 220,
        accent: colors.purple,
        title: "1. AUTH",
        lines: [
          "cond_run_* -> run",
          "cond_agt_* -> agent",
          "guard-mt-* -> member",
          "cond_live_* -> API key",
          "Unknown -> 401",
        ],
      },
      {
        id: "policy",
        x: 680,
        y: 135,
        w: 285,
        h: 220,
        accent: colors.red,
        title: "2. POLICY",
        lines: [
          "compute_policy(proxy)",
          "Match provider/model/prompt",
          "BLOCK -> 403",
          "WARN or ALLOW -> forward",
          "Error -> 403 fail-closed",
        ],
      },
      {
        id: "upstream",
        x: 1030,
        y: 135,
        w: 260,
        h: 220,
        accent: colors.teal,
        title: "3-4. UPSTREAM + KEY",
        lines: [
          "BYO gateway if configured",
          "Vendor direct otherwise",
          "Use proxy key or vendor key",
          "Missing key -> clear 400",
        ],
      },
      {
        id: "forward",
        x: 1360,
        y: 205,
        w: 190,
        h: 145,
        accent: colors.green,
        title: "5. FORWARD",
        lines: ["SSE passthrough", "Vendor format"],
      },
      {
        id: "audit",
        x: 675,
        y: 505,
        w: 310,
        h: 210,
        accent: colors.orange,
        title: "6. AUDIT",
        lines: [
          "Background write",
          "workspace + user",
          "provider + model",
          "decision + rule_id",
          "tokens + cost",
        ],
      },
    ],
    arrows: [
      ["incoming", "auth"],
      ["auth", "policy"],
      ["policy", "upstream"],
      ["upstream", "forward"],
      ["policy", "audit"],
      ["forward", "audit", "after stream"],
    ],
    callouts: [
      { x: 70, y: 780, text: "Fail-closed boundary: auth or policy uncertainty never reaches the upstream LLM.", color: colors.red },
    ],
  },
  {
    file: "04-policy-engine.md",
    image: "04-policy-engine.svg",
    alt: "Policy engine mental model",
    title: "Policy Engine",
    subtitle: "Workspace rules are flattened, cached, and evaluated first-match-wins for proxy and agent personas.",
    nodes: [
      {
        id: "packs",
        x: 70,
        y: 120,
        w: 280,
        h: 175,
        accent: colors.blue,
        title: "Skill packs",
        lines: ["conduct-base always on", "Optional SOC2/HIPAA packs", "Rule templates"],
      },
      {
        id: "overrides",
        x: 70,
        y: 350,
        w: 280,
        h: 180,
        accent: colors.orange,
        title: "Workspace overrides",
        lines: ["Disable pack rule", "Change action", "Add custom message"],
      },
      {
        id: "custom",
        x: 70,
        y: 585,
        w: 280,
        h: 170,
        accent: colors.purple,
        title: "Custom rules",
        lines: ["Workspace-authored", "ID collision takes precedence", "Persona-specific"],
      },
      {
        id: "compute",
        x: 455,
        y: 280,
        w: 330,
        h: 235,
        accent: colors.teal,
        title: "compute_policy()",
        lines: [
          "Assemble in source order",
          "Flatten final rule list",
          "Version hash payload",
          "One surface per persona",
        ],
      },
      {
        id: "cache",
        x: 875,
        y: 280,
        w: 300,
        h: 235,
        accent: colors.green,
        title: "GuardPolicyCache",
        lines: [
          "PK: workspace + persona",
          "payload: flattened rules",
          "computed_at",
          "Invalidated on rule changes",
        ],
      },
      {
        id: "match",
        x: 1265,
        y: 185,
        w: 285,
        h: 320,
        accent: colors.red,
        title: "Request match",
        lines: [
          "provider exact",
          "model regex",
          "prompt regex",
          "All present fields must match",
          "First match wins",
          "No match -> ALLOW",
        ],
      },
      {
        id: "decision",
        x: 1265,
        y: 590,
        w: 285,
        h: 160,
        accent: colors.slate,
        title: "Decision",
        lines: ["BLOCK", "WARN", "ALLOW", "Policy error -> BLOCK"],
      },
    ],
    arrows: [
      ["packs", "compute"],
      ["overrides", "compute"],
      ["custom", "compute"],
      ["compute", "cache"],
      ["cache", "match"],
      ["match", "decision"],
    ],
    callouts: [
      { x: 470, y: 760, text: "Personas: proxy enforces pre-call LLM policy; agent is stricter for runtime behavior.", color: colors.slate },
    ],
  },
  {
    file: "05-memory.md",
    image: "05-memory.svg",
    alt: "Agent memory mental model",
    title: "Agent Memory",
    subtitle: "Agents read nearest lessons before work and write new lessons afterward, scoped by workspace and repo.",
    nodes: [
      {
        id: "trigger",
        x: 70,
        y: 190,
        w: 240,
        h: 150,
        accent: colors.blue,
        title: "Run starts",
        lines: ["_trigger repo", "workspace_id", "state context"],
      },
      {
        id: "read",
        x: 390,
        y: 130,
        w: 315,
        h: 235,
        accent: colors.teal,
        title: "read_memory",
        lines: [
          "Resolve key template",
          "Embed query key",
          "Filter workspace/scope/key",
          "Order by vector distance",
          "Fallback: recent rows",
        ],
      },
      {
        id: "brain",
        x: 790,
        y: 180,
        w: 285,
        h: 175,
        accent: colors.purple,
        title: "Brain block",
        lines: ["Prior entries injected", "Avoid failed approach", "Reuse known pattern"],
      },
      {
        id: "write",
        x: 1160,
        y: 130,
        w: 325,
        h: 235,
        accent: colors.orange,
        title: "record_outcome",
        lines: [
          "Resolve summary template",
          "Embed lesson text",
          "Insert agent_memory row",
          "Link run_id",
          "Used by future runs",
        ],
      },
      {
        id: "table",
        x: 500,
        y: 520,
        w: 600,
        h: 205,
        accent: colors.green,
        title: "agent_memory",
        lines: [
          "workspace_id, scope, key",
          "summary",
          "embedding vector(1536)",
          "run_id, created_at",
        ],
      },
    ],
    arrows: [
      ["trigger", "read"],
      ["read", "brain"],
      ["brain", "write"],
      ["read", "table"],
      ["write", "table"],
      ["table", "read", "future recall"],
    ],
    callouts: [
      { x: 70, y: 790, text: "Bug fix captured here: reads filter on workspace_id + scope + key, not playbook_slug.", color: colors.green },
    ],
  },
  {
    file: "06-dsl-compiler.md",
    image: "06-dsl-compiler.svg",
    alt: "DSL compiler mental model",
    title: "DSL / Compiler",
    subtitle: "Publish-time processing turns YAML playbooks into cached graphs and compiled brain prompts.",
    nodes: [
      {
        id: "yaml",
        x: 65,
        y: 205,
        w: 250,
        h: 165,
        accent: colors.blue,
        title: "YAML source",
        lines: ["Canonical source", "inputs / blocks / on", "extends base"],
      },
      {
        id: "loader",
        x: 395,
        y: 140,
        w: 325,
        h: 260,
        accent: colors.teal,
        title: "Stage 1: Loader",
        lines: [
          "Parse + validate schema",
          "Resolve extends",
          "$use copies base blocks",
          "Embed snippets",
          "Build nodes + edges",
        ],
      },
      {
        id: "graph",
        x: 800,
        y: 180,
        w: 270,
        h: 185,
        accent: colors.green,
        title: "Workflow graph",
        lines: ["nodes[]", "edges[]", "sourceHandle pass/fail", "Stored as JSONB"],
      },
      {
        id: "compiler",
        x: 395,
        y: 500,
        w: 325,
        h: 240,
        accent: colors.purple,
        title: "Stage 2: Compiler",
        lines: [
          "Brain blocks only",
          "Extract structured slots",
          "Assemble Jinja prompt",
          "StrictUndefined",
          "Publish-time LLM calls",
        ],
      },
      {
        id: "artifacts",
        x: 800,
        y: 500,
        w: 330,
        h: 210,
        accent: colors.orange,
        title: "compiled_artifacts",
        lines: ["block_id -> system_prompt", "tool_schema", "Cached on WorkflowVersion"],
      },
      {
        id: "executor",
        x: 1240,
        y: 315,
        w: 290,
        h: 210,
        accent: colors.red,
        title: "Executor consumes",
        lines: ["graph traversal", "compiled prompts", "no runtime prompt generation"],
      },
    ],
    arrows: [
      ["yaml", "loader"],
      ["loader", "graph"],
      ["yaml", "compiler"],
      ["compiler", "artifacts"],
      ["graph", "executor"],
      ["artifacts", "executor"],
    ],
    callouts: [
      { x: 70, y: 790, text: "Key distinction: $use is copy + overlay at load time, not runtime inheritance.", color: colors.purple },
    ],
  },
  {
    file: "07-agent-identity.md",
    image: "07-agent-identity.svg",
    alt: "Agent identity mental model",
    title: "Agent Identity",
    subtitle: "Four token families authenticate agents, runs, CLI members, and user API access through one auth path.",
    nodes: [
      {
        id: "request",
        x: 60,
        y: 330,
        w: 235,
        h: 150,
        accent: colors.blue,
        title: "Incoming request",
        lines: ["Bearer token", "X-Api-Key", "or Clerk JWT"],
      },
      {
        id: "auth",
        x: 390,
        y: 250,
        w: 320,
        h: 310,
        accent: colors.purple,
        title: "Auth resolution order",
        lines: [
          "cond_run_*",
          "cond_agt_*",
          "guard-mt-*",
          "server CLI key",
          "cond_live_* hash",
          "Clerk JWT fallback",
          "No match -> 401",
        ],
      },
      {
        id: "run",
        x: 805,
        y: 120,
        w: 300,
        h: 160,
        accent: colors.orange,
        title: "Run token",
        lines: ["cond_run_*", "Single run", "Encrypted then cleared", "Sandbox execution"],
      },
      {
        id: "agent",
        x: 805,
        y: 320,
        w: 300,
        h: 160,
        accent: colors.teal,
        title: "Agent identity",
        lines: ["cond_agt_*", "Permanent", "AES-256-GCM", "Recurring agents"],
      },
      {
        id: "member",
        x: 805,
        y: 520,
        w: 300,
        h: 160,
        accent: colors.green,
        title: "Member token",
        lines: ["guard-mt-*", "Session", "Plaintext in DB", "Guard CLI proxy"],
      },
      {
        id: "api",
        x: 805,
        y: 720,
        w: 300,
        h: 150,
        accent: colors.red,
        title: "User API key",
        lines: ["cond_live_*", "Configurable TTL", "SHA-256 hash only", "API access"],
      },
      {
        id: "workspace",
        x: 1230,
        y: 330,
        w: 300,
        h: 180,
        accent: colors.slate,
        title: "Workspace context",
        lines: ["query param", "X-Workspace-Id", "Clerk org_id", "personal workspace", "dev fallback"],
      },
    ],
    arrows: [
      ["request", "auth"],
      ["auth", "run"],
      ["auth", "agent"],
      ["auth", "member"],
      ["auth", "api"],
      ["auth", "workspace"],
    ],
    callouts: [
      { x: 70, y: 890, text: "Security split: recoverable tokens are encrypted; user API keys are hash-only.", color: colors.red },
    ],
    height: 980,
  },
  {
    file: "08-playbooks.md",
    image: "08-playbooks.svg",
    alt: "Playbooks mental model",
    title: "Playbooks",
    subtitle: "Reusable YAML workflows install into workspaces, register triggers, and execute as runtime DAGs.",
    nodes: [
      {
        id: "yaml",
        x: 55,
        y: 150,
        w: 285,
        h: 255,
        accent: colors.blue,
        title: "Playbook YAML",
        lines: [
          "name + version",
          "extends base-autopilot",
          "inputs",
          "blocks",
          "on: trigger",
          "cleanup",
        ],
      },
      {
        id: "base",
        x: 55,
        y: 495,
        w: 285,
        h: 210,
        accent: colors.purple,
        title: "Base file pattern",
        lines: ["kind: base", "snippets", "template blocks", "$use copy + override"],
      },
      {
        id: "install",
        x: 430,
        y: 240,
        w: 300,
        h: 210,
        accent: colors.teal,
        title: "Install",
        lines: [
          "conduct agent install",
          "Create workflow",
          "Register GitHub webhook",
          "Repo allowlist + label",
        ],
      },
      {
        id: "chain",
        x: 820,
        y: 115,
        w: 345,
        h: 420,
        accent: colors.orange,
        title: "Autopilot chain",
        lines: [
          "security-scanner creates issue",
          "github_issue_labeled triggers",
          "recall_context",
          "plan_fix",
          "implement_fix",
          "run_tests",
          "open_pr",
          "record_outcome",
        ],
      },
      {
        id: "rules",
        x: 1245,
        y: 170,
        w: 300,
        h: 320,
        accent: colors.red,
        title: "Design rules",
        lines: [
          "agentic needs runs_on",
          "single outputs JSON only",
          "read memory before work",
          "write memory after work",
          "explicit max_turns",
        ],
      },
      {
        id: "runtime",
        x: 575,
        y: 640,
        w: 450,
        h: 150,
        accent: colors.green,
        title: "Runtime result",
        lines: ["Compiled graph executes block-by-block", "Cleanup runs even on failure"],
      },
    ],
    arrows: [
      ["base", "yaml"],
      ["yaml", "install"],
      ["install", "chain"],
      ["chain", "rules"],
      ["chain", "runtime"],
    ],
    callouts: [
      { x: 70, y: 810, text: "Think of a playbook as a productized DAG: trigger, inputs, executable blocks, and cleanup.", color: colors.slate },
    ],
  },
  {
    file: "09-pricing.md",
    image: "09-pricing.svg",
    alt: "Pricing mental model",
    title: "Pricing",
    subtitle: "A frozen rate snapshot converts LLM usage into per-turn, per-block, and per-run cost.",
    nodes: [
      {
        id: "snapshot",
        x: 80,
        y: 180,
        w: 310,
        h: 215,
        accent: colors.blue,
        title: "Run start",
        lines: [
          "get_current_pricing()",
          "DB rates or defaults",
          "Apply env overrides",
          "Freeze version_hash",
        ],
      },
      {
        id: "usage",
        x: 470,
        y: 130,
        w: 315,
        h: 230,
        accent: colors.purple,
        title: "LLM usage",
        lines: [
          "input_tokens",
          "output_tokens",
          "cache_read",
          "cache_write",
          "request_fee_usd",
        ],
      },
      {
        id: "formula",
        x: 860,
        y: 125,
        w: 370,
        h: 245,
        accent: colors.orange,
        title: "Cost formula",
        lines: [
          "tokens * rate / 1M",
          "sum input + output",
          "add cache read/write",
          "add request fee",
          "fallback unknown models",
        ],
      },
      {
        id: "block",
        x: 1310,
        y: 160,
        w: 225,
        h: 180,
        accent: colors.teal,
        title: "Block cost",
        lines: ["Each brain turn", "Accumulate cost_usd", "Track turns"],
      },
      {
        id: "run",
        x: 575,
        y: 530,
        w: 450,
        h: 200,
        accent: colors.green,
        title: "Run total",
        lines: [
          "Executor aggregates block costs",
          "Run trace shows cost_usd",
          "Guard spend dashboard consumes totals",
          "Frozen snapshot keeps reconciliation stable",
        ],
      },
    ],
    arrows: [
      ["snapshot", "formula"],
      ["usage", "formula"],
      ["formula", "block"],
      ["block", "run"],
      ["snapshot", "run", "same rates all run"],
    ],
    callouts: [
      { x: 80, y: 780, text: "Reason for snapshots: rate changes mid-run must not rewrite the meaning of earlier turns.", color: colors.blue },
    ],
  },
  {
    file: "10-auth-crypto.md",
    image: "10-auth-crypto.svg",
    alt: "Auth and crypto mental model",
    title: "Auth & Crypto",
    subtitle: "Human authentication and secret-at-rest protection are independent systems that meet at request handlers.",
    nodes: [
      {
        id: "request",
        x: 65,
        y: 330,
        w: 240,
        h: 150,
        accent: colors.blue,
        title: "Endpoint request",
        lines: ["User or API caller", "Router dependencies", "Workspace lookup"],
      },
      {
        id: "clerk",
        x: 390,
        y: 105,
        w: 350,
        h: 285,
        accent: colors.purple,
        title: "Clerk JWT verification",
        lines: [
          "Read KID",
          "Fetch/cache JWKS",
          "Verify RS256",
          "Validate issuer",
          "Optional audience",
          "Return sub + org_id",
        ],
      },
      {
        id: "crypto",
        x: 390,
        y: 505,
        w: 350,
        h: 275,
        accent: colors.teal,
        title: "AES-256-GCM",
        lines: [
          "96-bit random nonce",
          "nonce + ciphertext base64",
          "ENCRYPTION_KEY padded to 32 bytes",
          "Prod fails on default key",
        ],
      },
      {
        id: "secrets",
        x: 830,
        y: 505,
        w: 320,
        h: 250,
        accent: colors.orange,
        title: "Encrypted at rest",
        lines: [
          "integration credentials",
          "agent identity token",
          "run token until first read",
          "CredentialStore prevents log leaks",
        ],
      },
      {
        id: "hash",
        x: 830,
        y: 125,
        w: 320,
        h: 215,
        accent: colors.red,
        title: "Hash-only secrets",
        lines: ["cond_live_* API key", "run token hash", "SHA-256 lookup", "Plaintext never persisted"],
      },
      {
        id: "rbac",
        x: 1245,
        y: 300,
        w: 300,
        h: 220,
        accent: colors.green,
        title: "Endpoint guard",
        lines: [
          "get_workspace_id",
          "get_current_user",
          "require_permission",
          "RBAC via role_permissions",
        ],
      },
    ],
    arrows: [
      ["request", "clerk"],
      ["request", "crypto"],
      ["clerk", "rbac"],
      ["hash", "rbac"],
      ["crypto", "secrets"],
      ["secrets", "rbac"],
    ],
    callouts: [
      { x: 75, y: 795, text: "Rule of thumb: use require_permission() on new endpoints; require_workspace_role() is legacy.", color: colors.green },
    ],
  },
  {
    file: "11-database-schema.md",
    image: "11-database-schema.svg",
    alt: "Database schema mental model",
    title: "Database Schema",
    subtitle: "Workspace is the root. Workflows, runs, credentials, identities, guard policy, and memory hang from it.",
    nodes: [
      {
        id: "workspace",
        x: 650,
        y: 110,
        w: 300,
        h: 120,
        accent: colors.blue,
        title: "Workspace",
        lines: ["Tenant boundary", "Common foreign key"],
      },
      {
        id: "workflows",
        x: 80,
        y: 330,
        w: 270,
        h: 190,
        accent: colors.purple,
        title: "workflows",
        lines: ["current_version_id", "playbook_slug", "guard_enabled", "archived_at"],
      },
      {
        id: "versions",
        x: 420,
        y: 330,
        w: 300,
        h: 210,
        accent: colors.teal,
        title: "workflow_versions",
        lines: ["yaml_source", "graph JSONB", "compiled_artifacts", "published_at"],
      },
      {
        id: "runs",
        x: 800,
        y: 330,
        w: 285,
        h: 230,
        accent: colors.orange,
        title: "runs",
        lines: ["status", "state JSONB", "outcome", "attempt_count", "locked_at/by"],
      },
      {
        id: "events",
        x: 1165,
        y: 330,
        w: 300,
        h: 200,
        accent: colors.green,
        title: "run_events",
        lines: ["run_id", "block_id", "kind", "payload JSONB", "created_at"],
      },
      {
        id: "integrations",
        x: 115,
        y: 680,
        w: 285,
        h: 190,
        accent: colors.red,
        title: "integrations",
        lines: ["handle", "service", "encrypted_credentials", "environment_id nullable"],
      },
      {
        id: "identities",
        x: 480,
        y: 680,
        w: 300,
        h: 190,
        accent: colors.slate,
        title: "agent identities",
        lines: ["token_prefix", "token_encrypted", "run_tokens", "invalidated_at"],
      },
      {
        id: "guard",
        x: 860,
        y: 680,
        w: 295,
        h: 190,
        accent: colors.blue,
        title: "guard tables",
        lines: ["GuardConfig", "SkillPack", "GuardAuditEvent", "GuardPolicyCache"],
      },
      {
        id: "memory",
        x: 1230,
        y: 680,
        w: 290,
        h: 190,
        accent: colors.teal,
        title: "agent_memory",
        lines: ["scope + key", "summary", "embedding vector", "run_id"],
      },
    ],
    arrows: [
      ["workspace", "workflows"],
      ["workflows", "versions"],
      ["versions", "runs"],
      ["runs", "events"],
      ["workspace", "integrations"],
      ["workspace", "identities"],
      ["workspace", "guard"],
      ["workspace", "memory"],
    ],
    callouts: [
      { x: 80, y: 920, text: "Non-obvious invariant: yaml_source is canonical; graph and compiled_artifacts are derived caches.", color: colors.purple },
    ],
    height: 1060,
  },
  {
    file: "12-data-flow.md",
    image: "12-data-flow.svg",
    alt: "End-to-end data flow mental model",
    title: "End-to-End Data Flow",
    subtitle: "External triggers become queued runs, block execution, guarded LLM calls, durable state, and UI updates.",
    nodes: [
      {
        id: "external",
        x: 70,
        y: 175,
        w: 250,
        h: 145,
        accent: colors.blue,
        title: "External event",
        lines: ["GitHub label", "manual trigger", "schedule"],
      },
      {
        id: "ingestion",
        x: 430,
        y: 140,
        w: 360,
        h: 235,
        accent: colors.teal,
        title: "Ingestion",
        lines: [
          "Verify HMAC",
          "Normalize payload",
          "Match trigger conditions",
          "Create Run pending",
          "Mint cond_run_*",
          "Redis RPUSH queue",
        ],
      },
      {
        id: "executor",
        x: 900,
        y: 140,
        w: 390,
        h: 255,
        accent: colors.orange,
        title: "Executor",
        lines: [
          "Acquire lease",
          "Load graph + artifacts",
          "Decrypt credentials",
          "Restore checkpoint",
          "Topological block loop",
          "Merge outputs into state",
        ],
      },
      {
        id: "tool",
        x: 510,
        y: 455,
        w: 285,
        h: 175,
        accent: colors.green,
        title: "Tool block",
        lines: ["Decrypt creds", "Call integration API", "Return structured output"],
      },
      {
        id: "brain",
        x: 900,
        y: 430,
        w: 390,
        h: 225,
        accent: colors.purple,
        title: "Brain block",
        lines: [
          "Compiled system prompt",
          "Optional E2B/Modal session",
          "Build messages",
          "POST to Guard proxy",
          "Dispatch tool calls",
          "Accumulate cost + turns",
        ],
      },
      {
        id: "guard",
        x: 1380,
        y: 410,
        w: 300,
        h: 250,
        accent: colors.red,
        title: "Guard proxy",
        lines: [
          "Auth token -> workspace",
          "Policy cache match",
          "Select upstream",
          "Forward SSE",
          "Write audit event",
        ],
      },
      {
        id: "llm",
        x: 1390,
        y: 145,
        w: 280,
        h: 155,
        accent: colors.slate,
        title: "Upstream LLM",
        lines: ["Anthropic/OpenAI", "or BYO gateway", "Portkey/Helicone"],
      },
      {
        id: "state",
        x: 215,
        y: 760,
        w: 360,
        h: 205,
        accent: colors.blue,
        title: "State + checkpoint",
        lines: ["JSONB state accumulator", "Redis checkpoint", "{{block.field}} references", "Resume support"],
      },
      {
        id: "complete",
        x: 700,
        y: 760,
        w: 360,
        h: 205,
        accent: colors.green,
        title: "Completion",
        lines: ["Run.status succeeded", "actual_turns", "outcome artifact", "cost_usd total", "WebSocket event"],
      },
      {
        id: "credentials",
        x: 1185,
        y: 760,
        w: 390,
        h: 205,
        accent: colors.orange,
        title: "Credential boundary",
        lines: [
          "Encrypted Integration row",
          "In-memory CredentialStore",
          "Shell sees real env var",
          "LLM sees placeholder only",
        ],
      },
    ],
    arrows: [
      ["external", "ingestion"],
      ["ingestion", "executor"],
      ["executor", "tool"],
      ["executor", "brain"],
      ["brain", "guard"],
      ["guard", "llm"],
      ["llm", "guard"],
      ["tool", "state"],
      ["brain", "state"],
      ["state", "executor", "next block"],
      ["executor", "complete"],
      ["executor", "credentials"],
      ["credentials", "brain"],
    ],
    callouts: [
      { x: 70, y: 1030, text: "Key handoffs: webhook -> queue -> executor -> block -> state -> UI, with Guard around every LLM call.", color: colors.slate },
    ],
    width: 1760,
    height: 1120,
  },
];

function esc(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function wrapLine(text, maxChars) {
  const words = String(text).split(/\s+/);
  const lines = [];
  let current = "";
  for (const word of words) {
    if (!current) {
      current = word;
    } else if (`${current} ${word}`.length <= maxChars) {
      current += ` ${word}`;
    } else {
      lines.push(current);
      current = word;
    }
  }
  if (current) lines.push(current);
  return lines;
}

function textBlock({ x, y, lines, size = 24, weight = 400, color = colors.ink, maxChars = 30, lineHeight = 1.25 }) {
  const rendered = [];
  let dy = 0;
  for (const line of lines) {
    const wrapped = wrapLine(line, maxChars);
    for (const part of wrapped) {
      rendered.push(
        `<text x="${x}" y="${y + dy}" font-size="${size}" font-weight="${weight}" fill="${color}">${esc(part)}</text>`,
      );
      dy += size * lineHeight;
    }
  }
  return rendered.join("\n");
}

function nodeBox(node) {
  const maxChars = Math.max(18, Math.floor((node.w - 48) / 12));
  const body = textBlock({
    x: node.x + 26,
    y: node.y + 82,
    lines: node.lines,
    size: node.size ?? 23,
    color: colors.ink,
    maxChars,
    lineHeight: 1.2,
  });
  return `
  <g id="${esc(node.id)}">
    <rect x="${node.x}" y="${node.y}" width="${node.w}" height="${node.h}" rx="20" fill="${colors.panel}" stroke="${colors.line}" stroke-width="2"/>
    <rect x="${node.x}" y="${node.y}" width="12" height="${node.h}" rx="6" fill="${node.accent}"/>
    <text x="${node.x + 26}" y="${node.y + 44}" font-size="29" font-weight="700" fill="${colors.ink}">${esc(node.title)}</text>
    ${body}
  </g>`;
}

function center(node, side) {
  const x = side === "left" ? node.x : side === "right" ? node.x + node.w : node.x + node.w / 2;
  const y = side === "top" ? node.y : side === "bottom" ? node.y + node.h : node.y + node.h / 2;
  return { x, y };
}

function chooseSides(a, b) {
  const dx = b.x + b.w / 2 - (a.x + a.w / 2);
  const dy = b.y + b.h / 2 - (a.y + a.h / 2);
  if (Math.abs(dx) > Math.abs(dy)) {
    return dx > 0 ? ["right", "left"] : ["left", "right"];
  }
  return dy > 0 ? ["bottom", "top"] : ["top", "bottom"];
}

function arrow(a, b, label, nodesById) {
  const from = nodesById.get(a);
  const to = nodesById.get(b);
  const [fromSide, toSide] = chooseSides(from, to);
  const start = center(from, fromSide);
  const end = center(to, toSide);
  const midX = (start.x + end.x) / 2;
  const midY = (start.y + end.y) / 2;
  const isHorizontal = fromSide === "left" || fromSide === "right";
  let d;
  if (isHorizontal) {
    d = `M ${start.x} ${start.y} C ${midX} ${start.y}, ${midX} ${end.y}, ${end.x} ${end.y}`;
  } else {
    d = `M ${start.x} ${start.y} C ${start.x} ${midY}, ${end.x} ${midY}, ${end.x} ${end.y}`;
  }
  const labelSvg = label
    ? `<text x="${midX}" y="${midY - 12}" text-anchor="middle" font-size="20" font-weight="700" fill="${colors.muted}">${esc(label)}</text>`
    : "";
  return `<path d="${d}" fill="none" stroke="${colors.slate}" stroke-width="3" marker-end="url(#arrowhead)"/>${labelSvg}`;
}

function callout(item) {
  return `
  <g>
    <rect x="${item.x}" y="${item.y}" width="1460" height="72" rx="18" fill="#eef2ff" stroke="#c7d2fe"/>
    <circle cx="${item.x + 38}" cy="${item.y + 36}" r="12" fill="${item.color}"/>
    <text x="${item.x + 68}" y="${item.y + 45}" font-size="25" font-weight="650" fill="${colors.ink}">${esc(item.text)}</text>
  </g>`;
}

function renderDiagram(diagram) {
  const width = diagram.width ?? 1600;
  const height = diagram.height ?? 900;
  const nodesById = new Map(diagram.nodes.map((node) => [node.id, node]));
  const nodeSvg = diagram.nodes.map(nodeBox).join("\n");
  const arrowSvg = diagram.arrows.map(([a, b, label]) => arrow(a, b, label, nodesById)).join("\n");
  const calloutSvg = (diagram.callouts ?? []).map(callout).join("\n");

  return `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" role="img" aria-labelledby="title desc">
  <title id="title">${esc(diagram.title)}</title>
  <desc id="desc">${esc(diagram.subtitle)}</desc>
  <defs>
    <marker id="arrowhead" markerWidth="14" markerHeight="10" refX="12" refY="5" orient="auto">
      <path d="M 0 0 L 14 5 L 0 10 z" fill="${colors.slate}"/>
    </marker>
    <filter id="shadow" x="-10%" y="-10%" width="120%" height="120%">
      <feDropShadow dx="0" dy="10" stdDeviation="12" flood-color="#0f172a" flood-opacity="0.10"/>
    </filter>
  </defs>
  <style>
    text { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; letter-spacing: 0; }
  </style>
  <rect width="${width}" height="${height}" fill="${colors.bg}"/>
  <text x="58" y="66" font-size="42" font-weight="800" fill="${colors.ink}">${esc(diagram.title)}</text>
  <text x="60" y="105" font-size="23" fill="${colors.muted}">${esc(diagram.subtitle)}</text>
  <g>
    ${arrowSvg}
  </g>
  <g filter="url(#shadow)">
    ${nodeSvg}
  </g>
  ${calloutSvg}
</svg>
`;
}

function imageEmbed(diagram) {
  return `![${diagram.alt}](images/${diagram.image})`;
}

async function updateMarkdown(diagram) {
  const target = path.join(docsDir, diagram.file);
  const source = await readFile(target, "utf8");
  const embed = imageEmbed(diagram);
  if (source.includes(embed)) return source;

  const lines = source.split("\n");
  const titleIndex = lines.findIndex((line) => line.startsWith("# "));
  if (titleIndex === -1) {
    throw new Error(`No H1 found in ${diagram.file}`);
  }

  const insertAt = titleIndex + 1;
  lines.splice(insertAt, 0, "", embed);
  return lines.join("\n");
}

await mkdir(imagesDir, { recursive: true });

for (const diagram of diagrams) {
  await writeFile(path.join(imagesDir, diagram.image), renderDiagram(diagram), "utf8");
  await writeFile(path.join(docsDir, diagram.file), await updateMarkdown(diagram), "utf8");
}

console.log(`Generated ${diagrams.length} mental-model SVGs in ${path.relative(root, imagesDir)}`);
