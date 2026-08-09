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

function ProofArcSection() {
  return (
    <section className="bg-stone-950 px-6 py-20">
      <div className="max-w-5xl mx-auto">
        <div className="text-center mb-12">
          <p className="text-xs font-semibold uppercase tracking-widest text-indigo-400 mb-3">What changes on day one</p>
          <h2 className="text-3xl sm:text-4xl font-black text-white tracking-tight">
            Every AI coding session is visible.
          </h2>
        </div>
        <div className="max-w-2xl mx-auto">
          <div className="border border-stone-700 rounded-xl bg-stone-900 p-8">
            <h3 className="text-base font-bold text-white mb-3 leading-snug">Full session visibility from install</h3>
            <p className="text-sm text-stone-400 leading-relaxed">
              Within ten minutes you know which AI tools your team is running, who is using them, and what they are doing. Spend is visible by developer and by day. Policy violations surface in the activity feed as they happen.
            </p>
          </div>
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
          <CtaLink className="rounded-xl bg-white text-indigo-600 px-8 py-3.5 text-base font-bold hover:bg-indigo-50 transition-colors w-full sm:w-auto text-center" />
          <a
            href="https://cal.com/sudhi-seshachala-pks7pd"
            target="_blank"
            rel="noopener"
            className="rounded-xl border border-white/40 text-white px-8 py-3.5 text-base font-semibold hover:bg-white/10 transition-colors w-full sm:w-auto text-center"
          >
            Book a demo
          </a>
        </div>
      </div>
    </section>
  )
}
