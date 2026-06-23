import type { Metadata } from "next"

export const metadata: Metadata = { title: "Connect your AI tools to ConductGuard — Docs" }

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

export default function McpSetupDocsPage() {
  return (
    <div className="max-w-3xl mx-auto px-6 py-16">
      <p className="text-xs font-bold uppercase tracking-widest text-indigo-600 mb-2">Setup guide</p>
      <h1 className="text-4xl font-bold text-stone-900 mb-3">Connect your AI tools to ConductGuard</h1>
      <p className="text-lg text-stone-600 leading-relaxed mb-6">
        Conduct AI Guard is a default MCP server for every workspace. It works with any client that
        speaks MCP — Claude, Codex, Cursor, VS Code + Copilot, Devin, and more. Once a client is
        pointed at your workspace URL, every tool call is audited and policy-enforced.
      </p>

      <div className="bg-indigo-50 border border-indigo-100 rounded-xl p-5 mb-12">
        <p className="text-sm font-semibold text-indigo-900 mb-1">Fastest path: let the CLI do it</p>
        <p className="text-sm text-indigo-800 leading-relaxed mb-3">
          The Conduct CLI auto-detects every supported client on your machine and writes the right config.
        </p>
        <Pre>conduct guard sync</Pre>
        <p className="text-xs text-indigo-700 mt-3">
          Covers Claude Code, Claude Desktop, Cursor, Codex CLI, Windsurf, and VS Code + Copilot.
          Devin is cloud-only — see its section below for the URL-paste flow.
        </p>
      </div>

      <section className="mb-12">
        <h2 className="text-2xl font-semibold text-stone-900 mb-2">Your workspace URL</h2>
        <p className="text-stone-600 mb-4">
          Grab the URL from your <a href="/integrations" className="text-indigo-600 underline">MCP servers page</a>{" "}
          (click <em>Edit</em> on the <strong>Conduct AI Guard</strong> row, then <em>Reveal</em> + <em>Copy</em>).
          The shape looks like:
        </p>
        <Pre>https://api.conductai.ai/guard/mcp?workspace_id=&lt;your-ws&gt;&amp;token=&lt;your-token&gt;</Pre>
        <p className="text-sm text-stone-500 mt-3">
          The token is scoped to the member who copies it. Treat it like a personal access token — do not paste it in shared docs or repos.
        </p>
      </section>

      <section className="mb-12">
        <h2 className="text-2xl font-semibold text-stone-900 mb-3">Claude.ai (web)</h2>
        <ol className="list-none p-0">
          <Step n={1}>Open Claude.ai → <strong>Settings</strong> → <strong>MCP Servers</strong>.</Step>
          <Step n={2}>Click <strong>Add server</strong> and paste your workspace URL.</Step>
          <Step n={3}>Save. Then in any chat, type <Code>load mcp</Code> or <Code>enable guard</Code> to activate it for that conversation.</Step>
        </ol>
      </section>

      <section className="mb-12">
        <h2 className="text-2xl font-semibold text-stone-900 mb-3">Claude Desktop</h2>
        <p className="text-stone-600 mb-3">Either run the CLI:</p>
        <Pre>conduct guard sync</Pre>
        <p className="text-stone-600 mt-4 mb-2">Or edit <Code>claude_desktop_config.json</Code> directly:</p>
        <Pre>{`{
  "mcpServers": {
    "conduct-guard": {
      "url": "https://api.conductai.ai/guard/mcp?workspace_id=<your-ws>&token=<your-token>"
    }
  }
}`}</Pre>
        <p className="text-stone-600 mt-3">Restart Claude Desktop to pick up the change.</p>
      </section>

      <section className="mb-12">
        <h2 className="text-2xl font-semibold text-stone-900 mb-3">Claude for Work</h2>
        <ol className="list-none p-0">
          <Step n={1}><strong>Admin Console</strong> → <strong>Integrations</strong> → <strong>MCP</strong>.</Step>
          <Step n={2}>Add a new server and paste your workspace URL.</Step>
          <Step n={3}>Type <Code>load mcp</Code> in any chat to activate it for that conversation.</Step>
        </ol>
        <p className="text-sm text-stone-500 mt-3">
          For enterprise rollout, your admin can pre-provision the MCP server so it's available to every seat
          without each user pasting a URL.
        </p>
      </section>

      <section className="mb-12">
        <h2 className="text-2xl font-semibold text-stone-900 mb-3">Codex CLI</h2>
        <p className="text-stone-600 mb-3">
          Run <Code>conduct guard sync</Code> — it writes the config to <Code>~/.codex/config.toml</Code>.
          Or add the block manually:
        </p>
        <Pre>{`# ~/.codex/config.toml
[mcp_servers.conduct-guard]
url = "https://api.conductai.ai/guard/mcp?workspace_id=<your-ws>&token=<your-token>"`}</Pre>
        <p className="text-stone-600 mt-3">Restart your Codex session to pick up the new server.</p>
      </section>

      <section className="mb-12">
        <h2 className="text-2xl font-semibold text-stone-900 mb-3">Cursor</h2>
        <ol className="list-none p-0">
          <Step n={1}>Open Cursor → <strong>Settings</strong> → <strong>MCP</strong>.</Step>
          <Step n={2}>Click <strong>Add new MCP server</strong>, paste the workspace URL, save.</Step>
          <Step n={3}>Reload Cursor. Tool calls from agent runs now flow through ConductGuard.</Step>
        </ol>
      </section>

      <section className="mb-12">
        <h2 className="text-2xl font-semibold text-stone-900 mb-3">VS Code + GitHub Copilot</h2>
        <p className="text-stone-600 mb-3">
          If you have the GitHub Copilot extension installed in VS Code, <Code>conduct guard sync</Code>{" "}
          detects it and writes the MCP config to <Code>Code/User/mcp.json</Code>. Copilot Chat picks it
          up automatically.
        </p>
        <p className="text-stone-600 mb-3">Or add it manually in your VS Code <Code>settings.json</Code>:</p>
        <Pre>{`{
  "mcp.servers": {
    "conduct-guard": {
      "url": "https://api.conductai.ai/guard/mcp?workspace_id=<your-ws>&token=<your-token>"
    }
  }
}`}</Pre>
        <p className="text-stone-600 mt-3">Reload the VS Code window to pick up the new server.</p>
      </section>

      <section className="mb-12">
        <h2 className="text-2xl font-semibold text-stone-900 mb-3">Devin</h2>
        <p className="text-stone-600 mb-3">
          Devin runs in the cloud, so there's no local config to sync. Paste the workspace URL into
          Devin directly:
        </p>
        <ol className="list-none p-0">
          <Step n={1}>Open Devin → <strong>Workspace Settings</strong> → <strong>MCP Servers</strong>.</Step>
          <Step n={2}>Click <strong>Add Server</strong>, paste your workspace URL, save.</Step>
          <Step n={3}>Devin's agents now route tool calls through ConductGuard automatically.</Step>
        </ol>
        <p className="text-sm text-stone-500 mt-3">
          Devin sessions run remotely, so the token in the URL must belong to the workspace member you
          want activity attributed to. Treat it as a service credential.
        </p>
      </section>

      <section className="mb-12">
        <h2 className="text-2xl font-semibold text-stone-900 mb-3">Windsurf</h2>
        <p className="text-stone-600 mb-3">
          <Code>conduct guard sync</Code> writes to <Code>~/.windsurf/mcp.json</Code> if Windsurf is
          installed. Or add the block manually:
        </p>
        <Pre>{`# ~/.windsurf/mcp.json
{
  "mcpServers": {
    "conduct-guard": {
      "url": "https://api.conductai.ai/guard/mcp?workspace_id=<your-ws>&token=<your-token>"
    }
  }
}`}</Pre>
      </section>

      <section className="mb-12">
        <h2 className="text-2xl font-semibold text-stone-900 mb-3">Other MCP clients</h2>
        <p className="text-stone-600">
          Any other MCP-aware tool follows the same pattern: add your workspace URL to that tool's
          MCP server config. If you'd like CLI auto-detection added,{" "}
          <a href="https://github.com/sseshachala/conduct-cli/issues" target="_blank" rel="noopener" className="text-indigo-600 underline">open an issue</a>{" "}
          with the tool's config path.
        </p>
      </section>

      <section className="mb-12">
        <h2 className="text-2xl font-semibold text-stone-900 mb-3">What gets enforced</h2>
        <ul className="list-disc pl-6 space-y-2 text-stone-700">
          <li>Every tool call goes through ConductGuard <strong>before</strong> the model can execute it.</li>
          <li>Policy rules (block / warn / audit) are applied based on your workspace's active skill packs.</li>
          <li>Spend budgets are checked per-developer and per-team — runs are blocked when limits are exceeded.</li>
          <li>Activity is logged to <a href="/guard/activity" className="text-indigo-600 underline">Guard → Activity</a> with the rule that fired and the decision.</li>
        </ul>
      </section>

      <section>
        <h2 className="text-2xl font-semibold text-stone-900 mb-3">Troubleshooting</h2>
        <div className="space-y-4 text-stone-700">
          <div>
            <p className="font-semibold">Tool calls aren't getting enforced.</p>
            <p className="text-sm text-stone-600 mt-1">For Claude.ai and Claude for Work, make sure you typed <Code>load mcp</Code> in the chat — MCP servers are per-conversation. For Codex / Cursor / Desktop, restart the client after editing config.</p>
          </div>
          <div>
            <p className="font-semibold">Token revoked or rotated.</p>
            <p className="text-sm text-stone-600 mt-1">Run <Code>conduct guard init</Code> to generate a fresh token, then re-paste the URL into your client.</p>
          </div>
          <div>
            <p className="font-semibold">Policy isn't matching what I expect.</p>
            <p className="text-sm text-stone-600 mt-1">Open <a href="/guard/policies" className="text-indigo-600 underline">Guard → Policies</a> and check which rules are active for your workspace.</p>
          </div>
        </div>
      </section>
    </div>
  )
}
