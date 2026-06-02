import Link from "next/link"

export const metadata = { title: "Docs — Conduct AI" }

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

function Badge({ children, color = "stone" }: { children: string; color?: "stone" | "green" | "blue" | "amber" | "purple" }) {
  const colors = {
    stone:  "bg-stone-100 text-stone-600",
    green:  "bg-green-50 text-green-700",
    blue:   "bg-blue-50 text-blue-700",
    amber:  "bg-amber-50 text-amber-700",
    purple: "bg-purple-50 text-purple-700",
  }
  return <span className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full ${colors[color]}`}>{children}</span>
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

export default function DocsPage() {
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

      <div className="max-w-5xl mx-auto px-6 py-12 flex gap-12">

        {/* Sidebar nav */}
        <nav className="w-52 shrink-0 hidden md:block sticky top-8 self-start">
          <p className="text-[10px] font-semibold text-stone-400 uppercase tracking-wider mb-3">How it works</p>
          <ul className="space-y-1 text-sm text-stone-600">
            <li><a href="#how-it-works" className="hover:text-stone-900 transition-colors block py-0.5">Architecture</a></li>
            <li><a href="#threat-model" className="hover:text-stone-900 transition-colors block py-0.5">Security & threat model</a></li>
          </ul>

          <p className="text-[10px] font-semibold text-stone-400 uppercase tracking-wider mt-6 mb-3">Getting started</p>
          <ul className="space-y-1 text-sm text-stone-600">
            <li><a href="#overview" className="hover:text-stone-900 transition-colors block py-0.5">Overview</a></li>
            <li><a href="#environments" className="hover:text-stone-900 transition-colors block py-0.5">Environments</a></li>
          </ul>

          <p className="text-[10px] font-semibold text-stone-400 uppercase tracking-wider mt-6 mb-3">CLI</p>
          <ul className="space-y-1 text-sm text-stone-600">
            <li><a href="#cli-install" className="hover:text-stone-900 transition-colors block py-0.5">Installation</a></li>
            <li><a href="#cli-auth" className="hover:text-stone-900 transition-colors block py-0.5">Authentication</a></li>
            <li><a href="#cli-commands" className="hover:text-stone-900 transition-colors block py-0.5">Commands</a></li>
          </ul>

          <p className="text-[10px] font-semibold text-stone-400 uppercase tracking-wider mt-6 mb-3">Testing</p>
          <ul className="space-y-1 text-sm text-stone-600">
            <li><a href="#ci" className="hover:text-stone-900 transition-colors block py-0.5">CI / GitHub Actions</a></li>
          </ul>

          <p className="text-[10px] font-semibold text-stone-400 uppercase tracking-wider mt-6 mb-3">API Reference</p>
          <ul className="space-y-1 text-sm text-stone-600">
            <li><a href="#api-auth" className="hover:text-stone-900 transition-colors block py-0.5">Authentication</a></li>
            <li><a href="#api-workflows" className="hover:text-stone-900 transition-colors block py-0.5">Workflows</a></li>
            <li><a href="#api-runs" className="hover:text-stone-900 transition-colors block py-0.5">Runs</a></li>
            <li><a href="#api-keys" className="hover:text-stone-900 transition-colors block py-0.5">API Keys</a></li>
          </ul>

          <p className="text-[10px] font-semibold text-stone-400 uppercase tracking-wider mt-6 mb-3">Blocks</p>
          <ul className="space-y-1 text-sm text-stone-600">
            <li><a href="#memory-block" className="hover:text-stone-900 transition-colors block py-0.5">Memory block</a></li>
            <li><a href="#guard-block" className="hover:text-stone-900 transition-colors block py-0.5">Guard block</a></li>
          </ul>

          <p className="text-[10px] font-semibold text-stone-400 uppercase tracking-wider mt-6 mb-3">ConductGuard</p>
          <ul className="space-y-1 text-sm text-stone-600">
            <li><a href="#guard" className="hover:text-stone-900 transition-colors block py-0.5">Overview</a></li>
            <li><a href="#guard-user-flow" className="hover:text-stone-900 transition-colors block py-0.5">Developer setup</a></li>
            <li><a href="#guard-hook" className="hover:text-stone-900 transition-colors block py-0.5">Hook & tool coverage</a></li>
            <li><a href="#guard-mcp" className="hover:text-stone-900 transition-colors block py-0.5">conductguard-mcp</a></li>
            <li><a href="#guard-spend" className="hover:text-stone-900 transition-colors block py-0.5">Spend controls</a></li>
            <li><a href="#guard-roles" className="hover:text-stone-900 transition-colors block py-0.5">Roles & permissions</a></li>
            <li><a href="#guard-onboarding" className="hover:text-stone-900 transition-colors block py-0.5">Team onboarding</a></li>
          </ul>

          <p className="text-[10px] font-semibold text-stone-400 uppercase tracking-wider mt-6 mb-3">Integrations</p>
          <ul className="space-y-1 text-sm text-stone-600">
            <li><a href="#github" className="hover:text-stone-900 transition-colors block py-0.5">GitHub</a></li>
            <li><a href="#slack" className="hover:text-stone-900 transition-colors block py-0.5">Slack</a></li>
            <li><a href="#linear" className="hover:text-stone-900 transition-colors block py-0.5">Linear</a></li>
            <li><a href="#email" className="hover:text-stone-900 transition-colors block py-0.5">Email</a></li>
          </ul>
        </nav>

        {/* Content */}
        <main className="flex-1 min-w-0 space-y-16">

          {/* ── How Conduct works ── */}
          <section id="how-it-works">
            <h1 className="text-3xl font-bold text-stone-900 mb-3">How Conduct works</h1>
            <p className="text-stone-600 leading-relaxed text-base mb-10">
              Conduct is a governed automation layer for AI agents. You install a playbook, configure it once,
              and it turns tickets, PRs, alerts, and incidents into repeatable workflows — triggered by a webhook, on a schedule, or on demand.
              Every run is traced, every outcome is recorded.
            </p>

            <div className="space-y-0">
              {[
                {
                  step: "1",
                  title: "Playbook",
                  body: "A YAML file that defines what an agent does — its blocks (AI reasoning, tool calls, approval gates), its triggers, and its inputs. Playbooks live in the Conduct marketplace and can be customized.",
                  detail: "Each block is typed: brain (LLM reasoning), tool_call (GitHub, Slack, Linear), approval (human gate), or condition (branching logic). The graph is editable on the canvas.",
                },
                {
                  step: "2",
                  title: "Install",
                  body: "Installing a playbook creates a workflow in your workspace. Conduct generates the agent graph, registers any GitHub webhooks, and stores the resolved inputs. No code to write.",
                  detail: "Under the hood: a WorkflowVersion record is created from the playbook YAML. The YAML is interpreted at install time — the canvas shows the live graph.",
                },
                {
                  step: "3",
                  title: "Configure",
                  body: "Assign an environment to the agent. An environment holds your credentials (GitHub PAT, Slack token, Linear key, LLM API key). One environment can be shared across many agents.",
                  detail: "Credentials are encrypted with AES-256-GCM before storage. They are decrypted in-process at runtime, scoped to the agent's workspace, and never returned to the client.",
                },
                {
                  step: "4",
                  title: "Run",
                  body: "A run is created by a trigger: a GitHub webhook (pull_request, issues), a schedule (cron), a manual click in the UI, or a POST to the API. Runs execute the graph block by block.",
                  detail: "The executor advances one block at a time. If a block hits an approval gate, the run is paused and waits for a human decision before proceeding.",
                },
                {
                  step: "5",
                  title: "Trace",
                  body: "Every run streams live events: block_started, brain_tool_call, block_completed, run_paused. The run detail page shows the full trace in real time via Server-Sent Events.",
                  detail: "Events are written to run_events and are immutable. You can replay any run's trace after the fact — nothing is discarded.",
                },
                {
                  step: "6",
                  title: "Outcome",
                  body: "When a run completes, Conduct writes a semantic outcome: pr_opened, review_completed, issue_triaged, incident_investigated. Outcomes power the Dashboard metrics.",
                  detail: "The outcome is derived from the playbook slug and the run's state (e.g. a pr_url in the state means a PR was opened). Pre-outcome runs use heuristic fallback — historical counts never drop.",
                },
                {
                  step: "7",
                  title: "Audit",
                  body: "Every tool call, decision, and output is in the run_events log. The audit trail is immutable and workspace-scoped — you can always answer 'what did the agent do and why?'",
                  detail: "Run events include the full payload for each action: the GitHub API call, the PR number opened, the Slack message sent. Nothing is summarized away.",
                },
              ].map(({ step, title, body, detail }) => (
                <div key={step} className="flex gap-6 pb-8 relative">
                  <div className="flex flex-col items-center">
                    <div className="w-8 h-8 rounded-full bg-stone-900 text-white text-sm font-bold flex items-center justify-center shrink-0 z-10">
                      {step}
                    </div>
                    {parseInt(step) < 7 && (
                      <div className="w-px flex-1 bg-stone-200 mt-2" />
                    )}
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

          {/* ── Security & Threat Model ── */}
          <section id="threat-model">
            <SectionHeading id="threat-model">Security & threat model</SectionHeading>
            <p className="text-stone-500 text-sm mb-6">
              What Conduct protects today, what it does not, and where we're headed.
              We believe you deserve an honest answer to "is it safe to give this agent my GitHub token?"
            </p>

            <SubHeading>What we protect</SubHeading>
            <div className="rounded-xl border border-stone-200 divide-y divide-stone-100 text-sm mb-6">
              {[
                {
                  label: "Credentials encrypted at rest",
                  detail: "Every secret is encrypted with AES-256-GCM before writing to the database. The encryption key is an env var — never stored alongside the ciphertext.",
                },
                {
                  label: "Workspace isolation",
                  detail: "Every query is scoped to workspace_id. A credential, agent, or run from workspace A is never accessible to workspace B — enforced at the ORM layer on every request.",
                },
                {
                  label: "Human approval gates",
                  detail: "Any block can be marked as an approval gate. The run pauses and cannot proceed until an authorized user approves or rejects. Useful for 'open the PR, but don't merge without me'.",
                },
                {
                  label: "Immutable audit log",
                  detail: "run_events are append-only. Every tool call, LLM decision, and output is recorded with a timestamp. There is no delete path for run events.",
                },
                {
                  label: "HMAC-validated webhooks",
                  detail: "GitHub webhook payloads are validated with HMAC-SHA256 before the run is created. Unauthenticated payloads are rejected with 401.",
                },
                {
                  label: "Hashed API keys",
                  detail: "API keys are bcrypt-hashed before storage. The plaintext is shown once at creation and never stored. A compromised database does not expose working keys.",
                },
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
                {
                  label: "Credential mediation",
                  detail: "Credentials are decrypted and passed to the executor at runtime. The executor sees the plaintext token. A compromised executor process could exfiltrate it. Mitigation: the executor runs server-side, not client-side.",
                },
                {
                  label: "Network egress allowlist",
                  detail: "Agents can call any external URL during a run (GitHub, Slack, custom APIs). There is no per-environment allowlist today. A misconfigured or malicious playbook could make arbitrary outbound requests.",
                },
                {
                  label: "Runtime isolation depends on execution backend",
                  detail: "Some blocks execute in the API worker while sandbox-backed agent execution can run in workspace-scoped Modal or SSH environments. Treat sandbox isolation as a configured runtime property, not a blanket guarantee across every block.",
                },
                {
                  label: "Playbook static analysis",
                  detail: "Conduct does not analyze a playbook's tool calls before you install it. You should review the YAML before installing third-party or custom playbooks — especially what tools they call and what inputs they send.",
                },
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
                ["Credential proxy", "Agents call a proxy that holds the token — the executor never sees plaintext. Revocation and rate-limiting become centralizable."],
                ["Egress allowlist per environment", "Each environment declares which hostnames agents are allowed to call. Requests outside the allowlist are rejected before execution."],
                ["Per-block process isolation", "Every execution path gets isolated at the process or sandbox boundary. A crashing block cannot affect others and cannot access another run's memory."],
                ["Playbook supply chain analysis", "Static analysis of YAML before install: what tools are called, what data is read, what external endpoints are contacted. Surfaced as a risk summary before you confirm."],
              ].map(([label, detail]) => (
                <div key={label} className="flex gap-4 px-4 py-3">
                  <span className="font-medium text-stone-700 w-48 shrink-0">{label}</span>
                  <span className="text-stone-500 text-xs leading-relaxed">{detail}</span>
                </div>
              ))}
            </div>

            <div className="rounded-xl bg-stone-100 border border-stone-200 px-4 py-3 text-sm text-stone-600">
              <strong>Questions or concerns?</strong> Email <a href="mailto:security@conductai.ai" className="text-indigo-600 hover:underline">security@conductai.ai</a>.
              For responsible disclosure, please include a description of the issue and steps to reproduce.
            </div>
          </section>

          {/* ── Overview ── */}
          <section id="overview">
            <h1 className="text-3xl font-bold text-stone-900 mb-3">Documentation</h1>
            <p className="text-stone-600 leading-relaxed text-base">
              Conduct AI lets you build and run governed AI automations across your tools — GitHub, Slack, Linear, and more.
              Agents are configured on a canvas, scoped to an environment, and triggered on-demand, by webhook, or on a schedule.
            </p>
          </section>

          {/* ── Environments ── */}
          <section id="environments">
            <SectionHeading id="environments">Environments</SectionHeading>
            <p className="text-stone-500 text-sm mb-4">A named set of credentials (e.g. <Code>production</Code>, <Code>staging</Code>) assigned to an agent.</p>
            <ol className="list-decimal list-inside space-y-2 text-sm text-stone-600">
              <li>Go to <strong>Settings → Environments</strong> and create an environment.</li>
              <li>Click the environment and connect your integrations (GitHub, Slack, etc.).</li>
              <li>Open an agent on the canvas, go to <strong>Settings</strong>, and assign the environment.</li>
            </ol>
          </section>

          {/* ── CLI Installation ── */}
          <section id="cli-install">
            <SectionHeading id="cli-install">CLI — Installation</SectionHeading>
            <p className="text-stone-500 text-sm mb-4">
              <Code>conduct-cli</Code> is the official command-line tool for Conduct AI. Requires Python 3.9+.
            </p>

            <SubHeading>Install from PyPI</SubHeading>
            <Pre>{`pip install conduct-cli

# verify
conduct --version`}</Pre>

            <SubHeading>Or install with pipx (recommended for isolation)</SubHeading>
            <Pre>{`pipx install conduct-cli`}</Pre>
          </section>

          {/* ── CLI Auth ── */}
          <section id="cli-auth">
            <SectionHeading id="cli-auth">CLI — Authentication</SectionHeading>
            <p className="text-stone-600 text-sm mb-4">
              Generate an API key from <strong>Settings → API Keys</strong> in the dashboard.
              Keys start with <Code>cond_live_</Code> and are shown only once — copy it before closing the modal.
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

          {/* ── CLI Commands ── */}
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
                    ["conduct login", "Save connection config to ~/.conduct/config.json"],
                    ["conduct projects", "List all projects in the workspace"],
                    ["conduct create <name>", "Create a project"],
                    ["conduct delete <name> --yes", "Delete a project and all its agents"],
                    ["conduct reset <name> --yes", "Remove all agents from a project (clean slate)"],
                    ["conduct playbooks", "Browse all available playbooks"],
                    ["conduct playbooks <slug>", "Show detail and inputs for one playbook"],
                    ["conduct install <slug>", "Install one agent from a playbook into a project"],
                    ["conduct install-all --project <p>", "Install all playbooks into a project"],
                    ["conduct agents", "List all installed agents in the workspace"],
                    ["conduct agents --project <name>", "Filter agents by project name"],
                    ["conduct test <name>", "Fire test trigger on a named agent, stream live output"],
                    ["conduct test <n1> <n2> ...", "Test multiple named agents in sequence"],
                    ["conduct test --all", "Test every playbook-based agent in sequence"],
                    ["conduct test --all --project <name>", "Limit --all to one project"],
                    ["conduct test --all --repo owner/repo", "Override test repo for all agents"],
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

            <SubHeading>Install a single agent</SubHeading>
            <Pre>{`conduct install autopilot-quick \\
  --project DevOps \\
  --repo    myorg/my-repo

# Override a specific input
conduct install pr-reviewer \\
  --project DevOps \\
  --input   model=claude-sonnet-4-6`}</Pre>

            <SubHeading>conduct test — all options</SubHeading>
            <Pre>{`conduct test [agent_name ...] [--all] [--project <name>] [--repo owner/repo]

# Fire test trigger on one agent (streams live output)
conduct test "Autopilot Quick"

# Test multiple agents by name
conduct test "Autopilot Quick" "PR Reviewer" "Issue Triage"

# Test all playbook-based agents in the workspace
conduct test --all

# Limit --all to one project
conduct test --all --project DevOps

# Override the repo in the test payload (e.g. use a testbed repo)
conduct test --all --project DevOps --repo myorg/my-testbed

# Combine: all agents in a project, against a specific repo
conduct test --all --project DevOps --repo sseshachala/conductai-testbed-node

# Exit code: 0 if all pass, 1 if any fail — safe to use in CI`}</Pre>

            <div className="rounded-xl bg-stone-100 border border-stone-200 px-4 py-3 text-sm text-stone-700 mt-3">
              <strong>--repo</strong> replaces the <code className="font-mono text-xs bg-white px-1 rounded">clone_url</code> and <code className="font-mono text-xs bg-white px-1 rounded">repo</code> fields in the <code className="font-mono text-xs bg-white px-1 rounded">test_trigger</code> payload.
              Useful for pointing agents at a small testbed repo so they don't run against your production codebase.
            </div>

            <SubHeading>Dependency path</SubHeading>
            <p className="text-stone-600 text-sm mb-3">
              <code className="font-mono text-xs bg-stone-100 px-1 rounded">conduct test</code> requires the agent to already be installed.
              Every agent requires <code className="font-mono text-xs bg-stone-100 px-1 rounded">--repo</code> at install time — the repo is baked in and used at every run.
            </p>
            <Pre>{`# PR-based agents (security-scanner, pr-reviewer, copilot-reviewer)
# Step 1 — install and register GitHub webhook
conduct install security_scanner \\
  --project MyProject \\
  --repo    owner/repo

# Step 2 — test against a real PR (--pr injects PR number into the payload)
conduct test "Security Scanner" \\
  --repo owner/repo \\
  --pr   246`}</Pre>
            <Pre>{`# Issue-based agents (autopilot-quick, autopilot-full, issue-triage)
# Step 1 — install and register GitHub webhook
conduct install autopilot_quick \\
  --project MyProject \\
  --repo    owner/repo

# Step 2 — test (uses built-in dummy issue payload)
conduct test "Autopilot Quick" --repo owner/repo`}</Pre>
            <Pre>{`# Scheduled / inbound-webhook agents (dependency-updater, incident-responder)
# Step 1 — install (no GitHub webhook registered; repo stored as agent context)
conduct install dependency_updater \\
  --project MyProject \\
  --repo    owner/repo

# Step 2 — test (agent clones the repo and scans dependencies)
conduct test "Dependency Updater" --repo owner/repo`}</Pre>
          </section>

          {/* ── CI / GitHub Actions ── */}
          <section id="ci">
            <SectionHeading id="ci">CI / GitHub Actions</SectionHeading>
            <p className="text-stone-500 text-sm mb-4">
              Run a full smoke test on every push or on a nightly schedule — install all agents, fire test runs, and get a downloadable report.
            </p>

            <SubHeading>1. Add the workflow file</SubHeading>
            <p className="text-stone-600 text-sm mb-3">
              Copy <Code>.github/workflows/smoke_test.yml</Code> from the <Code>conductai</Code> repo into your own repository,
              or create it with the contents below.
            </p>
            <Pre>{`# .github/workflows/smoke_test.yml
name: Nightly Smoke Test

on:
  schedule:
    - cron: '0 6 * * *'   # 1 AM CDT every night
  workflow_dispatch:       # also triggerable manually from GitHub UI
    inputs:
      project:
        description: 'Conduct project name'
        default: 'DevOps'
      repo:
        description: 'Target GitHub repo (owner/repo)'
        default: 'myorg/my-repo'

jobs:
  smoke:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    env:
      PROJECT: \${{ github.event.inputs.project || 'DevOps' }}
      REPO:    \${{ github.event.inputs.repo    || 'myorg/my-repo' }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install conduct CLI
        run: pip install conduct-cli --quiet

      - name: Write conduct config
        run: |
          mkdir -p ~/.conduct
          cat > ~/.conduct/config.json <<EOF
          {
            "server":       "\${{ secrets.CONDUCT_SERVER }}",
            "workspace_id": "\${{ secrets.CONDUCT_WORKSPACE_ID }}",
            "api_key":      "\${{ secrets.CONDUCT_API_KEY }}"
          }
          EOF

      - name: Run smoke test
        id: smoke
        run: |
          bash scripts/smoke_test.sh \\
            --project "$PROJECT" \\
            --repo    "$REPO"
        continue-on-error: true

      - name: Upload report
        uses: actions/upload-artifact@v4
        with:
          name: smoke-report-\${{ github.run_id }}
          path: reports/smoke_*.txt
          retention-days: 30

      - name: Fail if smoke test failed
        if: steps.smoke.outcome == 'failure'
        run: exit 1`}</Pre>

            <SubHeading>2. Add GitHub secrets</SubHeading>
            <p className="text-stone-600 text-sm mb-3">
              Go to your repo → <strong>Settings → Secrets and variables → Actions → New repository secret</strong> and add:
            </p>
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
                    ["CONDUCT_SERVER", "https://api.conductai.ai"],
                    ["CONDUCT_WORKSPACE_ID", "Your workspace UUID (Settings page)"],
                    ["CONDUCT_API_KEY", "A cond_live_… key (Settings → API Keys)"],
                  ].map(([secret, value]) => (
                    <tr key={secret}>
                      <td className="px-4 py-3 font-mono text-xs text-stone-800">{secret}</td>
                      <td className="px-4 py-3 text-stone-500">{value}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <SubHeading>3. Run manually from GitHub UI</SubHeading>
            <p className="text-stone-600 text-sm mb-3">
              Go to <strong>Actions → Nightly Smoke Test → Run workflow</strong>. You can override the project name, repo, and PR number inline — useful for testing a branch before merging.
            </p>

            <SubHeading>What the smoke test does</SubHeading>
            <div className="rounded-xl border border-stone-200 divide-y divide-stone-100 text-sm mb-4">
              {[
                ["Step 1 — Reset", "Deletes all agents in the project for a clean slate."],
                ["Step 2 — Install all", "Installs every Conduct playbook against your repo."],
                ["Step 3 — Test all", "Fires a test run per agent, streams output, collects pass/fail."],
                ["Report", "Saved to reports/smoke_TIMESTAMP.txt and uploaded as a CI artifact."],
              ].map(([step, desc]) => (
                <div key={step} className="flex gap-4 px-4 py-3">
                  <span className="font-medium text-stone-700 w-40 shrink-0">{step}</span>
                  <span className="text-stone-500">{desc}</span>
                </div>
              ))}
            </div>

            <div className="rounded-xl bg-stone-100 border border-stone-200 px-4 py-3 text-sm text-stone-700">
              <strong>Exit code:</strong> the workflow fails (red check, email notification) if any agent test fails.
              Exit 0 only when every agent passes.
            </div>
          </section>

          {/* ── API Auth ── */}
          <section id="api-auth">
            <SectionHeading id="api-auth">API — Authentication</SectionHeading>
            <p className="text-stone-600 text-sm mb-4">
              All API requests require two headers: an <strong>Authorization</strong> bearer token and a <strong>workspace ID</strong>.
            </p>

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

          {/* ── API Workflows ── */}
          <section id="api-workflows">
            <SectionHeading id="api-workflows">API — Workflows</SectionHeading>
            <p className="text-stone-500 text-sm mb-5">Manage and trigger agents.</p>

            <Endpoint method="GET" path="/workflows" desc="List all workflows in the workspace.">
              <Pre>{`curl https://api.conductai.ai/workflows \\
  -H "X-Api-Key: cond_live_xxx" \\
  -H "X-Workspace-Id: <workspace-id>"

# Response
[
  {
    "id": "53ab8977-...",
    "name": "Autopilot Quick",
    "status": "active",
    "playbook_slug": "autopilot-quick",
    "project_id": "a1b2c3d4-..."
  }
]`}</Pre>
            </Endpoint>

            <Endpoint method="GET" path="/workflows/{id}" desc="Get a workflow including its graph and current version.">
              <Pre>{`curl https://api.conductai.ai/workflows/53ab8977-... \\
  -H "X-Api-Key: cond_live_xxx" \\
  -H "X-Workspace-Id: <workspace-id>"`}</Pre>
            </Endpoint>

            <Endpoint method="POST" path="/workflows/{id}/trigger" desc="Fire a test trigger using the playbook's built-in test payload. Returns a run_id immediately.">
              <Pre>{`curl -X POST https://api.conductai.ai/workflows/53ab8977-.../trigger \\
  -H "X-Api-Key: cond_live_xxx" \\
  -H "X-Workspace-Id: <workspace-id>" \\
  -H "Content-Type: application/json" \\
  -d '{}'

# Response
{
  "ok": true,
  "run_id": "b858c434-...",
  "max_turns": 20
}`}</Pre>
            </Endpoint>
          </section>

          {/* ── API Runs ── */}
          <section id="api-runs">
            <SectionHeading id="api-runs">API — Runs</SectionHeading>
            <p className="text-stone-500 text-sm mb-5">Inspect and stream run results.</p>

            <Endpoint method="GET" path="/workflows/{id}/runs" desc="List all runs for a workflow.">
              <Pre>{`curl https://api.conductai.ai/workflows/53ab8977-.../runs \\
  -H "X-Api-Key: cond_live_xxx" \\
  -H "X-Workspace-Id: <workspace-id>"`}</Pre>
            </Endpoint>

            <Endpoint method="GET" path="/workflows/{id}/runs/{run_id}" desc="Get a run including status, state, and metadata.">
              <Pre>{`# Response
{
  "id": "b858c434-...",
  "status": "succeeded",
  "triggered_by": "manual:test_trigger",
  "started_at": "2026-05-26T12:00:00Z",
  "completed_at": "2026-05-26T12:03:21Z",
  "state": { ... }
}`}</Pre>
            </Endpoint>

            <Endpoint method="GET" path="/workflows/{id}/runs/{run_id}/stream" desc="Server-Sent Events stream of live run events. Streams block_started, block_completed, brain_tool_call, run_completed, and more. Closes with [DONE].">
              <Pre>{`# Pass token and workspace_id as query params (EventSource workaround)
const es = new EventSource(
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
              <Pre>{`curl -X POST https://api.conductai.ai/workflows/.../runs/.../approve \\
  -H "X-Api-Key: cond_live_xxx" \\
  -H "X-Workspace-Id: <workspace-id>" \\
  -H "Content-Type: application/json" \\
  -d '{"decision": "approved", "approver": "alice"}'`}</Pre>
            </Endpoint>

            <Endpoint method="POST" path="/workflows/{id}/runs/{run_id}/cancel" desc="Cancel a running or pending run.">
              <Pre>{`curl -X POST https://api.conductai.ai/workflows/.../runs/.../cancel \\
  -H "X-Api-Key: cond_live_xxx" \\
  -H "X-Workspace-Id: <workspace-id>"`}</Pre>
            </Endpoint>
          </section>

          {/* ── API Keys ── */}
          <section id="api-keys">
            <SectionHeading id="api-keys">API — API Keys</SectionHeading>
            <p className="text-stone-500 text-sm mb-5">Manage programmatic access keys for your workspace.</p>

            <Endpoint method="POST" path="/workspaces/{id}/api-keys" desc="Generate a new API key. The plaintext key is returned once — store it immediately.">
              <Pre>{`curl -X POST https://api.conductai.ai/workspaces/<id>/api-keys \\
  -H "Authorization: Bearer <clerk-token>" \\
  -H "X-Workspace-Id: <id>" \\
  -H "Content-Type: application/json" \\
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

            <Endpoint method="GET" path="/workspaces/{id}/api-keys" desc="List all API keys (prefix and metadata only — plaintext is never returned again)." />

            <Endpoint method="DELETE" path="/workspaces/{id}/api-keys/{key_id}" desc="Revoke an API key immediately." />
          </section>

          {/* ── Memory block ── */}
          <section id="memory-block">
            <SectionHeading id="memory-block">Memory block</SectionHeading>
            <p className="text-stone-500 text-sm mb-6 leading-relaxed">
              The Memory block gives agents a persistent knowledge store. Before a run, a <strong>read</strong> block
              retrieves past summaries relevant to the current task. After the run, a <strong>write</strong> block records
              what was done. On the next run, the agent has context from everything it has done before on that repo.
            </p>

            <SubHeading>How it fits in a playbook</SubHeading>
            <p className="text-stone-500 text-sm mb-3">Place memory blocks around the brain block — recall before, record after:</p>
            <div className="rounded-xl border border-stone-200 overflow-hidden mb-6">
              <div className="px-4 py-3 bg-stone-50 border-b border-stone-200 text-xs font-semibold text-stone-500 uppercase tracking-wider">Recommended block order</div>
              {[
                { block: "Trigger", note: "Issue labeled, PR opened, cron, etc." },
                { block: "Memory (read)", note: "Retrieves past summaries — available as {{recall.entries}} in the brain", amber: true },
                { block: "Fetch Issue / tool block", note: "Gets fresh data from GitHub, Linear, etc." },
                { block: "Brain (Agent Step)", note: "Receives both the current task and recalled context" },
                { block: "Memory (write)", note: "Records what was done — used by future runs", amber: true },
                { block: "Notify (Slack / email)", note: "Posts the outcome" },
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
                    ["action", "read | write", "read retrieves past summaries before the brain runs. write stores the outcome after the run completes."],
                    ["scope", "repo | workspace", "repo isolates memories per repository. workspace shares memories across all repos in the workspace for this playbook."],
                    ["key", "auto-set", "Groups memories together. Auto-populated from scope: repo → {{_trigger.repo_full_name}}, workspace → \"workspace\". Read-only in the UI."],
                    ["limit", "number (default 5)", "read only. Maximum number of past summaries to retrieve. Retrieves the most semantically similar entries first."],
                    ["summary", "template string", "write only. What to store. Supports {{block_id.field}} refs resolved at runtime. Example: Fixed {{fetch_issue.title}} via {{brain.approach}}"],
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

            <SubHeading>Scope in detail</SubHeading>
            <p className="text-stone-500 text-sm mb-4 leading-relaxed">
              Memory is always isolated by <strong>playbook</strong>. Autopilot Quick and Autopilot Full on the same repo
              never share memories — each agent develops independent expertise. Scope controls the second dimension:
              how memories are grouped within a playbook.
            </p>
            <div className="rounded-xl border border-stone-200 overflow-hidden mb-4">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-stone-50 border-b border-stone-200">
                    <th className="text-left px-4 py-2.5 text-xs font-semibold text-stone-500 uppercase tracking-wider w-32"></th>
                    <th className="text-left px-4 py-2.5 text-xs font-semibold text-stone-500 uppercase tracking-wider">Repo scope</th>
                    <th className="text-left px-4 py-2.5 text-xs font-semibold text-stone-500 uppercase tracking-wider">Workspace scope</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-stone-100 text-sm">
                  {[
                    ["Key", "{{_trigger.repo_full_name}} → e.g. acme/api", "\"workspace\" (constant)"],
                    ["Memory bucket per…", "Each repository separately", "All repos in the workspace combined"],
                    ["Shared across repos?", "No", "Yes"],
                    ["Shared across playbooks?", "No", "No"],
                    ["Best for", "Repo-specific conventions, file layout, past bug patterns", "Team-wide standards, commit conventions, cross-repo practices"],
                    ["Example learning", "\"This repo uses tabs, not spaces. Tests live in /spec.\"", "\"This team always squashes commits and requires a CHANGELOG entry.\""],
                  ].map(([label, repo, ws]) => (
                    <tr key={label}>
                      <td className="px-4 py-3 text-xs font-semibold text-stone-500 align-top">{label}</td>
                      <td className="px-4 py-3 text-xs text-stone-600 leading-relaxed">{repo}</td>
                      <td className="px-4 py-3 text-xs text-stone-600 leading-relaxed">{ws}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <SubHeading>How recall works</SubHeading>
            <p className="text-stone-500 text-sm mb-3 leading-relaxed">
              When a read block runs, Conduct embeds the key (e.g. <Code>acme/api</Code>) as a vector and queries
              past summaries using cosine similarity. The most relevant entries — not just the most recent — are returned.
              This means if an agent fixed a similar bug 50 runs ago, that context surfaces before a recent unrelated one.
            </p>
            <p className="text-stone-500 text-sm mb-6 leading-relaxed">
              Retrieved entries are available in the brain prompt as <Code>{"{{recall_block_id.entries}}"}</Code> — a list
              of <Code>summary</Code> and <Code>at</Code> (timestamp) objects. The brain prompt template can include them
              under a &ldquo;Prior context&rdquo; heading so the agent reasons over both new and past information.
            </p>

            <SubHeading>Setup</SubHeading>
            <ol className="list-decimal list-inside space-y-2 text-sm text-stone-600 mb-4">
              <li>Go to <strong>Settings → Environments</strong> and open your environment.</li>
              <li>Add a credential: handle <Code>openai</Code>, key <Code>api_key</Code>, value <Code>sk-…</Code></li>
              <li>Drag a Memory block onto your canvas. Set action=<Code>read</Code>, connect it before the brain block.</li>
              <li>Drag a second Memory block. Set action=<Code>write</Code>, write a summary template, connect it after the brain block.</li>
            </ol>
            <div className="rounded-xl bg-stone-100 border border-stone-200 px-4 py-3 text-sm text-stone-700 mb-6">
              <strong>No OpenAI key?</strong> Memory still works — Conduct falls back to recency-based retrieval
              (the 5 most recent summaries instead of the most semantically similar). You lose similarity search
              but not the feature.
            </div>

            <SubHeading>YAML reference</SubHeading>
            <Pre>{`blocks:
  recall_context:
    type: memory
    label: Recall prior context
    action: read
    scope: repo
    key: "{{_trigger.repo_full_name}}"
    limit: 5
    next: fetch_issue

  # ... fetch_issue, implement_fix ...

  record_outcome:
    type: memory
    label: Record outcome
    action: write
    scope: repo
    key: "{{_trigger.repo_full_name}}"
    summary: |
      Issue #{{fetch_issue.issue_number}}: {{fetch_issue.title}}
      Fix: {{implement_fix.approach}}
      Files: {{implement_fix.files_changed}}
    next: notify`}</Pre>
          </section>

          {/* ── Guard block ── */}
          <section id="guard-block">
            <SectionHeading id="guard-block">Guard block</SectionHeading>
            <p className="text-stone-500 text-sm mb-6 leading-relaxed">
              The Guard block evaluates your team&apos;s policies mid-workflow. Place it before sensitive operations
              (file writes, deployments, external API calls) to enforce spend limits, blocked actions, and custom
              regex rules. On a policy violation, the block either halts the run (<code className="font-mono text-xs bg-stone-100 px-1 rounded">block</code> mode),
              adds a warning and continues (<code className="font-mono text-xs bg-stone-100 px-1 rounded">warn</code>), or silently records the event (<code className="font-mono text-xs bg-stone-100 px-1 rounded">audit</code>).
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
    # rule_ids: [uuid1, uuid2]  # optional — evaluate specific rules only
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
                    ["enforcement_mode", "block — halt the run on violation. warn — add to warnings list, continue. audit — record silently, continue. Default: block."],
                    ["context_keys", "Optional list of block IDs whose state to serialize for policy evaluation. Omit to send the full run state."],
                    ["rule_ids", "Optional list of policy UUIDs to evaluate. Omit to evaluate all active policies for the team."],
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
  "team_id": "uuid",
  "rules_checked": 4,
  "violations": 0,
  "warnings": []           # list of warning messages (warn/audit mode)
}`}</Pre>

            <div className="mt-3 rounded-xl bg-amber-50 border border-amber-200 px-4 py-3 text-sm text-amber-800">
              <strong>Guard block requires Guard to be installed.</strong> If the team has no Guard configured, the block
              fails with installation instructions. If <code className="font-mono text-xs">enforcement_mode: block</code> is set
              and Guard is not installed, the run halts. Use <code className="font-mono text-xs">warn</code> or <code className="font-mono text-xs">audit</code> mode
              if you want the workflow to continue without Guard.
            </div>
          </section>

          {/* ── ConductGuard overview ── */}
          <section id="guard">
            <SectionHeading id="guard">ConductGuard — Overview</SectionHeading>
            <p className="text-stone-500 text-sm mb-6 leading-relaxed">
              ConductGuard is the team policy layer for AI tools. It has two enforcement surfaces:
            </p>
            <div className="rounded-xl border border-stone-200 divide-y divide-stone-100 text-sm mb-8">
              {[
                {
                  label: "Workflow enforcement (Guard block)",
                  detail: "Evaluates policies mid-run inside Conduct workflows. The Guard block checks active team policies against the run state and halts, warns, or audits based on enforcement_mode.",
                },
                {
                  label: "Local enforcement (hook + MCP)",
                  detail: "Intercepts AI tool calls in Claude Code, Cursor, and other editors before they reach the model. Checks hard caps, evaluates policies, and blocks or warns at call time. No workflow required.",
                },
              ].map(({ label, detail }) => (
                <div key={label} className="px-4 py-3">
                  <p className="font-medium text-stone-800 mb-0.5">{label}</p>
                  <p className="text-stone-500 text-xs leading-relaxed">{detail}</p>
                </div>
              ))}
            </div>

            <SubHeading>Policy anatomy</SubHeading>
            <p className="text-stone-500 text-sm mb-3">Policies are created in Guard → Policies and consist of:</p>
            <div className="rounded-xl border border-stone-200 overflow-hidden mb-6">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-stone-50 border-b border-stone-200">
                    <th className="text-left px-4 py-2.5 text-xs font-semibold text-stone-500 uppercase tracking-wider w-36">Field</th>
                    <th className="text-left px-4 py-2.5 text-xs font-semibold text-stone-500 uppercase tracking-wider">Description</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-stone-100 text-sm">
                  {[
                    ["match_tool", "Which AI tool triggers this rule (e.g. claude-code, cursor, * for any)."],
                    ["match_pattern", "Regex matched against the serialized tool call input. Trigger if matched."],
                    ["match_path_pattern", "Regex matched against file paths in the tool call. Trigger if matched."],
                    ["enforcement_mode", "block | warn | audit — what happens when the rule triggers."],
                    ["alert_message", "Message sent to Slack when the rule triggers (if Slack is configured)."],
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

          {/* ── Developer setup ── */}
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
              itself and re-runs the original command — the developer never needs to manually update.
              Set <Code>CONDUCT_NO_AUTOUPDATE=1</Code> to disable (useful in CI).
            </p>
          </section>

          {/* ── Hook & tool coverage ── */}
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
                    ["Codex CLI",   "PreToolUse hook (~/.codex/hooks.json)",      "Hard block — same script, same exit-code-2 protocol"],
                    ["Cursor",      "MCP server (conductguard-mcp)",              "Advisory — AI sees Guard tools, can self-enforce"],
                    ["Windsurf",    "MCP server (conductguard-mcp)",              "Advisory — AI sees Guard tools, can self-enforce"],
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
                ["1. Budget check (cached 5 min)", "Calls GET /guard/spend/budget-check with workspace_id. If the hard cap is hit, exits with code 2 — the tool treats this as a block."],
                ["2. Policy evaluation", "Loads ~/.conductguard/policy.json. Evaluates match_tool, match_pattern, and match_path_pattern. If a rule fires: block exits 2, warn prints a message, audit falls through silently."],
                ["3. Event posted (async)", "Every tool call — allowed or blocked — is posted to /guard/events in a background subprocess. This powers the Activity log and Active developers metrics on the dashboard."],
                ["4. Slack alert", "If a block or warn rule has an alert configured, the Guard API notifies the workspace's Slack channel."],
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

          {/* ── conductguard-mcp ── */}
          <section id="guard-mcp">
            <SectionHeading id="guard-mcp">conductguard-mcp</SectionHeading>
            <p className="text-stone-500 text-sm mb-4 leading-relaxed">
              An MCP server that gives Cursor, Windsurf, and any MCP-compatible editor direct access to Guard.
              Registered automatically at login — no manual config needed. The AI can query its own policies
              before taking sensitive actions.
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
                {
                  tool: "guard_status",
                  desc: "Returns workspace ID, policy count, policy version, and developer email. Useful for confirming Guard is active.",
                  args: "None",
                },
                {
                  tool: "guard_check",
                  desc: "Evaluates a tool call against active policies. Returns ALLOWED, BLOCKED, or WARNING with the matching rule. Use before sensitive file edits or API calls.",
                  args: "tool_name (str), tool_input (object, optional)",
                },
                {
                  tool: "guard_sync",
                  desc: "Pulls the latest policies from the server and writes them to ~/.conductguard/policy.json. Call after an admin updates a rule.",
                  args: "None",
                },
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

            <p className="text-stone-500 text-sm">
              JSON-RPC 2.0 over stdio. Protocol version <Code>2024-11-05</Code>.
            </p>
          </section>

          {/* ── Spend controls ── */}
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

# No auth required — open endpoint for hook use
# Response:
{
  "hard_blocked": false,
  "reason": null,
  "monthly_cost_usd": 12.40,
  "hard_limit_usd": 50.00
}

# When blocked:
{
  "hard_blocked": true,
  "reason": "Monthly budget of $50.00 exceeded ($51.20 used)",
  "monthly_cost_usd": 51.20,
  "hard_limit_usd": 50.00
}`}</Pre>

            <div className="mt-3 rounded-xl bg-stone-100 border border-stone-200 px-4 py-3 text-sm text-stone-700">
              The hook caches the response at <Code>~/.conductguard/budget_cache.json</Code> for 5 minutes.
              Delete it to force an immediate re-check.
            </div>
          </section>

          {/* ── Roles & Permissions ── */}
          <section id="guard-roles">
            <SectionHeading id="guard-roles">Roles & permissions</SectionHeading>
            <p className="text-stone-500 text-sm mb-6 leading-relaxed">
              Every workspace member has one of four roles. Roles are the single source of truth — set in workspace
              settings, enforced across Guard, API keys, and the CLI.
            </p>

            <SubHeading>Role definitions</SubHeading>
            <div className="rounded-xl border border-stone-200 divide-y divide-stone-100 text-sm mb-8">
              {[
                {
                  role: "Admin",
                  color: "bg-purple-50 text-purple-700",
                  desc: "Full access: Guard policies, spend limits, members, settings, API key revoke, and all playbooks.",
                },
                {
                  role: "Security",
                  color: "bg-blue-50 text-blue-700",
                  desc: "Full Guard access — create/edit policies and view all activity. View-only spend. Cannot manage members or revoke API keys.",
                },
                {
                  role: "Developer",
                  color: "bg-green-50 text-green-700",
                  desc: "View-only Guard (no create/edit). Can generate their own API key. Full access to runs, playbooks, and canvas.",
                },
                {
                  role: "Viewer",
                  color: "bg-stone-100 text-stone-600",
                  desc: "View-only across all of Guard, runs, and audit log. No execution or edit rights.",
                },
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
                    ["View Guard dashboard",      true,  true,  true,  true ],
                    ["View activity log",         true,  true,  true,  true ],
                    ["View policies",             true,  true,  true,  true ],
                    ["Create / edit policies",    true,  true,  false, false],
                    ["View spend data",           true,  true,  true,  true ],
                    ["Set spend limits",          true,  false, false, false],
                    ["View members",              true,  true,  true,  true ],
                    ["Invite / remove members",   true,  false, false, false],
                    ["Configure Guard settings",  true,  false, false, false],
                    ["Generate API key",          true,  false, true,  false],
                    ["Revoke API key",            true,  false, false, false],
                    ["Run playbooks / canvas",    true,  true,  true,  false],
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

          {/* ── Team onboarding ── */}
          <section id="guard-onboarding">
            <SectionHeading id="guard-onboarding">Team onboarding</SectionHeading>
            <p className="text-stone-500 text-sm mb-6 leading-relaxed">
              End-to-end flow for getting a team onto Guard. Each developer runs two commands — everything else is automatic.
            </p>

            <div className="space-y-0">
              {[
                {
                  step: "1",
                  title: "Admin installs Guard",
                  body: "Settings → Modules → ConductGuard → Install. Guard is provisioned with 18 starter policies. The admin shares the invite code or adds team members directly.",
                },
                {
                  step: "2",
                  title: "Invite your team",
                  body: "Guard → Members → Invite. Assign roles: Developer for engineers, Security for security team, Viewer for stakeholders. Members are added to the workspace.",
                },
                {
                  step: "3",
                  title: "Developer generates an API key",
                  body: "Settings → API Keys → Generate key. Admin and Developer roles can generate keys. The key is tied to their workspace and role.",
                },
                {
                  step: "4",
                  title: "Developer logs in",
                  body: "One command installs Guard, downloads policies, registers the hook in Claude Code and Codex, and registers the MCP server in Cursor and Windsurf — all automatically.",
                  code: "pip install conduct-cli\nconduct login --server https://api.conductai.ai --api-key cond_live_xxxx",
                },
                {
                  step: "5",
                  title: "Guard enforces from this moment",
                  body: "Every AI tool call on the developer's machine is intercepted and checked against workspace policies. All activity — allowed and blocked — appears in the Guard dashboard.",
                },
              ].map(({ step, title, body, code }) => (
                <div key={step} className="flex gap-6 pb-8 relative">
                  <div className="flex flex-col items-center">
                    <div className="w-8 h-8 rounded-full bg-stone-900 text-white text-sm font-bold flex items-center justify-center shrink-0 z-10">
                      {step}
                    </div>
                    {parseInt(step) < 5 && (
                      <div className="w-px flex-1 bg-stone-200 mt-2" />
                    )}
                  </div>
                  <div className="pt-1 pb-2 flex-1">
                    <p className="font-semibold text-stone-900 mb-1">{title}</p>
                    <p className="text-sm text-stone-600 leading-relaxed mb-2">{body}</p>
                    {code && (
                      <pre className="bg-stone-900 text-stone-100 rounded-lg px-4 py-3 text-xs font-mono mt-2 overflow-x-auto">{code}</pre>
                    )}
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

          {/* ── GitHub ── */}
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
                    ["Contents", "Read and write", "Create branches, push commits, read code"],
                    ["Pull requests", "Read and write", "Open, review, and merge PRs"],
                    ["Actions", "Read and write", "Trigger and monitor workflow runs"],
                    ["Metadata", "Read-only (required)", "Auto-granted, cannot be removed"],
                  ].map(([perm, access, use]) => (
                    <tr key={perm}>
                      <td className="px-4 py-3 font-medium text-stone-800">{perm}</td>
                      <td className="px-4 py-3">
                        <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${
                          access.includes("Read-only") ? "bg-stone-100 text-stone-500" : "bg-green-50 text-green-700"
                        }`}>{access}</span>
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

          {/* ── Slack ── */}
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
                    ["chat:write", "Post messages to channels"],
                    ["im:write", "Send direct messages"],
                    ["channels:read", "List channels to target"],
                    ["users:read", "Resolve user IDs for DMs"],
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

          {/* ── Linear ── */}
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

          {/* ── Email ── */}
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

        </main>
      </div>
    </div>
  )
}
