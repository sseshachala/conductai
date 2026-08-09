import { CtaLink } from "@/components/marketing/CtaLink"

const SOLUTIONS = [
  {
    href: "/solutions/engineering-leaders",
    title: "Engineering leaders",
    desc: "Policy personas per team, spend hard-stops, and a CI gate that blocks non-compliant commits. Ship AI-assisted code without becoming the incident report.",
    featured: true,
  },
  {
    href: "/solutions/security-compliance",
    title: "Security and compliance",
    desc: "SHA-256 hash-chained audit log, PII screening, credential leak detection. Everything a SOC2 auditor or CISO needs without a custom integration.",
    featured: false,
  },
  {
    href: "/solutions/security-loop",
    title: "Security Loop",
    desc: "Closed loop from scan to defect to autopilot fix to PR. Guard enforces scope at every step — the loop does not escape its boundaries.",
    featured: false,
  },
  {
    href: "/solutions/action-governance",
    title: "Action governance",
    desc: "Approval gates as first-class workflow blocks. Human sovereignty enforced before destructive or irreversible actions — not logged after.",
    featured: false,
  },
  {
    href: "/solutions/memory-hardening",
    title: "Memory hardening",
    desc: "Guard policies applied to agent memory reads and writes. Prevent prompt injection via poisoned context, not just poisoned prompts.",
    featured: false,
  },
  {
    href: "/solutions/okta-plus-conduct",
    title: "Okta and Conduct",
    desc: "Okta issues identity. Conduct governs what that identity can do at runtime. The two layers are complementary, not redundant.",
    featured: false,
  },
  {
    href: "/solutions/financial-services",
    title: "Financial services",
    desc: "Agent governance for regulated environments — spend controls, data residency policies, and audit trails designed for financial compliance teams.",
    featured: false,
  },
  {
    href: "/solutions/life-sciences",
    title: "Life sciences",
    desc: "Guard policies for clinical data handling, PII screening aligned to HIPAA patterns, and audit trails that meet FDA 21 CFR Part 11 requirements.",
    featured: false,
  },
]

export default function SolutionsPage() {
  const featured = SOLUTIONS.find(s => s.featured)!
  const rest = SOLUTIONS.filter(s => !s.featured)

  return (
    <>
      <HeroSection />
      <FeaturedCard solution={featured} />
      <GridSection solutions={rest} />
      <ThreatModelSection />
    </>
  )
}

/* ─── Hero ──────────────────────────────────────────────────────────────── */

function HeroSection() {
  return (
    <section className="max-w-5xl mx-auto px-6 pt-20 pb-10 text-center">
      <div className="inline-flex items-center gap-2 bg-stone-100 text-stone-600 px-4 py-1.5 rounded-full text-xs font-semibold uppercase tracking-widest mb-8">
        <span className="w-1.5 h-1.5 rounded-full bg-stone-400 inline-block" />
        Solutions
      </div>
      <h1 className="text-4xl sm:text-5xl font-black tracking-tight text-stone-900 leading-[1.05] mb-5">
        One governance layer. Every team.
      </h1>
      <p className="text-lg text-stone-500 max-w-2xl mx-auto leading-relaxed">
        Guard enforces the same policy across every AI agent your team runs. How you configure that policy depends on your role, your industry, and what keeps you up at night.
      </p>
    </section>
  )
}

/* ─── Featured card ─────────────────────────────────────────────────────── */

function FeaturedCard({ solution }: { solution: typeof SOLUTIONS[number] }) {
  return (
    <section className="max-w-5xl mx-auto px-6 pb-8">
      <a
        href={solution.href}
        className="block rounded-2xl border-2 border-indigo-200 bg-indigo-50 p-10 hover:border-indigo-300 hover:shadow-md transition-all group"
      >
        <div className="flex items-start justify-between gap-6">
          <div className="flex-1">
            <div className="flex items-center gap-3 mb-4">
              <span className="text-xs font-bold uppercase tracking-widest text-indigo-600 bg-indigo-100 px-3 py-1 rounded-full">
                Featured
              </span>
            </div>
            <h2 className="text-2xl sm:text-3xl font-black text-stone-900 tracking-tight mb-3">
              {solution.title}
            </h2>
            <p className="text-stone-500 leading-relaxed max-w-xl">{solution.desc}</p>
          </div>
          <span className="text-stone-300 group-hover:text-stone-500 transition-colors text-2xl hidden sm:block">→</span>
        </div>
        <div className="mt-6 flex flex-wrap gap-2">
          {["Policy personas per team", "Spend hard-stops", "CI release gate", "10-minute install"].map(tag => (
            <span key={tag} className="text-xs font-medium text-indigo-700 bg-indigo-100 px-3 py-1 rounded-full">
              {tag}
            </span>
          ))}
        </div>
      </a>
    </section>
  )
}

/* ─── Grid ──────────────────────────────────────────────────────────────── */

function GridSection({ solutions }: { solutions: typeof SOLUTIONS }) {
  return (
    <section className="max-w-5xl mx-auto px-6 pb-16">
      <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5">
        {solutions.map(s => (
          <a
            key={s.href}
            href={s.href}
            className="block rounded-xl border border-stone-200 bg-white p-6 hover:border-stone-300 hover:shadow-sm transition-all group"
          >
            <h3 className="font-bold text-stone-900 mb-2 group-hover:text-indigo-700 transition-colors">
              {s.title}
            </h3>
            <p className="text-sm text-stone-500 leading-relaxed">{s.desc}</p>
          </a>
        ))}
      </div>
    </section>
  )
}

/* ─── Threat model ──────────────────────────────────────────────────────── */

function ThreatModelSection() {
  return (
    <section className="bg-stone-50 border-t border-stone-200 px-6 py-14">
      <div className="max-w-3xl mx-auto flex flex-col sm:flex-row items-start sm:items-center justify-between gap-6">
        <div>
          <h2 className="text-lg font-bold text-stone-900 mb-2">What Guard does not protect (yet).</h2>
          <p className="text-stone-500 text-sm leading-relaxed max-w-xl">
            We publish our threat model openly — credentials in executor memory, no egress allowlist, no pre-install static analysis on third-party playbooks. Read the gaps and our plan for each.
          </p>
        </div>
        <a
          href="/security"
          className="flex-shrink-0 rounded-lg border border-stone-300 bg-white text-stone-700 px-5 py-2.5 text-sm font-semibold hover:border-stone-400 hover:shadow-sm transition-all"
        >
          Read our threat model →
        </a>
      </div>
    </section>
  )
}
