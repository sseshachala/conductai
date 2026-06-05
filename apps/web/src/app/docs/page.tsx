"use client"
import { useState } from "react"
import Link from "next/link"

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
  { id: "getting-started", label: "Getting started" },
  { id: "api",             label: "API reference" },
  { id: "blocks",          label: "Blocks" },
  { id: "guard",           label: "ConductGuard" },
  { id: "integrations",    label: "Integrations" },
] as const

type TabId = typeof TABS[number]["id"]

// ── Sidebar sections per tab ───────────────────────────────────────────────────

const TAB_NAV: Record<TabId, { href: string; label: string }[]> = {
  "overview": [
    { href: "#how-it-works", label: "Architecture" },
    { href: "#threat-model", label: "Security & threat model" },
  ],
  "getting-started": [
    { href: "#overview",     label: "Overview" },
    { href: "#environments", label: "Environments" },
    { href: "#cli-install",  label: "CLI — Installation" },
    { href: "#cli-auth",     label: "CLI — Authentication" },
    { href: "#cli-commands", label: "CLI — Commands" },
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
    { href: "#guard-block",  label: "Guard block" },
  ],
  "guard": [
    { href: "#guard",             label: "Overview" },
    { href: "#guard-agent",       label: "Agent guard" },
    { href: "#guard-user-flow",   label: "Developer setup" },
    { href: "#guard-hook",        label: "Hook & tool coverage" },
    { href: "#guard-sync",        label: "Sync & re-sync" },
    { href: "#guard-mcp",         label: "conductguard-mcp" },
    { href: "#guard-spend",       label: "Spend controls" },
    { href: "#guard-savings",     label: "Maximize savings" },
    { href: "#guard-roles",       label: "Roles & permissions" },
    { href: "#guard-onboarding",  label: "Team onboarding" },
    { href: "#guard-scenarios",      label: "Test scenarios" },
    { href: "#guard-token-savings",  label: "RTK + Agent Booster" },
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
          and it turns tickets, PRs, alerts, and incidents into repeatable workflows — triggered by a webhook,
          on a schedule, or on demand. Every run is traced, every outcome is recorded.
        </p>
        <div className="space-y-0">
          {[
            { step: "1", title: "Playbook",  body: "A YAML file that defines what an agent does — its blocks (AI reasoning, tool calls, approval gates), its triggers, and its inputs. Playbooks live in the Conduct marketplace and can be customized.", detail: "Each block is typed: brain (LLM reasoning), tool_call (GitHub, Slack, Linear), approval (human gate), or condition (branching logic). The graph is editable on the canvas." },
            { step: "2", title: "Install",   body: "Installing a playbook creates a workflow in your workspace. Conduct generates the agent graph, registers any GitHub webhooks, and stores the resolved inputs. No code to write.", detail: "Under the hood: a WorkflowVersion record is created from the playbook YAML. The YAML is interpreted at install time — the canvas shows the live graph." },
            { step: "3", title: "Configure", body: "Assign an environment to the agent. An environment holds your credentials (GitHub PAT, Slack token, Linear key, LLM API key). One environment can be shared across many agents.", detail: "Credentials are encrypted with AES-256-GCM before storage. They are decrypted in-process at runtime, scoped to the agent's workspace, and never returned to the client." },
            { step: "4", title: "Run",       body: "A run is created by a trigger: a GitHub webhook (pull_request, issues), a schedule (cron), a manual click in the UI, or a POST to the API. Runs execute the graph block by block.", detail: "The executor advances one block at a time. If a block hits an approval gate, the run is paused and waits for a human decision before proceeding." },
            { step: "5", title: "Trace",     body: "Every run streams live events: block_started, brain_tool_call, block_completed, run_paused. The run detail page shows the full trace in real time via Server-Sent Events.", detail: "Events are written to run_events and are immutable. You can replay any run's trace after the fact — nothing is discarded." },
            { step: "6", title: "Outcome",   body: "When a run completes, Conduct writes a semantic outcome: pr_opened, review_completed, issue_triaged, incident_investigated. Outcomes power the Dashboard metrics.", detail: "The outcome is derived from the playbook slug and the run's state. Pre-outcome runs use heuristic fallback — historical counts never drop." },
            { step: "7", title: "Audit",     body: "Every tool call, decision, and output is in the run_events log. The audit trail is immutable and workspace-scoped — you can always answer 'what did the agent do and why?'", detail: "Run events include the full payload for each action: the GitHub API call, the PR number opened, the Slack message sent. Nothing is summarized away." },
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
            { label: "Credentials encrypted at rest",    detail: "Every secret is encrypted with AES-256-GCM before writing to the database. The encryption key is an env var — never stored alongside the ciphertext." },
            { label: "Workspace isolation",              detail: "Every query is scoped to workspace_id. A credential, agent, or run from workspace A is never accessible to workspace B — enforced at the ORM layer on every request." },
            { label: "Human approval gates",             detail: "Any block can be marked as an approval gate. The run pauses and cannot proceed until an authorized user approves or rejects." },
            { label: "Immutable audit log",              detail: "run_events are append-only. Every tool call, LLM decision, and output is recorded with a timestamp. There is no delete path for run events." },
            { label: "HMAC-validated webhooks",          detail: "GitHub webhook payloads are validated with HMAC-SHA256 before the run is created. Unauthenticated payloads are rejected with 401." },
            { label: "Hashed API keys",                  detail: "API keys are bcrypt-hashed before storage. The plaintext is shown once at creation and never stored. A compromised database does not expose working keys." },
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
            ["Credential proxy",              "Agents call a proxy that holds the token — the executor never sees plaintext. Revocation and rate-limiting become centralizable."],
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
    </div>
  )
}

function TabGettingStarted() {
  return (
    <div className="space-y-16">
      <section id="overview">
        <h1 className="text-3xl font-bold text-stone-900 mb-3">Documentation</h1>
        <p className="text-stone-600 leading-relaxed text-base">
          Conduct AI lets you build and run governed AI automations across your tools — GitHub, Slack, Linear, and more.
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

      <section id="cli-install">
        <SectionHeading id="cli-install">CLI — Installation</SectionHeading>
        <p className="text-stone-500 text-sm mb-4"><Code>conduct-cli</Code> is the official command-line tool for Conduct AI. Requires Python 3.9+.</p>
        <SubHeading>Install from PyPI</SubHeading>
        <Pre>{`pip install conduct-cli

# verify
conduct --version`}</Pre>
        <SubHeading>Or install with pipx (recommended for isolation)</SubHeading>
        <Pre>{`pipx install conduct-cli`}</Pre>
      </section>

      <section id="cli-auth">
        <SectionHeading id="cli-auth">CLI — Authentication</SectionHeading>
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
          <strong>Where is my workspace ID?</strong> Open the app, go to Settings — the workspace ID is shown at the top of the page.
        </div>
      </section>

      <section id="cli-commands">
        <SectionHeading id="cli-commands">CLI — Commands</SectionHeading>
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

        <SubHeading>conduct test — all options</SubHeading>
        <Pre>{`conduct test [agent_name ...] [--all] [--project <name>] [--repo owner/repo]

# Fire test trigger on one agent (streams live output)
conduct test "Autopilot Quick"

# Test all playbook-based agents in the workspace
conduct test --all

# Limit --all to one project, against a specific repo
conduct test --all --project DevOps --repo sseshachala/conductai-testbed-node

# Exit code: 0 if all pass, 1 if any fail — safe to use in CI`}</Pre>
      </section>

      <section id="ci">
        <SectionHeading id="ci">CI / GitHub Actions</SectionHeading>
        <p className="text-stone-500 text-sm mb-4">Run a full smoke test on every push or nightly — install all agents, fire test runs, get a downloadable report.</p>

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
                ["conduct_run_workflow",   "Trigger a workflow run — provide workflow_id and an optional payload"],
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
        <SectionHeading id="api-auth">API — Authentication</SectionHeading>
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
        <SectionHeading id="api-workflows">API — Workflows</SectionHeading>
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
        <SectionHeading id="api-runs">API — Runs</SectionHeading>
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
        <SectionHeading id="api-keys">API — API Keys</SectionHeading>
        <p className="text-stone-500 text-sm mb-5">Manage programmatic access keys for your workspace.</p>

        <Endpoint method="POST" path="/workspaces/{id}/api-keys" desc="Generate a new API key. The plaintext key is returned once — store it immediately.">
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
        <Endpoint method="GET"    path="/workspaces/{id}/api-keys"         desc="List all API keys (prefix and metadata only — plaintext is never returned again)." />
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
            { block: "Memory (read)",    note: "Retrieves past summaries — available as {{recall.entries}} in the brain", amber: true },
            { block: "Fetch Issue",      note: "Gets fresh data from GitHub, Linear, etc." },
            { block: "Brain",            note: "Receives both the current task and recalled context" },
            { block: "Memory (write)",   note: "Records what was done — used by future runs", amber: true },
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
          <strong>No OpenAI key?</strong> Memory falls back to recency-based retrieval — the 5 most recent summaries
          instead of the most semantically similar. You lose similarity search but not the feature.
        </div>
      </section>

      <section id="guard-block">
        <SectionHeading id="guard-block">Guard block</SectionHeading>
        <p className="text-stone-500 text-sm mb-6 leading-relaxed">
          The Guard block evaluates your team's policies mid-workflow. Place it before sensitive operations
          (file writes, deployments, external API calls) to enforce spend limits, blocked actions, and custom regex rules.
        </p>

        <SubHeading>YAML reference</SubHeading>
        <Pre>{`blocks:
  check_policies:
    type: guard
    label: Check team policies
    enforcement_mode: block    # block | warn | audit (default: block)
    context_keys:              # optional — subset of state to evaluate
      - fetch_issue
      - brain
    next: deploy_fix`}</Pre>

        <SubHeading>Fields</SubHeading>
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
                ["enforcement_mode", "block — halt the run on violation. warn — add to warnings, continue. audit — record silently, continue. Default: block."],
                ["context_keys",     "Optional list of block IDs whose state to serialize for policy evaluation. Omit to send the full run state."],
                ["rule_ids",         "Optional list of policy UUIDs to evaluate. Omit to evaluate all active policies."],
              ].map(([field, desc]) => (
                <tr key={field}>
                  <td className="px-4 py-3 font-mono text-xs text-stone-800 align-top">{field}</td>
                  <td className="px-4 py-3 text-xs text-stone-500 leading-relaxed">{desc}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <SubHeading>Output</SubHeading>
        <Pre>{`# Available as {{check_policies.*}} in downstream blocks
{
  "status": "passed",      # passed | violated
  "rules_checked": 4,
  "violations": 0,
  "warnings": []
}`}</Pre>

        <div className="mt-3 rounded-xl bg-amber-50 border border-amber-200 px-4 py-3 text-sm text-amber-800">
          <strong>Guard block requires Guard to be installed.</strong> If no Guard config is found, the block fails
          with installation instructions. Use <code className="font-mono text-xs">warn</code> or{" "}
          <code className="font-mono text-xs">audit</code> mode if you want the workflow to continue without Guard.
        </div>
      </section>
    </div>
  )
}

function TabGuard() {
  return (
    <div className="space-y-16">
      <section id="guard">
        <SectionHeading id="guard">ConductGuard — Overview</SectionHeading>
        <p className="text-stone-500 text-sm mb-6 leading-relaxed">
          ConductGuard is the team policy layer for AI tools. It has two enforcement surfaces:
        </p>
        <div className="rounded-xl border border-stone-200 divide-y divide-stone-100 text-sm mb-8">
          {[
            { label: "Workflow enforcement (Guard block)", detail: "Evaluates policies mid-run inside Conduct workflows. The Guard block checks active team policies against the run state and halts, warns, or audits based on enforcement_mode." },
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
                ["enforcement_mode",   "block | warn | audit — what happens when the rule triggers."],
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
          workflow. No YAML block needed — it fires as an executor hook and records results in the run trace.
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
                ["block", "Run halts immediately — the AI step never executes. Use for hard policy lines (e.g. no access to prod repos)."],
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
          skip the auto-hook for that run only — useful for local dev and debugging. The toggle sends{" "}
          <Code>guard_enabled: false</Code> in the run payload.
        </p>

        <SubHeading>Where to configure</SubHeading>
        <p className="text-stone-500 text-sm mb-2">
          Workspace-level enforcement mode lives in <strong>Guard → Settings → Agent guard</strong>. The selected mode
          applies to all runs in the workspace unless overridden per-run.
        </p>
        <p className="text-stone-500 text-sm">
          Guard must be installed (Guard config present) for the hook to evaluate policies. If Guard is not installed the
          hook skips silently — no runs are blocked.
        </p>
      </section>

      <section id="guard-user-flow">
        <SectionHeading id="guard-user-flow">Developer setup</SectionHeading>
        <p className="text-stone-500 text-sm mb-4 leading-relaxed">
          Guard is provisioned automatically at login — no separate install step. One command wires up the hook,
          registers the MCP server, and downloads active policies.
        </p>

        <Pre>{`# 1. Install the CLI (once)
pip install conduct-cli

# 2. Generate an API key — Settings → API Keys (admin or developer role)
# 3. Login — Guard sets itself up automatically
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
          itself and re-runs the original command — developers never need to manually update.
          Set <Code>CONDUCT_NO_AUTOUPDATE=1</Code> to disable (useful in CI).
        </p>
      </section>

      <section id="guard-sync">
        <SectionHeading id="guard-sync">Sync &amp; re-sync</SectionHeading>
        <p className="text-stone-500 text-sm mb-4 leading-relaxed">
          Each developer machine caches a local copy of the workspace policy file. The CLI polls{" "}
          <Code>GET /guard/policies/sync</Code> every 60 seconds and automatically re-syncs when the server version
          changes — no manual action needed under normal operation.
        </p>

        <SubHeading>When a re-sync is triggered</SubHeading>
        <div className="rounded-xl border border-stone-200 divide-y divide-stone-100 text-sm mb-6">
          {[
            ["Policy created / edited / deleted", "The server version timestamp updates — all machines re-sync within 60s."],
            ["Re-sync button (Guard → Settings)",  "Bumps a resync_requested_at timestamp on the workspace. Machines pick it up on the next poll cycle."],
            ["conduct guard sync (CLI)",           "Forces an immediate pull regardless of cached version. Useful after a network gap or machine restore."],
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
                ["Claude Code", "PreToolUse hook (~/.claude/settings.json)", "Hard block — every tool call intercepted before execution"],
                ["Codex CLI",   "PreToolUse hook (~/.codex/hooks.json)",     "Hard block — same script, same exit-code-2 protocol"],
                ["Cursor",      "MCP server (conductguard-mcp)",             "Advisory — AI sees Guard tools, can self-enforce"],
                ["Windsurf",    "MCP server (conductguard-mcp)",             "Advisory — AI sees Guard tools, can self-enforce"],
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
            ["1. Budget check (cached 5 min)", "Calls GET /guard/spend/budget-check. If the hard cap is hit, exits with code 2 — the tool treats this as a block."],
            ["2. Policy evaluation",           "Loads ~/.conductguard/policy.json. Evaluates match_tool, match_pattern, and match_path_pattern. block exits 2, warn prints a message, audit falls through."],
            ["3. Event posted (async)",        "Every tool call — allowed or blocked — is posted to /guard/events. This powers the Activity log and Active developers metrics."],
            ["4. Slack alert",                 "If a block or warn rule has an alert configured, the Guard API notifies the workspace's Slack channel."],
          ].map(([step, desc]) => (
            <div key={step} className="flex gap-4 px-4 py-3">
              <span className="font-medium text-stone-700 w-52 shrink-0 text-xs">{step}</span>
              <span className="text-stone-500 text-xs leading-relaxed">{desc}</span>
            </div>
          ))}
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
# and ~/.claude/settings.json — whichever exist on the machine.
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
            { tool: "guard_check",  desc: "Evaluates a tool call against active policies. Returns ALLOWED, BLOCKED, or WARNING with the matching rule.", args: "tool_name (str), tool_input (object, optional)" },
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
            ["Alert threshold",      "Optional — percentage of budget at which Slack alerts fire (e.g. 80%). Developers continue past the threshold; the hard limit is the actual block."],
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
          Guard tracks AI spend — but the real leverage is reducing how many tokens your team burns in the first place.
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
                detail: "Symbol-slice reads on top of RTK. Only the relevant function or class enters context — not the whole file.",
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
        <SubHeading>RTK — token optimizer for command output</SubHeading>
        <p className="text-stone-500 text-sm mb-3 leading-relaxed">
          RTK (Rust Token Killer) wraps every shell command Claude Code runs — git, test, build, docker — and strips noise before it
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
          Your team's real savings appear in the <strong>Est. savings</strong> card — not zero.
        </div>

        {/* Agent Booster install block */}
        <SubHeading>Agent Booster — token optimizer for file reads</SubHeading>
        <p className="text-stone-500 text-sm mb-3 leading-relaxed">
          Agent Booster indexes your codebase and serves only the relevant symbol slice when Claude reads a file — the
          function, class, or block it actually needs, not the entire 800-line file. 62% savings on file reads observed in practice.
          Stacks on top of RTK — both run in the same session.
        </p>
        <Pre>{`# Install
pip install agent-booster

# Index your repo (one-time, re-runs incrementally)
booster index

# See your savings
booster gain

# Real output (1 active day, 30 reads):
# Total reads:   30
# Tokens served: 57,764
# Tokens saved:  96,324  (62%)
# Top file:      executor.py — 22,904 tokens saved`}</Pre>
        <div className="mt-3 rounded-xl border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-800 mb-4">
          <strong>Guard integration (coming soon):</strong> Guard reads <Code>booster gain</Code> at each sync alongside RTK.
          The combined RTK + Booster delta is posted as <strong>Est. savings</strong> on the Spend dashboard.
          Admins see exactly how much each tool is contributing.
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
                ["RTK",           "Command output — git, test, build, docker, grep", "85–99%", "rtk gain -f json"],
                ["Agent Booster", "File reads — serves symbol slices, not full files",  "50–70%", "booster gain"],
                ["Combined",      "Both layers stacked in the same session",            "90–94%", "Guard sync posts delta"],
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
          Every workspace member has one of four roles — the single source of truth enforced across Guard, API keys, and the CLI.
        </p>

        <SubHeading>Role definitions</SubHeading>
        <div className="rounded-xl border border-stone-200 divide-y divide-stone-100 text-sm mb-8">
          {[
            { role: "Admin",     color: "bg-purple-50 text-purple-700", desc: "Full access: Guard policies, spend limits, members, settings, API key revoke, and all playbooks." },
            { role: "Security",  color: "bg-blue-50 text-blue-700",     desc: "Full Guard access — create/edit policies and view all activity. View-only spend. Cannot manage members or revoke API keys." },
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
          End-to-end flow for getting a team onto Guard. Each developer runs two commands — everything else is automatic.
        </p>

        <div className="space-y-0">
          {[
            { step: "1", title: "Admin installs Guard",          body: "Settings → Modules → ConductGuard → Install. Guard is provisioned with 18 starter policies. The admin shares the invite code or adds team members directly." },
            { step: "2", title: "Invite your team",              body: "Guard → Members → Invite. Assign roles: Developer for engineers, Security for security team, Viewer for stakeholders." },
            { step: "3", title: "Developer generates an API key",body: "Settings → API Keys → Generate key. Admin and Developer roles can generate keys. The key is tied to their workspace and role." },
            { step: "4", title: "Developer logs in",             body: "One command installs Guard, downloads policies, registers the hook in Claude Code and Codex, and registers the MCP server in Cursor and Windsurf.", code: "pip install conduct-cli\nconduct login --server https://api.conductai.ai --api-key cond_live_xxxx" },
            { step: "5", title: "Guard enforces from this moment",body: "Every AI tool call on the developer's machine is intercepted and checked against workspace policies. All activity — allowed and blocked — appears in the Guard dashboard." },
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
          <strong>CLI auto-updates.</strong> Developers never need to manually upgrade — the CLI checks PyPI on
          every run and upgrades itself if a newer version is available.
        </div>
      </section>

      <section id="guard-scenarios">
        <SectionHeading id="guard-scenarios">Test scenarios</SectionHeading>
        <p className="text-stone-500 text-sm mb-6 leading-relaxed">
          Four end-to-end scenarios that cover every Guard enforcement path. Run them in order after onboarding a developer to verify the full stack — hook, API, Slack, and activity log — is wired correctly.
        </p>

        <Screenshot
          src="/guard-docs/dashboard.png"
          alt="Guard dashboard showing active developers, events, tokens, and cost trend chart"
          caption="Guard dashboard — real-time overview of team AI usage. The cost trend chart breaks down spend by Claude vs Codex."
        />
        <Screenshot
          src="/guard-docs/activity-log.png"
          alt="Guard activity log showing tool calls from Claude Code and Codex with token counts"
          caption="Activity log — every tool call is recorded: who, which AI tool, what command, and token cost. Both Claude Code and Codex sessions appear here."
        />

        {/* Scenario 1 */}
        <div className="mb-12">
          <div className="flex items-center gap-3 mb-3">
            <span className="w-7 h-7 rounded-full bg-stone-900 text-white text-xs font-bold flex items-center justify-center shrink-0">1</span>
            <h3 className="font-semibold text-stone-900 text-base">Workspace hard cap — blocks all tool calls</h3>
          </div>
          <p className="text-sm text-stone-500 mb-4 ml-10">Verify that setting the workspace monthly budget below current spend blocks every subsequent tool call for all users.</p>
          <div className="ml-10">
            <Screenshot
              src="/guard-docs/spend-controls.png"
              alt="Spend Controls panel showing team monthly budget, per-developer limit, alert threshold, and hard cap"
              caption="Guard → Spend — set the Team monthly budget and Hard cap here. Enable 'Hard cap on' to block sessions at 100%."
            />
          </div>
          <div className="ml-10 rounded-xl border border-stone-200 divide-y divide-stone-100 mb-4">
            {[
              { label: "Set workspace budget below current spend", detail: "Guard → Spend → Team monthly budget → set to a value ≤ current spend → Save." },
              { label: "Sync and clear the cache", detail: "conduct guard sync && rm ~/.conductguard/budget_cache.json" },
              { label: "Verify the API", detail: 'GET /guard/spend/budget-check — expect { "hard_blocked": true }' },
              { label: "Test the hook", detail: `echo '{"tool_name":"bash","tool_input":{"command":"ls"},"session_id":"test"}' | python3.11 ~/.conductguard/hook.py\nExpected: exit 2 with budget block message` },
            ].map(({ label, detail }) => (
              <div key={label} className="px-4 py-3">
                <p className="text-xs font-semibold text-stone-700 mb-1">{label}</p>
                <pre className="text-xs text-stone-500 font-mono whitespace-pre-wrap leading-relaxed">{detail}</pre>
              </div>
            ))}
          </div>
          <div className="ml-10 mb-4">
            <p className="text-xs font-semibold text-stone-500 uppercase tracking-wider mb-2">What it looks like in Claude Code (live session, 2026-06-02)</p>
            <Screenshot
              src="/guard-docs/budget-cap-bash-blocked.png"
              alt="Claude Code terminal showing ConductGuard budget hard cap blocking a bash tool call"
              caption="Every tool call — Bash, Read, Edit — is blocked until the budget is raised. The message surfaces inline before the tool runs."
            />
            <Screenshot
              src="/guard-docs/budget-cap-claude-blocked.png"
              alt="Claude Code response showing Guard budget hard cap hit and instructions to raise the workspace budget"
              caption="Claude Code itself reports the block. Guard stops the entire session cold — no workaround from inside the agent."
            />
          </div>
          <div className="ml-10 rounded-xl bg-stone-50 border border-stone-200 px-4 py-2.5 text-xs text-stone-500">
            <strong className="text-stone-700">Teardown:</strong> Raise the budget above current spend → Save. Run conduct guard sync &amp;&amp; rm ~/.conductguard/budget_cache.json.
          </div>
        </div>

        {/* Scenario 2 */}
        <div className="mb-12">
          <div className="flex items-center gap-3 mb-3">
            <span className="w-7 h-7 rounded-full bg-stone-900 text-white text-xs font-bold flex items-center justify-center shrink-0">2</span>
            <h3 className="font-semibold text-stone-900 text-base">Per-developer hard cap — blocks one user</h3>
          </div>
          <p className="text-sm text-stone-500 mb-4 ml-10">Verify that a per-developer spend limit blocks tool calls for a specific user without affecting others.</p>
          <div className="ml-10 rounded-xl border border-stone-200 divide-y divide-stone-100 mb-4">
            {[
              { label: "Set per-developer limit below the user's spend", detail: "Guard → Spend → Default per-developer limit → set below current user spend → Save." },
              { label: "Sync and clear the cache", detail: "conduct guard sync && rm ~/.conductguard/budget_cache.json" },
              { label: "Verify the API with clerk_user_id", detail: "GET /guard/spend/budget-check?workspace_id=<ws>&clerk_user_id=<uid>\nExpect { \"hard_blocked\": true } for this user only." },
              { label: "Test the hook", detail: "Same hook test as Scenario 1 — expect exit 2 with per-user block message." },
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
              caption="Guard → Spend — By Developer table shows each user's sessions, token usage, cost, savings, and individual budget. By AI Tool breakdown shows Claude Code vs Codex split."
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
            <h3 className="font-semibold text-stone-900 text-base">Policy rule — blocks a specific tool call</h3>
          </div>
          <p className="text-sm text-stone-500 mb-4 ml-10">Verify that a Guard policy rule matches a pattern in a tool call, blocks it with a custom message, logs it to the activity feed, and fires a Slack notification.</p>
          <div className="ml-10 rounded-xl border border-stone-200 divide-y divide-stone-100 mb-4">
            {[
              { label: "Create the policy rule", detail: "Guard → Policies → Add rule\nRule ID: no-rm | Match tool: bash | Match pattern: rm | Action: block\nMessage: Deleting files is not allowed. Use git to revert changes instead." },
              { label: "Sync the policy", detail: "conduct guard sync" },
              { label: "Test the hook directly", detail: `echo '{"tool_name":"bash","tool_input":{"command":"rm -rf /tmp/test"},"session_id":"test"}' | python3.11 ~/.conductguard/hook.py; echo "exit: $?"` },
              { label: "Trigger from Claude Code", detail: "Ask Claude to run: bash -c 'rm -rf /tmp/test'\nExpected: PreToolUse hook error — tool call blocked inline." },
              { label: "Verify activity log", detail: "Guard → Activity — find the event. Confirm decision=blocked, rule_id=no-rm, tool_name=bash." },
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
              caption="Claude Code surfaces the block inline — the tool call never runs. The error shows the rule message exactly as configured in Guard → Policies."
            />
          </div>
          <div className="ml-10">
            <Screenshot
              src="/guard-docs/audit-blocked.png"
              alt="Audit log showing blocked bash commands with no-rm rule alongside allowed events"
              caption="Guard → Activity — blocked events are tagged in red with the rule ID. Allowed events show green. Every tool call — blocked or allowed — is recorded."
            />
          </div>
          <div className="ml-10 mb-4">
            <p className="text-xs font-semibold text-stone-500 uppercase tracking-wider mb-2">Real Slack notifications from a live session (2026-06-02)</p>
            <Screenshot
              src="/guard-docs/slack-drop-table-block.png"
              alt="Slack message from ConductAI showing salessupport@organicsphere.com blocked by no-drop-table rule"
              caption="DROP TABLE blocked — Slack fires instantly with the developer email, rule ID, and policy message."
            />
            <Screenshot
              src="/guard-docs/slack-file-delete-block.png"
              alt="Slack showing multiple no-rm blocks for salessupport@organicsphere.com in rapid succession"
              caption="Multiple blocks in the same session — each blocked tool call fires its own Slack message in real time."
            />
            <Screenshot
              src="/guard-docs/Password-keys-compromise.png"
              alt="Slack message from ConductAI showing salessupport@organicsphere.com warned by no-hardcoded-secrets rule in claude-code"
              caption="Hardcoded secret detected — Guard warns the developer in Slack instantly with the rule ID and policy message. The developer email is always surfaced so managers know exactly who triggered the alert."
            />
            <p className="text-xs text-stone-400 mt-1 leading-relaxed">The block fires on every blocked call. Spend alerts are deduped per 5% increment — policy blocks are not deduped.</p>
          </div>
          <div className="ml-10 rounded-xl bg-stone-50 border border-stone-200 px-4 py-2.5 text-xs text-stone-500">
            <strong className="text-stone-700">Teardown:</strong> Guard → Policies → delete no-rm → Save. Run conduct guard sync.
          </div>
        </div>

        {/* Scenario 4 */}
        <div className="mb-12">
          <div className="flex items-center gap-3 mb-3">
            <span className="w-7 h-7 rounded-full bg-stone-900 text-white text-xs font-bold flex items-center justify-center shrink-0">4</span>
            <h3 className="font-semibold text-stone-900 text-base">Alert threshold — fires Slack notification</h3>
          </div>
          <p className="text-sm text-stone-500 mb-4 ml-10">Verify that spend crossing the alert threshold triggers a Slack notification, deduped per 5% increment.</p>
          <div className="ml-10">
            <Screenshot
              src="/guard-docs/settings-notifications.png"
              alt="Guard Settings page showing Slack channel input and notification toggles for block/warn and budget threshold"
              caption="Guard → Settings — configure the Slack channel and toggle which events trigger notifications. Both toggles must be on to receive spend alerts and block notifications."
            />
          </div>
          <div className="ml-10 rounded-xl border border-stone-200 divide-y divide-stone-100 mb-4">
            {[
              { label: "Set alert threshold below current spend %", detail: "Guard → Spend → Alert threshold → set below current spend percentage → Save.\nExample: if spend is at 85% of budget, set threshold to 80%." },
              { label: "Trigger any tool call", detail: "In a Claude Code session, trigger any passing tool call (e.g. list files). The hook checks spend on every call." },
              { label: "Verify Slack", detail: "Expected: ⚠️ Guard spend alert (workspace-wide): $X.XX of $Y.YY used (Z%) — alert threshold 80% reached" },
            ].map(({ label, detail }) => (
              <div key={label} className="px-4 py-3">
                <p className="text-xs font-semibold text-stone-700 mb-1">{label}</p>
                <pre className="text-xs text-stone-500 font-mono whitespace-pre-wrap leading-relaxed">{detail}</pre>
              </div>
            ))}
          </div>
          <div className="ml-10 mb-4">
            <p className="text-xs font-semibold text-stone-500 uppercase tracking-wider mb-2">Real Slack output from a live session (2026-06-02)</p>
            <pre className="bg-stone-900 text-green-400 rounded-xl px-4 py-3 text-xs font-mono overflow-x-auto leading-relaxed">{`7:45 PM  ⚠️ Guard spend alert (workspace-wide): $25.05 of $30.00 used (83%) — alert threshold 80% reached
7:50 PM  ⚠️ Guard spend alert (workspace-wide): $27.39 of $30.00 used (91%) — alert threshold 80% reached
7:52 PM  ⚠️ Guard spend alert (workspace-wide): $28.60 of $30.00 used (95%) — alert threshold 80% reached
7:53 PM  ⚠️ Guard spend alert (workspace-wide): $30.23 of $30.00 used (101%) — alert threshold 80% reached`}</pre>
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
                ["Wrong Python binary", "Apple system Python has network restrictions — hook fails silently", "Re-run conduct guard sync (auto-detects Homebrew Python since v0.4.20)"],
                ["Missing clerk_user_id", "Per-user budget checks silently skipped", "Run conduct guard sync — added in v0.4.16"],
                ["Alert dedup", "Alerts fire once per 5% increment — won't re-fire in the same band", "Adjust spend or threshold to cross a new 5% boundary"],
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
          Together they cut the token footprint of every Claude Code, Cursor, and Codex session — and Guard surfaces the combined savings on the dashboard automatically.
        </p>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-8">
          <div className="rounded-xl border border-stone-200 px-5 py-4">
            <div className="flex items-center gap-2 mb-2">
              <span className="text-xs font-bold px-2 py-0.5 rounded bg-stone-900 text-white font-mono">RTK</span>
              <span className="text-xs text-stone-400">Rust Token Killer</span>
            </div>
            <p className="text-sm text-stone-600 leading-relaxed mb-3">
              Wraps every CLI tool your agent calls — <Code>git</Code>, <Code>pytest</Code>, <Code>tsc</Code>, <Code>docker</Code> — and strips noise before the output reaches the model. Typical savings: <strong>60–99%</strong> per command.
            </p>
            <Pre>{`pip install rtk\nrtk git status   # 80% fewer tokens\nrtk pytest       # failures only, 90% savings`}</Pre>
          </div>
          <div className="rounded-xl border border-stone-200 px-5 py-4">
            <div className="flex items-center gap-2 mb-2">
              <span className="text-xs font-bold px-2 py-0.5 rounded bg-indigo-600 text-white font-mono">Booster</span>
              <span className="text-xs text-stone-400">Agent Booster</span>
            </div>
            <p className="text-sm text-stone-600 leading-relaxed mb-3">
              Indexes your codebase with AST + vector embeddings. Intercepts raw file reads and grep calls, returning only the relevant symbol slices. Typical savings: <strong>60–70%</strong> per read. Hooks are active immediately after install — no session restart needed.
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
          Every time a developer runs <Code>conduct guard sync</Code>, the CLI reads <Code>rtk gain</Code> and <Code>booster gain</Code> locally and posts the totals to the Guard API. The <strong>Est. savings</strong> card on the Guard dashboard aggregates this across all team members in real time — no extra setup required.
        </p>
        <Pre>{`conduct guard sync\n\n#   Policy refreshed: 19 rule(s)\n#   Hook script updated\n#   Savings reported`}</Pre>

        <div className="mt-8 rounded-xl bg-indigo-50 border border-indigo-200 px-6 py-5 flex flex-col sm:flex-row sm:items-center gap-4">
          <div className="flex-1">
            <p className="font-semibold text-indigo-900 mb-1">Add Agent Booster to your workflow</p>
            <p className="text-sm text-indigo-700 leading-relaxed">
              One command indexes your repo, wires the hooks, and starts tracking savings — no session restart needed.
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

  const navItems = TAB_NAV[activeTab]

  return (
    <div className="min-h-screen bg-stone-50">
      <header className="bg-white border-b border-stone-200 px-6 py-4 flex items-center justify-between">
        <Link href="/" className="flex items-center gap-2">
          <img src="/logo.png" alt="Conduct AI" className="h-8 w-auto" />
        </Link>
        <Link href="/dashboard" className="text-sm text-stone-500 hover:text-stone-900 transition-colors">
          Open app →
        </Link>
      </header>

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
          {activeTab === "integrations"    && <TabIntegrations />}
        </main>
      </div>
    </div>
  )
}
