import { CtaLink } from "@/components/marketing/CtaLink"

export const metadata = {
  title: "Life Sciences | Conduct",
  description:
    "Guard controls for agentic AI in life sciences. Aligned to FDA Computer Software Assurance, FDA/EMA Good Machine Learning Practice, ICH Q9, GAMP 5, ISO 42001, HIPAA, and EU AI Act Article 26. 9 rules ship in the conduct-life-sciences pack.",
}

export default function LifeSciencesPage() {
  return (
    <>
      <HeroSection />
      <ContextSection />
      <PrincipleMappingSection />
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
        For pharma, biotech, medical devices, and clinical research
      </div>
      <h1 className="text-5xl sm:text-6xl font-black tracking-tight text-stone-900 leading-[1.05] mb-6">
        AI may inform.{" "}
        <span className="bg-gradient-to-r from-indigo-600 to-violet-600 bg-clip-text text-transparent">A human owns the decision.</span>
      </h1>
      <p className="text-xl text-stone-500 max-w-3xl mx-auto leading-relaxed mb-6">
        FDA's position is unambiguous. AI may inform the work, but a human must remain responsible for the decision and be able to explain why it was appropriate. No dashboard satisfies that requirement on its own. Guard produces the receipts that do.
      </p>
      <p className="text-base text-stone-500 max-w-2xl mx-auto leading-relaxed italic mb-8">
        Aligned to FDA CSA, FDA and EMA Good Machine Learning Practice, ICH Q9, GAMP 5, ISO 42001, and EU AI Act.
      </p>
      <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
        <a
          href="/registry?tab=compliance&pack=conduct-life-sciences"
          className="rounded-xl bg-stone-900 text-white px-7 py-3.5 text-base font-semibold hover:bg-stone-700 transition-colors w-full sm:w-auto text-center"
        >
          Install the life sciences pack
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

const CONTEXT = [
  {
    headline: "There is no single AI rulebook",
    body: "Validation teams piece together governance from FDA Computer Software Assurance, the 2025 FDA draft on AI credibility, ICH Q9 quality risk management, GAMP 5 for automated manufacturing, ISO 42001, and voluntary standards. Every framework is right about part of the problem. None is complete for agents.",
  },
  {
    headline: "2026 raised the bar",
    body: "FDA and EMA jointly issued ten Good Machine Learning Practice principles in early 2026. EU AI Act high-risk obligations are phasing in this year. The direction is clearer. The methods are still fragmented.",
  },
  {
    headline: "Human accountability is non-negotiable",
    body: "The one point every framework agrees on. Agents may propose. Humans decide. Every decision needs a recorded reason. Guard is the runtime layer that makes that recording automatic instead of forensic.",
  },
]

function ContextSection() {
  return (
    <section className="bg-stone-50 border-y border-stone-200 px-6 py-20">
      <div className="max-w-5xl mx-auto">
        <h2 className="text-center text-2xl font-black text-stone-900 tracking-tight mb-10">
          Fragmented frameworks. One consistent obligation.
        </h2>
        <div className="grid md:grid-cols-3 gap-6">
          {CONTEXT.map((c) => (
            <div key={c.headline} className="border border-stone-200 rounded-xl bg-white p-6">
              <h3 className="text-sm font-bold text-stone-900 mb-2">{c.headline}</h3>
              <p className="text-sm text-stone-500 leading-relaxed">{c.body}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

const PRINCIPLES = [
  {
    principle: "Human accountability",
    guard: "Clinical-adjacent and patient-safety-adjacent agent actions block until a human review event is recorded. Agent proposes, human decides, both are on the audit chain.",
  },
  {
    principle: "Groundedness",
    guard: "Agent proposals lacking provenance to an authoritative source (protocol, monograph, published study, internal SOP) trigger a warning. Missing citation is a first-class signal.",
  },
  {
    principle: "Intended use scope",
    guard: "Actions outside the validated intended-use scope warn. Off-label, unvalidated, and research-only scopes are surfaced immediately.",
  },
  {
    principle: "Data integrity for GxP systems",
    guard: "Writes to LIMS, EDC, MES, EBR, or CTMS require a two-person integrity check. Agent proposes, human confirms, both events are recorded with time and identity.",
  },
  {
    principle: "Credibility assessment",
    guard: "Expired or missing credibility assessment blocks agent action. Cadence is set proportional to risk tier and pathway.",
  },
  {
    principle: "Change control",
    guard: "Model swaps in regulated pathways warn without an accompanying revalidation event. Silent model changes break FDA CSA validation status.",
  },
  {
    principle: "PHI handling",
    guard: "Agent actions on PHI-classified data require documented HIPAA scope check. Data classification and access basis are confirmed before commit.",
  },
]

function PrincipleMappingSection() {
  return (
    <section className="max-w-5xl mx-auto px-6 py-20">
      <div className="text-center mb-12">
        <h2 className="text-3xl sm:text-4xl font-black text-stone-900 tracking-tight mb-4">
          How Guard covers the underlying principles.
        </h2>
        <p className="text-stone-500 max-w-2xl mx-auto">
          Every framework agrees on the same set of principles. Guard applies them at the runtime layer so they hold on every agent action, not just at annual review.
        </p>
      </div>
      <div className="space-y-3">
        {PRINCIPLES.map((p) => (
          <div key={p.principle} className="border border-stone-200 rounded-xl p-6 bg-white flex gap-5">
            <div className="w-48 flex-shrink-0">
              <p className="text-xs font-bold uppercase tracking-widest text-indigo-600">{p.principle}</p>
            </div>
            <p className="text-sm text-stone-600 leading-relaxed">{p.guard}</p>
          </div>
        ))}
      </div>
    </section>
  )
}

const RULES = [
  { label: "Block", body: "Clinical decision-adjacent agent action without recorded human review." },
  { label: "Block", body: "Agent write to LIMS, EDC, MES, EBR, or CTMS without two-person integrity check." },
  { label: "Block", body: "Agent action when credibility assessment is expired or missing." },
  { label: "Block", body: "Patient-safety-adjacent action without human-in-the-loop attestation." },
  { label: "Block", body: "Agent action on PHI-classified data without documented HIPAA scope check." },
  { label: "Warn", body: "Agent proposal lacking provenance to authoritative source." },
  { label: "Warn", body: "Agent action outside validated intended-use scope." },
  { label: "Warn", body: "Model swap in regulated pathway without accompanying revalidation event." },
  { label: "Audit", body: "Every artifact-touching agent action for FDA CSA lifecycle traceability." },
]

function PackRulesSection() {
  return (
    <section className="bg-stone-950 px-6 py-20">
      <div className="max-w-4xl mx-auto">
        <div className="text-center mb-10">
          <p className="text-xs font-semibold uppercase tracking-widest text-indigo-400 mb-3">conduct-life-sciences v1.0.0</p>
          <h2 className="text-3xl font-black text-white tracking-tight mb-4">
            Nine rules ship in the pack today.
          </h2>
          <p className="text-stone-400 max-w-2xl mx-auto text-sm leading-relaxed">
            Every rule is tagged to FDA CSA, FDA/EMA GMLP, ICH Q9, GAMP 5, ISO 42001, HIPAA, or EU AI Act Article 26. Evidence attaches to every decision.
          </p>
        </div>
        <div className="space-y-3">
          {RULES.map((r, i) => (
            <div key={i} className="border border-stone-700 rounded-xl bg-stone-900 p-5 flex items-start gap-4">
              <span className={`px-2.5 py-1 rounded-lg text-xs font-bold uppercase tracking-wider flex-shrink-0 mt-0.5 ${r.label === "Block" ? "bg-red-500/20 text-red-300 border border-red-500/40" : r.label === "Warn" ? "bg-amber-500/20 text-amber-300 border border-amber-500/40" : "bg-sky-500/20 text-sky-300 border border-sky-500/40"}`}>
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
        Guard sits between your agents and every GxP system. Existing validation process wraps around it.
      </p>
      <div className="border border-stone-200 rounded-xl p-6 bg-stone-50">
        <ol className="space-y-4 text-sm text-stone-700 leading-relaxed">
          <li>
            <span className="font-bold text-stone-900">1. Install the pack.</span>{" "}
            One click from the Registry. Rules load, framework mappings attach, audit chain begins recording.
          </li>
          <li>
            <span className="font-bold text-stone-900">2. Declare intended use and risk tier per agent.</span>{" "}
            Tier and intended-use scope drive the obligations. Deviation triggers warnings or blocks.
          </li>
          <li>
            <span className="font-bold text-stone-900">3. Guard evaluates every proposed action.</span>{" "}
            Clinical, safety, GxP writes, and PHI-adjacent actions get the strictest treatment. Everything else stays fast.
          </li>
          <li>
            <span className="font-bold text-stone-900">4. Every decision is a signed audit row.</span>{" "}
            Validation team gets a queryable evidence table. FDA CSA lifecycle traceability without manual archaeology.
          </li>
          <li>
            <span className="font-bold text-stone-900">5. Your existing validation process wraps around Guard.</span>{" "}
            Credibility assessments, intended-use scope, change control, and periodic review all point at the same audit chain.
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
          Human accountability, provable at commit.
        </h2>
        <p className="text-indigo-100 text-lg mb-8">
          Nine rules. One pack. Aligned to every framework your validation team is already reconciling.
        </p>
        <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
          <a
            href="/registry?tab=compliance&pack=conduct-life-sciences"
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
