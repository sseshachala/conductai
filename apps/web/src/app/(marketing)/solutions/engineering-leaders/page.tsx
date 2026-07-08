import { CtaLink } from "@/components/marketing/CtaLink"

/* ─── Page ──────────────────────────────────────────────────────────────── */

export default function EngineeringLeadersPage() {
  return (
    <>
      <HeroSection />
      <ProblemSection />
      <PitchSection />
      <ProofArcSection />
      <CtaSection />
    </>
  )
}

/* ─── Hero ──────────────────────────────────────────────────────────────── */

function HeroSection() {
  return (
    <section className="max-w-5xl mx-auto px-6 pt-20 pb-16 text-center">
      <div className="inline-flex items-center gap-2 bg-stone-100 text-stone-600 px-4 py-1.5 rounded-full text-xs font-semibold uppercase tracking-widest mb-8">
        <span className="w-1.5 h-1.5 rounded-full bg-stone-400 inline-block" />
        For engineering leaders
      </div>
      <h1 className="text-5xl sm:text-6xl font-black tracking-tight text-stone-900 leading-[1.05] mb-6">
        Ship AI-assisted code without becoming<br className="hidden sm:block" />
        <span className="bg-gradient-to-r from-indigo-600 to-violet-600 bg-clip-text text-transparent"> the incident report.</span>
      </h1>
      <p className="text-xl text-stone-500 max-w-2xl mx-auto leading-relaxed mb-8">
        ConductAI gives platform teams a control plane for AI coding agents — policy personas per team, spend hard-stops, and a CI gate that blocks non-compliant commits.
      </p>
      <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
        <CtaLink className="rounded-xl bg-stone-900 text-white px-7 py-3.5 text-base font-semibold hover:bg-stone-700 transition-colors w-full sm:w-auto text-center" />
        <a
          href="https://cal.com/sudhi-seshachala-pks7pd"
          target="_blank"
          rel="noopener"
          className="rounded-xl border border-stone-300 bg-white text-stone-700 px-7 py-3.5 text-base font-semibold hover:border-stone-400 hover:shadow-sm transition-all w-full sm:w-auto text-center"
        >
          Book a demo
        </a>
      </div>
    </section>
  )
}

/* ─── Problem ───────────────────────────────────────────────────────────── */

const PROBLEMS = [
  {
    headline: "AI agents are multiplying.",
    body: "Every developer has Claude Code, Copilot, or Cursor. There's no inventory of what they're doing.",
  },
  {
    headline: "Spend is invisible.",
    body: "AI token costs accumulate per-developer with no budget controls. Finance asks. Engineering shrugs.",
  },
  {
    headline: "The blast radius is unknown.",
    body: "When an agent deletes the wrong file or exfiltrates a secret, you find out from the security team, not from a dashboard.",
  },
]

function ProblemSection() {
  return (
    <section className="bg-stone-50 border-y border-stone-200 px-6 py-20">
      <div className="max-w-5xl mx-auto">
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

/* ─── Pitch ─────────────────────────────────────────────────────────────── */

const FEATURES = [
  {
    icon: "👥",
    title: "Policy personas per team",
    desc: "Conservative / Standard / Developer. Assign per team. Change without redeploying.",
  },
  {
    icon: "💸",
    title: "Spend hard-stops",
    desc: "Per-developer and per-workspace token budgets. Agents stop when the limit is hit.",
  },
  {
    icon: "🚦",
    title: "CI release gate",
    desc: "conduct ci --exit-nonzero-on-block. Blocks PRs from merging if a Guard policy was violated in the session that produced them.",
  },
]

function PitchSection() {
  return (
    <section className="max-w-5xl mx-auto px-6 py-20">
      <div className="text-center mb-12">
        <h2 className="text-3xl sm:text-4xl font-black text-stone-900 tracking-tight mb-4">
          One control plane for every AI coding session.
        </h2>
      </div>
      <div className="grid md:grid-cols-3 gap-5">
        {FEATURES.map((f) => (
          <div key={f.title} className="border border-stone-200 rounded-xl p-6 bg-white hover:border-stone-300 hover:shadow-sm transition-all">
            <span className="text-2xl block mb-3">{f.icon}</span>
            <h3 className="text-sm font-bold text-stone-900 mb-2">{f.title}</h3>
            <p className="text-sm text-stone-500 leading-relaxed">{f.desc}</p>
          </div>
        ))}
      </div>
    </section>
  )
}

/* ─── Proof arc ─────────────────────────────────────────────────────────── */

const PROOF_MILESTONES = [
  {
    period: "Month 1",
    headline: "Every AI coding session is visible.",
    body: "You know which tools are running, who's using them, and what they're doing.",
  },
  {
    period: "Month 3",
    headline: "Policy violations drop 60%.",
    body: "Developers self-correct when they see the audit trail.",
  },
  {
    period: "Month 6",
    headline: "Security can generate SOC 2 evidence in minutes.",
    body: "No manual log review.",
  },
]

function ProofArcSection() {
  return (
    <section className="bg-stone-950 px-6 py-20">
      <div className="max-w-5xl mx-auto">
        <div className="text-center mb-12">
          <p className="text-xs font-semibold uppercase tracking-widest text-indigo-400 mb-3">What changes</p>
          <h2 className="text-3xl sm:text-4xl font-black text-white tracking-tight">
            Month by month, the control compounds.
          </h2>
        </div>
        <div className="grid md:grid-cols-3 gap-5">
          {PROOF_MILESTONES.map((m, i) => (
            <div key={m.period} className="border border-stone-700 rounded-xl bg-stone-900 p-6">
              <p className="text-xs font-bold uppercase tracking-widest text-indigo-400 mb-3">{m.period}</p>
              <h3 className="text-sm font-bold text-white mb-2 leading-snug">{m.headline}</h3>
              <p className="text-xs text-stone-400 leading-relaxed">{m.body}</p>
              <div className="mt-4 flex items-center gap-1">
                {PROOF_MILESTONES.map((_, j) => (
                  <span
                    key={j}
                    className={`h-1 rounded-full transition-all ${
                      j <= i ? "bg-indigo-500 flex-1" : "bg-stone-700 w-4"
                    }`}
                  />
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

/* ─── CTA ───────────────────────────────────────────────────────────────── */

function CtaSection() {
  return (
    <section className="px-6 py-24 bg-gradient-to-br from-indigo-600 to-violet-600">
      <div className="max-w-3xl mx-auto text-center">
        <h2 className="text-3xl sm:text-4xl font-black text-white tracking-tight leading-tight mb-4">
          Ready to put a control plane on your AI agents?
        </h2>
        <div className="flex flex-col sm:flex-row items-center justify-center gap-3 mt-8">
          <a
            href="https://cal.com/sudhi-seshachala-pks7pd"
            target="_blank"
            rel="noopener"
            className="rounded-xl bg-white text-indigo-600 px-8 py-3.5 text-base font-bold hover:bg-indigo-50 transition-colors w-full sm:w-auto text-center"
          >
            Book a demo
          </a>
        </div>
      </div>
    </section>
  )
}
