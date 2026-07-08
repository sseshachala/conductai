import { CtaLink } from "@/components/marketing/CtaLink"

/* ─── Page ──────────────────────────────────────────────────────────────── */

export default function SecurityCompliancePage() {
  return (
    <>
      <HeroSection />
      <ProblemSection />
      <PitchSection />
      <CompliancePacksCallout />
      <CtaSection />
    </>
  )
}

/* ─── Hero ──────────────────────────────────────────────────────────────── */

function HeroSection() {
  return (
    <section className="max-w-5xl mx-auto px-6 pt-20 pb-16 text-center">
      <div className="inline-flex items-center gap-2 bg-indigo-50 text-indigo-700 px-4 py-1.5 rounded-full text-xs font-semibold uppercase tracking-widest mb-8">
        <span className="w-1.5 h-1.5 rounded-full bg-indigo-500 inline-block" />
        For security &amp; compliance
      </div>
      <h1 className="text-5xl sm:text-6xl font-black tracking-tight text-stone-900 leading-[1.05] mb-6">
        AI agents are an unaudited actor class.{" "}
        <span className="bg-gradient-to-r from-indigo-600 to-violet-600 bg-clip-text text-transparent">Until now.</span>
      </h1>
      <p className="text-xl text-stone-500 max-w-2xl mx-auto leading-relaxed mb-8">
        ConductAI maps every agent decision to OWASP identifiers your auditor already recognises — with an immutable audit log and one-click compliance pack installation.
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
    headline: "No audit trail.",
    body: "Your SIEM sees network traffic. Your EDR sees file writes. Neither knows an AI agent caused them or what policy was in effect.",
  },
  {
    headline: "Compliance frameworks don't cover agents.",
    body: "SOC 2, HIPAA, and PCI DSS were written before autonomous AI tools existed. Your auditor is improvising.",
  },
  {
    headline: "Shadow agents are invisible.",
    body: "Developers install AI tools without IT approval. You have no inventory of what's running or what it has access to.",
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

const CAPABILITIES = [
  {
    icon: "🗂️",
    title: "OWASP-mapped events",
    desc: "Every Guard decision is tagged with the OWASP LLM Top 10 category it enforced. Your auditor speaks this language.",
  },
  {
    icon: "🔗",
    title: "Immutable audit log",
    desc: "Hash-chained. Every event links to the policy version that produced it. Tamper-evident by construction.",
  },
  {
    icon: "📑",
    title: "SOC 2 evidence generation",
    desc: "Export a filtered audit log by date range and control category. One click, not a week of log mining.",
  },
  {
    icon: "🔍",
    title: "Shadow agent discovery",
    desc: "Guard's hook detects AI tools running on developer machines without IT registration. Surfaces them in the dashboard.",
  },
]

function PitchSection() {
  return (
    <section className="max-w-5xl mx-auto px-6 py-20">
      <div className="text-center mb-12">
        <h2 className="text-3xl sm:text-4xl font-black text-stone-900 tracking-tight mb-4">
          Enforcement, not just observation.
        </h2>
      </div>
      <div className="grid sm:grid-cols-2 gap-5">
        {CAPABILITIES.map((c) => (
          <div key={c.title} className="border border-stone-200 rounded-xl p-6 bg-white hover:border-stone-300 hover:shadow-sm transition-all flex gap-4">
            <span className="text-2xl flex-shrink-0 mt-0.5">{c.icon}</span>
            <div>
              <h3 className="text-sm font-bold text-stone-900 mb-2">{c.title}</h3>
              <p className="text-sm text-stone-500 leading-relaxed">{c.desc}</p>
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}

/* ─── Compliance packs callout ──────────────────────────────────────────── */

const PACKS = ["OWASP LLM Top 10", "SOC 2", "HIPAA", "PCI DSS"]

function CompliancePacksCallout() {
  return (
    <section className="bg-stone-950 px-6 py-20">
      <div className="max-w-5xl mx-auto">
        <div className="border border-stone-700 rounded-xl bg-stone-900 p-8 text-center">
          <p className="text-xs font-semibold uppercase tracking-widest text-indigo-400 mb-4">One-click compliance packs</p>
          <div className="flex flex-wrap items-center justify-center gap-3 mb-6">
            {PACKS.map((pack) => (
              <span
                key={pack}
                className="border border-stone-700 rounded-lg px-4 py-2 text-sm font-semibold text-stone-300 bg-stone-800"
              >
                {pack}
              </span>
            ))}
          </div>
          <p className="text-stone-400 text-sm leading-relaxed max-w-lg mx-auto mb-8">
            Each pack installs a pre-built rule set signed by Conduct. Policies propagate to every governed agent instantly.
          </p>
          <a
            href="/registry"
            className="inline-flex items-center gap-1 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white px-6 py-3 text-sm font-semibold transition-colors"
          >
            Browse the Registry →
          </a>
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
          Give your auditor something they can work with.
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
          <a
            href="/registry"
            className="rounded-xl border border-white/40 text-white px-8 py-3.5 text-base font-semibold hover:bg-white/10 transition-colors w-full sm:w-auto text-center"
          >
            Browse compliance packs →
          </a>
        </div>
      </div>
    </section>
  )
}
