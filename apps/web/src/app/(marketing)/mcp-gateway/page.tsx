import Link from "next/link"
import { DecisionCard } from "@/components/marketing/facelift/DecisionCard"

export const metadata = {
  title: "MCP — Runtime policy for MCP actions | Conduct",
  description:
    "Guard intercepts every MCP tool call before it executes. Policy applies at the MCP call, not the client. Allow, approve, or block — with a signed receipt.",
}

export default function MCPPage() {
  return (
    <div className="min-h-screen bg-white">
      <main className="max-w-5xl mx-auto px-6">

        {/* Hero — Figma frame 14: dark full-width band */}
        <section className="-mx-6 sm:-mx-10 lg:-mx-20 px-6 sm:px-10 lg:px-20 py-20 sm:py-24 bg-stone-950 mb-16 grid grid-cols-1 lg:grid-cols-2 gap-10 items-center">
          <div>
            <p className="text-xs font-mono font-bold uppercase tracking-widest text-indigo-400 mb-4">
              MCP
            </p>
            <h1 className="text-4xl sm:text-5xl font-black tracking-tight text-white leading-[1.05] mb-6">
              Policy for every MCP tool invocation.
            </h1>
            <p className="text-lg text-stone-400 leading-relaxed mb-4">
              Guard sits between the MCP client and the MCP server. Every tool call is evaluated
              against policy before it reaches the server — applying runtime policy and evidence-model
              enforcement across every MCP-compatible client.
            </p>
            <p className="text-sm font-mono font-bold text-indigo-300 tracking-wider mb-6">
              Allow. Approve. Block. Prove.
            </p>
            <div className="flex flex-wrap gap-3">
              <Link
                href="/sign-up"
                className="inline-block rounded-xl bg-indigo-600 text-white px-6 py-3 text-sm font-semibold hover:bg-indigo-500 transition-colors"
              >
                Start Discovery — 14 days free
              </Link>
              <Link
                href="/book-demo"
                className="inline-block rounded-xl border border-stone-700 bg-transparent text-stone-200 px-6 py-3 text-sm font-semibold hover:bg-stone-900 transition-colors"
              >
                Book a Demo
              </Link>
            </div>
          </div>
          <div className="lg:pl-4">
            {/* SVG diagram — clients → ConductAI → MCP server. See docs/design/figma/screenshots/mcp-hero-diagram.svg */}
            <img
              src="/design/mcp-hero-diagram.svg"
              alt="MCP clients Claude Desktop, ChatGPT, and Cursor route tool invocations through ConductAI, which decides ALLOW, APPROVE, or BLOCK before the MCP server executes the tool."
              className="w-full h-auto rounded-2xl border border-stone-800 shadow-md"
              loading="lazy"
            />
          </div>
        </section>

        {/* Control before the tool executes — Figma frame 14 */}
        <section className="mb-20">
          <h2 className="text-2xl font-bold text-stone-900 mb-3">
            Control before the tool executes.
          </h2>
          <p className="text-stone-500 text-sm leading-relaxed mb-8 max-w-2xl">
            Guard evaluates the tool call after the model chooses it and before the MCP server receives it.
            The same policy that governs Claude Code CLI actions also governs MCP tool calls through the same engine.
          </p>
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <DecisionCard
              compact
              agent="cursor-agent-17"
              action="read_repository"
              resource="approved-repos"
              policy="repo-scope-v2"
              decision="ALLOW"
              reason="Repository on approved list"
            />
            <DecisionCard
              compact
              agent="claude-desktop"
              action="send_external_email"
              resource="finance-recipients"
              policy="external-comms-v1"
              decision="APPROVE"
              reason="External send requires human approval"
            />
            <DecisionCard
              compact
              agent="claude-code / deploy-agent"
              action="read_production_secret"
              resource="SECRET_KEY"
              policy="no-prod-secret-read"
              decision="BLOCK"
              reason="Production secret access denied by policy"
            />
          </div>
        </section>

        {/* Wrap the invocation. Keep the server. — Figma frame 14 */}
        <section className="mb-20 grid grid-cols-1 lg:grid-cols-2 gap-8 items-center">
          <div>
            <h2 className="text-2xl font-bold text-stone-900 mb-3">
              Wrap the invocation. Keep the server.
            </h2>
            <p className="text-stone-500 text-sm leading-relaxed mb-4">
              Guard adapts the compatible client and MCP server. Your existing MCP servers stay in place —
              Guard sits at the transport layer, evaluates each tool call, and forwards allowed calls unchanged.
            </p>
            <p className="text-xs font-mono text-stone-400 uppercase tracking-widest">
              No client changes required
            </p>
          </div>
          <pre className="rounded-xl border border-stone-800/60 bg-stone-950 text-stone-300 text-[12px] leading-relaxed p-5 overflow-x-auto font-mono shadow-md">
{`{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "deploy_production",
    "arguments": { "env": "prod" }
  }
}
`}
            <span className="block mt-3 text-emerald-400 text-[11px]">{"// guard: APPROVE → routed to Slack"}</span>
          </pre>
        </section>

        {/* MCP capabilities */}
        <section className="mb-20 border border-stone-200 rounded-2xl p-8 bg-stone-50">
          <h2 className="text-lg font-bold text-stone-900 mb-4">What Guard brings to MCP</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-6 text-sm text-stone-600">
            <div>
              <p className="font-semibold text-stone-900 mb-2">Tool discovery and registration</p>
              <p className="leading-relaxed">
                Conduct exposes a <span className="font-mono text-stone-700">.well-known/mcp.json</span> endpoint.
                MCP clients can discover and register Guard-wrapped servers automatically.
              </p>
            </div>
            <div>
              <p className="font-semibold text-stone-900 mb-2">Tool interception and Guard checks</p>
              <p className="leading-relaxed">
                Every tool invocation is intercepted. Guard evaluates it against the workspace policy
                before forwarding. No client-side configuration required.
              </p>
            </div>
            <div>
              <p className="font-semibold text-stone-900 mb-2">OAuth support</p>
              <p className="leading-relaxed">
                Guard supports OAuth for MCP tool authentication. Clients authenticate once;
                Guard manages token scope and rotation.
              </p>
            </div>
            <div>
              <p className="font-semibold text-stone-900 mb-2">Hash-chained evidence</p>
              <p className="leading-relaxed">
                Every MCP tool call decision is recorded in the same audit trail as CLI and proxy
                decisions. One receipt format across all enforcement surfaces.
              </p>
            </div>
          </div>
        </section>

        {/* Supported MCP clients */}
        <section className="mb-20">
          <h2 className="text-2xl font-bold text-stone-900 mb-3">Works with any MCP client</h2>
          <p className="text-sm text-stone-600 mb-6 max-w-2xl leading-relaxed">
            If it speaks MCP, Guard wraps it. There is no allow-list of vendors — any client that implements
            the Model Context Protocol connects through the same discovery endpoint and gets the same policy,
            audit, and OAuth handling. The clients below are the ones we test on every release.
          </p>
          <div className="border border-stone-200 rounded-2xl overflow-hidden bg-white">
            <div className="divide-y divide-stone-100">
              {[
                { client: "Claude Desktop", note: "Native MCP support" },
                { client: "Claude Code", note: "MCP tool calling in the CLI" },
                { client: "Cursor", note: "MCP tool calling in the IDE" },
                { client: "OpenAI Codex CLI", note: "MCP tool calling" },
                { client: "ChatGPT Desktop", note: "MCP connectors" },
                { client: "Gemini CLI", note: "MCP tool calling" },
                { client: "Windsurf", note: "MCP tool calling in the IDE" },
                { client: "VS Code (Copilot Chat)", note: "MCP tool calling" },
                { client: "Any MCP-compatible client", note: "Direct MCP or LLM proxy — no client changes required" },
              ].map(({ client, note }) => (
                <div key={client} className="flex items-center justify-between px-6 py-4 text-sm">
                  <div>
                    <span className="font-medium text-stone-900">{client}</span>
                    <span className="text-stone-400 ml-2 text-xs">{note}</span>
                  </div>
                  <span className="text-[10px] font-mono font-bold uppercase tracking-wider border border-emerald-200 bg-emerald-50 text-emerald-700 rounded px-2 py-0.5">
                    Shipped
                  </span>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* CTA */}
        {/* CTA — Figma indigo band */}
        <section className="-mx-6 sm:-mx-10 lg:-mx-20 px-6 sm:px-10 lg:px-20 py-16 sm:py-24 bg-indigo-600 mb-0 text-center">
          <h2 className="text-2xl sm:text-3xl font-bold text-white tracking-tight mb-6 max-w-2xl mx-auto">
            Policy at the MCP call. Not the client.
          </h2>
          <div className="flex flex-wrap justify-center gap-3">
            <Link
              href="/sign-up"
              className="inline-block rounded-xl bg-white text-indigo-700 px-6 py-3 text-sm font-semibold hover:bg-indigo-50 transition-colors"
            >
              Start Discovery — 14 days free
            </Link>
            <Link
              href="/guard"
              className="inline-block rounded-xl border border-indigo-300 bg-transparent text-white px-6 py-3 text-sm font-semibold hover:bg-indigo-700 transition-colors"
            >
              See how Guard works →
            </Link>
          </div>
        </section>

      </main>
    </div>
  )
}
