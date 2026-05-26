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
          <p className="text-[10px] font-semibold text-stone-400 uppercase tracking-wider mb-3">Getting started</p>
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

          <p className="text-[10px] font-semibold text-stone-400 uppercase tracking-wider mt-6 mb-3">API Reference</p>
          <ul className="space-y-1 text-sm text-stone-600">
            <li><a href="#api-auth" className="hover:text-stone-900 transition-colors block py-0.5">Authentication</a></li>
            <li><a href="#api-workflows" className="hover:text-stone-900 transition-colors block py-0.5">Workflows</a></li>
            <li><a href="#api-runs" className="hover:text-stone-900 transition-colors block py-0.5">Runs</a></li>
            <li><a href="#api-keys" className="hover:text-stone-900 transition-colors block py-0.5">API Keys</a></li>
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

          {/* ── Overview ── */}
          <section id="overview">
            <h1 className="text-3xl font-bold text-stone-900 mb-3">Documentation</h1>
            <p className="text-stone-600 leading-relaxed text-base">
              Conduct AI lets you build and run AI agents that interact with your tools — GitHub, Slack, Linear, and more.
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
                    ["conduct create project <name>", "Create a project"],
                    ["conduct delete project <name> --yes", "Delete a project and all its agents"],
                    ["conduct reset project <name> --yes", "Remove all agents from a project (clean slate)"],
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
