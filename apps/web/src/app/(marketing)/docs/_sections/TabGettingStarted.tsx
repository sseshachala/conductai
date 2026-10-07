import { Code, Pre, SectionHeading, SubHeading } from "./shared"

export function TabGettingStarted() {
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
            { name: "On-premise", icon: "🔒", desc: "Docker self-hosted shipped. Fully air-gapped installs are running with design partners — not yet GA." },
          ].map(t => (
            <div key={t.name} className="rounded-xl border border-stone-200 bg-stone-50 px-4 py-3">
              <p className="font-semibold text-stone-800 text-sm">{t.icon} {t.name}</p>
              <p className="text-stone-500 text-xs mt-1">{t.desc}</p>
            </div>
          ))}
        </div>
        <p className="text-sm text-stone-500">See the full comparison at <a href="/deployment" className="text-indigo-600 hover:underline">conductai.ai/deployment</a>, or <a href="https://cal.com/sudhi-seshachala-pks7pd" className="text-indigo-600 hover:underline" target="_blank" rel="noopener">book a call</a> for BYOC or on-premise setup.</p>
      </section>

      <section id="quick-trial">
        <SectionHeading id="quick-trial">Zero-install trial (60 seconds)</SectionHeading>
        <p className="text-stone-500 text-sm mb-4">
          Point any Anthropic-SDK client on your machine at the hosted Guard proxy with a trial token. No local install, no signup form — the shell script prompts for email + company and does the rest.
        </p>
        <Pre>{`curl -fsSL conductai.ai/install | sh`}</Pre>
        <p className="text-stone-500 text-sm mt-4 mb-2">What it does:</p>
        <ul className="list-disc list-inside space-y-1 text-sm text-stone-600 mb-4">
          <li>Provisions a 7-day trial workspace (200 requests/day shared across Anthropic + OpenAI, no credit card)</li>
          <li>Drops <Code>~/.conduct/env</Code> with <Code>ANTHROPIC_BASE_URL</Code> + <Code>OPENAI_BASE_URL</Code> + a trial <Code>cond_agt_trial_*</Code> token</li>
          <li>Prints a magic-link URL — click to sign into your dashboard, no password</li>
          <li>Prints a copy-pasteable trip-a-block curl so you can see the receipt flow immediately</li>
        </ul>
        <p className="text-stone-500 text-sm mb-2">Try it (Anthropic):</p>
        <Pre>{`source ~/.conduct/env
curl -sS "$ANTHROPIC_BASE_URL/v1/messages" \\
  -H "x-api-key: $ANTHROPIC_API_KEY" \\
  -H 'anthropic-version: 2023-06-01' \\
  -H 'content-type: application/json' \\
  -d '{"model":"claude-3-5-sonnet-20241022","max_tokens":128,"messages":[{"role":"user","content":"Please redact my SSN 123-45-6789 for me."}]}'`}</Pre>
        <p className="text-stone-500 text-sm mt-3">
          Response is a 403 with <Code>→ Receipt: https://conductai.ai/theguard/blocks/…</Code> in the message. Click the URL to open the block receipt, ask Lens follow-up questions (<em>Why did this block? What would have allowed it? Draft an exception</em>), or share externally via <strong>Make shareable</strong>.
        </p>

        <SubHeading>OpenAI (also trial-funded)</SubHeading>
        <p className="text-stone-500 text-sm mb-3">
          The install script also wires <Code>OPENAI_BASE_URL</Code>. Same trial token authenticates you; same 200 requests/day cap is shared across Anthropic + OpenAI.
        </p>
        <Pre>{`source ~/.conduct/env
curl -sS "$OPENAI_BASE_URL/v1/chat/completions" \\
  -H "Authorization: Bearer $OPENAI_API_KEY" \\
  -H 'content-type: application/json' \\
  -d '{"model":"gpt-4o","messages":[{"role":"user","content":"Please redact my SSN 123-45-6789 for me."}]}'`}</Pre>

        <SubHeading>Perplexity, Bedrock, others</SubHeading>
        <p className="text-stone-500 text-sm mb-3">
          Gateway routes exist under <Code>/gateway/v1/perplexity</Code> and future providers. Guard policy + hash-chained audit apply uniformly. Trial upstream key isn't funded for these yet — bring your own vendor key in <strong>Settings → Environments</strong>. The proxy forwards to your vault key transparently.
        </p>

        <p className="text-stone-500 text-sm mt-4">
          Under the hood: same Clerk user, same workspace, same trial guarantees as browser signup. Sign in later via the magic link or at <a href="/sign-in" className="text-indigo-600 hover:underline">conductai.ai/sign-in</a>.
        </p>
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
                ["Claude.ai (native)","Add MCP → sign in with Conduct (OAuth 2.1 + PKCE)", "no local file — server-side"],
                ["Claude Code",      "conduct login  /  conduct mcp install", "~/.claude/settings.json"],
                ["Codex CLI",        "conduct login  /  conduct mcp install", "~/.codex/config.toml"],
                ["Cursor",           "Add MCP → sign in  ·  or: conduct login  /  conduct mcp install", "~/.cursor/mcp.json"],
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
