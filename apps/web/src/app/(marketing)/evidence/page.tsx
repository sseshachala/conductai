import Link from "next/link"
import { EvidenceReceipt } from "@/components/marketing/facelift/EvidenceReceipt"

export const metadata = {
  title: "Evidence — Conduct",
  description:
    "Every action taken by an AI agent leaves a signed, replayable audit record. Decision, approval, execution, integrity — one receipt per action.",
}

export default function EvidencePage() {
  return (
    <div className="min-h-screen bg-white">
      <main className="max-w-5xl mx-auto px-6 py-20">
        <section className="mb-16 text-center">
          <p className="text-xs font-semibold uppercase tracking-widest text-stone-400 mb-4">
            Evidence
          </p>
          <h1 className="text-4xl sm:text-5xl font-black tracking-tight text-stone-900 leading-[1.05] mb-6">
            Know exactly what happened — and why.
          </h1>
          <p className="text-lg text-stone-500 max-w-2xl mx-auto leading-relaxed">
            Every action Guard evaluates leaves a receipt: the decision, the
            rule it matched, who approved it, and a signed record you can
            replay. One answer per action, not a log to correlate.
          </p>
        </section>

        <section className="mb-20 flex justify-center">
          <EvidenceReceipt />
        </section>

        <section className="mb-20 grid grid-cols-1 sm:grid-cols-2 gap-8 text-sm text-stone-600">
          <div>
            <h2 className="text-lg font-bold text-stone-900 mb-2">
              What each receipt contains
            </h2>
            <ul className="list-disc pl-5 space-y-1">
              <li>Decision (allow / approve / block) and the rule that fired</li>
              <li>The agent, user, resource, and action attempted</li>
              <li>Approval chain if human review was required</li>
              <li>Execution outcome and any downstream effects</li>
              <li>Integrity marker so tampering is detectable</li>
            </ul>
          </div>
          <div>
            <h2 className="text-lg font-bold text-stone-900 mb-2">
              What you can do with it
            </h2>
            <ul className="list-disc pl-5 space-y-1">
              <li>Answer a regulator or auditor with a signed record</li>
              <li>Reconstruct any agent decision after the fact</li>
              <li>Map decisions to compliance controls (SOC2, HIPAA)</li>
              <li>Retain and export by policy, not by log volume</li>
            </ul>
          </div>
        </section>

        <section className="text-center border-t border-stone-100 pt-16">
          <p className="text-sm text-stone-400 mb-4">
            Full pillar page — mapping, retention, compliance exports — shipping soon.
          </p>
          <Link
            href="/guard"
            className="inline-block rounded-xl bg-stone-900 text-white px-6 py-3 text-sm font-semibold hover:bg-stone-700 transition-colors"
          >
            See how Guard enforces →
          </Link>
        </section>
      </main>
    </div>
  )
}
