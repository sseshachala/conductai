import Link from "next/link"
import { AgentSurfaceStrip } from "@/components/marketing/facelift/AgentSurfaceStrip"
import { DecisionCard } from "@/components/marketing/facelift/DecisionCard"

export const metadata = {
  title: "Engineering Agents — Consistent policy across every AI tool | Conduct",
  description:
    "Let developers choose their AI tools. Guard enforces consistent policy across Claude Code, Cursor, Copilot, and Codex — without slowing anyone down.",
}

export default function EngineeringAgentsPage() {
  return (
    <div className="min-h-screen bg-white">
      <main className="max-w-5xl mx-auto px-6">

        {/* Hero */}
        <section className="pt-20 pb-16 text-center">
          <p className="text-xs font-mono font-bold uppercase tracking-widest text-stone-400 mb-4">
            Engineering Agents
          </p>
          <h1 className="text-4xl sm:text-5xl font-black tracking-tight text-stone-900 leading-[1.05] mb-6">
            Let developers choose. Enforce policy everywhere.
          </h1>
          <p className="text-lg text-stone-500 max-w-2xl mx-auto leading-relaxed mb-10">
            Your engineers use Claude Code, Cursor, Copilot, and Codex. Guard applies the same
            runtime policy across all of them — without a separate configuration per tool.
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

        {/* Let developers choose */}
        <section className="mb-20">
          <h2 className="text-2xl font-bold text-stone-900 mb-3">Developers keep their tools.</h2>
          <p className="text-stone-500 text-sm leading-relaxed mb-8 max-w-2xl">
            Guard integrates through the CLI hook, the HTTP proxy, and the MCP layer. Developers
            install once and keep using whichever AI tool they prefer. Policy travels with the agent,
            not with the tool.
          </p>
          <AgentSurfaceStrip />
        </section>

        {/* Consistent policy */}
        <section className="mb-20">
          <h2 className="text-2xl font-bold text-stone-900 mb-3">
            Consistent policy across every agent tool.
          </h2>
          <p className="text-stone-500 text-sm leading-relaxed mb-8 max-w-2xl">
            The same policy file governs all four agent tools. A rule written for Claude Code applies
            to Cursor and Codex without modification. One policy, no per-tool exceptions.
          </p>
          <div className="border border-stone-200 rounded-2xl overflow-hidden bg-white">
            <div className="px-6 py-4 bg-stone-50 border-b border-stone-200">
              <p className="text-xs font-mono font-bold uppercase tracking-widest text-stone-400">
                Same rule — all surfaces
              </p>
            </div>
            <div className="divide-y divide-stone-100">
              {[
                { agent: "claude-code / deploy-agent", tool: "Claude Code", surface: "CLI hook" },
                { agent: "cursor-agent-17", tool: "Cursor", surface: "CLI hook · proxy" },
                { agent: "copilot-reviewer", tool: "Copilot", surface: "CLI hook" },
                { agent: "codex / release-agent", tool: "Codex", surface: "CLI hook · proxy" },
              ].map(({ agent, tool, surface }) => (
                <div key={agent} className="flex items-center justify-between px-6 py-3 font-mono text-xs">
                  <div className="flex items-center gap-3">
                    <span className="text-stone-900 font-medium">{agent}</span>
                    <span className="text-stone-400 hidden sm:inline">·</span>
                    <span className="text-stone-400 hidden sm:inline">{tool}</span>
                  </div>
                  <span className="text-stone-400 text-[10px]">{surface}</span>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* Action table */}
        <section className="mb-20">
          <h2 className="text-2xl font-bold text-stone-900 mb-3">
            Allow, approve, or block — per action.
          </h2>
          <p className="text-stone-500 text-sm leading-relaxed mb-8 max-w-2xl">
            Guard applies the same decision framework across all agent tools. Routine actions
            proceed without friction. Consequential ones pause for approval. Prohibited ones stop.
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-6">
            <DecisionCard
              agent="claude-code / deploy-agent"
              action="run_tests"
              resource="orders-db"
              policy="production-change-v4"
              decision="ALLOW"
              reason="Action within policy limits"
              compact
            />
            <DecisionCard
              agent="codex / release-agent"
              action="deploy_production"
              resource="payments-api"
              policy="production-change-v4"
              decision="APPROVE"
              reason="Production deployment outside approved change window"
              showButtons
              compact
            />
            <DecisionCard
              agent="cursor-agent-17"
              action="update_terraform"
              resource="prod-vpc"
              policy="no-production-network-change"
              decision="BLOCK"
              reason="Production network modifications require approved change record."
              compact
            />
          </div>
        </section>

        {/* Why this matters for eng leads */}
        <section className="mb-20 border border-stone-200 rounded-2xl p-8 bg-stone-50">
          <h2 className="text-lg font-bold text-stone-900 mb-4">What this changes for engineering leads</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-6 text-sm text-stone-600">
            <div>
              <p className="font-semibold text-stone-900 mb-2">Before Guard</p>
              <ul className="space-y-2 leading-relaxed">
                <li>Each AI tool enforces policy differently — or not at all</li>
                <li>Audit trails scattered across tools</li>
                <li>Policy drift as teams adopt new agents</li>
                <li>Compliance questions answered by guessing</li>
              </ul>
            </div>
            <div>
              <p className="font-semibold text-stone-900 mb-2">With Guard</p>
              <ul className="space-y-2 leading-relaxed">
                <li>One policy file governs all agent tools</li>
                <li>Every decision logged in one audit trail</li>
                <li>New agents inherit policy automatically</li>
                <li>Compliance questions answered with signed receipts</li>
              </ul>
            </div>
          </div>
        </section>

        {/* CTA */}
        <section className="mb-20 text-center border-t border-stone-100 pt-16">
          <h2 className="text-2xl font-bold text-stone-900 mb-4">
            Consistent policy. Every agent. Every action.
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
