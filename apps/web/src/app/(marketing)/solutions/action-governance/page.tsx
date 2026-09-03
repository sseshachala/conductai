import Link from "next/link"
import { DecisionCard } from "@/components/marketing/facelift/DecisionCard"

export const metadata = {
  title: "Action Governance — Control what AI agents do | Conduct",
  description:
    "Guard evaluates every consequential action before it executes. Refund caps, production deployments, secret reads — policy runs at the action, not the report.",
}

export default function ActionGovernancePage() {
  return (
    <div className="min-h-screen bg-white">
      <main className="max-w-5xl mx-auto px-6">

        {/* Hero */}
        <section className="pt-20 pb-16 text-center">
          <p className="text-xs font-mono font-bold uppercase tracking-widest text-stone-400 mb-4">
            Action Governance
          </p>
          <h1 className="text-4xl sm:text-5xl font-black tracking-tight text-stone-900 leading-[1.05] mb-6">
            Control the action before it becomes an outcome.
          </h1>
          <p className="text-lg text-stone-500 max-w-2xl mx-auto leading-relaxed mb-10">
            Every AI agent action that touches money, infrastructure, or sensitive data is evaluated
            by Guard before it executes. Allow, approve, or block — with a signed record of why.
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

        {/* 3 stories — the core */}
        <section className="mb-20">
          <h2 className="text-2xl font-bold text-stone-900 mb-3">Three stories. One engine.</h2>
          <p className="text-stone-500 text-sm leading-relaxed mb-10 max-w-2xl">
            The same Guard policy engine handles the full range of consequential business actions.
            The decision, the rule, and the reason are the same data structure across all three.
          </p>

          {/* Story 1 — Refund cap */}
          <div className="mb-12">
            <div className="mb-4">
              <span className="text-xs font-mono font-bold uppercase tracking-widest text-stone-400">Story 1</span>
              <h3 className="text-lg font-bold text-stone-900 mt-1">Refund over the cap</h3>
              <p className="text-sm text-stone-500 mt-1 max-w-xl leading-relaxed">
                A support agent attempts to process a $840 refund for customer C-8911. The refund-cap
                policy blocks it. A smaller refund ($120) on the same account proceeds immediately.
              </p>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
              <DecisionCard
                agent="codex / release-agent"
                action="process_refund"
                resource="customer C-8911"
                policy="refund-cap"
                decision="BLOCK"
                reason="Refunds over $500 require human approval per FIN-07."
              />
              <DecisionCard
                agent="codex / release-agent"
                action="process_refund"
                resource="customer C-8911"
                policy="refund-cap"
                decision="ALLOW"
                reason="Refund of $120 is within the $500 automatic approval limit."
              />
            </div>
          </div>

          {/* Story 2 — Production deploy approval */}
          <div className="mb-12">
            <div className="mb-4">
              <span className="text-xs font-mono font-bold uppercase tracking-widest text-stone-400">Story 2</span>
              <h3 className="text-lg font-bold text-stone-900 mt-1">Production deployment outside change window</h3>
              <p className="text-sm text-stone-500 mt-1 max-w-xl leading-relaxed">
                A deploy agent attempts to push to production at 14:32 UTC — outside the approved change
                window. Guard routes to Slack for human approval rather than blocking outright.
              </p>
            </div>
            <div className="max-w-sm">
              <DecisionCard
                agent="claude-code / deploy-agent"
                action="deploy_production"
                resource="payments-api"
                policy="production-change-v4"
                decision="APPROVE"
                reason="Production deployment outside approved change window"
                showButtons
              />
            </div>
          </div>

          {/* Story 3 — Secret read block */}
          <div className="mb-4">
            <div className="mb-4">
              <span className="text-xs font-mono font-bold uppercase tracking-widest text-stone-400">Story 3</span>
              <h3 className="text-lg font-bold text-stone-900 mt-1">Secret read in production environment</h3>
              <p className="text-sm text-stone-500 mt-1 max-w-xl leading-relaxed">
                An agent attempts to read a production secret during a scheduled task. Guard blocks
                the action — secret access from automated agents requires an explicit exemption.
              </p>
            </div>
            <div className="max-w-sm">
              <DecisionCard
                agent="cursor-agent-17"
                action="read_env"
                resource="orders-db"
                policy="no-production-network-change"
                decision="BLOCK"
                reason="Production secret reads by automated agents are not permitted without an approved exemption."
              />
            </div>
          </div>
        </section>

        {/* What this is not */}
        <section className="mb-20 border border-stone-200 rounded-2xl p-8 bg-stone-50">
          <h2 className="text-lg font-bold text-stone-900 mb-3">
            Policy at the action, not at the report.
          </h2>
          <p className="text-stone-500 text-sm leading-relaxed max-w-2xl">
            Action governance is not an audit log you review after the fact. Guard runs at the moment
            the agent calls the action — before money moves, before the deployment lands, before the
            secret is read. The decision is made then, with a receipt that proves it.
          </p>
        </section>

        {/* CTA */}
        <section className="mb-20 text-center border-t border-stone-100 pt-16">
          <h2 className="text-2xl font-bold text-stone-900 mb-4">
            Govern the action, not the aftermath.
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
