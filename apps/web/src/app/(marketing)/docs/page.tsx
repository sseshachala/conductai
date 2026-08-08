"use client"
import { useEffect, useState } from "react"
import Link from "next/link"

const VALID_TABS = ["overview", "guard", "mcp-tools", "getting-started", "blocks", "api", "integrations"] as const

// ── Shared components ──────────────────────────────────────────────────────────

function Code({ children }: { children: React.ReactNode }) {
  return <code className="bg-stone-100 px-1.5 py-0.5 rounded text-sm font-mono text-stone-800">{children}</code>
}

function Pre({ children }: { children: string }) {
  return (
    <pre className="bg-stone-900 text-stone-100 rounded-xl px-5 py-4 text-sm font-mono overflow-x-auto leading-relaxed">
      {children}
    </pre>
  )
}

function Step({ n, children }: { n: number; children: React.ReactNode }) {
  return (
    <li className="flex gap-3 mb-2">
      <span className="flex-shrink-0 w-6 h-6 rounded-full bg-stone-900 text-white text-xs font-semibold grid place-items-center mt-0.5">{n}</span>
      <div className="flex-1 text-stone-700 leading-relaxed">{children}</div>
    </li>
  )
}

function SectionHeading({ id, children }: { id: string; children: React.ReactNode }) {
  return <h2 id={id} className="text-xl font-bold text-stone-900 mb-1 scroll-mt-8">{children}</h2>
}

function SubHeading({ children }: { children: React.ReactNode }) {
  return <h3 className="text-sm font-semibold text-stone-700 mb-2 mt-5">{children}</h3>
}

function Screenshot({ src, alt, caption }: { src: string; alt: string; caption: string }) {
  return (
    <figure className="my-4">
      <img src={src} alt={alt} className="rounded-xl border border-stone-200 w-full shadow-sm" />
      <figcaption className="text-xs text-stone-400 mt-2 text-center">{caption}</figcaption>
    </figure>
  )
}

function Method({ m }: { m: string }) {
  const colors: Record<string, string> = {
    GET:    "bg-blue-50 text-blue-700",
    POST:   "bg-green-50 text-green-700",
    DELETE: "bg-red-50 text-red-700",
    PATCH:  "bg-amber-50 text-amber-700",
  }
  return <span className={`text-[10px] font-bold px-2 py-0.5 rounded font-mono ${colors[m] ?? "bg-stone-100 text-stone-600"}`}>{m}</span>
}

function Endpoint({ method, path, desc, children }: { method: string; path: string; desc: string; children?: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-stone-200 overflow-hidden mb-4">
      <div className="flex items-center gap-3 px-4 py-3 bg-stone-50 border-b border-stone-200">
        <Method m={method} />
        <code className="text-sm font-mono text-stone-800 font-medium">{path}</code>
      </div>
      <div className="px-4 py-3">
        <p className="text-sm text-stone-600 mb-3">{desc}</p>
        {children}
      </div>
    </div>
  )
}

// ── Tab definitions ────────────────────────────────────────────────────────────

const TABS = [
  { id: "overview",        label: "Overview" },
  { id: "guard",           label: "Guard" },
  { id: "mcp-tools",       label: "MCP & Tools" },
  { id: "getting-started", label: "Automations" },
  { id: "blocks",          label: "Blocks" },
  { id: "api",             label: "API reference" },
  { id: "integrations",    label: "Integrations" },
] as const

type TabId = typeof TABS[number]["id"]

// ── Sidebar sections per tab ───────────────────────────────────────────────────

const TAB_NAV: Record<TabId, { href: string; label: string }[]> = {
  "overview": [
    { href: "#how-it-works", label: "Architecture" },
    { href: "#threat-model", label: "Security & threat model" },
    { href: "#action-tools", label: "Gating agent actions" },
    { href: "#cedar-import", label: "Cedar policy import" },
  ],
  "getting-started": [
    { href: "#overview",     label: "Overview" },
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
    { href: "#guard-spend",       label: "Spend controls" },
    { href: "#guard-savings",     label: "Maximize savings" },
    { href: "#guard-roles",       label: "Roles & permissions" },
    { href: "#guard-onboarding",  label: "Team onboarding" },
    { href: "#guard-scenarios",      label: "Test scenarios" },
    { href: "#guard-token-savings",  label: "RTK + Agent Booster" },
    { href: "#guard-policy-reference", label: "Policy reference" },
  ],
  "mcp-tools": [
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
    { href: "#github", label: "GitHub" },
    { href: "#slack",  label: "Slack" },
    { href: "#linear", label: "Linear" },
    { href: "#email",  label: "Email" },
  ],
}

// ── Tab content components ─────────────────────────────────────────────────────

