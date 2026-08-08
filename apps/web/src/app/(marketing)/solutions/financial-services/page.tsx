import { CtaLink } from "@/components/marketing/CtaLink"

export const metadata = {
  title: "Financial Services | Conduct",
  description:
    "Interim controls for agentic AI in banking while SR 26-2 catches up. Guard aligns to SR 11-7 pillars, OCC 2021-19, FFIEC IT Handbook, NYDFS 500, GLBA, ECOA, FCRA. 8 rules ship in the conduct-financial-services pack.",
}

export default function FinancialServicesPage() {
  return (
    <>
      <HeroSection />
      <GapSection />
      <PillarMappingSection />
      <PackRulesSection />
      <IntegrationSection />
      <CtaSection />
    </>
  )
}

function HeroSection() {
  return (
    <section className="max-w-5xl mx-auto px-6 pt-20 pb-16 text-center">
      <div className="inline-flex items-center gap-2 bg-indigo-50 text-indigo-700 px-4 py-1.5 rounded-full text-xs font-semibold uppercase tracking-widest mb-8">
        <span className="w-1.5 h-1.5 rounded-full bg-indigo-500 inline-block" />
        For banks, credit unions, and financial services
      </div>
      <h1 className="text-5xl sm:text-6xl font-black tracking-tight text-stone-900 leading-[1.05] mb-6">
        SR 26-2 excluded agents.{" "}
        <span className="bg-gradient-to-r from-indigo-600 to-violet-600 bg-clip-text text-transparent">You still have to govern them.</span>
      </h1>
      <p className="text-xl text-stone-500 max-w-3xl mx-auto leading-relaxed mb-6">
        The most mature model risk regime in the world just told banks the systems they are deploying sit outside the framework. 42 percent of financial firms are using or assessing agents. 21 percent have deployed. The deployment curve is ahead of the guidance curve. Guard ships the interim controls.
      </p>
      <p className="text-base text-stone-500 max-w-2xl mx-auto leading-relaxed italic mb-8">
        Aligned to SR 11-7 pillars while agent-specific guidance is pending.
      </p>
      <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
        <a
          href="/registry?tab=compliance&pack=conduct-financial-services"
          className="rounded-xl bg-stone-900 text-white px-7 py-3.5 text-base font-semibold hover:bg-stone-700 transition-colors w-full sm:w-auto text-center"
        >
          Install the financial services pack
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

const GAPS = [
  {
    headline: "SR 26-2 (April 2026)",
    body: "The Federal Reserve, OCC, and FDIC replaced SR 11-7 with SR 26-2, the first major revision in 15 years. It explicitly scoped generative and agentic AI out as novel and rapidly evolving. Agent-specific guidance is signaled but not yet issued.",
  },
  {
    headline: "42 percent already using",
    body: "NVIDIA 2026 State of AI in Financial Services survey. 42 percent of financial firms using or assessing agents. 21 percent have deployed. Banks are not waiting for the framework to catch up.",
  },
  {
    headline: "SR 11-7 principles still apply",
    body: "The pillars have not changed: model inventory, independent validation, ongoing monitoring, governance. What changed is that the methods behind those pillars no longer fit systems that adapt their steps at runtime. The interim answer is control at the runtime layer, not new validation cadence.",
  },
]

function GapSection() {
  return (
    <section className="bg-stone-50 border-y border-stone-200 px-6 py-20">
      <div className="max-w-5xl mx-auto">
        <h2 className="text-center text-2xl font-black text-stone-900 tracking-tight mb-10">
          The regulatory gap you are managing today.
        </h2>
        <div className="grid md:grid-cols-3 gap-6">
          {GAPS.map((g) => (
            <div key={g.headline} className="border border-stone-200 rounded-xl bg-white p-6">
              <h3 className="text-sm font-bold text-stone-900 mb-2">{g.headline}</h3>
              <p className="text-sm text-stone-500 leading-relaxed">{g.body}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

const PILLARS = [
  {
    pillar: "Model inventory",
    guard: "agent_identity registry with owner, source, platform of origin, and risk tier. Observed inventory derived from behavior, not just what was declared.",
  },
  {
    pillar: "Independent validation",
    guard: "Guard Verify adversarial battery plus hash-chained audit trail that a third-party auditor can verify without Conduct's cooperation.",
  },
  {
    pillar: "Ongoing monitoring",
    guard: "Guard console tracks per-agent block count, warn count, monthly spend, and warns at 80 percent of the committee cap.",
  },
  {
    pillar: "Governance",
    guard: "Tier-3 agents require recorded human oversight. Production promotion requires owner attestation. Credit and lending decisions require human-in-the-loop.",
  },
  {
    pillar: "Change management",
    guard: "Model swaps warn without a change control event. Every rule change is a versioned, signed audit event.",
  },
]

function PillarMappingSection() {
  return (
    <section className="max-w-5xl mx-auto px-6 py-20">
      <div className="text-center mb-12">
        <h2 className="text-3xl sm:text-4xl font-black text-stone-900 tracking-tight mb-4">
          How Guard maps to SR 11-7 pillars.
        </h2>
        <p className="text-stone-500 max-w-2xl mx-auto">
          The pillars have not changed. The runtime layer that satisfies them for agents did not exist. Now it does.
        </p>
      </div>
      <div className="space-y-3">
        {PILLARS.map((p) => (
          <div key={p.pillar} className="border border-stone-200 rounded-xl p-6 bg-white flex gap-5">
            <div className="w-48 flex-shrink-0">
              <p className="text-xs font-bold uppercase tracking-widest text-indigo-600">{p.pillar}</p>
            </div>
            <p className="text-sm text-stone-600 leading-relaxed">{p.guard}</p>
          </div>
        ))}
      </div>
    </section>
  )
}

const RULES = [
  { label: "Block", body: "Tier-3 agent action without a recorded human oversight event within 24 hours." },
  { label: "Block", body: "Agent promotion to production without documented owner attestation." },
  { label: "Block", body: "Agent write to core banking or ledger systems without segregation-of-duties evidence." },
  { label: "Block", body: "Credit, lending, or underwriting decisions without human-in-the-loop attestation." },
  { label: "Block", body: "Agent action on customer PII or account data without documented control mapping." },
  { label: "Block", body: "Cross-tenant or cross-portfolio customer data read without explicit permit." },
  { label: "Warn", body: "Model swap mid-workflow without accompanying change control event." },
  { label: "Warn", body: "Monthly agent spend reaching 80 percent of committee cap." },
]

function PackRulesSection() {
  return (
    <section className="bg-stone-950 px-6 py-20">
      <div className="max-w-4xl mx-auto">
        <div className="text-center mb-10">
          <p className="text-xs font-semibold uppercase tracking-widest text-indigo-400 mb-3">conduct-financial-services v1.0.0</p>
          <h2 className="text-3xl font-black text-white tracking-tight mb-4">
            Eight rules ship in the pack today.
          </h2>
          <p className="text-stone-400 max-w-2xl mx-auto text-sm leading-relaxed">
            Every rule is tagged to SR 11-7, OCC 2021-19, FFIEC, NYDFS 500, GLBA, ECOA, or FCRA. Compliance evidence attaches to every decision.
          </p>
        </div>
        <div className="space-y-3">
          {RULES.map((r, i) => (
            <div key={i} className="border border-stone-700 rounded-xl bg-stone-900 p-5 flex items-start gap-4">
              <span className={`px-2.5 py-1 rounded-lg text-xs font-bold uppercase tracking-wider flex-shrink-0 mt-0.5 ${r.label === "Block" ? "bg-red-500/20 text-red-300 border border-red-500/40" : "bg-amber-500/20 text-amber-300 border border-amber-500/40"}`}>
                {r.label}
              </span>
              <p className="text-sm text-stone-300 leading-relaxed">{r.body}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

function IntegrationSection() {
  return (
    <section className="max-w-4xl mx-auto px-6 py-20">
      <h2 className="text-center text-3xl font-black text-stone-900 tracking-tight mb-6">
        How it plugs in.
      </h2>
      <p className="text-center text-stone-500 max-w-2xl mx-auto mb-10">
        Guard sits between your agents and every downstream system. Existing SR 11-7 process wraps around it.
      </p>
      <div className="border border-stone-200 rounded-xl p-6 bg-stone-50">
        <ol className="space-y-4 text-sm text-stone-700 leading-relaxed">
          <li>
            <span className="font-bold text-stone-900">1. Install the pack.</span>{" "}
            One click from the Registry. Rules load, framework mappings attach, audit chain begins recording immediately.
          </li>
          <li>
            <span className="font-bold text-stone-900">2. Tag your agents by risk tier.</span>{" "}
            Tier 1 (internal, reversible), Tier 2 (consequential, recoverable), Tier 3 (consequential, irreversible, regulated). Tier drives the obligations.
          </li>
          <li>
            <span className="font-bold text-stone-900">3. Guard evaluates every proposed action.</span>{" "}
            Allow, warn, or block based on tier, target system, and current governance state. Fail closed.
          </li>
          <li>
            <span className="font-bold text-stone-900">4. Every decision is a signed audit row.</span>{" "}
            Model risk committee gets a queryable evidence table, not a screenshot deck. Auditors get proof, not assertions.
          </li>
          <li>
            <span className="font-bold text-stone-900">5. Your existing SR 11-7 process wraps around Guard.</span>{" "}
            Independent validation, model inventory, ongoing monitoring all point at the same audit chain. Guard produces the artifacts your MRM function is already asking for.
          </li>
        </ol>
      </div>
    </section>
  )
}

function CtaSection() {
  return (
    <section className="px-6 py-24 bg-gradient-to-br from-indigo-600 to-violet-600">
      <div className="max-w-3xl mx-auto text-center">
        <h2 className="text-3xl sm:text-4xl font-black text-white tracking-tight leading-tight mb-4">
          Interim controls, credible with the model risk committee.
        </h2>
        <p className="text-indigo-100 text-lg mb-8">
          The pack ships today. Ready when the eventual guidance arrives.
        </p>
        <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
          <a
            href="/registry?tab=compliance&pack=conduct-financial-services"
            className="rounded-xl bg-white text-indigo-600 px-8 py-3.5 text-base font-bold hover:bg-indigo-50 transition-colors w-full sm:w-auto text-center"
          >
            Install the pack
          </a>
          <a
            href="/frameworks"
            className="rounded-xl border border-white/40 text-white px-8 py-3.5 text-base font-semibold hover:bg-white/10 transition-colors w-full sm:w-auto text-center"
          >
            See all compliance frameworks
          </a>
        </div>
      </div>
    </section>
  )
}
