import { CtaLink } from "@/components/marketing/CtaLink"

export const metadata = {
  title: "Security Loop | Conduct",
  description:
    "Scan to fix, closed. The Security Loop turns scanner findings into signed, merged mitigation PRs with hash-chained evidence for every step.",
}

export default function SecurityLoopPage() {
  return (
    <>
      <HeroSection />
      <ProblemSection />
      <HowItWorksSection />
      <ProofPointsSection />
      <IntegrationsSection />
      <CtaSection />
    </>
  )
}

function HeroSection() {
  return (
    <section className="max-w-5xl mx-auto px-6 pt-20 pb-16 text-center">
      <div className="inline-flex items-center gap-2 bg-indigo-50 text-indigo-700 px-4 py-1.5 rounded-full text-xs font-semibold uppercase tracking-widest mb-8">
        <span className="w-1.5 h-1.5 rounded-full bg-indigo-500 inline-block" />
        For AppSec and security engineering
      </div>
      <h1 className="text-5xl sm:text-6xl font-black tracking-tight text-stone-900 leading-[1.05] mb-6">
        The loop is the deliverable.{" "}
        <span className="bg-gradient-to-r from-indigo-600 to-violet-600 bg-clip-text text-transparent">Not the report.</span>
      </h1>
      <p className="text-xl text-stone-500 max-w-2xl mx-auto leading-relaxed mb-8">
        The Security Loop closes scan-to-fix. A scanner produces a finding. An autopilot playbook drafts
        the mitigation PR. A human approves. Every step signs into one hash-chained record you can hand to
        your auditor.
      </p>
      <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
        <a
          href="/secure"
          className="rounded-xl bg-stone-900 text-white px-7 py-3.5 text-base font-semibold hover:bg-stone-700 transition-colors w-full sm:w-auto text-center"
        >
          Install Security Loop
        </a>
        <a
          href="https://cal.com/sudhi-seshachala-pks7pd"
          target="_blank"
          rel="noopener"
          className="rounded-xl border border-stone-300 bg-white text-stone-700 px-7 py-3.5 text-base font-semibold hover:border-stone-400 hover:shadow-sm transition-all w-full sm:w-auto text-center"
        >
          Book a walkthrough
        </a>
      </div>
    </section>
  )
}

const PROBLEMS = [
  {
    headline: "Findings age in a ticket queue.",
    body: "The scanner produces a report. It becomes a Jira board. Six weeks later, a stressed engineer either fixes it, silently downgrades it, or loses it.",
  },
  {
    headline: "The scan is not the outcome.",
    body: "Buying more scanners produces more findings, not fewer vulnerabilities. The bottleneck was never detection. It was remediation.",
  },
  {
    headline: "Audits ask for proof, not tickets.",
    body: "An auditor wants to see the specific finding, the specific fix, and the reviewer who approved it. Screenshots do not survive scrutiny.",
  },
]

