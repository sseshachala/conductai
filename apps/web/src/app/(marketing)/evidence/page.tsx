import Link from "next/link"
import { EvidenceReceipt } from "@/components/marketing/facelift/EvidenceReceipt"
import { LensTranscript } from "@/components/marketing/facelift/LensTranscript"

export const metadata = {
  title: "Evidence — Conduct",
  description:
    "Every action taken by an AI agent leaves a signed, replayable audit record. Decision, approval, execution, integrity — one receipt per action.",
}

export default function EvidencePage() {
  return (
    <div className="min-h-screen bg-white">
      <main className="max-w-5xl mx-auto px-6">

        {/* Hero — Figma frame 13 */}
        <section className="pt-20 pb-16 grid grid-cols-1 lg:grid-cols-2 gap-10 items-center">
          <div>
            <p className="text-xs font-mono font-bold uppercase tracking-widest text-stone-400 mb-4">
              Evidence
            </p>
            <h1 className="text-4xl sm:text-5xl font-black tracking-tight text-stone-900 leading-[1.05] mb-6">
              Know exactly what happened — and why.
            </h1>
            <p className="text-lg text-stone-500 leading-relaxed mb-8">
              Every action Guard evaluates leaves a receipt: the decision, the rule it matched,
              who approved it, and a signed record you can replay. One answer per action, not a log to correlate.
            </p>
            <div className="flex flex-wrap gap-3">
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
          </div>
          <div className="lg:pl-4 flex justify-center lg:justify-end">
            <EvidenceReceipt />
          </div>
        </section>

        {/* What each receipt contains — Figma frame 13 (6-card grid) */}
        <section className="mb-20">
          <h2 className="text-2xl font-bold text-stone-900 mb-6">What each receipt contains</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {[
              {
                title: "Decision",
                body: "Every allow, approve, and block is a receipt. The rule that fired and the reason string are embedded — not inferred from logs.",
              },
              {
                title: "Approval",
                body: "When Guard routes an action to human approval, the receipt records who approved it, when, and on what grounds. Full approval chain preserved.",
              },
              {
                title: "Execution",
                body: "After the action executes, the outcome is appended to the same receipt. One record from policy decision through execution result.",
              },
              {
                title: "Integrity",
                body: "Receipts are SHA-256 hash-chained. Alter any record and the chain breaks at verification. Verify on demand via the Guard API.",
              },
              {
                title: "Retention",
                body: "Stored per workspace with configurable retention. Export by time window, agent, policy, or decision type — set in Guard configuration, not separately.",
              },
              {
                title: "Reference",
                body: "Timestamp tied to canonical reference date. Every receipt is replayable — reconstruct any agent decision after the fact.",
              },
            ].map(({ title, body }) => (
              <div key={title} className="border border-stone-200 rounded-xl p-5 bg-white shadow-sm">
                <h3 className="text-base font-bold text-stone-900 mb-2">{title}</h3>
                <p className="text-sm text-stone-500 leading-relaxed">{body}</p>
              </div>
            ))}
          </div>
        </section>

        {/* Compliance mapping — Figma frame 13 (dark tag row) */}
        <section className="mb-20 -mx-6 sm:-mx-10 lg:-mx-20 px-6 sm:px-10 lg:px-20 py-14 bg-stone-950 rounded-3xl">
          <h2 className="text-2xl font-bold text-white mb-3">Compliance mapping</h2>
          <p className="text-stone-400 text-sm leading-relaxed mb-8 max-w-2xl">
            Guard ships 15 compliance packs. When a pack rule fires, the receipt records which standard was
            enforced and which rule matched. Reports are generated from the audit trail — not from manual
            assertions.
          </p>
          <div className="flex flex-wrap gap-2">
            {[
              "SOC 2 CC7.3",
              "HIPAA §164.312",
              "PCI DSS 4.0",
              "EU AI Act",
              "NIST AI RMF",
              "ISO 42001",
              "OWASP Agentic Top 10",
              "IRS 1075",
            ].map((standard) => (
              <span
                key={standard}
                className="border border-stone-700 rounded-lg bg-stone-900 px-3 py-1.5 text-xs font-mono text-stone-300"
              >
                {standard}
              </span>
            ))}
          </div>
          <p className="text-xs text-stone-500 mt-6">
            + 7 more packs. See{" "}
            <Link href="/solutions/security-compliance" className="underline hover:text-stone-300">
              Security Teams
            </Link>{" "}
            for the full list.
          </p>
        </section>

        {/* Lens transcript — Figma frame 13 */}
        <section className="mb-20 grid grid-cols-1 lg:grid-cols-2 gap-8 items-start">
          <div>
            <h2 className="text-2xl font-bold text-stone-900 mb-3">
              &ldquo;Show me every block against payments this month.&rdquo;
            </h2>
            <p className="text-stone-500 text-sm leading-relaxed mb-3">
              Lens is the workspace chat surface. Ask questions about Guard activity, compliance state,
              or any agent action — get answers backed by the audit trail, not log correlation.
            </p>
            <p className="text-xs font-mono text-stone-400 uppercase tracking-widest">
              Every block against payments · Sep 2026
            </p>
          </div>
          <div>
            <LensTranscript />
          </div>
        </section>

        {/* CTA */}
        <section className="mb-20 text-center border-t border-stone-100 pt-16">
          <h2 className="text-2xl font-bold text-stone-900 mb-4">One receipt per action. Verifiable. Always.</h2>
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
              See how Guard enforces →
            </Link>
          </div>
        </section>

      </main>
    </div>
  )
}
