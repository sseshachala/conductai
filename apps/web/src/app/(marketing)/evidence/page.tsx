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
      <main className="max-w-5xl mx-auto px-6">

        {/* Hero */}
        <section className="pt-20 pb-16 text-center">
          <p className="text-xs font-mono font-bold uppercase tracking-widest text-stone-400 mb-4">
            Evidence
          </p>
          <h1 className="text-4xl sm:text-5xl font-black tracking-tight text-stone-900 leading-[1.05] mb-6">
            Know exactly what happened — and why.
          </h1>
          <p className="text-lg text-stone-500 max-w-2xl mx-auto leading-relaxed mb-10">
            Every action Guard evaluates leaves a receipt: the decision, the rule it matched,
            who approved it, and a signed record you can replay. One answer per action, not a log to correlate.
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

        {/* Receipt */}
        <section className="mb-20 flex justify-center">
          <EvidenceReceipt />
        </section>

        {/* What each receipt contains */}
        <section className="mb-20 grid grid-cols-1 sm:grid-cols-2 gap-8 text-sm text-stone-600">
          <div>
            <h2 className="text-lg font-bold text-stone-900 mb-3">What each receipt contains</h2>
            <ul className="space-y-2 leading-relaxed">
              <li className="flex items-start gap-2">
                <span className="w-1.5 h-1.5 rounded-full bg-stone-400 mt-1.5 shrink-0" />
                Decision (allow / approve / block) and the rule that fired
              </li>
              <li className="flex items-start gap-2">
                <span className="w-1.5 h-1.5 rounded-full bg-stone-400 mt-1.5 shrink-0" />
                The agent, user, resource, and action attempted
              </li>
              <li className="flex items-start gap-2">
                <span className="w-1.5 h-1.5 rounded-full bg-stone-400 mt-1.5 shrink-0" />
                Approval chain if human review was required
              </li>
              <li className="flex items-start gap-2">
                <span className="w-1.5 h-1.5 rounded-full bg-stone-400 mt-1.5 shrink-0" />
                Execution outcome and any downstream effects
              </li>
              <li className="flex items-start gap-2">
                <span className="w-1.5 h-1.5 rounded-full bg-stone-400 mt-1.5 shrink-0" />
                Integrity marker — SHA-256 hash chain so tampering is detectable
              </li>
              <li className="flex items-start gap-2">
                <span className="w-1.5 h-1.5 rounded-full bg-stone-400 mt-1.5 shrink-0" />
                Reference timestamp tied to the canonical reference date
              </li>
            </ul>
          </div>
          <div>
            <h2 className="text-lg font-bold text-stone-900 mb-3">What you can do with it</h2>
            <ul className="space-y-2 leading-relaxed">
              <li className="flex items-start gap-2">
                <span className="w-1.5 h-1.5 rounded-full bg-stone-400 mt-1.5 shrink-0" />
                Answer a regulator or auditor with a signed record
              </li>
              <li className="flex items-start gap-2">
                <span className="w-1.5 h-1.5 rounded-full bg-stone-400 mt-1.5 shrink-0" />
                Reconstruct any agent decision after the fact
              </li>
              <li className="flex items-start gap-2">
                <span className="w-1.5 h-1.5 rounded-full bg-stone-400 mt-1.5 shrink-0" />
                Map decisions to compliance controls (SOC 2, HIPAA, PCI DSS, EU AI Act)
              </li>
              <li className="flex items-start gap-2">
                <span className="w-1.5 h-1.5 rounded-full bg-stone-400 mt-1.5 shrink-0" />
                Retain and export by policy, not by log volume
              </li>
              <li className="flex items-start gap-2">
                <span className="w-1.5 h-1.5 rounded-full bg-stone-400 mt-1.5 shrink-0" />
                Verify chain integrity via the Guard verification API
              </li>
            </ul>
          </div>
        </section>

        {/* Decision / Approval / Execution */}
        <section className="mb-16 border-t border-stone-100 pt-16">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-8">
            <div>
              <h3 className="text-base font-bold text-stone-900 mb-2">Decision</h3>
              <p className="text-sm text-stone-500 leading-relaxed">
                Every allow, approve, and block is a receipt. The decision is not inferred from logs —
                it is the primary record. The rule that fired and the reason string are embedded.
              </p>
            </div>
            <div>
              <h3 className="text-base font-bold text-stone-900 mb-2">Approval</h3>
              <p className="text-sm text-stone-500 leading-relaxed">
                When Guard routes an action to human approval, the receipt records who approved it,
                when they approved it, and on what grounds. The full approval chain is part of the receipt.
              </p>
            </div>
            <div>
              <h3 className="text-base font-bold text-stone-900 mb-2">Execution</h3>
              <p className="text-sm text-stone-500 leading-relaxed">
                After the action executes, the outcome is appended to the same receipt. One record
                from policy decision through to execution result.
              </p>
            </div>
          </div>
        </section>

        {/* Integrity + Retention */}
        <section className="mb-16">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-8">
            <div className="border border-stone-200 rounded-xl p-6 bg-white">
              <h3 className="text-base font-bold text-stone-900 mb-2">Integrity</h3>
              <p className="text-sm text-stone-500 leading-relaxed mb-3">
                Receipts are SHA-256 hash-chained. Each entry includes the hash of the previous entry.
                Alter any record and the chain breaks at verification. The integrity endpoint lets you
                verify the full chain on demand.
              </p>
              <p className="text-xs font-mono text-stone-400">
                Guard verification API — get_verify_evidence
              </p>
            </div>
            <div className="border border-stone-200 rounded-xl p-6 bg-white">
              <h3 className="text-base font-bold text-stone-900 mb-2">Retention</h3>
              <p className="text-sm text-stone-500 leading-relaxed">
                Receipts are stored per workspace with configurable retention. Export by time window,
                agent, policy, or decision type. Retention policy is set in Guard configuration —
                not in the audit system separately.
              </p>
            </div>
          </div>
        </section>

        {/* Compliance mapping */}
        <section className="mb-20">
          <h2 className="text-2xl font-bold text-stone-900 mb-3">Compliance mapping</h2>
          <p className="text-stone-500 text-sm leading-relaxed mb-6 max-w-2xl">
            Guard ships 15 compliance packs. Each pack maps rules to a compliance standard. When a pack
            rule fires, the receipt records which standard was enforced and which rule matched. Compliance
            reports are generated from the audit trail — not from manual assertions.
          </p>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
            {[
              "SOC 2 CC7.3",
              "HIPAA §164.312",
              "PCI DSS 4.0",
              "EU AI Act",
              "NIST AI RMF",
              "ISO 42001",
              "OWASP Agentic Top 10",
              "IRS 1075",
              "Prompt injection",
              "Financial services",
            ].map((standard) => (
              <div
                key={standard}
                className="border border-stone-200 rounded-lg bg-stone-50 px-3 py-2 text-xs font-mono text-stone-600 text-center"
              >
                {standard}
              </div>
            ))}
          </div>
          <p className="text-xs text-stone-400 mt-3">
            + 5 more packs. See{" "}
            <Link href="/solutions/security-compliance" className="underline hover:text-stone-600">
              Security Teams
            </Link>{" "}
            for the full list.
          </p>
        </section>

        {/* Lens vocab */}
        <section className="mb-20 border border-stone-200 rounded-xl bg-stone-50 px-6 py-5">
          <p className="text-xs font-mono text-stone-400 mb-2 uppercase tracking-widest">Lens</p>
          <p className="text-sm font-mono text-stone-700">
            &ldquo;Ask Lens: &lsquo;show me every block against{" "}
            <span className="text-red-600">payments-api</span> this month.&rsquo;&rdquo;
          </p>
          <p className="text-xs text-stone-400 mt-3 leading-relaxed">
            Lens is the workspace chat surface. Ask questions about Guard activity, compliance state,
            or any agent action — and get answers backed by the audit trail, not log correlation.
          </p>
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