function ProblemSection() {
  return (
    <section className="bg-stone-50 border-y border-stone-200 px-6 py-20">
      <div className="max-w-5xl mx-auto">
        <h2 className="text-center text-2xl font-black text-stone-900 tracking-tight mb-10">
          The problem is the gap between find and fix.
        </h2>
        <div className="grid md:grid-cols-3 gap-6">
          {PROBLEMS.map((p) => (
            <div key={p.headline} className="border border-stone-200 rounded-xl bg-white p-6">
              <h3 className="text-sm font-bold text-stone-900 mb-2">{p.headline}</h3>
              <p className="text-sm text-stone-500 leading-relaxed">{p.body}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

const STEPS = [
  {
    n: "01",
    title: "Scan",
    body: "Findings from Semgrep, Trivy, Snyk, Gitleaks, GitHub Advanced Security, or any tool that produces SARIF or JSON feed into one Guard findings table.",
  },
  {
    n: "02",
    title: "Route",
    body: "Findings above a configurable severity threshold trigger the autopilot playbook. Below it, they stay visible but wait for triage.",
  },
  {
    n: "03",
    title: "Draft",
    body: "The autopilot playbook reads the finding, understands the file, and drafts the mitigation PR. It runs inside a sandbox with scoped credentials, not the full repo write key.",
  },
  {
    n: "04",
    title: "Approve",
    body: "A code owner reviews. CI runs. When the PR merges, the finding closes with the merge SHA and the reviewer identity attached.",
  },
  {
    n: "05",
    title: "Prove",
    body: "The full chain (finding, PR, approval, merge) is one hash-chained record. Signed. Queryable. Handed to an auditor as evidence.",
  },
]

function HowItWorksSection() {
  return (
    <section className="max-w-5xl mx-auto px-6 py-20">
      <div className="text-center mb-12">
        <h2 className="text-3xl sm:text-4xl font-black text-stone-900 tracking-tight mb-4">
          How the loop actually runs.
        </h2>
        <p className="text-stone-500 max-w-2xl mx-auto">
          Five steps. Each one leaves an audit line behind. The scan-to-fix distance becomes a number
          you can graph and move.
        </p>
      </div>
      <div className="space-y-4">
        {STEPS.map((s) => (
          <div key={s.n} className="border border-stone-200 rounded-xl p-6 bg-white flex gap-5">
            <span className="text-xs font-mono text-stone-400 flex-shrink-0 mt-1">{s.n}</span>
            <div>
              <h3 className="text-base font-bold text-stone-900 mb-1.5">{s.title}</h3>
              <p className="text-sm text-stone-500 leading-relaxed">{s.body}</p>
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}

const METRICS = [
  { k: "Mean time to remediation", v: "The number your CISO cares about. Watch it fall." },
  { k: "Findings closed per week", v: "Loop throughput. Distinct from findings opened per week." },
  { k: "Autopilot success rate", v: "PRs merged without rework as a share of PRs drafted." },
  { k: "Human approvals per week", v: "The load on your reviewers. Guides scaling decisions." },
]

function ProofPointsSection() {
  return (
    <section className="bg-stone-50 border-y border-stone-200 px-6 py-20">
      <div className="max-w-5xl mx-auto">
        <h2 className="text-center text-3xl font-black text-stone-900 tracking-tight mb-10">
          Metrics that move once the loop is running.
        </h2>
        <div className="grid sm:grid-cols-2 gap-5">
          {METRICS.map((m) => (
            <div key={m.k} className="border border-stone-200 rounded-xl p-6 bg-white">
              <h3 className="text-sm font-bold text-stone-900 mb-2">{m.k}</h3>
              <p className="text-sm text-stone-500 leading-relaxed">{m.v}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

const SCANNERS = ["Semgrep", "Trivy", "Snyk", "Gitleaks", "GitHub Advanced Security"]

function IntegrationsSection() {
  return (
    <section className="bg-stone-950 px-6 py-20">
      <div className="max-w-5xl mx-auto">
        <div className="border border-stone-700 rounded-xl bg-stone-900 p-8 text-center">
          <p className="text-xs font-semibold uppercase tracking-widest text-indigo-400 mb-4">Plugs into what you already run</p>
          <div className="flex flex-wrap items-center justify-center gap-3 mb-6">
            {SCANNERS.map((s) => (
              <span
                key={s}
                className="border border-stone-700 rounded-lg px-4 py-2 text-sm font-semibold text-stone-300 bg-stone-800"
              >
                {s}
              </span>
            ))}
          </div>
          <p className="text-stone-400 text-sm leading-relaxed max-w-lg mx-auto">
            Any scanner that produces SARIF or JSON feeds Guard. Custom scanners work with a small adapter.
            No rip-and-replace.
          </p>
        </div>
      </div>
    </section>
  )
}

function CtaSection() {
  return (
    <section className="px-6 py-24 bg-gradient-to-br from-indigo-600 to-violet-600">
      <div className="max-w-3xl mx-auto text-center">
        <h2 className="text-3xl sm:text-4xl font-black text-white tracking-tight leading-tight mb-4">
          Stop shipping reports. Start closing findings.
        </h2>
        <p className="text-indigo-100 text-lg mb-8">
          The Security Loop is a shipped Guard surface. Install it on your workspace and point your first
          scanner at it in an afternoon.
        </p>
        <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
          <a
            href="/secure"
            className="rounded-xl bg-white text-indigo-600 px-8 py-3.5 text-base font-bold hover:bg-indigo-50 transition-colors w-full sm:w-auto text-center"
          >
            Install Security Loop
          </a>
          <a
            href="/use-cases#security-loop"
            className="rounded-xl border border-white/40 text-white px-8 py-3.5 text-base font-semibold hover:bg-white/10 transition-colors w-full sm:w-auto text-center"
          >
            Read the deep dive
          </a>
        </div>
      </div>
    </section>
  )
}
