import { Code, Pre, Step } from "./shared"

export function TabMcpTools() {
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
        <Pre>https://gateway.conductai.ai/mcp
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
        <Pre>{`claude mcp add conduct \\
  --transport http \\
  --url https://gateway.conductai.ai/mcp \\
  --header "Authorization: Bearer <your-token>"`}</Pre>
        <p className="text-stone-600 mt-4 mb-2">Or edit <Code>~/.claude/settings.json</Code> directly:</p>
        <Pre>{`{
  "mcpServers": {
    "conduct": {
      "type": "http",
      "url": "https://gateway.conductai.ai/mcp",
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
    "conduct": {
      "url": "https://gateway.conductai.ai/mcp",
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
        <Pre>{`URL:  https://gateway.conductai.ai/mcp
Auth: OAuth  (discovered from /.well-known/oauth-protected-resource/mcp)`}</Pre>
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
    "conduct": {
      "type": "http",
      "url": "https://gateway.conductai.ai/mcp",
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
    "conduct": {
      "url": "https://gateway.conductai.ai/mcp",
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
    "conduct": {
      "type": "http",
      "url": "https://gateway.conductai.ai/mcp",
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
    "conduct": {
      "url": "https://gateway.conductai.ai/mcp",
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
