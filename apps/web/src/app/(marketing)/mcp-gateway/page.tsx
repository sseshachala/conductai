import Link from "next/link"
import { RuntimeFlow } from "@/components/marketing/facelift/RuntimeFlow"
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

        {/* Hero */}
        <section className="pt-20 pb-16 text-center">
          <p className="text-xs font-mono font-bold uppercase tracking-widest text-stone-400 mb-4">
            MCP
          </p>
          <h1 className="text-4xl sm:text-5xl font-black tracking-tight text-stone-900 leading-[1.05] mb-6">
            Runtime policy for MCP actions.
          </h1>
          <p className="text-lg text-stone-500 max-w-2xl mx-auto leading-relaxed mb-10">
            Guard sits between the MCP client and the MCP server. Every tool call is evaluated
            against policy before it reaches the server. Policy applies at the MCP call — not at
            the client, not at the model.
          </p>
          <div className="flex flex-wrap justify-center gap-3">
            <Link
              href="/sign-up"
              className="inline-block rounded-xl bg-stone-900 text-white px-6 py-3 text-sm font-semibold hover:bg-stone-700 transition-colors"
            >
              Start Discovery — 14 days free
            </Link>
            <Link
              href="/demo"
              className="inline-block rounded-xl border border-stone-200 bg-white text-stone-700 px-6 py-3 text-sm font-semibold hover:bg-stone-50 transition-colors"
            >
              Book a Demo
            </Link>
          </div>
        </section>

        {/* MCP flow diagram */}
        <section className="mb-20">
          <h2 className="text-2xl font-bold text-stone-900 mb-3">
            MCP client → Guard → MCP server.
          </h2>
          <p className="text-stone-500 text-sm leading-relaxed mb-8 max-w-2xl">
            Guard wraps the MCP transport layer. Clients connect to Guard as if it were the MCP server.
            Guard evaluates each tool call and forwards allowed calls to the upstream server.
            Blocked calls never reach the server.
          </p>
          <div className="border border-stone-200 rounded-2xl bg-stone-50 p-8 mb-8">
            <RuntimeFlow variant="compact" />
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-sm font-mono">
            {[
              { step: "1", label: "MCP Client", desc: "Claude Desktop, Cursor, or any MCP-compatible client sends a tool call." },
              { step: "2", label: "Guard evaluates", desc: "Guard checks the tool call against policy. Allow, approve, or block — before the server sees it." },
              { step: "3", label: "MCP Server", desc: "Allowed calls reach the server. Blocked calls return a Guard decision with reason." },
            ].map(({ step, label, desc }) => (
              <div key={step} className="border border-stone-200 rounded-xl bg-white p-5">
                <div className="flex items-center gap-2 mb-2">
                  <span className="w-5 h-5 rounded-full bg-stone-900 text-white text-[10px] font-bold flex items-center justify-center shrink-0">
                    {step}
                  </span>
                  <span className="font-bold text-stone-900 text-[13px]">{label}</span>
                </div>
                <p className="text-stone-500 text-[12px] leading-relaxed">{desc}</p>
              </div>
            ))}
          </div>
        </section>

        {/* Policy applies at the MCP call */}
        <section className="mb-20">
          <h2 className="text-2xl font-bold text-stone-900 mb-3">
            Policy at the call, not the client.
          </h2>
          <p className="text-stone-500 text-sm leading-relaxed mb-8 max-w-2xl">
            MCP clients do not enforce policy — they issue tool calls. Guard is the enforcement
            point that sits at the transport layer. The same policy that governs Claude Code CLI
            actions also governs MCP tool calls through the same engine.
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
            <DecisionCard
              agent="claude-code / deploy-agent"
              action="update_terraform"
              resource="prod-vpc"
              policy="no-production-network-change"
              decision="BLOCK"
              reason="Production network modifications require approved change record."
            />
            <DecisionCard
              agent="cursor-agent-17"
              action="deploy_production"
              resource="payments-api"
              policy="production-change-v4"
              decision="APPROVE"
              reason="Production deployment outside approved change window"
              showButtons
            />
          </div>
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
          <h2 className="text-2xl font-bold text-stone-900 mb-3">Supported MCP clients</h2>
          <div className="border border-stone-200 rounded-2xl overflow-hidden bg-white">
            <div className="divide-y divide-stone-100">
              {[
                { client: "Claude Desktop", note: "Native MCP support", status: "Shipped" },
                { client: "Cursor", note: "MCP tool calling", status: "Shipped" },
                { client: "Custom agents", note: "Any MCP-compatible client via proxy or direct MCP", status: "Shipped" },
              ].map(({ client, note, status }) => (
                <div key={client} className="flex items-center justify-between px-6 py-4 text-sm">
                  <div>
                    <span className="font-medium text-stone-900">{client}</span>
                    <span className="text-stone-400 ml-2 text-xs">{note}</span>
                  </div>
                  <span className="text-[10px] font-mono font-bold uppercase tracking-wider border border-emerald-200 bg-emerald-50 text-emerald-700 rounded px-2 py-0.5">
                    {status}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* CTA */}
        <section className="mb-20 text-center border-t border-stone-100 pt-16">
          <h2 className="text-2xl font-bold text-stone-900 mb-4">
            Policy at the MCP call. Not the client.
          </h2>
          <div className="flex flex-wrap justify-center gap-3">
            <Link
              href="/sign-up"
              className="inline-block rounded-xl bg-stone-900 text-white px-6 py-3 text-sm font-semibold hover:bg-stone-700 transition-colors"
            >
              Start Discovery — 14 days free
            </Link>
            <Link
              href="/guard"
              className="inline-block rounded-xl border border-stone-200 bg-white text-stone-700 px-6 py-3 text-sm font-semibold hover:bg-stone-50 transition-colors"
            >
              See how Guard works →
            </Link>
          </div>
        </section>

      </main>
    </div>
  )
}