function TabOverview() {
  return (
    <div className="space-y-16">
      <section id="how-it-works">
        <h1 className="text-3xl font-bold text-stone-900 mb-3">How Conduct works</h1>
        <p className="text-stone-600 leading-relaxed text-base mb-10">
          Conduct is a governed automation layer for AI agents. You install a playbook, configure it once,
          and it turns tickets, PRs, alerts, and incidents into repeatable workflows, triggered by a webhook,
          on a schedule, or on demand. Every run is traced, every outcome is recorded.
        </p>
        <div className="space-y-0">
          {[
            { step: "1", title: "Playbook",  body: "A YAML file that defines what an agent does, its blocks (AI reasoning, tool calls, approval gates), its triggers, and its inputs. Playbooks live in the Conduct registry and can be customized.", detail: "Each block is typed: brain (LLM reasoning), tool_call (GitHub, Slack, Linear), approval (human gate), or condition (branching logic). The graph is editable on the canvas." },
            { step: "2", title: "Install",   body: "Installing a playbook creates a workflow in your workspace. Conduct generates the agent graph, registers any GitHub webhooks, and stores the resolved inputs. No code to write.", detail: "Under the hood: a WorkflowVersion record is created from the playbook YAML. The YAML is interpreted at install time, the canvas shows the live graph." },
            { step: "3", title: "Configure", body: "Assign an environment to the agent. An environment holds your credentials (GitHub PAT, Slack token, Linear key, LLM API key). One environment can be shared across many agents.", detail: "Credentials are encrypted with AES-256-GCM before storage. They are decrypted in-process at runtime, scoped to the agent's workspace, and never returned to the client." },
            { step: "4", title: "Run",       body: "A run is created by a trigger: a GitHub webhook (pull_request, issues), a schedule (cron), a manual click in the UI, or a POST to the API. Runs execute the graph block by block.", detail: "The executor advances one block at a time. If a block hits an approval gate, the run is paused and waits for a human decision before proceeding." },
            { step: "5", title: "Trace",     body: "Every run streams live events: block_started, brain_tool_call, block_completed, run_paused. The run detail page shows the full trace in real time via Server-Sent Events.", detail: "Events are written to run_events and are immutable. You can replay any run's trace after the fact, nothing is discarded." },
            { step: "6", title: "Outcome",   body: "When a run completes, Conduct writes a semantic outcome: pr_opened, review_completed, issue_triaged, incident_investigated. Outcomes power the Dashboard metrics.", detail: "The outcome is derived from the playbook slug and the run's state. Pre-outcome runs use heuristic fallback, historical counts never drop." },
            { step: "7", title: "Audit",     body: "Every tool call, decision, and output is in the run_events log. The audit trail is immutable and workspace-scoped, you can always answer 'what did the agent do and why?'", detail: "Run events include the full payload for each action: the GitHub API call, the PR number opened, the Slack message sent. Nothing is summarized away." },
          ].map(({ step, title, body, detail }) => (
            <div key={step} className="flex gap-6 pb-8 relative">
              <div className="flex flex-col items-center">
                <div className="w-8 h-8 rounded-full bg-stone-900 text-white text-sm font-bold flex items-center justify-center shrink-0 z-10">{step}</div>
                {parseInt(step) < 7 && <div className="w-px flex-1 bg-stone-200 mt-2" />}
              </div>
              <div className="pt-1 pb-2">
                <p className="font-semibold text-stone-900 mb-1">{title}</p>
                <p className="text-sm text-stone-600 leading-relaxed mb-2">{body}</p>
                <p className="text-xs text-stone-400 leading-relaxed">{detail}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      <section id="threat-model">
        <SectionHeading id="threat-model">Security & threat model</SectionHeading>
        <p className="text-stone-500 text-sm mb-6">
          What Conduct protects today, what it does not, and where we're headed.
          We believe you deserve an honest answer to "is it safe to give this agent my GitHub token?"
        </p>

        <SubHeading>What we protect</SubHeading>
        <div className="rounded-xl border border-stone-200 divide-y divide-stone-100 text-sm mb-6">
          {[
            { label: "Credentials encrypted at rest",    detail: "Every secret is encrypted with AES-256-GCM before writing to the database. The encryption key is an env var, never stored alongside the ciphertext." },
            { label: "Workspace isolation",              detail: "Every query is scoped to workspace_id. A credential, agent, or run from workspace A is never accessible to workspace B, enforced at the ORM layer on every request." },
            { label: "Human approval gates",             detail: "Any block can be marked as an approval gate. The run pauses and cannot proceed until an authorized user approves or rejects." },
            { label: "Immutable audit log",              detail: "run_events are append-only. Every tool call, LLM decision, and output is recorded with a timestamp. There is no delete path for run events." },
            { label: "HMAC-validated webhooks",          detail: "GitHub webhook payloads are validated with HMAC-SHA256 before the run is created. Unauthenticated payloads are rejected with 401." },
            { label: "Hashed API keys",                  detail: "API keys are SHA-256 hashed before storage. The plaintext is shown once at creation and never stored. A compromised database does not expose working keys." },
          ].map(({ label, detail }) => (
            <div key={label} className="px-4 py-3">
              <p className="font-medium text-stone-800 mb-0.5">{label}</p>
              <p className="text-stone-500 text-xs leading-relaxed">{detail}</p>
            </div>
          ))}
        </div>

        <SubHeading>What we do not protect (yet)</SubHeading>
        <div className="rounded-xl border border-amber-200 bg-amber-50 divide-y divide-amber-100 text-sm mb-6">
          {[
            { label: "Credential mediation",             detail: "Credentials are decrypted and passed to the executor at runtime. The executor sees the plaintext token. A compromised executor process could exfiltrate it. Mitigation: the executor runs server-side, not client-side." },
            { label: "Network egress allowlist",         detail: "Agents can call any external URL during a run. There is no per-environment allowlist today. A misconfigured or malicious playbook could make arbitrary outbound requests." },
            { label: "Runtime isolation",                detail: "Some blocks execute in the API worker while sandbox-backed execution can run in workspace-scoped environments. Treat sandbox isolation as a configured runtime property, not a blanket guarantee." },
            { label: "Playbook static analysis",         detail: "Conduct does not analyze a playbook's tool calls before you install it. You should review the YAML before installing third-party or custom playbooks." },
          ].map(({ label, detail }) => (
            <div key={label} className="px-4 py-3">
              <p className="font-medium text-amber-900 mb-0.5">{label}</p>
              <p className="text-amber-800 text-xs leading-relaxed">{detail}</p>
            </div>
          ))}
        </div>

        <SubHeading>Long-term direction</SubHeading>
        <div className="rounded-xl border border-stone-200 divide-y divide-stone-100 text-sm mb-4">
          {[
            ["Credential proxy",              "Agents call a proxy that holds the token, the executor never sees plaintext. Revocation and rate-limiting become centralizable."],
            ["Egress allowlist per environment","Each environment declares which hostnames agents are allowed to call. Requests outside the allowlist are rejected before execution."],
            ["Per-block process isolation",   "Every execution path gets isolated at the process or sandbox boundary. A crashing block cannot affect others."],
            ["Playbook supply chain analysis","Static analysis of YAML before install: what tools are called, what data is read, what external endpoints are contacted."],
          ].map(([label, detail]) => (
            <div key={label} className="flex gap-4 px-4 py-3">
              <span className="font-medium text-stone-700 w-48 shrink-0">{label}</span>
              <span className="text-stone-500 text-xs leading-relaxed">{detail}</span>
            </div>
          ))}
        </div>

        <div className="rounded-xl bg-stone-100 border border-stone-200 px-4 py-3 text-sm text-stone-600">
          <strong>Questions or concerns?</strong> Email <a href="mailto:security@conductai.ai" className="text-indigo-600 hover:underline">security@conductai.ai</a>.
        </div>
      </section>

      <section id="action-tools" className="scroll-mt-8">
        <SectionHeading id="action-tools">Gating agent actions</SectionHeading>
        <p className="text-stone-600 leading-relaxed mb-4">
          When an agent calls a tool that takes a real action (refund, cancel, update, send, delete), Guard
          evaluates the call against the current policy before the action runs. Warn hands off to a human.
          Block returns a clean refusal. Every decision lands in the same hash-chained audit as your model calls.
        </p>
        <p className="text-stone-600 leading-relaxed mb-4">
          Rules are declarative YAML. Ship a rule without a deploy. Below is a minimal example that caps a
          support agent&apos;s refunds and requires supervisor review above a threshold.
        </p>
        <Pre>{`# ~/.conductguard/policies/refund-cap.yaml
name: refund-cap
applies_to:
  - "tool:issue_refund"
rules:
  - id: block-over-1000
    when:
      arg.amount_usd: { gt: 1000 }
    action: block
    reason: "Refund exceeds hard cap. Route to finance."

  - id: warn-over-2x-dispute
    when:
      arg.amount_usd: { gt: "\${arg.disputed_amount_usd} * 2" }
    action: warn
    handoff: supervisor
    reason: "Refund is more than twice the disputed amount. Supervisor review required."`}</Pre>
        <p className="text-stone-500 text-sm mt-4">
          The same pattern applies to any action tool: cancellation reason lists, pricing commitments, DB writes,
          outbound sends. See{" "}
          <a href="?tab=guard#guard-policy-reference" className="text-indigo-600 hover:underline">Policy reference</a>{" "}
          for the full rule grammar.
        </p>
      </section>
      <section id="cedar-import" className="scroll-mt-8">
        <SectionHeading id="cedar-import">Cedar policy import</SectionHeading>
        <p className="text-stone-600 leading-relaxed mb-4">
          Guard accepts policies in <a href="https://www.cedarpolicy.com/" target="_blank" rel="noopener" className="text-indigo-600 hover:underline">Cedar</a>,
          the AWS-blessed open standard used by AWS Verified Permissions and (via Dogwood)
          Amazon Bedrock AgentCore. Import Cedar policies from your existing IAM stack, and
          Guard converts them to its native pack format. Runtime evaluation is unchanged.
        </p>
        <SubHeading>CLI import</SubHeading>
        <Pre>{`# Preview
conduct import-cedar my-policy.json \
  --pack-slug my-cedar-import \
  --pack-name "My Cedar Import"

# Install
conduct import-cedar my-policy.json \
  --pack-slug my-cedar-import \
  --pack-name "My Cedar Import" \
  --install`}</Pre>
        <SubHeading>Cedar text export</SubHeading>
        <p className="text-stone-500 text-sm mb-3">
          Every installed pack renders as Cedar text syntax for readability. Click{" "}
          <strong>View as Cedar</strong> on any pack detail page in the Registry, or fetch
          it via the API:
        </p>
        <Pre>{`GET /guard/registry/packs/{slug}/cedar
GET /guard/registry/packs/{slug}/cedar?version=2.2.0`}</Pre>
        <p className="text-stone-500 text-sm mt-3">
          See the{" "}
          <a href="https://github.com/sseshachala/conductai/blob/main/docs/cedar-adapter-usage.md" className="text-indigo-600 hover:underline">
            full Cedar adapter user guide
          </a>{" "}
          for the mapping table, error taxonomy, and runnable examples.
        </p>
      </section>
    </div>
  )
}

function TabGettingStarted() {
  return (
    <div className="space-y-16">
      <section id="overview">
        <h1 className="text-3xl font-bold text-stone-900 mb-3">Documentation</h1>
        <p className="text-stone-600 leading-relaxed text-base">
          Conduct AI lets you build and run governed AI automations across your tools. GitHub, Slack, Linear, and more.
          Agents are configured on a canvas, scoped to an environment, and triggered on-demand, by webhook, or on a schedule.
        </p>
      </section>

      <section id="environments">
        <SectionHeading id="environments">Environments</SectionHeading>
        <p className="text-stone-500 text-sm mb-4">A named set of credentials (e.g. <Code>production</Code>, <Code>staging</Code>) assigned to an agent.</p>
        <ol className="list-decimal list-inside space-y-2 text-sm text-stone-600">
          <li>Go to <strong>Settings → Environments</strong> and create an environment.</li>
          <li>Click the environment and connect your integrations (GitHub, Slack, etc.).</li>
          <li>Open an agent on the canvas, go to <strong>Settings</strong>, and assign the environment.</li>
        </ol>
      </section>

      <section id="deployment">
        <SectionHeading id="deployment">Deployment options</SectionHeading>
        <p className="text-stone-500 text-sm mb-4">ConductGuard runs in three modes. Same policy engine, same CLI, same audit trail — wherever your data must stay.</p>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-4">
          {[
            { name: "SaaS", icon: "☁️", desc: "Managed by Conduct. Up in minutes, no infra required. Default for most teams." },
            { name: "BYOC", icon: "🏢", desc: "Runs inside your AWS, GCP, or Azure account. Data stays in your cloud boundary." },
            { name: "On-premise", icon: "🔒", desc: "Air-gapped deployment. Nothing leaves your network. Available on Enterprise." },
          ].map(t => (
            <div key={t.name} className="rounded-xl border border-stone-200 bg-stone-50 px-4 py-3">
              <p className="font-semibold text-stone-800 text-sm">{t.icon} {t.name}</p>
              <p className="text-stone-500 text-xs mt-1">{t.desc}</p>
            </div>
          ))}
        </div>
        <p className="text-sm text-stone-500">See the full comparison at <a href="/deployment" className="text-indigo-600 hover:underline">conductai.ai/deployment</a>, or <a href="https://cal.com/sudhi-seshachala-pks7pd" className="text-indigo-600 hover:underline" target="_blank" rel="noopener">book a call</a> for BYOC or on-premise setup.</p>
      </section>

      <section id="cli-install">
        <SectionHeading id="cli-install">CLI. Installation</SectionHeading>
        <p className="text-stone-500 text-sm mb-4"><Code>conduct-cli</Code> is the official command-line tool for Conduct AI. Requires Python 3.9+.</p>
        <SubHeading>Install from PyPI</SubHeading>
        <Pre>{`pip install conduct-cli

# verify
conduct --version`}</Pre>
        <SubHeading>Or install with pipx (recommended for isolation)</SubHeading>
        <Pre>{`pipx install conduct-cli`}</Pre>
      </section>

      <section id="cli-auth">
        <SectionHeading id="cli-auth">CLI. Authentication</SectionHeading>
        <p className="text-stone-600 text-sm mb-4">
          Generate an API key from <strong>Settings → API Keys</strong> in the dashboard.
          Keys start with <Code>cond_live_</Code> and are shown only once.
        </p>
        <Pre>{`conduct login \\
  --server    https://api.conductai.ai \\
  --api-key   cond_live_xxxxxxxxxxxxxxxx \\
  --workspace <your-workspace-id>

# Credentials are saved to ~/.conduct/config.json`}</Pre>
        <div className="mt-3 rounded-xl bg-amber-50 border border-amber-200 px-4 py-3 text-sm text-amber-800">
          <strong>Where is my workspace ID?</strong> Open the app, go to Settings, the workspace ID is shown at the top of the page.
        </div>
      </section>

      <section id="cli-commands">
        <SectionHeading id="cli-commands">CLI. Commands</SectionHeading>
        <p className="text-stone-500 text-sm mb-5">Full command reference.</p>

        <div className="rounded-xl border border-stone-200 overflow-hidden mb-8">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-stone-50 border-b border-stone-200">
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-stone-500 uppercase tracking-wider w-72">Command</th>
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-stone-500 uppercase tracking-wider">Description</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-stone-100">
              {[
                ["conduct login",                      "Save connection config to ~/.conduct/config.json"],
                ["conduct switch",                     "List available workspaces (current marked with *)"],
                ["conduct switch <name>",              "Switch active workspace, updates CLI + Guard config, re-syncs policies"],
                ["conduct whoami",                     "Show current workspace, server, Guard status, and Booster status"],
                ["conduct projects",                   "List all projects in the workspace"],
                ["conduct create <name>",              "Create a project"],
                ["conduct delete <name> --yes",        "Delete a project and all its agents"],
                ["conduct reset <name> --yes",         "Remove all agents from a project (clean slate)"],
                ["conduct playbooks",                  "Browse all available playbooks"],
                ["conduct playbooks <slug>",           "Show detail and inputs for one playbook"],
                ["conduct install <slug>",             "Install one agent from a playbook into a project"],
                ["conduct install-all --project <p>", "Install all playbooks into a project"],
                ["conduct agents",                     "List all installed agents in the workspace"],
                ["conduct agents --project <name>",   "Filter agents by project name"],
                ["conduct test <name>",                "Fire test trigger on a named agent, stream live output"],
                ["conduct test <n1> <n2> ...",         "Test multiple named agents in sequence"],
                ["conduct test --all",                 "Test every playbook-based agent in sequence"],
                ["conduct test --all --project <name>","Limit --all to one project"],
                ["conduct test --all --repo owner/repo","Override test repo for all agents"],
              ].map(([cmd, desc]) => (
                <tr key={cmd}>
                  <td className="px-4 py-3 font-mono text-xs text-stone-800 whitespace-nowrap">{cmd}</td>
                  <td className="px-4 py-3 text-stone-500">{desc}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <SubHeading>Quick workflow</SubHeading>
        <Pre>{`# 1. Log in
conduct login --server https://api.conductai.ai --api-key cond_live_xxx --workspace <id>

# 2. Create a project and install all agents
conduct install-all --project DevOps --repo myorg/my-repo

# 3. Test them all
conduct test --all --project DevOps --repo myorg/my-repo`}</Pre>

        <SubHeading>conduct test, all options</SubHeading>
        <Pre>{`conduct test [agent_name ...] [--all] [--project <name>] [--repo owner/repo]

# Fire test trigger on one agent (streams live output)
conduct test "Autopilot Quick"

# Test all playbook-based agents in the workspace
conduct test --all

# Limit --all to one project, against a specific repo
conduct test --all --project DevOps --repo sseshachala/conductai-testbed-node

# Exit code: 0 if all pass, 1 if any fail, safe to use in CI`}</Pre>

        <div className="mt-6 rounded-xl border border-indigo-200 bg-indigo-50 px-5 py-4 flex items-center justify-between gap-4">
          <div>
            <p className="text-sm font-semibold text-indigo-900">Install as a Claude Code plugin</p>
            <p className="text-xs text-indigo-600 mt-0.5">
              Wire conduct-cli and ConductGuard MCP into Claude Code in one command —
              no manual <Code>.mcp.json</Code> edits needed.
            </p>
          </div>
          <a
            href="/tools/conduct-cli"
            className="shrink-0 inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-700 transition-colors"
          >
            Learn more →
          </a>
        </div>
      </section>

      <section id="ci">
        <SectionHeading id="ci">CI / GitHub Actions</SectionHeading>
        <p className="text-stone-500 text-sm mb-4">Run a full smoke test on every push or nightly, install all agents, fire test runs, get a downloadable report.</p>

        <SubHeading>Workflow file</SubHeading>
        <Pre>{`# .github/workflows/smoke_test.yml
name: Nightly Smoke Test
on:
  schedule:
    - cron: '0 6 * * *'
  workflow_dispatch:
    inputs:
      project: { description: 'Conduct project', default: 'DevOps' }
      repo:    { description: 'Target repo (owner/repo)', default: 'myorg/my-repo' }

jobs:
  smoke:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.11' }
      - run: pip install conduct-cli --quiet
      - name: Write conduct config
        run: |
          mkdir -p ~/.conduct
          echo '{\"server\":\"$\{{ secrets.CONDUCT_SERVER }}\",\"workspace_id\":\"$\{{ secrets.CONDUCT_WORKSPACE_ID }}\",\"api_key\":\"$\{{ secrets.CONDUCT_API_KEY }}\"}' > ~/.conduct/config.json
      - run: conduct test --all --project "$\{{ github.event.inputs.project || 'DevOps' }}" --repo "$\{{ github.event.inputs.repo || 'myorg/my-repo' }}"`}</Pre>

        <SubHeading>Required secrets</SubHeading>
        <div className="rounded-xl border border-stone-200 overflow-hidden mb-4">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-stone-50 border-b border-stone-200">
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-stone-500 uppercase tracking-wider">Secret</th>
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-stone-500 uppercase tracking-wider">Value</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-stone-100">
              {[
                ["CONDUCT_SERVER",       "https://api.conductai.ai"],
                ["CONDUCT_WORKSPACE_ID", "Your workspace UUID (Settings page)"],
                ["CONDUCT_API_KEY",      "A cond_live_… key (Settings → API Keys)"],
              ].map(([s, v]) => (
                <tr key={s}>
                  <td className="px-4 py-3 font-mono text-xs text-stone-800">{s}</td>
                  <td className="px-4 py-3 text-stone-500">{v}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section id="cli-mcp">
        <SectionHeading id="cli-mcp">MCP Server</SectionHeading>
        <p className="text-stone-500 text-sm mb-4 leading-relaxed">
          <Code>conduct-mcp</Code> is a zero-dependency MCP server that ships inside <Code>conduct-cli</Code>.
          It exposes your Conduct workspace as tools that Claude Code, Codex, Cursor, Windsurf, and VS Code (Copilot) can call directly —
          no copy-pasting workflow IDs or run commands.
        </p>

        <SubHeading>Installation</SubHeading>
        <p className="text-stone-500 text-sm mb-3">
          The server binary is installed automatically with the CLI. Register it in your AI tools with one command:
        </p>
        <Pre>{`pip install conduct-cli
conduct login --server https://api.conductai.ai --api-key cond_live_xxxx
# ↑ login auto-registers conduct-mcp in Claude Code and Codex

# Or register manually at any time:
conduct mcp install`}</Pre>

        <p className="text-stone-500 text-sm mt-3 mb-4">
          <Code>conduct mcp install</Code> detects which AI tools are present and registers <Code>conduct-mcp</Code>
          in each: it runs <Code>claude mcp add conduct conduct-mcp</Code> for Claude Code and writes the
          <Code>[[mcp_servers]]</Code> block into <Code>~/.codex/config.toml</Code> for Codex.
          Restart your AI tool once to pick up the server.
        </p>

        <SubHeading>Available tools</SubHeading>
        <div className="rounded-xl border border-stone-200 overflow-hidden mb-6">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-stone-50 border-b border-stone-200">
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-stone-500 uppercase tracking-wider w-56">Tool</th>
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-stone-500 uppercase tracking-wider">What it does</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-stone-100">
              {[
                ["conduct_list_agents",    "List all installed agents in your workspace (id, name, status)"],
                ["conduct_list_projects",  "List all projects in your workspace"],
                ["conduct_list_playbooks", "List available playbook templates"],
                ["conduct_run_workflow",   "Trigger a workflow run, provide workflow_id and an optional payload"],
                ["conduct_get_run",        "Fetch the status and result of any run by workflow_id + run_id"],
                ["conduct_guard_status",   "Show active ConductGuard policy: rule count, team info, policy version"],
              ].map(([tool, desc]) => (
                <tr key={tool}>
                  <td className="px-4 py-3 font-mono text-xs text-stone-800">{tool}</td>
                  <td className="px-4 py-3 text-xs text-stone-500">{desc}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <SubHeading>Example usage in Claude Code</SubHeading>
        <Pre>{`# After conduct mcp install + restart, ask Claude:
"List my Conduct agents"
"Run the autopilot workflow on myorg/my-repo"
"What's the status of run abc-123 in workflow xyz-456?"`}</Pre>

        <SubHeading>Tool coverage by AI client</SubHeading>
        <div className="rounded-xl border border-stone-200 overflow-hidden mb-4">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-stone-50 border-b border-stone-200">
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-stone-500 uppercase tracking-wider">Tool</th>
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-stone-500 uppercase tracking-wider">Registered by</th>
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-stone-500 uppercase tracking-wider">Config written</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-stone-100">
              {[
                ["Claude Code",      "conduct login  /  conduct mcp install", "~/.claude/settings.json"],
                ["Codex CLI",        "conduct login  /  conduct mcp install", "~/.codex/config.toml"],
                ["Cursor",           "conduct login  /  conduct mcp install", "~/.cursor/mcp.json"],
                ["Windsurf",         "conduct login  /  conduct mcp install", "~/.codeium/windsurf/mcp_config.json"],
                ["VS Code (Copilot)","conduct login  /  conduct mcp install", "VS Code settings.json → mcp.servers"],
              ].map(([tool, how, cfg]) => (
                <tr key={tool}>
                  <td className="px-4 py-3 text-xs font-medium text-stone-800">{tool}</td>
                  <td className="px-4 py-3 font-mono text-xs text-stone-500">{how}</td>
                  <td className="px-4 py-3 font-mono text-xs text-stone-500">{cfg}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}

function TabApi() {
  return (
    <div className="space-y-16">
      <section id="api-auth">
        <SectionHeading id="api-auth">API. Authentication</SectionHeading>
        <p className="text-stone-600 text-sm mb-4">All API requests require two headers.</p>
        <div className="rounded-xl border border-stone-200 overflow-hidden mb-5">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-stone-50 border-b border-stone-200">
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-stone-500 uppercase tracking-wider">Header</th>
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-stone-500 uppercase tracking-wider">Value</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-stone-100">
              <tr>
                <td className="px-4 py-3 font-mono text-xs text-stone-800">X-Api-Key</td>
                <td className="px-4 py-3 text-stone-500">Your <Code>cond_live_</Code> API key (from Settings → API Keys)</td>
              </tr>
              <tr>
                <td className="px-4 py-3 font-mono text-xs text-stone-800">X-Workspace-Id</td>
                <td className="px-4 py-3 text-stone-500">Your workspace UUID</td>
              </tr>
            </tbody>
          </table>
        </div>
        <Pre>{`curl https://api.conductai.ai/workflows \\
  -H "X-Api-Key: cond_live_xxxxxxxxxxxxxxxx" \\
  -H "X-Workspace-Id: <workspace-id>"`}</Pre>
      </section>

      <section id="api-workflows">
        <SectionHeading id="api-workflows">API. Workflows</SectionHeading>
        <p className="text-stone-500 text-sm mb-5">Manage and trigger agents.</p>

        <Endpoint method="GET" path="/workflows" desc="List all workflows in the workspace.">
          <Pre>{`[
  {
    "id": "53ab8977-...",
    "name": "Autopilot Quick",
    "status": "active",
    "playbook_slug": "autopilot-quick",
    "project_id": "a1b2c3d4-..."
  }
]`}</Pre>
        </Endpoint>

        <Endpoint method="GET" path="/workflows/{id}" desc="Get a workflow including its graph and current version." />

        <Endpoint method="POST" path="/workflows/{id}/trigger" desc="Fire a test trigger using the playbook's built-in test payload. Returns run_id immediately.">
          <Pre>{`curl -X POST https://api.conductai.ai/workflows/53ab8977-.../trigger \\
  -H "X-Api-Key: cond_live_xxx" \\
  -H "X-Workspace-Id: <workspace-id>" \\
  -d '{}'

# Response
{ "ok": true, "run_id": "b858c434-...", "max_turns": 20 }`}</Pre>
        </Endpoint>
      </section>

      <section id="api-runs">
        <SectionHeading id="api-runs">API. Runs</SectionHeading>
        <p className="text-stone-500 text-sm mb-5">Inspect and stream run results.</p>

        <Endpoint method="GET" path="/workflows/{id}/runs" desc="List all runs for a workflow." />

        <Endpoint method="GET" path="/workflows/{id}/runs/{run_id}" desc="Get a run including status, state, and metadata.">
          <Pre>{`{
  "id": "b858c434-...",
  "status": "succeeded",
  "triggered_by": "manual:test_trigger",
  "started_at": "2026-05-26T12:00:00Z",
  "completed_at": "2026-05-26T12:03:21Z"
}`}</Pre>
        </Endpoint>

        <Endpoint method="GET" path="/workflows/{id}/runs/{run_id}/stream" desc="Server-Sent Events stream of live run events. Closes with [DONE].">
          <Pre>{`const es = new EventSource(
  \`https://api.conductai.ai/workflows/\${id}/runs/\${runId}/stream\` +
  \`?token=\${clerkToken}&workspace_id=\${workspaceId}\`
)
es.onmessage = (e) => {
  if (e.data === "[DONE]") { es.close(); return }
  const event = JSON.parse(e.data)
  console.log(event.kind, event.block_id, event.payload)
}`}</Pre>
          <div className="mt-3 rounded-lg bg-stone-50 border border-stone-200 p-3">
            <p className="text-xs font-semibold text-stone-500 uppercase tracking-wider mb-2">Event kinds</p>
            <div className="flex flex-wrap gap-1.5">
              {["block_started","block_completed","block_failed","block_skipped","brain_tool_call","run_completed","run_failed","run_paused"].map(k => (
                <Code key={k}>{k}</Code>
              ))}
            </div>
          </div>
        </Endpoint>

        <Endpoint method="POST" path="/workflows/{id}/runs/{run_id}/approve" desc="Approve or reject a paused run (human-in-the-loop).">
          <Pre>{`-d '{"decision": "approved", "approver": "alice"}'`}</Pre>
        </Endpoint>

        <Endpoint method="POST" path="/workflows/{id}/runs/{run_id}/cancel" desc="Cancel a running or pending run." />
      </section>

      <section id="api-keys">
        <SectionHeading id="api-keys">API. API Keys</SectionHeading>
        <p className="text-stone-500 text-sm mb-5">Manage programmatic access keys for your workspace.</p>

        <Endpoint method="POST" path="/workspaces/{id}/api-keys" desc="Generate a new API key. The plaintext key is returned once, store it immediately.">
          <Pre>{`curl -X POST https://api.conductai.ai/workspaces/<id>/api-keys \\
  -H "Authorization: Bearer <clerk-token>" \\
  -H "X-Workspace-Id: <id>" \\
  -d '{"name": "CI pipeline"}'

# Response
{
  "id": "...",
  "name": "CI pipeline",
  "key": "cond_live_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
  "key_prefix": "cond_live_xxxx",
  "created_at": "2026-05-26T12:00:00Z"
}`}</Pre>
        </Endpoint>
        <Endpoint method="GET"    path="/workspaces/{id}/api-keys"         desc="List all API keys (prefix and metadata only, plaintext is never returned again)." />
        <Endpoint method="DELETE" path="/workspaces/{id}/api-keys/{key_id}" desc="Revoke an API key immediately." />
      </section>
    </div>
  )
}

function TabBlocks() {
  return (
    <div className="space-y-16">
      <section id="memory-block">
        <SectionHeading id="memory-block">Memory block</SectionHeading>
        <p className="text-stone-500 text-sm mb-6 leading-relaxed">
          The Memory block gives agents a persistent knowledge store. A <strong>read</strong> block
          retrieves past summaries before a run; a <strong>write</strong> block records what was done after.
          On the next run the agent has full context of what it did before on that repo.
        </p>

        <SubHeading>Recommended block order</SubHeading>
        <div className="rounded-xl border border-stone-200 overflow-hidden mb-6">
          {[
            { block: "Trigger",          note: "Issue labeled, PR opened, cron, etc." },
            { block: "Memory (read)",    note: "Retrieves past summaries, available as {{recall.entries}} in the brain", amber: true },
            { block: "Fetch Issue",      note: "Gets fresh data from GitHub, Linear, etc." },
            { block: "Brain",            note: "Receives both the current task and recalled context" },
            { block: "Memory (write)",   note: "Records what was done, used by future runs", amber: true },
            { block: "Notify",           note: "Posts the outcome to Slack / email" },
          ].map(({ block, note, amber }) => (
            <div key={block} className={`flex items-start gap-4 px-4 py-2.5 border-b border-stone-100 last:border-0 ${amber ? "bg-amber-50" : ""}`}>
              <span className={`text-xs font-semibold w-44 shrink-0 mt-0.5 ${amber ? "text-amber-700" : "text-stone-700"}`}>{block}</span>
              <span className="text-xs text-stone-500">{note}</span>
            </div>
          ))}
        </div>

        <SubHeading>Configuration fields</SubHeading>
        <div className="rounded-xl border border-stone-200 overflow-hidden mb-6">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-stone-50 border-b border-stone-200">
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-stone-500 uppercase tracking-wider w-32">Field</th>
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-stone-500 uppercase tracking-wider w-28">Values</th>
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-stone-500 uppercase tracking-wider">Description</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-stone-100 text-sm">
              {[
                ["action",  "read | write",       "read retrieves past summaries before the brain runs. write stores the outcome after the run completes."],
                ["scope",   "repo | workspace",   "repo isolates memories per repository. workspace shares memories across all repos in the workspace for this playbook."],
                ["key",     "auto-set",            "Groups memories together. Auto-populated from scope. Read-only in the UI."],
                ["limit",   "number (default 5)", "read only. Maximum past summaries to retrieve. Returns the most semantically similar entries first."],
                ["summary", "template string",    "write only. What to store. Supports {{block_id.field}} refs. Example: Fixed {{fetch_issue.title}} via {{brain.approach}}"],
              ].map(([field, values, desc]) => (
                <tr key={field}>
                  <td className="px-4 py-3 font-mono text-xs text-stone-800 align-top">{field}</td>
                  <td className="px-4 py-3 text-xs text-stone-500 align-top whitespace-nowrap">{values}</td>
                  <td className="px-4 py-3 text-xs text-stone-500 leading-relaxed">{desc}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <SubHeading>YAML reference</SubHeading>
        <Pre>{`blocks:
  recall_context:
    type: memory
    action: read
    scope: repo
    key: "{{_trigger.repo_full_name}}"
    limit: 5
    next: fetch_issue

  record_outcome:
    type: memory
    action: write
    scope: repo
    key: "{{_trigger.repo_full_name}}"
    summary: |
      Issue #{{fetch_issue.issue_number}}: {{fetch_issue.title}}
      Fix: {{implement_fix.approach}}
    next: notify`}</Pre>

        <div className="mt-4 rounded-xl bg-stone-100 border border-stone-200 px-4 py-3 text-sm text-stone-700">
          <strong>No OpenAI key?</strong> Memory falls back to recency-based retrieval, the 5 most recent summaries
          instead of the most semantically similar. You lose similarity search but not the feature.
        </div>
      </section>

    </div>
  )
}

function TabGuard() {
  return (
    <div className="space-y-16">
      <section id="guard">
        <SectionHeading id="guard">ConductGuard. Overview</SectionHeading>
        <div className="rounded-lg border-l-4 border-indigo-500 bg-indigo-50 px-4 py-3 mb-6">
          <p className="text-sm font-semibold text-indigo-900 leading-snug">
            GitHub gives the CISO a setting. ConductGuard gives them enforcement.
          </p>
          <p className="text-xs text-indigo-700 mt-1 leading-relaxed">
            Most AI tool governance is a toggle the user can flip off. Guard is a proxy — one env var routes every LLM call through it regardless of framework, language, or developer discipline. Actions Guard denies are not unlikely. They are structurally impossible.
          </p>
        </div>
        <p className="text-stone-500 text-sm mb-6 leading-relaxed">
          ConductGuard is the team policy layer for AI tools. It has two enforcement surfaces:
        </p>
        <div className="rounded-xl border border-stone-200 divide-y divide-stone-100 text-sm mb-8">
          {[
            { label: "Workflow enforcement (Agent guard)", detail: "Automatic policy check before every agentic AI step. No YAML block needed, the executor hook evaluates active policies against the run state and halts, warns, or audits based on the workspace enforcement mode." },
            { label: "Local enforcement (hook + MCP)",     detail: "Intercepts AI tool calls in Claude Code, Cursor, and other editors before they reach the model. Checks hard caps, evaluates policies, and blocks or warns at call time. No workflow required." },
          ].map(({ label, detail }) => (
            <div key={label} className="px-4 py-3">
              <p className="font-medium text-stone-800 mb-0.5">{label}</p>
              <p className="text-stone-500 text-xs leading-relaxed">{detail}</p>
            </div>
          ))}
        </div>

        <SubHeading>Policy anatomy</SubHeading>
        <div className="rounded-xl border border-stone-200 overflow-hidden mb-6">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-stone-50 border-b border-stone-200">
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-stone-500 uppercase tracking-wider w-40">Field</th>
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-stone-500 uppercase tracking-wider">Description</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-stone-100 text-sm">
              {[
                ["match_tool",         "Which AI tool triggers this rule (e.g. claude-code, cursor, * for any)."],
                ["match_pattern",      "Regex matched against the serialized tool call input. Trigger if matched."],
                ["match_path_pattern", "Regex matched against file paths in the tool call. Trigger if matched."],
                ["enforcement_mode",   "block | warn | audit, what happens when the rule triggers."],
                ["alert_message",      "Message sent to Slack when the rule triggers (if Slack is configured)."],
              ].map(([field, desc]) => (
                <tr key={field}>
                  <td className="px-4 py-3 font-mono text-xs text-stone-800 align-top">{field}</td>
                  <td className="px-4 py-3 text-xs text-stone-500 leading-relaxed">{desc}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section id="guard-agent">
        <SectionHeading id="guard-agent">Agent guard</SectionHeading>
        <p className="text-stone-500 text-sm mb-4 leading-relaxed">
          Agent guard is an automatic policy check that runs before every <Code>mode: agentic</Code> brain block in a
          workflow. No YAML block needed, it fires as an executor hook and records results in the run trace.
        </p>

        <SubHeading>Enforcement modes</SubHeading>
        <div className="rounded-xl border border-stone-200 overflow-hidden mb-6">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-stone-50 border-b border-stone-200">
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-stone-500 uppercase tracking-wider w-28">Mode</th>
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-stone-500 uppercase tracking-wider">Behaviour</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-stone-100 text-sm">
              {[
                ["block", "Run halts immediately, the AI step never executes. Use for hard policy lines (e.g. no access to prod repos)."],
                ["warn",  "Policy match is flagged in the run trace and the Steps tab, but the run continues. Default for new workspaces."],
                ["audit", "Match is recorded silently in Guard activity. No interruption visible to the developer or the run."],
              ].map(([mode, desc]) => (
                <tr key={mode}>
                  <td className="px-4 py-3 font-mono text-xs text-stone-800 align-top">{mode}</td>
                  <td className="px-4 py-3 text-xs text-stone-500 leading-relaxed">{desc}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <SubHeading>Disabling per run</SubHeading>
        <p className="text-stone-500 text-sm mb-3">
          The run trigger modal has a <strong>Guard</strong> toggle (on by default). Flip it off before firing a run to
          skip the auto-hook for that run only, useful for local dev and debugging. The toggle sends{" "}
          <Code>guard_enabled: false</Code> in the run payload.
        </p>

        <SubHeading>Where to configure</SubHeading>
        <p className="text-stone-500 text-sm mb-2">
          Workspace-level enforcement mode lives in <strong>Guard → Settings → Agent guard</strong>. The selected mode
          applies to all runs in the workspace unless overridden per-run.
        </p>
        <p className="text-stone-500 text-sm">
          Guard must be installed (Guard config present) for the hook to evaluate policies. If Guard is not installed the
          hook skips silently, no runs are blocked.
        </p>
      </section>

      <section id="guard-user-flow">
        <SectionHeading id="guard-user-flow">Developer setup</SectionHeading>
        <p className="text-stone-500 text-sm mb-4 leading-relaxed">
          Guard is provisioned automatically at login, no separate install step. One command wires up the hook,
          registers the MCP server, and downloads active policies.
        </p>

        <Pre>{`# 1. Install the CLI (once)
pip install conduct-cli

# 2. Generate an API key. Settings → API Keys (admin or developer role)
# 3. Login. Guard sets itself up automatically
conduct login --server https://api.conductai.ai --api-key cond_live_xxxx

# That's it. Guard is now active. Verify:
conduct guard status`}</Pre>

        <p className="text-stone-500 text-sm mt-4 mb-3">
          Login auto-provisions Guard by calling <Code>GET /guard/config/installed</Code>, downloading the workspace
          policy file to <Code>~/.conductguard/policy.json</Code>, writing the hook script to{" "}
          <Code>~/.conductguard/hook.py</Code>, and registering it in every AI tool config found on the machine.
        </p>

        <SubHeading>Guard CLI commands</SubHeading>
        <div className="rounded-xl border border-stone-200 overflow-hidden mb-6">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-stone-50 border-b border-stone-200">
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-stone-500 uppercase tracking-wider w-56">Command</th>
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-stone-500 uppercase tracking-wider">Description</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-stone-100">
              {[
                ["conduct guard status", "Show policy count, today's spend, violations, and active developer info"],
                ["conduct guard sync",   "Pull latest policies from the server and refresh the hook script in all tools"],
                ["conduct guard audit",  "Show recent activity log (last 24 h by default, --since 7d for a week)"],
              ].map(([cmd, desc]) => (
                <tr key={cmd}>
                  <td className="px-4 py-3 font-mono text-xs text-stone-800">{cmd}</td>
                  <td className="px-4 py-3 text-xs text-stone-500">{desc}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <SubHeading>Auto-update</SubHeading>
        <p className="text-stone-500 text-sm mb-3">
          The CLI checks PyPI for a newer version on every command (cached 24 h). If one is found it upgrades
          itself and re-runs the original command, developers never need to manually update.
          Set <Code>CONDUCT_NO_AUTOUPDATE=1</Code> to disable (useful in CI).
        </p>
      </section>

      <section id="guard-sync">
        <SectionHeading id="guard-sync">Sync &amp; re-sync</SectionHeading>
        <p className="text-stone-500 text-sm mb-4 leading-relaxed">
          Each developer machine caches a local copy of the workspace policy file at{" "}
          <Code>~/.conductguard/policy.json</Code>. The Guard hook checks the server version on every tool call,
          throttled to one network request per 60 seconds. If the version has changed, the hook silently
          re-downloads the policy before evaluating the current call, no manual action needed.
        </p>

        <SubHeading>When a re-sync is triggered</SubHeading>
        <div className="rounded-xl border border-stone-200 divide-y divide-stone-100 text-sm mb-6">
          {[
            ["Policy created / edited / deleted", "Server version timestamp updates. Each machine re-syncs on the next tool call after its 60s window expires."],
            ["Re-sync button (Guard → Settings)",  "Bumps resync_requested_at on the workspace. Machines pick it up on the next tool call after the 60s cache window."],
            ["conduct guard sync (CLI)",           "Forces an immediate pull regardless of cached version. Useful after a network gap, machine restore, or when you need instant propagation."],
          ].map(([trigger, detail]) => (
            <div key={trigger} className="px-4 py-3">
              <p className="font-medium text-stone-800 text-xs mb-0.5">{trigger}</p>
              <p className="text-stone-500 text-xs leading-relaxed">{detail}</p>
            </div>
          ))}
        </div>

        <SubHeading>Sync status card</SubHeading>
        <p className="text-stone-500 text-sm mb-2">
          <strong>Guard → Settings</strong> shows a live <em>Sync status</em> card: <Code>synced / total</Code> machines
          in green when all developers are up to date, amber when any machine hasn{"'"}t pulled the latest version yet.
          The count comes from the <Code>/guard/developer-tools</Code> endpoint which tracks per-developer tool
          coverage snapshots pushed at login and by <Code>conduct guard sync</Code>.
        </p>
      </section>

      <section id="guard-hook">
        <SectionHeading id="guard-hook">Hook & tool coverage</SectionHeading>
        <p className="text-stone-500 text-sm mb-4 leading-relaxed">
          Guard uses two enforcement surfaces depending on the AI tool. Both are registered automatically at login.
        </p>

        <SubHeading>Coverage by tool</SubHeading>
        <div className="rounded-xl border border-stone-200 overflow-hidden mb-6">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-stone-50 border-b border-stone-200">
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-stone-500 uppercase tracking-wider">Tool</th>
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-stone-500 uppercase tracking-wider">Mechanism</th>
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-stone-500 uppercase tracking-wider">Enforcement</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-stone-100">
              {[
                ["Claude Code", "PreToolUse · PreCompact · SessionStart hooks (~/.claude/settings.json)", "Hard block, every tool call intercepted; session state preserved across compaction"],
                ["Codex CLI",   "PreToolUse hook (~/.codex/hooks.json)",     "Hard block, same script, same exit-code-2 protocol"],
                ["Cursor",      "MCP server (conductguard-mcp)",             "Advisory. AI sees Guard tools, can self-enforce"],
                ["Windsurf",    "MCP server (conductguard-mcp)",             "Advisory. AI sees Guard tools, can self-enforce"],
              ].map(([tool, mech, enf]) => (
                <tr key={tool}>
                  <td className="px-4 py-3 text-xs font-medium text-stone-800">{tool}</td>
                  <td className="px-4 py-3 font-mono text-xs text-stone-500">{mech}</td>
                  <td className="px-4 py-3 text-xs text-stone-500">{enf}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <SubHeading>What the hook does on every call</SubHeading>
        <div className="rounded-xl border border-stone-200 divide-y divide-stone-100 text-sm mb-6">
          {[
            ["1. Budget check (cached 5 min)", "Calls GET /guard/spend/budget-check. If the hard cap is hit, exits with code 2, the tool treats this as a block."],
            ["2. Policy evaluation",           "Loads ~/.conductguard/policy.json. Evaluates match_tool, match_pattern, and match_path_pattern. block exits 2, warn prints a message, audit falls through."],
            ["3. Event posted (async)",        "Every tool call, allowed or blocked, is posted to /guard/events. This powers the Activity log and Active developers metrics."],
            ["4. Slack alert",                 "If a block or warn rule has an alert configured, the Guard API notifies the workspace's Slack channel."],
          ].map(([step, desc]) => (
            <div key={step} className="flex gap-4 px-4 py-3">
              <span className="font-medium text-stone-700 w-52 shrink-0 text-xs">{step}</span>
              <span className="text-stone-500 text-xs leading-relaxed">{desc}</span>
            </div>
          ))}
        </div>

        <SubHeading>Session persistence across compaction</SubHeading>
        <p className="text-stone-500 text-sm mb-4 leading-relaxed">
          When Claude Code compacts a long conversation, guard state (budget position, recent blocks, active workspace) would otherwise be lost. ConductGuard wires two additional hooks to preserve context across compaction events.
        </p>
        <div className="rounded-xl border border-stone-200 divide-y divide-stone-100 text-sm mb-6">
          {[
            ["PreCompact hook", "Fires before compaction. Writes a priority-tiered snapshot to .booster/session_snapshot.json. Tier 1: git branch + last 3 commits, memory index headline; Tier 2: guard budget state (via conductguard status --json); Tier 3: cwd metadata. Write is atomic (tmp → rename) and never blocks Claude Code on failure."],
            ["SessionStart hook", "Fires when a new session opens. Reads the snapshot if it exists and is under 2 hours old, then injects a ≤5-line context reminder into Claude's view: branch, last commit, guard budget %, and memory index headline. Skips silently if snapshot is stale or missing."],
            ["Snapshot location", ".booster/session_snapshot.json in the project root. Three priority tiers ensure critical state is always preserved, lower-priority metadata is dropped if space is tight."],
          ].map(([step, desc]) => (
            <div key={step} className="flex gap-4 px-4 py-3">
              <span className="font-medium text-stone-700 w-44 shrink-0 text-xs">{step}</span>
              <span className="text-stone-500 text-xs leading-relaxed">{desc}</span>
            </div>
          ))}
        </div>

        <SubHeading>Covered tools, confirmed in the wild</SubHeading>
        <p className="text-stone-500 text-sm mb-5 leading-relaxed">
          ConductGuard has been tested and confirmed working on the following tools. Hard block means every tool call. Bash, Read, Edit, Write, is intercepted before execution and stopped cold at the PreToolUse hook.
        </p>
        <div className="grid grid-cols-1 gap-4 mb-6 sm:grid-cols-2">

          <div className="rounded-xl border border-stone-200 overflow-hidden">
            <div className="px-4 py-3 flex items-center justify-between border-b border-stone-100 bg-stone-50">
              <span className="font-semibold text-stone-800 text-sm">Claude Code</span>
              <span className="text-xs font-semibold text-emerald-700 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded-full">✓ Live</span>
            </div>
            <div className="px-4 py-3 text-xs text-stone-500 space-y-1 border-b border-stone-100">
              <div><span className="font-medium text-stone-700">Hook:</span> PreToolUse · PostToolUse · Stop</div>
              <div><span className="font-medium text-stone-700">Enforcement:</span> Hard block, exit code 2</div>
              <div><span className="font-medium text-stone-700">Config:</span> <code className="font-mono bg-stone-100 px-1 rounded">~/.claude/settings.json</code></div>
            </div>
            <div className="p-3 bg-stone-950 space-y-1 font-mono text-xs">
              <p className="text-stone-500"># Claude Code, budget hard cap hit</p>
              <p className="text-amber-400">• PreToolUse hook (blocked)</p>
              <p className="text-stone-300 pl-2">feedback: [ConductGuard] Your team&apos;s monthly</p>
              <p className="text-stone-300 pl-2">AI budget of $650.00 has been reached.</p>
              <p className="text-stone-300 pl-2">New tool calls are paused until the limit</p>
              <p className="text-stone-300 pl-2">is raised. Contact your security team.</p>
              <p className="text-stone-500 mt-2"># Every tool call blocked until cap raised</p>
              <p className="text-amber-400">• PreToolUse hook (blocked)</p>
              <p className="text-amber-400">• PreToolUse hook (blocked)</p>
              <p className="text-amber-400">• PreToolUse hook (blocked)</p>
            </div>
          </div>

          <div className="rounded-xl border border-stone-200 overflow-hidden">
            <div className="px-4 py-3 flex items-center justify-between border-b border-stone-100 bg-stone-50">
              <span className="font-semibold text-stone-800 text-sm">Codex CLI</span>
              <span className="text-xs font-semibold text-emerald-700 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded-full">✓ Live</span>
            </div>
            <div className="px-4 py-3 text-xs text-stone-500 space-y-1 border-b border-stone-100">
              <div><span className="font-medium text-stone-700">Hook:</span> PreToolUse</div>
              <div><span className="font-medium text-stone-700">Enforcement:</span> Hard block, exit code 2</div>
              <div><span className="font-medium text-stone-700">Config:</span> <code className="font-mono bg-stone-100 px-1 rounded">~/.codex/hooks.json</code></div>
            </div>
            <div className="p-3 bg-stone-950 space-y-1 font-mono text-xs">
              <p className="text-stone-500"># Codex CLI, same hook, same block</p>
              <p className="text-amber-400">• PreToolUse hook (blocked)</p>
              <p className="text-stone-300 pl-2">feedback: [ConductGuard] Your team&apos;s monthly</p>
              <p className="text-stone-300 pl-2">AI budget of $650.00 has been reached.</p>
              <p className="text-stone-300 pl-2">New tool calls are paused until the limit</p>
              <p className="text-stone-300 pl-2">is raised. Contact your security team.</p>
              <p className="text-stone-400 mt-2 italic"># Codex stopped cold, same script,</p>
              <p className="text-stone-400 italic"># same exit-code-2 protocol as Claude Code</p>
            </div>
          </div>

          <div className="rounded-xl border border-stone-200 overflow-hidden opacity-60">
            <div className="px-4 py-3 flex items-center justify-between border-b border-stone-100 bg-stone-50">
              <span className="font-semibold text-stone-800 text-sm">Cursor</span>
              <span className="text-xs font-semibold text-stone-500 bg-stone-100 border border-stone-200 px-2 py-0.5 rounded-full">Coming soon</span>
            </div>
            <div className="px-4 py-3 text-xs text-stone-400 space-y-1">
              <div><span className="font-medium text-stone-500">Hook:</span> MCP server (advisory)</div>
              <div><span className="font-medium text-stone-500">Enforcement:</span> Advisory. AI self-enforces via Guard MCP tools</div>
              <div><span className="font-medium text-stone-500">Hard block:</span> In development</div>
            </div>
          </div>

          <div className="rounded-xl border border-stone-200 overflow-hidden opacity-60">
            <div className="px-4 py-3 flex items-center justify-between border-b border-stone-100 bg-stone-50">
              <span className="font-semibold text-stone-800 text-sm">Windsurf</span>
              <span className="text-xs font-semibold text-stone-500 bg-stone-100 border border-stone-200 px-2 py-0.5 rounded-full">Coming soon</span>
            </div>
            <div className="px-4 py-3 text-xs text-stone-400 space-y-1">
              <div><span className="font-medium text-stone-500">Hook:</span> MCP server (advisory)</div>
              <div><span className="font-medium text-stone-500">Enforcement:</span> Advisory. AI self-enforces via Guard MCP tools</div>
              <div><span className="font-medium text-stone-500">Hard block:</span> In development</div>
            </div>
          </div>

        </div>

        <div className="rounded-xl bg-stone-100 border border-stone-200 px-4 py-3 text-sm text-stone-700">
          <strong>Exit codes:</strong> 0 = pass (tool runs), 2 = block (tool aborted).
          The tool surfaces the rule message to the developer so they know why the call was blocked.
        </div>
      </section>

      <section id="guard-mcp">
        <SectionHeading id="guard-mcp">conductguard-mcp</SectionHeading>
        <p className="text-stone-500 text-sm mb-4 leading-relaxed">
          An MCP server that gives Cursor, Windsurf, and any MCP-compatible editor direct access to Guard.
          Registered automatically at login. The AI can query its own policies before taking sensitive actions.
        </p>

        <SubHeading>Auto-registered config (written by conduct login)</SubHeading>
        <Pre>{`# Written to ~/.cursor/mcp.json, ~/.windsurf/mcp.json, ~/.codex/mcp.json
# and ~/.claude/settings.json, whichever exist on the machine.
{
  "mcpServers": {
    "conductguard": {
      "command": "conductguard-mcp",
      "args": ["--workspace", "<workspace-id>", "--token", "<member-token>", "--api-url", "https://api.conductai.ai"]
    }
  }
}`}</Pre>

        <SubHeading>Tools exposed</SubHeading>
        <div className="rounded-xl border border-stone-200 divide-y divide-stone-100 text-sm mb-6">
          {[
            { tool: "guard_status", desc: "Returns workspace ID, policy count, policy version, and developer email. Useful for confirming Guard is active.", args: "None" },
            { tool: "guard_check",  desc: "Evaluates a tool call against active policies. Returns ALLOWED, BLOCKED, or WARNING with the matching rule.", args: "tool_name (str), tool_input (object), pack (str, optional), prompt (str, optional)" },
            { tool: "guard_sync",   desc: "Pulls the latest policies from the server and writes them to ~/.conductguard/policy.json.", args: "None" },
          ].map(({ tool, desc, args }) => (
            <div key={tool} className="px-4 py-3">
              <div className="flex items-center gap-2 mb-1">
                <code className="font-mono text-xs font-semibold text-stone-800 bg-stone-100 px-1.5 py-0.5 rounded">{tool}</code>
                <span className="text-[10px] text-stone-400">args: {args}</span>
              </div>
              <p className="text-xs text-stone-500 leading-relaxed">{desc}</p>
            </div>
          ))}
        </div>
        <p className="text-stone-500 text-sm">JSON-RPC 2.0 over stdio. Protocol version <Code>2024-11-05</Code>.</p>

        <SubHeading>guard_check parameters</SubHeading>
        <div className="rounded-xl border border-stone-200 divide-y divide-stone-100 text-sm mb-4">
          {[
            ["tool_name", "required", "Name of the tool being called (e.g. bash, Write, WebFetch)."],
            ["tool_input", "required", "Input arguments as an object. Serialised and matched against active rules."],
            ["pack",       "optional", "Scope evaluation to a specific compliance pack (e.g. conduct-owasp, conduct-soc2). Omit to use workspace default policy."],
            ["prompt",     "optional", "User prompt context. Prepended to the audit log entry — helps trace which instruction triggered the action."],
          ].map(([param, req, desc]) => (
            <div key={param} className="flex gap-4 px-4 py-3 items-start">
              <code className="font-mono text-xs font-semibold text-stone-800 bg-stone-100 px-1.5 py-0.5 rounded w-24 shrink-0">{param}</code>
              <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded shrink-0 mt-0.5 ${req === "required" ? "bg-rose-50 text-rose-600" : "bg-stone-100 text-stone-500"}`}>{req}</span>
              <span className="text-xs text-stone-500 leading-relaxed">{desc}</span>
            </div>
          ))}
        </div>
      </section>

      <section id="guard-tokens">
        <SectionHeading id="guard-tokens">Agent tokens</SectionHeading>
        <p className="text-stone-500 text-sm mb-5 leading-relaxed">
          Guard issues two token types. Both work with the proxy and MCP endpoint and write to the same audit trail.
        </p>
        <div className="rounded-xl border border-stone-200 divide-y divide-stone-100 text-sm mb-5">
          {[
            ["cond_agt_*", "Session token",  "8 hours",    "conduct login",        "Interactive tools — Claude Code, Cursor, Windsurf, Codex CLI."],
            ["cond_api_*", "API token",      "Long-lived", "Agent Identity page",  "CI/CD, server agents, integrations. Revocable from the dashboard."],
          ].map(([prefix, label, ttl, source, use]) => (
            <div key={prefix} className="px-4 py-4">
              <div className="flex items-center gap-2 mb-2">
                <code className="font-mono text-xs font-semibold text-stone-800 bg-stone-100 px-1.5 py-0.5 rounded">{prefix}</code>
                <span className="text-[10px] font-semibold text-stone-500 bg-stone-50 border border-stone-200 px-1.5 py-0.5 rounded">{label}</span>
                <span className="text-[10px] text-stone-400">expires: {ttl}</span>
              </div>
              <p className="text-xs text-stone-500 leading-relaxed"><span className="text-stone-700 font-medium">Issued by:</span> {source} &nbsp;·&nbsp; <span className="text-stone-700 font-medium">Use for:</span> {use}</p>
            </div>
          ))}
        </div>

        <SubHeading>RFC 8693 token exchange</SubHeading>
        <Pre>{`POST /token
Content-Type: application/x-www-form-urlencoded

grant_type=urn:ietf:params:oauth:grant-type:token-exchange
&subject_token=<clerk_jwt>
&subject_token_type=urn:ietf:params:oauth:token-type:jwt
&resource=<workspace_id>

# Response
{
  "access_token": "cond_agt_...",
  "token_type": "Bearer",
  "expires_in": 28800,
  "refresh_token": "cond_ref_...",
  "workspace_id": "<uuid>"
}`}</Pre>
        <p className="text-stone-500 text-xs mt-3">conduct login calls this endpoint automatically after browser auth. Use it directly from any RFC 8693-compatible OAuth client.</p>
      </section>

      <section id="guard-spend">
        <SectionHeading id="guard-spend">Spend controls</SectionHeading>
        <p className="text-stone-500 text-sm mb-6 leading-relaxed">
          Guard tracks AI spend per developer. Admins set budgets in Guard → Spend.
          When a developer hits their hard cap, the hook blocks their next tool call.
        </p>

        <SubHeading>Budget hierarchy</SubHeading>
        <div className="rounded-xl border border-stone-200 divide-y divide-stone-100 text-sm mb-6">
          {[
            ["Workspace hard limit", "Monthly cap for the entire workspace. When the total hits this limit, all developers are blocked."],
            ["Per-developer limit",  "Monthly cap per developer. Set in Guard → Spend → Budgets."],
            ["Alert threshold",      "Optional, percentage of budget at which Slack alerts fire (e.g. 80%). Developers continue past the threshold; the hard limit is the actual block."],
          ].map(([label, desc]) => (
            <div key={label} className="flex gap-4 px-4 py-3">
              <span className="font-medium text-stone-700 w-44 shrink-0 text-xs">{label}</span>
              <span className="text-stone-500 text-xs leading-relaxed">{desc}</span>
            </div>
          ))}
        </div>

        <SubHeading>Budget check API</SubHeading>
        <Pre>{`GET /guard/spend/budget-check?workspace_id=<uuid>

# Response
{ "hard_blocked": false, "monthly_cost_usd": 12.40, "hard_limit_usd": 50.00 }

# When blocked:
{ "hard_blocked": true, "reason": "Monthly budget of $50.00 exceeded ($51.20 used)", ... }`}</Pre>

        <div className="mt-3 rounded-xl bg-stone-100 border border-stone-200 px-4 py-3 text-sm text-stone-700">
          The hook caches the response at <Code>~/.conductguard/budget_cache.json</Code> for 5 minutes.
          Delete it to force an immediate re-check.
        </div>
      </section>

      <section id="guard-savings">
        <SectionHeading id="guard-savings">Maximize savings</SectionHeading>
        <p className="text-stone-500 text-sm mb-6 leading-relaxed">
          Guard tracks AI spend, but the real leverage is reducing how many tokens your team burns in the first place.
          Two tools stack on top of each other to compress token usage before it hits the model.
          Guard captures the combined savings and shows them on the Spend dashboard.
        </p>

        {/* Real numbers comparison */}
        <div className="rounded-xl border-2 border-stone-200 overflow-hidden mb-3">
          <div className="grid grid-cols-3 divide-x divide-stone-200">
            {[
              {
                state: "No optimisation",
                bg: "bg-white",
                tokens: "34.8M",
                tokenLabel: "tokens consumed (command output)",
                saved: "$0",
                savedLabel: "saved",
                savedColor: "text-stone-300",
                rate: "—",
                rateLabel: "savings rate",
                detail: "Full git diff, full test log, full build output fed into context on every tool call.",
              },
              {
                state: "+ RTK",
                bg: "bg-indigo-50",
                tokens: "286K",
                tokenLabel: "tokens consumed (after filtering)",
                saved: "$103.51",
                savedLabel: "saved (real, this install)",
                savedColor: "text-indigo-600",
                rate: "99.2%",
                rateLabel: "across 3,316 commands",
                detail: "Failures only. Compact diffs. Deduped logs. 34.5M tokens that never entered the context window.",
              },
              {
                state: "+ RTK + Agent Booster",
                bg: "bg-green-50",
                tokens: "57.8K",
                tokenLabel: "tokens served from file reads",
                saved: "$103.80",
                savedLabel: "saved combined (real)",
                savedColor: "text-green-600",
                rate: "62%",
                rateLabel: "on file reads (30 reads)",
                detail: "Symbol-slice reads on top of RTK. Only the relevant function or class enters context, not the whole file.",
              },
            ].map(({ state, bg, tokens, tokenLabel, saved, savedLabel, savedColor, rate, rateLabel, detail }) => (
              <div key={state} className={`${bg} px-4 py-4`}>
                <p className="text-[10px] font-bold text-stone-500 uppercase tracking-wider mb-3">{state}</p>
                <p className="text-2xl font-bold text-stone-900 leading-none">{tokens}</p>
                <p className="text-[10px] text-stone-400 mb-3">{tokenLabel}</p>
                <p className={`text-lg font-bold ${savedColor}`}>{saved}</p>
                <p className="text-[10px] text-stone-400 mb-3">{savedLabel}</p>
                <p className="text-sm font-semibold text-stone-700">{rate}</p>
                <p className="text-[10px] text-stone-400 mb-3">{rateLabel}</p>
                <p className="text-xs text-stone-500 leading-relaxed border-t border-stone-200 pt-3 mt-1">{detail}</p>
              </div>
            ))}
          </div>
        </div>
        <p className="text-xs text-stone-400 mb-8">
          Real numbers from a single developer install. RTK: 3,316 commands, 34.5M tokens saved at Claude Sonnet input pricing ($3/M tokens).
          Agent Booster: 30 reads, 96K tokens saved. Combined: 34.6M tokens, $103.80 saved.
        </p>

        {/* RTK install block */}
        <SubHeading>RTK, token optimizer for command output</SubHeading>
        <p className="text-stone-500 text-sm mb-3 leading-relaxed">
          RTK (Rust Token Killer) wraps every shell command Claude Code runs, git, test, build, docker, and strips noise before it
          enters the context window. Failures only. Compact diffs. Deduplicated logs. 60–99% savings depending on command type.
        </p>
        <Pre>{`# Install
pip install rtk-cli   # or: cargo install rtk

# See your savings at any time
rtk gain

# Real output (single developer install):
# Total commands:  3,316
# Tokens saved:    34.5M  (99.2%)
# Est. cost saved: $103.51  (at Claude Sonnet $3/M input)`}</Pre>
        <div className="mt-3 rounded-xl border border-indigo-200 bg-indigo-50 px-4 py-3 text-sm text-indigo-800 mb-8">
          <strong>Guard integration (coming soon):</strong> Once RTK is installed, Guard reads <Code>rtk gain</Code> at each sync,
          diffs against the last baseline, and posts the delta to the Spend dashboard automatically.
          Your team's real savings appear in the <strong>Est. savings</strong> card, not zero.
        </div>

        {/* Agent Booster install block */}
        <SubHeading>Agent Booster, token optimizer for file reads</SubHeading>
        <p className="text-stone-500 text-sm mb-3 leading-relaxed">
          Agent Booster indexes your codebase and serves only the relevant symbol slice when Claude reads a file, the
          function, class, or block it actually needs, not the entire 800-line file. 62% savings on file reads observed in practice.
          Also cuts <strong>output</strong> tokens via verbosity modes and compresses project memory. Stacks on top of RTK.
        </p>
        <Pre>{`# Install
pip install agent-booster

# Index your repo + wire hooks
booster init claude

# Set verbosity mode, cuts output tokens 30–75%
booster verbosity full     # lite | full | ultra | off

# Compress memory files via haiku (~60% smaller)
booster compress           # add --dry-run to preview

# See combined input + output savings
booster gain

# Real output (6 active days):
# Tokens saved (reads):   1,208,085  (77%)
# Tokens saved (output):  ~1,833     (full verbosity)
# Combined savings:       ~1,209,918 tokens`}</Pre>
        <div className="mt-3 rounded-xl border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-800 mb-4">
          <strong>Guard integration:</strong> The <Code>booster-stop.py</Code> Stop hook captures actual output tokens at each session end and stores them locally. <Code>conduct guard sync</Code> ships them to Guard alongside RTK savings.
          The combined RTK + Booster delta appears as <strong>Est. savings</strong> on the Guard Spend dashboard, broken down by developer.
        </div>

        {/* Savings breakdown table */}
        <SubHeading>What Guard will show</SubHeading>
        <div className="rounded-xl border border-stone-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-stone-50 border-b border-stone-200">
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-stone-500 uppercase tracking-wider">Source</th>
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-stone-500 uppercase tracking-wider">What it compresses</th>
                <th className="text-right px-4 py-2.5 text-xs font-semibold text-stone-500 uppercase tracking-wider">Typical rate</th>
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-stone-500 uppercase tracking-wider">Tracked by</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-stone-100">
              {[
                ["RTK",               "Command output, git, test, build, docker, grep", "85–99%", "rtk gain -f json"],
                ["Booster, reads",   "File reads, serves symbol slices, not full files",  "50–70%", "booster gain"],
                ["Booster, output",  "Response verbosity (lite/full/ultra modes)",          "30–75%", "booster gain"],
                ["Combined",          "All layers stacked in the same session",              "90–94%", "Guard sync posts delta"],
              ].map(([src, what, rate, how]) => (
                <tr key={src}>
                  <td className="px-4 py-3 text-xs font-semibold text-stone-800">{src}</td>
                  <td className="px-4 py-3 text-xs text-stone-500">{what}</td>
                  <td className="px-4 py-3 text-xs text-right font-mono text-green-600">{rate}</td>
                  <td className="px-4 py-3 text-xs font-mono text-stone-400">{how}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section id="guard-roles">
        <SectionHeading id="guard-roles">Roles & permissions</SectionHeading>
        <p className="text-stone-500 text-sm mb-6 leading-relaxed">
          Every workspace member has one of four roles, the single source of truth enforced across Guard, API keys, and the CLI.
        </p>

        <SubHeading>Role definitions</SubHeading>
        <div className="rounded-xl border border-stone-200 divide-y divide-stone-100 text-sm mb-8">
          {[
            { role: "Admin",     color: "bg-purple-50 text-purple-700", desc: "Full access: Guard policies, spend limits, members, settings, API key revoke, and all playbooks." },
            { role: "Security",  color: "bg-blue-50 text-blue-700",     desc: "Full Guard access, create/edit policies and view all activity. View-only spend. Cannot manage members or revoke API keys." },
            { role: "Developer", color: "bg-green-50 text-green-700",   desc: "View-only Guard (no create/edit). Can generate their own API key. Full access to runs, playbooks, and canvas." },
            { role: "Viewer",    color: "bg-stone-100 text-stone-600",  desc: "View-only across all of Guard, runs, and audit log. No execution or edit rights." },
          ].map(({ role, color, desc }) => (
            <div key={role} className="flex items-start gap-4 px-4 py-3">
              <span className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full shrink-0 mt-0.5 ${color}`}>{role}</span>
              <span className="text-xs text-stone-500 leading-relaxed">{desc}</span>
            </div>
          ))}
        </div>

        <SubHeading>Guard capability matrix</SubHeading>
        <div className="rounded-xl border border-stone-200 overflow-hidden mb-4">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-stone-50 border-b border-stone-200">
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-stone-500 uppercase tracking-wider">Capability</th>
                {["Admin", "Security", "Developer", "Viewer"].map(h => (
                  <th key={h} className="text-center px-4 py-2.5 text-xs font-semibold text-stone-500 uppercase tracking-wider w-20">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-stone-100 text-sm">
              {[
                ["View Guard dashboard",     true,  true,  true,  true ],
                ["View activity log",        true,  true,  true,  true ],
                ["View policies",            true,  true,  true,  true ],
                ["Create / edit policies",   true,  true,  false, false],
                ["View spend data",          true,  true,  true,  true ],
                ["Set spend limits",         true,  false, false, false],
                ["View members",             true,  true,  true,  true ],
                ["Invite / remove members",  true,  false, false, false],
                ["Configure Guard settings", true,  false, false, false],
                ["Generate API key",         true,  false, true,  false],
                ["Revoke API key",           true,  false, false, false],
                ["Run playbooks / canvas",   true,  true,  true,  false],
              ].map(([label, admin, security, developer, viewer]) => (
                <tr key={label as string}>
                  <td className="px-4 py-2.5 text-xs text-stone-700">{label as string}</td>
                  {[admin, security, developer, viewer].map((allowed, i) => (
                    <td key={i} className="px-4 py-2.5 text-center text-xs">
                      {allowed
                        ? <span className="text-green-600 font-bold">✓</span>
                        : <span className="text-stone-300 font-medium">—</span>
                      }
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section id="guard-onboarding">
        <SectionHeading id="guard-onboarding">Team onboarding</SectionHeading>
        <p className="text-stone-500 text-sm mb-6 leading-relaxed">
          End-to-end flow for getting a team onto Guard. Each developer runs two commands, everything else is automatic.
        </p>

        <div className="space-y-0">
          {[
            { step: "1", title: "Admin installs Guard",          body: "Settings → Modules → ConductGuard → Install. Guard is provisioned with 18 starter policies. The admin shares the invite code or adds team members directly." },
            { step: "2", title: "Invite your team",              body: "Guard → Members → Invite. Assign roles: Developer for engineers, Security for security team, Viewer for stakeholders." },
            { step: "3", title: "Developer generates an API key",body: "Settings → API Keys → Generate key. Admin and Developer roles can generate keys. The key is tied to their workspace and role." },
            { step: "4", title: "Developer logs in",             body: "One command installs Guard, downloads policies, registers the hook in Claude Code and Codex, and registers the MCP server in Cursor and Windsurf.", code: "pip install conduct-cli\nconduct login --server https://api.conductai.ai --api-key cond_live_xxxx" },
            { step: "5", title: "Guard enforces from this moment",body: "Every AI tool call on the developer's machine is intercepted and checked against workspace policies. All activity, allowed and blocked, appears in the Guard dashboard." },
          ].map(({ step, title, body, code }) => (
            <div key={step} className="flex gap-6 pb-8 relative">
              <div className="flex flex-col items-center">
                <div className="w-8 h-8 rounded-full bg-stone-900 text-white text-sm font-bold flex items-center justify-center shrink-0 z-10">{step}</div>
                {parseInt(step) < 5 && <div className="w-px flex-1 bg-stone-200 mt-2" />}
              </div>
              <div className="pt-1 pb-2 flex-1">
                <p className="font-semibold text-stone-900 mb-1">{title}</p>
                <p className="text-sm text-stone-600 leading-relaxed mb-2">{body}</p>
                {code && <pre className="bg-stone-900 text-stone-100 rounded-lg px-4 py-3 text-xs font-mono mt-2 overflow-x-auto">{code}</pre>}
              </div>
            </div>
          ))}
        </div>

        <SubHeading>Keeping Guard current</SubHeading>
        <Pre>{`# After an admin updates policies:
conduct guard sync

# Check what's enforced right now:
conduct guard status

# See recent activity:
conduct guard audit --since 7d`}</Pre>

        <div className="mt-4 rounded-xl bg-stone-100 border border-stone-200 px-4 py-3 text-sm text-stone-700">
          <strong>CLI auto-updates.</strong> Developers never need to manually upgrade, the CLI checks PyPI on
          every run and upgrades itself if a newer version is available.
        </div>
      </section>

      <section id="guard-scenarios">
        <SectionHeading id="guard-scenarios">Test scenarios</SectionHeading>
        <p className="text-stone-500 text-sm mb-6 leading-relaxed">
          Four end-to-end scenarios that cover every Guard enforcement path. Run them in order after onboarding a developer to verify the full stack, hook, API, Slack, and activity log, is wired correctly.
        </p>

        <Screenshot
          src="/guard-docs/dashboard.png"
          alt="Guard dashboard showing active developers, events, tokens, and cost trend chart"
          caption="Guard dashboard, real-time overview of team AI usage. The cost trend chart breaks down spend by Claude vs Codex."
        />
        <Screenshot
          src="/guard-docs/activity-log.png"
          alt="Guard activity log showing tool calls from Claude Code and Codex with token counts"
          caption="Activity log, every tool call is recorded: who, which AI tool, what command, and token cost. Both Claude Code and Codex sessions appear here."
        />

        {/* Scenario 1 */}
        <div className="mb-12">
          <div className="flex items-center gap-3 mb-3">
            <span className="w-7 h-7 rounded-full bg-stone-900 text-white text-xs font-bold flex items-center justify-center shrink-0">1</span>
            <h3 className="font-semibold text-stone-900 text-base">Workspace hard cap, blocks all tool calls</h3>
          </div>
          <p className="text-sm text-stone-500 mb-4 ml-10">Verify that setting the workspace monthly budget below current spend blocks every subsequent tool call for all users.</p>
          <div className="ml-10">
            <Screenshot
              src="/guard-docs/spend-controls.png"
              alt="Spend Controls panel showing team monthly budget, per-developer limit, alert threshold, and hard cap"
              caption="Guard → Spend, set the Team monthly budget and Hard cap here. Enable 'Hard cap on' to block sessions at 100%."
            />
          </div>
          <div className="ml-10 rounded-xl border border-stone-200 divide-y divide-stone-100 mb-4">
            {[
              { label: "Set workspace budget below current spend", detail: "Guard → Spend → Team monthly budget → set to a value ≤ current spend → Save." },
              { label: "Sync and clear the cache", detail: "conduct guard sync && rm ~/.conductguard/budget_cache.json" },
              { label: "Verify the API", detail: 'GET /guard/spend/budget-check, expect { "hard_blocked": true }' },
              { label: "Test the hook", detail: `echo '{"tool_name":"bash","tool_input":{"command":"ls"},"session_id":"test"}' | python3.11 ~/.conductguard/hook.py\nExpected: exit 2 with budget block message` },
            ].map(({ label, detail }) => (
              <div key={label} className="px-4 py-3">
                <p className="text-xs font-semibold text-stone-700 mb-1">{label}</p>
                <pre className="text-xs text-stone-500 font-mono whitespace-pre-wrap leading-relaxed">{detail}</pre>
              </div>
            ))}
          </div>
          <div className="ml-10 mb-4">
            <p className="text-xs font-semibold text-stone-500 uppercase tracking-wider mb-2">What it looks like in Claude Code (live session, 2026-06-05)</p>
            <Screenshot
              src="/guard-docs/budget-cap-bash-blocked.png"
              alt="Claude Code terminal showing ConductGuard budget hard cap blocking a bash tool call"
              caption="Every tool call. Bash, Read, Edit, is blocked until the budget is raised. The message surfaces inline before the tool runs."
            />
            <Screenshot
              src="/guard-docs/budget-cap-claude-blocked.png"
              alt="Claude Code response showing Guard budget hard cap hit and instructions to raise the workspace budget"
              caption="Claude Code itself reports the block. Guard stops the entire session cold, no workaround from inside the agent."
            />
          </div>
          <div className="ml-10 mb-4">
            <p className="text-xs font-semibold text-stone-500 uppercase tracking-wider mb-2">Slack notification when the cap is hit (live, 2026-06-05)</p>
            <pre className="bg-stone-900 text-green-400 rounded-xl px-4 py-3 text-xs font-mono overflow-x-auto leading-relaxed">{`🛑 BUDGET CAP HIT by budget-hard-cap in claude-code
Developer: sudhi@b2bsphere.com
Your team's monthly AI budget of $500.00 has been reached.
New tool calls are paused until the limit is raised. Contact your security team.

🛑 BUDGET CAP HIT by budget-hard-cap in codex
Developer: sudhi@b2bsphere.com
Your team's monthly AI budget of $500.00 has been reached.
New tool calls are paused until the limit is raised. Contact your security team.`}</pre>
            <p className="text-xs text-stone-400 mt-2 leading-relaxed">
              The alert fires once per tool when the cap is first hit, not on every blocked call. Guard blocks <strong className="text-stone-600">all registered tools simultaneously</strong>: Claude Code, Codex, Cursor. Each fires its own notification so your security team knows which sessions are affected.
            </p>
          </div>
          <div className="ml-10 rounded-xl bg-stone-50 border border-stone-200 px-4 py-2.5 text-xs text-stone-500">
            <strong className="text-stone-700">Teardown:</strong> Raise the budget above current spend → Save. Run conduct guard sync &amp;&amp; rm ~/.conductguard/budget_cache.json.
          </div>
        </div>

        {/* Scenario 2 */}
        <div className="mb-12">
          <div className="flex items-center gap-3 mb-3">
            <span className="w-7 h-7 rounded-full bg-stone-900 text-white text-xs font-bold flex items-center justify-center shrink-0">2</span>
            <h3 className="font-semibold text-stone-900 text-base">Per-developer hard cap, blocks one user</h3>
          </div>
          <p className="text-sm text-stone-500 mb-4 ml-10">Verify that a per-developer spend limit blocks tool calls for a specific user without affecting others.</p>
          <div className="ml-10 rounded-xl border border-stone-200 divide-y divide-stone-100 mb-4">
            {[
              { label: "Set per-developer limit below the user's spend", detail: "Guard → Spend → Default per-developer limit → set below current user spend → Save." },
              { label: "Sync and clear the cache", detail: "conduct guard sync && rm ~/.conductguard/budget_cache.json" },
              { label: "Verify the API with clerk_user_id", detail: "GET /guard/spend/budget-check?workspace_id=<ws>&clerk_user_id=<uid>\nExpect { \"hard_blocked\": true } for this user only." },
              { label: "Test the hook", detail: "Same hook test as Scenario 1, expect exit 2 with per-user block message." },
            ].map(({ label, detail }) => (
              <div key={label} className="px-4 py-3">
                <p className="text-xs font-semibold text-stone-700 mb-1">{label}</p>
                <pre className="text-xs text-stone-500 font-mono whitespace-pre-wrap leading-relaxed">{detail}</pre>
              </div>
            ))}
          </div>
          <div className="ml-10">
            <Screenshot
              src="/guard-docs/spend-by-developer.png"
              alt="Spend breakdown by developer and by AI tool showing sessions, tokens, cost, and budget"
              caption="Guard → Spend. By Developer table shows each user's sessions, token usage, cost, savings, and individual budget. By AI Tool breakdown shows Claude Code vs Codex split."
            />
          </div>
          <div className="ml-10 rounded-xl bg-stone-50 border border-stone-200 px-4 py-2.5 text-xs text-stone-500">
            <strong className="text-stone-700">Teardown:</strong> Raise the per-developer limit above the user's spend → Save. Sync and clear cache.
          </div>
        </div>

        {/* Scenario 3 */}
        <div className="mb-12">
          <div className="flex items-center gap-3 mb-3">
            <span className="w-7 h-7 rounded-full bg-stone-900 text-white text-xs font-bold flex items-center justify-center shrink-0">3</span>
            <h3 className="font-semibold text-stone-900 text-base">Policy rule, blocks a specific tool call</h3>
          </div>
          <p className="text-sm text-stone-500 mb-4 ml-10">Verify that a Guard policy rule matches a pattern in a tool call, blocks it with a custom message, logs it to the activity feed, and fires a Slack notification.</p>
          <div className="ml-10 rounded-xl border border-stone-200 divide-y divide-stone-100 mb-4">
            {[
              { label: "Create the policy rule", detail: "Guard → Policies → Add rule\nRule ID: no-rm | Match tool: bash | Match pattern: rm | Action: block\nMessage: Deleting files is not allowed. Use git to revert changes instead." },
              { label: "Sync the policy", detail: "conduct guard sync" },
              { label: "Test the hook directly", detail: `echo '{"tool_name":"bash","tool_input":{"command":"rm -rf /tmp/test"},"session_id":"test"}' | python3.11 ~/.conductguard/hook.py; echo "exit: $?"` },
              { label: "Trigger from Claude Code", detail: "Ask Claude to run: bash -c 'rm -rf /tmp/test'\nExpected: PreToolUse hook error, tool call blocked inline." },
              { label: "Verify activity log", detail: "Guard → Activity, find the event. Confirm decision=blocked, rule_id=no-rm, tool_name=bash." },
            ].map(({ label, detail }) => (
              <div key={label} className="px-4 py-3">
                <p className="text-xs font-semibold text-stone-700 mb-1">{label}</p>
                <pre className="text-xs text-stone-500 font-mono whitespace-pre-wrap leading-relaxed">{detail}</pre>
              </div>
            ))}
          </div>
          <div className="ml-10">
            <Screenshot
              src="/guard-docs/block-claude-terminal.png"
              alt="Claude Code terminal showing PreToolUse hook blocking a bash command with ConductGuard error message"
              caption="Claude Code surfaces the block inline, the tool call never runs. The error shows the rule message exactly as configured in Guard → Policies."
            />
          </div>
          <div className="ml-10">
            <Screenshot
              src="/guard-docs/audit-blocked.png"
              alt="Audit log showing blocked bash commands with no-rm rule alongside allowed events"
              caption="Guard → Activity, blocked events are tagged in red with the rule ID. Allowed events show green. Every tool call, blocked or allowed, is recorded."
            />
          </div>
          <div className="ml-10 mb-4">
            <p className="text-xs font-semibold text-stone-500 uppercase tracking-wider mb-2">Real Slack notifications from a live session (2026-06-02)</p>
            <Screenshot
              src="/guard-docs/slack-drop-table-block.png"
              alt="Slack message from ConductAI showing salessupport@organicsphere.com blocked by no-drop-table rule"
              caption="DROP TABLE blocked. Slack fires instantly with the developer email, rule ID, and policy message."
            />
            <Screenshot
              src="/guard-docs/slack-file-delete-block.png"
              alt="Slack showing multiple no-rm blocks for salessupport@organicsphere.com in rapid succession"
              caption="Multiple blocks in the same session, each blocked tool call fires its own Slack message in real time."
            />
            <Screenshot
              src="/guard-docs/Password-keys-compromise.png"
              alt="Slack message from ConductAI showing salessupport@organicsphere.com warned by no-hardcoded-secrets rule in claude-code"
              caption="Hardcoded secret detected. Guard warns the developer in Slack instantly with the rule ID and policy message. The developer email is always surfaced so managers know exactly who triggered the alert."
            />
            <p className="text-xs text-stone-400 mt-1 leading-relaxed">The block fires on every blocked call. Spend alerts are deduped per 5% increment, policy blocks are not deduped.</p>
          </div>
          <div className="ml-10 rounded-xl bg-stone-50 border border-stone-200 px-4 py-2.5 text-xs text-stone-500">
            <strong className="text-stone-700">Teardown:</strong> Guard → Policies → delete no-rm → Save. Run conduct guard sync.
          </div>
        </div>

        {/* Scenario 4 */}
        <div className="mb-12">
          <div className="flex items-center gap-3 mb-3">
            <span className="w-7 h-7 rounded-full bg-stone-900 text-white text-xs font-bold flex items-center justify-center shrink-0">4</span>
            <h3 className="font-semibold text-stone-900 text-base">Alert threshold, fires Slack notification</h3>
          </div>
          <p className="text-sm text-stone-500 mb-4 ml-10">Verify that spend crossing the alert threshold triggers a Slack notification, deduped per 5% increment.</p>
          <div className="ml-10">
            <Screenshot
              src="/guard-docs/settings-notifications.png"
              alt="Guard Settings page showing Slack channel input and notification toggles for block/warn and budget threshold"
              caption="Guard → Settings, configure the Slack channel and toggle which events trigger notifications. Both toggles must be on to receive spend alerts and block notifications."
            />
          </div>
          <div className="ml-10 rounded-xl border border-stone-200 divide-y divide-stone-100 mb-4">
            {[
              { label: "Set alert threshold below current spend %", detail: "Guard → Spend → Alert threshold → set below current spend percentage → Save.\nExample: if spend is at 85% of budget, set threshold to 80%." },
              { label: "Trigger any tool call", detail: "In a Claude Code session, trigger any passing tool call (e.g. list files). The hook checks spend on every call." },
              { label: "Verify Slack", detail: "Expected: ⚠️ Guard spend alert (workspace-wide): $X.XX of $Y.YY used (Z%), alert threshold 80% reached" },
            ].map(({ label, detail }) => (
              <div key={label} className="px-4 py-3">
                <p className="text-xs font-semibold text-stone-700 mb-1">{label}</p>
                <pre className="text-xs text-stone-500 font-mono whitespace-pre-wrap leading-relaxed">{detail}</pre>
              </div>
            ))}
          </div>
          <div className="ml-10 mb-4">
            <p className="text-xs font-semibold text-stone-500 uppercase tracking-wider mb-2">Real Slack output from a live session (2026-06-02)</p>
            <pre className="bg-stone-900 text-green-400 rounded-xl px-4 py-3 text-xs font-mono overflow-x-auto leading-relaxed">{`7:45 PM  ⚠️ Guard spend alert (workspace-wide): $25.05 of $30.00 used (83%), alert threshold 80% reached
7:50 PM  ⚠️ Guard spend alert (workspace-wide): $27.39 of $30.00 used (91%), alert threshold 80% reached
7:52 PM  ⚠️ Guard spend alert (workspace-wide): $28.60 of $30.00 used (95%), alert threshold 80% reached
7:53 PM  ⚠️ Guard spend alert (workspace-wide): $30.23 of $30.00 used (101%), alert threshold 80% reached`}</pre>
            <p className="text-xs text-stone-400 mt-2 leading-relaxed">Each line represents a distinct 5% band crossing. Alerts do not fire on every tool call.</p>
          </div>
          <div className="ml-10 rounded-xl bg-stone-50 border border-stone-200 px-4 py-2.5 text-xs text-stone-500">
            <strong className="text-stone-700">Teardown:</strong> Set alert threshold back to your preferred operational value (e.g. 80%) and save.
          </div>
        </div>

        <div className="rounded-xl border border-stone-200 overflow-hidden mt-4">
          <div className="bg-stone-50 border-b border-stone-200 px-4 py-2.5">
            <p className="text-xs font-semibold text-stone-500 uppercase tracking-wider">Known issues</p>
          </div>
          <table className="w-full text-sm">
            <tbody className="divide-y divide-stone-100">
              {[
                ["Budget cache TTL", "Changes to spend limits take up to 5 min to reflect", "rm ~/.conductguard/budget_cache.json"],
                ["Wrong Python binary", "Apple system Python has network restrictions, hook fails silently", "Re-run conduct guard sync (auto-detects Homebrew Python since v0.4.20)"],
                ["Missing clerk_user_id", "Per-user budget checks silently skipped", "Run conduct guard sync, added in v0.4.16"],
                ["Alert dedup", "Alerts fire once per 5% increment, won't re-fire in the same band", "Adjust spend or threshold to cross a new 5% boundary"],
              ].map(([issue, detail, fix]) => (
                <tr key={issue}>
                  <td className="px-4 py-3 text-xs font-medium text-stone-800 w-44 align-top">{issue}</td>
                  <td className="px-4 py-3 text-xs text-stone-500 align-top">{detail}</td>
                  <td className="px-4 py-3 text-xs font-mono text-stone-500 align-top">{fix}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section id="guard-token-savings">
        <SectionHeading id="guard-token-savings">RTK + Agent Booster</SectionHeading>
        <p className="text-stone-500 text-sm mb-6 leading-relaxed">
          Guard controls what your team <em>spends</em>. RTK and Agent Booster control what your team <em>burns</em>.
          Together they cut the token footprint of every Claude Code, Cursor, and Codex session, and Guard surfaces the combined savings on the dashboard automatically.
        </p>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-8">
          <div className="rounded-xl border border-stone-200 px-5 py-4">
            <div className="flex items-center gap-2 mb-2">
              <span className="text-xs font-bold px-2 py-0.5 rounded bg-stone-900 text-white font-mono">RTK</span>
              <span className="text-xs text-stone-400">Rust Token Killer</span>
            </div>
            <p className="text-sm text-stone-600 leading-relaxed mb-3">
              Wraps every CLI tool your agent calls — <Code>git</Code>, <Code>pytest</Code>, <Code>tsc</Code>, <Code>docker</Code>, and strips noise before the output reaches the model. Typical savings: <strong>60–99%</strong> per command.
            </p>
            <Pre>{`pip install rtk\nrtk git status   # 80% fewer tokens\nrtk pytest       # failures only, 90% savings`}</Pre>
          </div>
          <div className="rounded-xl border border-stone-200 px-5 py-4">
            <div className="flex items-center gap-2 mb-2">
              <span className="text-xs font-bold px-2 py-0.5 rounded bg-indigo-600 text-white font-mono">Booster</span>
              <span className="text-xs text-stone-400">Agent Booster</span>
            </div>
            <p className="text-sm text-stone-600 leading-relaxed mb-3">
              Indexes your codebase with AST + vector embeddings. Intercepts raw file reads and grep calls, returning only the relevant symbol slices. Typical savings: <strong>60–70%</strong> per read. Hooks are active immediately after install, no session restart needed.
            </p>
            <Pre>{`pip install agent-booster\nbooster init claude   # indexes repo + wires hooks`}</Pre>
          </div>
        </div>

        <SubHeading>Real numbers from a single developer install</SubHeading>
        <div className="rounded-xl border border-stone-200 overflow-hidden mb-6">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-stone-50 border-b border-stone-200">
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-stone-500 uppercase tracking-wider">Tool</th>
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-stone-500 uppercase tracking-wider">Tokens saved</th>
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-stone-500 uppercase tracking-wider">Savings %</th>
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-stone-500 uppercase tracking-wider">Est. cost saved</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-stone-100">
              {[
                ["RTK",          "34.5M",  "99.2%", "$103.53"],
                ["Agent Booster","96.3K",  "62.5%", "—"],
              ].map(([tool, tokens, pct, cost]) => (
                <tr key={tool}>
                  <td className="px-4 py-3 font-mono text-xs font-semibold text-stone-800">{tool}</td>
                  <td className="px-4 py-3 text-stone-700 font-medium">{tokens}</td>
                  <td className="px-4 py-3"><span className="text-xs font-medium px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700">{pct}</span></td>
                  <td className="px-4 py-3 text-stone-700">{cost}</td>
                </tr>
              ))}
              <tr className="bg-stone-50">
                <td className="px-4 py-3 font-semibold text-stone-900">Combined</td>
                <td className="px-4 py-3 font-bold text-emerald-700">34.6M</td>
                <td className="px-4 py-3"><span className="text-xs font-bold px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-800">~99%</span></td>
                <td className="px-4 py-3 font-bold text-emerald-700">$103.53</td>
              </tr>
            </tbody>
          </table>
          <div className="border-t border-stone-100 px-4 py-2 bg-stone-50">
            <p className="text-xs text-stone-400">Measured over 1 day · 3,354 RTK commands · 30 Booster reads · Claude Sonnet pricing ($3.00/M tokens)</p>
          </div>
        </div>

        <SubHeading>How Guard surfaces savings</SubHeading>
        <p className="text-sm text-stone-600 leading-relaxed mb-4">
          At session end the <Code>booster-stop.py</Code> Stop hook automatically records actual output tokens (input savings come from the Read/Grep intercept hooks). When a developer runs <Code>conduct guard sync</Code>, the CLI reads <Code>rtk gain</Code> and <Code>booster gain</Code> and posts the totals to the Guard API. The <strong>Est. savings</strong> card on the Guard Spend dashboard shows the combined RTK + Booster delta per developer, no extra setup required.
        </p>
        <Pre>{`conduct guard sync\n\n#   Policy refreshed: 19 rule(s)\n#   Hook script updated\n#   Savings reported`}</Pre>

        <div className="mt-8 rounded-xl bg-indigo-50 border border-indigo-200 px-6 py-5 flex flex-col sm:flex-row sm:items-center gap-4">
          <div className="flex-1">
            <p className="font-semibold text-indigo-900 mb-1">Add Agent Booster to your workflow</p>
            <p className="text-sm text-indigo-700 leading-relaxed">
              One command indexes your repo, wires the hooks, and starts tracking savings, no session restart needed.
            </p>
          </div>
          <Link
            href="/tools/agent-booster"
            className="shrink-0 inline-flex items-center gap-2 px-5 py-2.5 rounded-lg bg-indigo-600 text-white text-sm font-semibold hover:bg-indigo-700 transition-colors"
          >
            Get Agent Booster →
          </Link>
        </div>
      </section>

      <section id="guard-policy-reference">
        <SectionHeading id="guard-policy-reference">Policy reference</SectionHeading>
        <p className="text-stone-500 text-sm mb-6 leading-relaxed">
          Everything a security reviewer needs to evaluate ConductGuard: the rule schema, how decisions flow through the hook chain,
          and how policy changes propagate to every developer in real time.
        </p>

        <SubHeading>Rule schema</SubHeading>
        <p className="text-stone-500 text-sm mb-3">Each rule in your policy JSON follows this shape:</p>
        <Pre>{`{
  "id":          "no-prod-push",          // unique slug, used in audit log
  "description": "Block git push to prod branches",
  "applies_to":  ["Bash"],               // tool names: Bash, Write, Edit, MultiEdit, Read, Glob, mcp__*
  "pattern":     "git push.*main|master", // regex matched against tool input (command, file_path, etc.)
  "action":      "block",                // "block" | "warn" | "audit"
  "overridable": false,                  // false = admin-only rule, cannot be disabled per-user
  "severity":    "high"                  // "critical" | "high" | "medium" | "low"
}`}</Pre>

        <div className="rounded-xl border border-stone-200 overflow-hidden my-6">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-stone-50 border-b border-stone-200">
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-stone-500 uppercase tracking-wider w-36">Field</th>
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-stone-500 uppercase tracking-wider w-24">Type</th>
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-stone-500 uppercase tracking-wider">Notes</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-stone-100">
              {[
                ["id",          "string",  "Unique within policy. Appears in audit log events."],
                ["description", "string",  "Human-readable label shown in Guard dashboard."],
                ["applies_to",  "string[]","Tool names to match. Use [\"*\"] to catch all tools."],
                ["pattern",     "string",  "Python-compatible regex. Matched against the serialised tool input."],
                ["action",      "string",  "block = terminate call; warn = proceed + emit warning; audit = proceed silently + log."],
                ["overridable", "boolean", "false = rule cannot be suppressed by developers. Enforced by signed policy."],
                ["severity",    "string",  "Surfaces in dashboard and Slack alerts. Does not affect block/warn logic."],
              ].map(([f, t, n]) => (
                <tr key={f}>
                  <td className="px-4 py-3 font-mono text-xs text-stone-800">{f}</td>
                  <td className="px-4 py-3 font-mono text-xs text-stone-500">{t}</td>
                  <td className="px-4 py-3 text-xs text-stone-500">{n}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <SubHeading>PreToolUse decision flow</SubHeading>
        <p className="text-stone-500 text-sm mb-4">
          Every time Claude Code is about to call a tool, the PreToolUse hook fires synchronously. This happens before the tool runs — giving Guard the ability to block it entirely.
        </p>
        <div className="rounded-xl border border-stone-200 bg-stone-50 px-5 py-4 mb-4 space-y-2 text-sm">
          {[
            ["1", "bg-stone-200 text-stone-700", "Tool call requested", "Claude invokes Bash / Write / Edit / mcp__* etc."],
            ["2", "bg-blue-100 text-blue-800",   "PreToolUse hook fires",  "posttooluse.py runs synchronously before the tool executes."],
            ["3", "bg-blue-100 text-blue-800",   "guard_check()",          "Serialised tool input matched against every active rule (regex, in order)."],
            ["4", "bg-red-100 text-red-800",     "BLOCK",                  "Hook exits non-zero → Claude Code aborts the tool call. Event written to audit log with decision=block."],
            ["4", "bg-amber-100 text-amber-800", "WARN",                   "Hook prints warning to stderr → tool proceeds. Event written with decision=warn."],
            ["4", "bg-emerald-100 text-emerald-800","ALLOW",               "No rule matched → tool proceeds. Event written with decision=allow (if audit mode on)."],
          ].map(([step, cls, label, desc], i) => (
            <div key={i} className="flex items-start gap-3">
              <span className={`shrink-0 mt-0.5 w-5 h-5 rounded-full flex items-center justify-center text-xs font-bold ${cls}`}>{step}</span>
              <div>
                <span className="font-semibold text-stone-800">{label} — </span>
                <span className="text-stone-500">{desc}</span>
              </div>
            </div>
          ))}
        </div>

        <SubHeading>PostToolUse lifecycle</SubHeading>
        <p className="text-stone-500 text-sm mb-4">
          After a tool completes, the PostToolUse hook fires to record what actually happened — token usage, blast radius, and any post-run policy checks.
        </p>
        <Pre>{`PostToolUse fires
  └─ read token counts from tool response
  └─ _compute_blast_radius(tool_name, tool_input, tool_response)
       → { files: N, symbols?: N, tier: "local"|"repo"|"network"|"destructive" }
  └─ _post_usage(tokens_in, tokens_out, blast_radius=…)
       → POST /guard/events/usage   ← updates audit event row in-place
  └─ journal_append(event)          ← async: drain daemon POSTs to API every 30s`}</Pre>

        <p className="text-stone-500 text-sm mt-3 mb-4">
          The <strong>blast radius</strong> column in the Guard Activity log is populated here. <Code>destructive</Code> tier commands (rm -rf, force-push, DROP TABLE) are flagged immediately; <Code>network</Code> tier captures outbound calls; <Code>repo</Code> tier tracks cross-repo mutations; <Code>local</Code> covers single-file writes.
        </p>

        <SubHeading>Policy propagation</SubHeading>
        <p className="text-stone-500 text-sm mb-4 leading-relaxed">
          A Guard policy is a signed JSON file. When an admin publishes a new policy from the dashboard, the signature is written server-side and the policy version incremented. The drain daemon running on each developer machine polls <Code>/guard/policy/latest</Code> every 30 seconds. On version change it writes the new policy to <Code>~/.conductguard/policy.json</Code> and verifies the Ed25519 signature before activating it.
        </p>
        <div className="rounded-xl border border-stone-200 bg-stone-50 px-5 py-4 mb-4 space-y-2 text-sm">
          {[
            ["Admin publishes policy",    "Dashboard signs + stores policy. Version counter incremented."],
            ["Drain daemon polls (30s)",  "GET /guard/policy/latest — returns version + signed payload."],
            ["Signature verified",        "Ed25519 public key from ~/.conductguard/public.pem checked. Tampered policy rejected."],
            ["Policy written atomically", "policy.json swapped atomically. Next PreToolUse call loads new rules."],
          ].map(([step, desc]) => (
            <div key={step} className="flex items-start gap-3">
              <span className="shrink-0 mt-0.5 w-1.5 h-1.5 rounded-full bg-indigo-400 mt-2" />
              <div>
                <span className="font-semibold text-stone-800">{step} — </span>
                <span className="text-stone-500">{desc}</span>
              </div>
            </div>
          ))}
        </div>
        <p className="text-stone-500 text-sm leading-relaxed">
          No redeploy, no agent restart, no per-developer action required. A rule change published at 14:00 is active on every enrolled developer machine by 14:01. <Code>overridable: false</Code> rules are enforced by the signed policy — a developer cannot remove them by editing a local config file.
        </p>

        <div className="mt-8 rounded-xl border border-stone-200 bg-stone-50 px-5 py-4">
          <p className="text-xs font-bold uppercase tracking-widest text-stone-400 mb-3">Supported tool names in <code>applies_to</code></p>
          <div className="flex flex-wrap gap-2">
            {["Bash","Write","Edit","MultiEdit","Read","Glob","Grep","mcp__*","WebFetch","WebSearch","*"].map(t => (
              <span key={t} className="px-2.5 py-1 rounded-lg bg-white border border-stone-200 font-mono text-xs text-stone-700">{t}</span>
            ))}
          </div>
          <p className="text-xs text-stone-400 mt-3">Use <Code>*</Code> to match every tool. MCP tools are matched by prefix — <Code>mcp__agent-booster__*</Code> matches all Agent Booster tools.</p>
        </div>
      </section>
    </div>
  )
}

function TabMcpTools() {
  return (
    <div className="space-y-12">
      <section id="mcp-overview" className="scroll-mt-8">
        <p className="text-xs font-bold uppercase tracking-widest text-indigo-600 mb-2">Setup guide</p>
        <h2 className="text-3xl font-bold text-stone-900 mb-3">Connect your AI tools to ConductGuard</h2>
        <p className="text-stone-600 leading-relaxed mb-6">
          Conduct AI Guard is a default MCP server for every workspace. It works with any client that
          speaks MCP — Claude, Codex, Cursor, VS Code + Copilot, Devin, and more. Once a client is
          pointed at your workspace URL, every tool call is audited and policy-enforced.
        </p>
        <div className="bg-indigo-50 border border-indigo-100 rounded-xl p-5">
          <p className="text-sm font-semibold text-indigo-900 mb-1">Fastest path: let the CLI do it</p>
          <p className="text-sm text-indigo-800 leading-relaxed mb-3">
            The Conduct CLI auto-detects every supported client on your machine and writes the right config.
          </p>
          <Pre>conduct guard sync</Pre>
          <p className="text-xs text-indigo-700 mt-3">
            Covers Claude Code, Claude Desktop, Cursor, Codex CLI, Windsurf, VS Code + Copilot, and
            Copilot CLI. Claude.ai, Claude for Work, ChatGPT, and Devin are cloud-only — paste the
            workspace URL into each per the sections below.
          </p>
        </div>
      </section>

      <section id="mcp-workspace-url" className="scroll-mt-8">
        <h3 className="text-2xl font-semibold text-stone-900 mb-3">MCP server URL</h3>
        <p className="text-stone-600 mb-4">
          The URL is the same for everyone — no workspace ID in the path. Your Bearer token scopes
          the connection to your org automatically.
        </p>
        <Pre>https://api.conductai.ai/guard/mcp
Authorization: Bearer &lt;your-token&gt;</Pre>
        <p className="text-sm text-stone-500 mt-3">
          The token is scoped to the member who copies it. Treat it like a personal access token —
          do not paste it in shared docs or repos.
        </p>
      </section>

      <section id="mcp-claude-web" className="scroll-mt-8">
        <h3 className="text-2xl font-semibold text-stone-900 mb-3">Claude.ai (web)</h3>
        <ol className="list-none p-0">
          <Step n={1}>Open Claude.ai → <strong>Settings</strong> → <strong>MCP Servers</strong>.</Step>
          <Step n={2}>Click <strong>Add server</strong> and paste your workspace URL.</Step>
          <Step n={3}>Save. Then in any chat, type <Code>load mcp</Code> or <Code>enable guard</Code> to activate it for that conversation.</Step>
        </ol>
      </section>

      <section id="mcp-claude-code" className="scroll-mt-8">
        <h3 className="text-2xl font-semibold text-stone-900 mb-3">Claude Code (CLI)</h3>
        <p className="text-stone-600 mb-3">
          Fastest path — <Code>conduct guard sync</Code> writes to <Code>~/.claude/settings.json</Code>{" "}
          automatically. Or add the server yourself with the built-in command:
        </p>
        <Pre>{`claude mcp add conduct-guard \\
  --transport http \\
  --url https://api.conductai.ai/guard/mcp \\
  --header "Authorization: Bearer <your-token>"`}</Pre>
        <p className="text-stone-600 mt-4 mb-2">Or edit <Code>~/.claude/settings.json</Code> directly:</p>
        <Pre>{`{
  "mcpServers": {
    "conduct-guard": {
      "type": "http",
      "url": "https://api.conductai.ai/guard/mcp",
      "headers": { "Authorization": "Bearer <your-token>" }
    }
  }
}`}</Pre>
        <p className="text-stone-600 mt-3">Restart your Claude Code session or run <Code>/mcp</Code> to confirm the server is listed.</p>
      </section>

      <section id="mcp-claude-desktop" className="scroll-mt-8">
        <h3 className="text-2xl font-semibold text-stone-900 mb-3">Claude Desktop</h3>
        <p className="text-stone-600 mb-3">Either run the CLI:</p>
        <Pre>conduct guard sync</Pre>
        <p className="text-stone-600 mt-4 mb-2">Or edit <Code>claude_desktop_config.json</Code> directly:</p>
        <Pre>{`{
  "mcpServers": {
    "conduct-guard": {
      "url": "https://api.conductai.ai/guard/mcp",
      "headers": { "Authorization": "Bearer <your-token>" }
    }
  }
}`}</Pre>
        <p className="text-stone-600 mt-3">Restart Claude Desktop to pick up the change.</p>
      </section>

      <section id="mcp-claude-work" className="scroll-mt-8">
        <h3 className="text-2xl font-semibold text-stone-900 mb-3">Claude for Work</h3>
        <ol className="list-none p-0">
          <Step n={1}><strong>Admin Console</strong> → <strong>Integrations</strong> → <strong>MCP</strong>.</Step>
          <Step n={2}>Add a new server and paste your workspace URL.</Step>
          <Step n={3}>Type <Code>load mcp</Code> in any chat to activate it for that conversation.</Step>
        </ol>
        <p className="text-sm text-stone-500 mt-3">
          For enterprise rollout, your admin can pre-provision the MCP server so it&apos;s available
          to every seat without each user pasting a URL.
        </p>
      </section>

      <section id="mcp-chatgpt" className="scroll-mt-8">
        <h3 className="text-2xl font-semibold text-stone-900 mb-3">ChatGPT (Team / Enterprise) &amp; Codex-in-ChatGPT</h3>
        <p className="text-stone-600 mb-3">
          ChatGPT connects to remote MCP servers via the Admin console&apos;s Connector program.
          The endpoint is the same URL every other client uses; the difference is that a workspace
          admin registers it once, then every seat gets it automatically.
        </p>
        <ol className="list-none p-0">
          <Step n={1}>Open <strong>ChatGPT Admin Console</strong> → <strong>Connectors</strong> → <strong>Add custom connector</strong>.</Step>
          <Step n={2}>Paste the workspace URL and select <strong>OAuth</strong> as the auth type — ChatGPT will discover the flow from the endpoint metadata.</Step>
          <Step n={3}>Approve the connector for the seats and workspaces that should use it. Users then enable it in any chat via the connector menu.</Step>
        </ol>
        <Pre>{`URL:  https://api.conductai.ai/guard/mcp
Auth: OAuth  (discovered from /.well-known/oauth-protected-resource/guard/mcp)`}</Pre>
        <p className="text-sm text-stone-500 mt-3">
          The same connector serves both ChatGPT chat and Codex-in-ChatGPT — one registration, both
          surfaces enforced. For open-source Codex CLI (<Code>codex</Code> package), see the section below.
        </p>
      </section>

      <section id="mcp-codex" className="scroll-mt-8">
        <h3 className="text-2xl font-semibold text-stone-900 mb-3">Codex CLI</h3>
        <p className="text-stone-600 mb-3">
          <Code>conduct guard sync</Code> writes to <Code>~/.codex/mcp.json</Code> automatically. Or
          add the block manually:
        </p>
        <Pre>{`# ~/.codex/mcp.json
{
  "mcpServers": {
    "conduct-guard": {
      "type": "http",
      "url": "https://api.conductai.ai/guard/mcp",
      "headers": { "Authorization": "Bearer <your-token>" }
    }
  }
}`}</Pre>
        <p className="text-stone-600 mt-3">Restart your Codex session to pick up the new server.</p>
      </section>

      <section id="mcp-cursor" className="scroll-mt-8">
        <h3 className="text-2xl font-semibold text-stone-900 mb-3">Cursor</h3>
        <ol className="list-none p-0">
          <Step n={1}>Open Cursor → <strong>Settings</strong> → <strong>MCP</strong>.</Step>
          <Step n={2}>Click <strong>Add new MCP server</strong>, paste the workspace URL, save.</Step>
          <Step n={3}>Reload Cursor. Tool calls from agent runs now flow through ConductGuard.</Step>
        </ol>
      </section>

      <section id="mcp-vscode" className="scroll-mt-8">
        <h3 className="text-2xl font-semibold text-stone-900 mb-3">VS Code + GitHub Copilot</h3>
        <p className="text-stone-600 mb-3">
          If you have the GitHub Copilot extension installed in VS Code, <Code>conduct guard sync</Code>{" "}
          detects it and writes the MCP config to <Code>Code/User/mcp.json</Code>. Copilot Chat picks it
          up automatically.
        </p>
        <p className="text-stone-600 mb-3">Or add it manually in your VS Code <Code>settings.json</Code>:</p>
        <Pre>{`{
  "mcp.servers": {
    "conduct-guard": {
      "url": "https://api.conductai.ai/guard/mcp",
      "headers": { "Authorization": "Bearer <your-token>" }
    }
  }
}`}</Pre>
        <p className="text-stone-600 mt-3">Reload the VS Code window to pick up the new server.</p>
      </section>

      <section id="mcp-copilot-cli" className="scroll-mt-8">
        <h3 className="text-2xl font-semibold text-stone-900 mb-3">GitHub Copilot CLI</h3>
        <p className="text-stone-600 mb-3">
          <Code>conduct guard sync</Code> writes to <Code>~/.copilot/mcp-config.json</Code> if the
          Copilot CLI is installed. Or add the block manually:
        </p>
        <Pre>{`# ~/.copilot/mcp-config.json
{
  "mcpServers": {
    "conduct-guard": {
      "type": "http",
      "url": "https://api.conductai.ai/guard/mcp",
      "headers": { "Authorization": "Bearer <your-token>" }
    }
  }
}`}</Pre>
        <p className="text-stone-600 mt-3">
          For project-scoped access, put the same block in <Code>.mcp.json</Code> at the repo root —
          Copilot picks it up per-project.
        </p>
      </section>

      <section id="mcp-devin" className="scroll-mt-8">
        <h3 className="text-2xl font-semibold text-stone-900 mb-3">Devin</h3>
        <p className="text-stone-600 mb-3">
          Devin runs in the cloud, so there&apos;s no local config to sync. Paste the workspace URL into
          Devin directly:
        </p>
        <ol className="list-none p-0">
          <Step n={1}>Open Devin → <strong>Workspace Settings</strong> → <strong>MCP Servers</strong>.</Step>
          <Step n={2}>Click <strong>Add Server</strong>, paste your workspace URL, save.</Step>
          <Step n={3}>Devin&apos;s agents now route tool calls through ConductGuard automatically.</Step>
        </ol>
        <p className="text-sm text-stone-500 mt-3">
          Devin sessions run remotely, so the token in the URL must belong to the workspace member you
          want activity attributed to. Treat it as a service credential.
        </p>
      </section>

      <section id="mcp-windsurf" className="scroll-mt-8">
        <h3 className="text-2xl font-semibold text-stone-900 mb-3">Windsurf</h3>
        <p className="text-stone-600 mb-3">
          <Code>conduct guard sync</Code> writes to <Code>~/.windsurf/mcp.json</Code> if Windsurf is
          installed. Or add the block manually:
        </p>
        <Pre>{`# ~/.windsurf/mcp.json
{
  "mcpServers": {
    "conduct-guard": {
      "url": "https://api.conductai.ai/guard/mcp",
      "headers": { "Authorization": "Bearer <your-token>" }
    }
  }
}`}</Pre>
      </section>

      <section id="mcp-other" className="scroll-mt-8">
        <h3 className="text-2xl font-semibold text-stone-900 mb-3">Other MCP clients</h3>
        <p className="text-stone-600">
          Any other MCP-aware tool follows the same pattern: add your workspace URL to that tool&apos;s
          MCP server config. If you&apos;d like CLI auto-detection added,{" "}
          <a href="https://github.com/sseshachala/conduct-cli/issues" target="_blank" rel="noopener" className="text-indigo-600 underline">open an issue</a>{" "}
          with the tool&apos;s config path.
        </p>
      </section>

      <section id="mcp-enforcement" className="scroll-mt-8">
        <h3 className="text-2xl font-semibold text-stone-900 mb-3">What gets enforced</h3>
        <ul className="list-disc pl-6 space-y-2 text-stone-700">
          <li>Every tool call goes through ConductGuard <strong>before</strong> the model can execute it.</li>
          <li>Policy rules (block / warn / audit) are applied based on your workspace&apos;s active skill packs.</li>
          <li>Spend budgets are checked per-developer and per-team — runs are blocked when limits are exceeded.</li>
          <li>Activity is logged to <a href="/theguard/activity" className="text-indigo-600 underline">Guard → Activity</a> with the rule that fired and the decision.</li>
        </ul>
      </section>

      <section id="mcp-troubleshoot" className="scroll-mt-8">
        <h3 className="text-2xl font-semibold text-stone-900 mb-3">Troubleshooting</h3>
        <div className="space-y-4 text-stone-700">
          <div>
            <p className="font-semibold">Tool calls aren&apos;t getting enforced.</p>
            <p className="text-sm text-stone-600 mt-1">For Claude.ai and Claude for Work, make sure you typed <Code>load mcp</Code> in the chat. MCP servers are per-conversation. For Codex / Cursor / Desktop, restart the client after editing config.</p>
          </div>
          <div>
            <p className="font-semibold">Token revoked or rotated.</p>
            <p className="text-sm text-stone-600 mt-1">Run <Code>conduct guard init</Code> to generate a fresh token, then re-paste the URL into your client.</p>
          </div>
          <div>
            <p className="font-semibold">Policy isn&apos;t matching what I expect.</p>
            <p className="text-sm text-stone-600 mt-1">Open <a href="/theguard/policies" className="text-indigo-600 underline">Guard → Policies</a> and check which rules are active for your workspace.</p>
          </div>
        </div>
      </section>
    </div>
  )
}

function TabIntegrations() {
  return (
    <div className="space-y-16">
      <section id="github">
        <SectionHeading id="github">GitHub</SectionHeading>
        <p className="text-stone-500 text-sm mb-4">Create branches, push commits, open and merge pull requests, trigger Actions.</p>

        <SubHeading>Creating a fine-grained Personal Access Token</SubHeading>
        <ol className="list-decimal list-inside space-y-2 text-sm text-stone-600 mb-6">
          <li>Go to <strong>GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens</strong>.</li>
          <li>Click <strong>Generate new token</strong>.</li>
          <li>Under <strong>Repository access</strong>, select the repos your agents will work with.</li>
          <li>Under <strong>Permissions</strong>, set the following:</li>
        </ol>

        <div className="rounded-xl border border-stone-200 overflow-hidden mb-6">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-stone-50 border-b border-stone-200">
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-stone-500 uppercase tracking-wider">Permission</th>
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-stone-500 uppercase tracking-wider">Access</th>
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-stone-500 uppercase tracking-wider">Needed for</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-stone-100">
              {[
                ["Contents",     "Read and write",          "Create branches, push commits, read code"],
                ["Pull requests","Read and write",          "Open, review, and merge PRs"],
                ["Actions",      "Read and write",          "Trigger and monitor workflow runs"],
                ["Metadata",     "Read-only (required)",    "Auto-granted, cannot be removed"],
              ].map(([perm, access, use]) => (
                <tr key={perm}>
                  <td className="px-4 py-3 font-medium text-stone-800">{perm}</td>
                  <td className="px-4 py-3">
                    <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${access.includes("Read-only") ? "bg-stone-100 text-stone-500" : "bg-green-50 text-green-700"}`}>{access}</span>
                  </td>
                  <td className="px-4 py-3 text-stone-500">{use}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="rounded-xl bg-amber-50 border border-amber-200 px-4 py-3 text-sm text-amber-800">
          <strong>Note:</strong> Fine-grained tokens are repo-scoped. If your agents work across multiple repos,
          either grant access to all repositories or create one token per repo group.
        </div>
      </section>

      <section id="slack">
        <SectionHeading id="slack">Slack</SectionHeading>
        <p className="text-stone-500 text-sm mb-4">Post messages, send DMs, and send approval requests to channels.</p>

        <SubHeading>Getting a Bot Token</SubHeading>
        <ol className="list-decimal list-inside space-y-2 text-sm text-stone-600 mb-4">
          <li>Go to <a href="https://api.slack.com/apps" target="_blank" rel="noopener noreferrer" className="text-indigo-600 hover:underline">api.slack.com/apps</a> and create a new app (from scratch).</li>
          <li>Under <strong>OAuth & Permissions</strong>, add these Bot Token Scopes:</li>
        </ol>

        <div className="rounded-xl border border-stone-200 overflow-hidden mb-4">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-stone-50 border-b border-stone-200">
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-stone-500 uppercase tracking-wider">Scope</th>
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-stone-500 uppercase tracking-wider">Needed for</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-stone-100">
              {[
                ["chat:write",   "Post messages to channels"],
                ["im:write",     "Send direct messages"],
                ["channels:read","List channels to target"],
                ["users:read",   "Resolve user IDs for DMs"],
              ].map(([scope, use]) => (
                <tr key={scope}>
                  <td className="px-4 py-3 font-mono text-xs text-stone-800">{scope}</td>
                  <td className="px-4 py-3 text-stone-500">{use}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <ol className="list-decimal list-inside space-y-2 text-sm text-stone-600" start={3}>
          <li>Click <strong>Install to Workspace</strong> and copy the <strong>Bot User OAuth Token</strong> (<Code>xoxb-…</Code>).</li>
          <li>Paste it into the Slack Connect form in your environment.</li>
        </ol>
      </section>

      <section id="linear">
        <SectionHeading id="linear">Linear</SectionHeading>
        <p className="text-stone-500 text-sm mb-4">Fetch issues, post comments, update issue status.</p>
        <ol className="list-decimal list-inside space-y-2 text-sm text-stone-600">
          <li>Go to <strong>Linear → Settings → API → Personal API keys</strong>.</li>
          <li>Create a new key and copy it (<Code>lin_api_…</Code>).</li>
          <li>Paste it into the Linear Connect form in your environment.</li>
        </ol>
        <p className="text-sm text-stone-500 mt-3">Personal API keys have access to everything your Linear account can access. Use a dedicated service account for production.</p>
      </section>

      <section id="email">
        <SectionHeading id="email">Email</SectionHeading>
        <p className="text-stone-500 text-sm mb-4">Send notifications via Resend (recommended) or SendGrid.</p>

        <SubHeading>Resend (recommended)</SubHeading>
        <ol className="list-decimal list-inside space-y-2 text-sm text-stone-600 mb-6">
          <li>Go to <a href="https://resend.com" target="_blank" rel="noopener noreferrer" className="text-indigo-600 hover:underline">resend.com</a> and create an account.</li>
          <li>Add and verify your sending domain under <strong>Domains</strong>.</li>
          <li>Go to <strong>API Keys</strong> and create a key with <strong>Sending access</strong>.</li>
          <li>Paste it into the Email Connect form (<Code>re_…</Code>).</li>
        </ol>

        <SubHeading>SendGrid (alternative)</SubHeading>
        <ol className="list-decimal list-inside space-y-2 text-sm text-stone-600">
          <li>Go to <strong>SendGrid → Settings → API Keys → Create API Key</strong>.</li>
          <li>Choose <strong>Restricted Access</strong> and enable <strong>Mail Send</strong>.</li>
          <li>Paste the key into the Email Connect form (<Code>SG.…</Code>).</li>
        </ol>
      </section>
    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function DocsPage() {
  const [activeTab, setActiveTab] = useState<TabId>("overview")

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const t = params.get("tab")
    if (t && (VALID_TABS as readonly string[]).includes(t)) {
      setActiveTab(t as TabId)
    }
  }, [])

  const navItems = TAB_NAV[activeTab]

  return (
    <div className="min-h-screen bg-stone-50">
      {/* Tab bar */}
      <div className="bg-white border-b border-stone-200 px-6">
        <div className="max-w-5xl mx-auto flex gap-0">
          {TABS.map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
                activeTab === tab.id
                  ? "border-stone-900 text-stone-900"
                  : "border-transparent text-stone-500 hover:text-stone-700 hover:border-stone-300"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      <div className="max-w-5xl mx-auto px-6 py-12 flex gap-12">
        {/* Sidebar */}
        <nav className="w-48 shrink-0 hidden md:block sticky top-8 self-start">
          <ul className="space-y-1 text-sm text-stone-600">
            {navItems.map(({ href, label }) => (
              <li key={href}>
                <a href={href} className="hover:text-stone-900 transition-colors block py-0.5">{label}</a>
              </li>
            ))}
          </ul>
        </nav>

        {/* Content */}
        <main className="flex-1 min-w-0">
          {activeTab === "overview"        && <TabOverview />}
          {activeTab === "getting-started" && <TabGettingStarted />}
          {activeTab === "api"             && <TabApi />}
          {activeTab === "blocks"          && <TabBlocks />}
          {activeTab === "guard"           && <TabGuard />}
          {activeTab === "mcp-tools"       && <TabMcpTools />}
          {activeTab === "integrations"    && <TabIntegrations />}
        </main>
      </div>
    </div>
  )
}
