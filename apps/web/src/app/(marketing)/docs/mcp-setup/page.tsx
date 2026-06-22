import type { Metadata } from "next"

export const metadata: Metadata = { title: "Connect Claude to ConductGuard — Docs" }

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
      <h1 className="text-4xl font-bold text-stone-900 mb-3">Connect Claude to ConductGuard</h1>
      <p className="text-lg text-stone-600 leading-relaxed mb-10">
        Conduct AI Guard is a default MCP server for every workspace. Once Claude is pointed at your
        workspace URL, every tool call is audited and policy-enforced — no extra agent to install.
      </p>

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
        <p className="text-stone-600 mb-3">
          The Conduct CLI handles the config for you. Run:
        </p>
        <Pre>conduct guard sync</Pre>
        <p className="text-stone-600 mt-3">
          This writes your workspace URL into Claude Desktop's <Code>claude_desktop_config.json</Code> and
          restarts the app's MCP connection. No manual JSON editing.
        </p>
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
            <p className="text-sm text-stone-600 mt-1">Make sure you typed <Code>load mcp</Code> or <Code>enable guard</Code> in the chat. MCP servers are per-conversation in Claude.ai.</p>
          </div>
          <div>
            <p className="font-semibold">Token revoked or rotated.</p>
            <p className="text-sm text-stone-600 mt-1">Run <Code>conduct guard init</Code> to generate a fresh token, then re-paste the URL in Claude.</p>
          </div>
          <div>
            <p className="font-semibold">Policy isn't matching what I expect.</p>
            <p className="text-sm text-stone-600 mt-1">Open <a href="/guard/policies" className="text-indigo-600 underline">Guard → Policies</a> and check which rules are active under your workspace persona.</p>
          </div>
        </div>
      </section>
    </div>
  )
}
