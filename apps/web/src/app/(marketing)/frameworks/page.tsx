import { CtaLink } from "@/components/marketing/CtaLink"

const MANDATORY_STYLE = {
  mandatory:  { label: "Mandatory",             color: "#b91c1c", bg: "#fef2f2" },
  voluntary:  { label: "Voluntary",             color: "#6b7280", bg: "#f3f4f6" },
  defacto:    { label: "Voluntary (de facto)",  color: "#92400e", bg: "#fffbeb" },
  cardbrand:  { label: "Mandatory (card brands)",color: "#7c3aed", bg: "#f5f3ff" },
}

const FRAMEWORKS = [
  {
    slug: "conduct-eu-ai-act",
    icon: "🇪🇺",
    name: "EU AI Act",
    tag: "Regulation",
    tagColor: "#4f46e5",
    tagBg: "#eef2ff",
    type: "Regulation",
    mandatory: "mandatory" as const,
    buyer: "Any EU-market AI system",
    headline: "Enforce Article 5 prohibitions and transparency requirements — automatically.",
    description:
      "The EU AI Act bans social scoring, emotion recognition in workplaces, mass surveillance, and subliminal manipulation. ConductGuard enforces these prohibitions at the point of code — before the agent runs.",
    articles: [
      { ref: "Article 5.1a", label: "Subliminal manipulation — blocked" },
      { ref: "Article 5.1b", label: "Biometric categorization — blocked" },
      { ref: "Article 5.1c", label: "Social scoring — blocked" },
      { ref: "Article 5.1f", label: "Emotion recognition in workplaces — blocked" },
      { ref: "Article 5.1h", label: "Mass surveillance — blocked" },
      { ref: "Article 10",   label: "Data governance — PII in training blocked" },
      { ref: "Article 12",   label: "Logging — audit log enforced" },
      { ref: "Article 13",   label: "Transparency — disclosure required" },
      { ref: "Article 14",   label: "Human oversight — override blocked" },
      { ref: "Article 53",   label: "GPAI high-risk use — warned" },
    ],
    ruleCount: 10,
  },
  {
    slug: "conduct-nist-ai-rmf",
    icon: "🏛️",
    name: "NIST AI RMF",
    tag: "Risk Framework",
    tagColor: "#0369a1",
    tagBg: "#e0f2fe",
    type: "Risk framework",
    mandatory: "defacto" as const,
    buyer: "Federal agencies",
    headline: "Map AI agent risk across GOVERN, MAP, MEASURE, and MANAGE.",
    description:
      "The NIST AI Risk Management Framework structures AI risk across four functions. ConductGuard ships one rule per key control — blocking policy bypass, flagging high-risk deployments, and alerting on disabled monitoring.",
    articles: [
      { ref: "GOVERN 1.2", label: "Least privilege — escalation blocked" },
      { ref: "GOVERN 2.2", label: "Policy bypass — blocked" },
      { ref: "GOVERN 4.1", label: "Accountability logging — enforced" },
      { ref: "GOVERN 6.1", label: "Human oversight — override blocked" },
      { ref: "MAP 1.5",    label: "Unverified data sources — warned" },
      { ref: "MAP 5.1",    label: "High-risk domain deployment — warned" },
      { ref: "MEASURE 1.1",label: "Monitoring disabled — blocked" },
      { ref: "MEASURE 2.5",label: "Error swallowing — flagged" },
      { ref: "MANAGE 1.3", label: "Third-party AI vendors — audit required" },
      { ref: "MANAGE 4.1", label: "Data retention — policy enforced" },
    ],
    ruleCount: 10,
  },
  {
    slug: "conduct-iso-42001",
    icon: "📐",
    name: "ISO 42001",
    tag: "Standard",
    tagColor: "#0f766e",
    tagBg: "#f0fdfa",
    type: "AI management system",
    mandatory: "voluntary" as const,
    buyer: "Boards, compliance teams",
    headline: "Operational controls, bias testing, and incident capture — built in.",
    description:
      "ISO 42001 is the international management system standard for AI. ConductGuard operationalises Clauses 8–10: access control, bias testing, data quality, impact assessment, responsible use, and incident capture.",
    articles: [
      { ref: "Clause 8.1", label: "Operational controls and human oversight" },
      { ref: "Clause 8.1", label: "Access control and supplier relationships" },
      { ref: "Clause 8.2", label: "Bias testing — unvalidated models flagged" },
      { ref: "Clause 8.4", label: "Data quality — unlabeled data warned" },
      { ref: "Clause 8.4", label: "Data minimisation — PII in training blocked" },
      { ref: "Clause 8.5", label: "Impact assessment — high-risk use flagged" },
      { ref: "Clause 8.6", label: "Responsible use — off-label use blocked" },
      { ref: "Clause 8.6", label: "Prohibited practices alignment" },
      { ref: "Clause 9.1", label: "Monitoring — disable attempt blocked" },
      { ref: "Clause 10.2",label: "Incident capture — error swallowing blocked" },
    ],
    ruleCount: 10,
  },
  {
    slug: "conduct-irs-1075",
    icon: "🏛️",
    name: "IRS Publication 1075",
    tag: "Government",
    tagColor: "#92400e",
    tagBg: "#fef3c7",
    type: "Federal regulation",
    mandatory: "mandatory" as const,
    buyer: "Govt agencies + contractors handling tax data",
    headline: "Protect Federal Tax Information from AI exposure — enforced at the code layer.",
    description:
      "IRS Publication 1075 governs Federal Tax Information (FTI) under IRC Section 6103. Any agency or contractor handling IRS-shared tax data must safeguard it from disclosure, improper use, and inadequate storage. ConductGuard blocks EINs, AGI values, and W-2/1099 data from entering AI prompts, training datasets, or external endpoints.",
    articles: [
      { ref: "Sec 4 / IRC 6103", label: "EIN in AI prompt — blocked" },
      { ref: "Sec 4 / IRC 6103", label: "Tax return data in model context — blocked" },
      { ref: "Sec 4",            label: "FTI to external AI endpoint — blocked" },
      { ref: "Sec 4",            label: "FTI in training datasets — blocked" },
      { ref: "Sec 9",            label: "FTI in unencrypted files — blocked" },
      { ref: "Sec 4 / Sec 10",  label: "FTI unredacted in logs — blocked" },
      { ref: "Sec 4",           label: "Third-party AI FTI processor — warned" },
      { ref: "IRC 6103 / Sec 4", label: "FTI beyond authorised purpose — blocked" },
    ],
    ruleCount: 8,
  },
  {
    slug: "conduct-owasp",
    icon: "🔐",
    name: "OWASP Top 10 for LLMs",
    tag: "Security",
    tagColor: "#b91c1c",
    tagBg: "#fef2f2",
    type: "Security standard",
    mandatory: "voluntary" as const,
    buyer: "Security teams, enterprise customers",
    headline: "The 10 most critical LLM security risks — enforced at the hook layer.",
    description:
      "OWASP's LLM Top 10 covers prompt injection, insecure output handling, training data poisoning, and supply chain vulnerabilities. ConductGuard maps rules to each identifier so your security team speaks the same language as your auditor.",
    articles: [
      { ref: "LLM01", label: "Prompt injection — blocked" },
      { ref: "LLM02", label: "Insecure output handling — flagged" },
      { ref: "LLM03", label: "Training data poisoning — warned" },
      { ref: "LLM04", label: "Model DoS — rate patterns blocked" },
      { ref: "LLM05", label: "Supply chain vulnerabilities — warned" },
      { ref: "LLM06", label: "Sensitive information disclosure — blocked" },
      { ref: "LLM07", label: "Insecure plugin design — flagged" },
      { ref: "LLM08", label: "Excessive agency — override blocked" },
      { ref: "LLM09", label: "Overreliance — human oversight enforced" },
      { ref: "LLM10", label: "Model theft — exfiltration blocked" },
    ],
    ruleCount: 20,
  },
  {
    slug: "conduct-soc2",
    icon: "📋",
    name: "SOC 2",
    tag: "Audit",
    tagColor: "#7c3aed",
    tagBg: "#f5f3ff",
    type: "Security audit",
    mandatory: "voluntary" as const,
    buyer: "Enterprise customers",
    headline: "Audit-ready AI agent controls mapped to Trust Service Criteria.",
    description:
      "SOC 2 auditors look for evidence of control. ConductGuard produces that evidence automatically — blocking hardcoded secrets, warning on PII in logs, and flagging debug mode in production.",
    articles: [
      { ref: "CC6.1", label: "Logical access — hardcoded secrets blocked" },
      { ref: "CC6.3", label: "Least privilege — escalation blocked" },
      { ref: "CC7.2", label: "System monitoring — PII in logs warned" },
      { ref: "CC8.1", label: "Change management — debug mode in prod flagged" },
    ],
    ruleCount: 4,
  },
  {
    slug: "conduct-hipaa",
    icon: "🏥",
    name: "HIPAA",
    tag: "Healthcare",
    tagColor: "#0369a1",
    tagBg: "#e0f2fe",
    type: "Federal regulation",
    mandatory: "mandatory" as const,
    buyer: "Healthcare + business associates",
    headline: "Block PHI in source and flag unencrypted health data before it ships.",
    description:
      "HIPAA §164.312 requires technical safeguards for electronic PHI. ConductGuard blocks patient IDs, SSNs, and DOBs from entering source files and flags unencrypted transmission patterns.",
    articles: [
      { ref: "§164.312(a)", label: "Access control — PHI access blocked" },
      { ref: "§164.312(b)", label: "Audit controls — PHI in source flagged" },
      { ref: "§164.312(e)", label: "Transmission security — unencrypted PHI warned" },
    ],
    ruleCount: 3,
  },
  {
    slug: "conduct-pci-dss",
    icon: "💳",
    name: "PCI DSS",
    tag: "Finance",
    tagColor: "#92400e",
    tagBg: "#fffbeb",
    type: "Industry standard",
    mandatory: "cardbrand" as const,
    buyer: "Any entity processing payments",
    headline: "Block PANs and CVVs in source. Flag weak TLS before it reaches production.",
    description:
      "PCI DSS Requirements 3 and 4 prohibit storing card data in source and mandate strong encryption in transit. ConductGuard enforces both at the code layer — no post-commit remediation needed.",
    articles: [
      { ref: "Req 3.4", label: "PAN in source — blocked" },
      { ref: "Req 3.5", label: "CVV in source — blocked" },
      { ref: "Req 4.2", label: "Weak TLS / cleartext — flagged" },
    ],
    ruleCount: 3,
  },
]

export default function FrameworksPage() {
  return (
    <>
      <HeroSection />
      <FrameworkGrid />
      <CTASection />
    </>
  )
}

function HeroSection() {
  return (
    <section className="max-w-5xl mx-auto px-6 pt-20 pb-16 text-center">
      <div className="inline-flex items-center gap-2 bg-indigo-50 text-indigo-700 px-4 py-1.5 rounded-full text-xs font-semibold uppercase tracking-widest mb-8">
        <span className="w-1.5 h-1.5 rounded-full bg-indigo-500 inline-block" />
        Compliance frameworks
      </div>
      <h1 className="text-5xl sm:text-6xl font-black tracking-tight text-stone-900 leading-[1.05] mb-6">
        Every framework your auditor<br />
        <span className="bg-gradient-to-r from-indigo-600 to-violet-600 bg-clip-text text-transparent">cares about. Pre-built.</span>
      </h1>
      <p className="text-xl text-stone-500 max-w-2xl mx-auto leading-relaxed mb-4">
        EU AI Act, NIST AI RMF, ISO 42001, OWASP LLM Top 10, SOC 2, HIPAA, PCI DSS. Install a pack. Guard enforces it. Audit log is automatic.
      </p>
      <p className="text-base text-stone-500 max-w-2xl mx-auto leading-relaxed mb-8">
        Conduct makes compliance structural — not documented after the fact, enforced before execution. Every allowed action produces a Governance Authorization Artifact: replay-verifiable evidence that authorisation was confirmed before execution. Custody proof, not a reconstructed log.
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

function FrameworkGrid() {
  return (
    <section className="max-w-6xl mx-auto px-6 pb-24 space-y-12">
      {FRAMEWORKS.map(fw => (
        <div key={fw.slug} className="rounded-2xl border border-stone-200 bg-white overflow-hidden">
          {/* Header */}
          <div className="flex flex-col sm:flex-row sm:items-center gap-4 px-8 py-6 border-b border-stone-100">
            <div className="text-4xl">{fw.icon}</div>
            <div className="flex-1">
              <div className="flex items-center gap-2 mb-2 flex-wrap">
                <h2 className="text-xl font-black text-stone-900">{fw.name}</h2>
                <span className="text-xs font-semibold px-2.5 py-0.5 rounded-full" style={{ color: fw.tagColor, background: fw.tagBg }}>{fw.tag}</span>
                <span className="text-xs text-stone-400">{fw.ruleCount} rules</span>
              </div>
              <div className="flex flex-wrap gap-3 mb-2 text-xs text-stone-500">
                <span><span className="font-medium text-stone-700">Type:</span> {fw.type}</span>
                <span className="text-stone-300">·</span>
                <span>
                  <span className="font-medium text-stone-700">Mandatory: </span>
                  <span className="font-semibold px-1.5 py-0.5 rounded" style={{ color: MANDATORY_STYLE[fw.mandatory].color, background: MANDATORY_STYLE[fw.mandatory].bg }}>
                    {MANDATORY_STYLE[fw.mandatory].label}
                  </span>
                </span>
                <span className="text-stone-300">·</span>
                <span><span className="font-medium text-stone-700">Buyer:</span> {fw.buyer}</span>
              </div>
              <p className="text-stone-500 text-sm leading-relaxed">{fw.description}</p>
            </div>
            <a
              href={`/registry?tab=compliance`}
              className="flex-shrink-0 rounded-xl bg-stone-900 text-white px-5 py-2.5 text-sm font-semibold hover:bg-stone-700 transition-colors text-center"
            >
              Install pack →
            </a>
          </div>
          {/* Rules table */}
          <div className="px-8 py-5">
            <p className="text-xs font-semibold uppercase tracking-widest text-stone-400 mb-3">Control coverage</p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-8 gap-y-2">
              {fw.articles.map((a, i) => (
                <div key={i} className="flex items-start gap-2.5 text-sm">
                  <span className="flex-shrink-0 font-mono text-xs text-indigo-600 bg-indigo-50 px-2 py-0.5 rounded mt-0.5">{a.ref}</span>
                  <span className="text-stone-600">{a.label}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      ))}
    </section>
  )
}

function CTASection() {
  return (
    <section className="py-24 px-6 bg-gradient-to-br from-indigo-600 to-violet-600">
      <div className="max-w-3xl mx-auto text-center">
        <h2 className="text-3xl sm:text-4xl font-black text-white tracking-tight leading-tight mb-4">
          Your auditor wants evidence.<br />Guard produces it automatically.
        </h2>
        <p className="text-indigo-200 text-lg leading-relaxed mb-10 max-w-xl mx-auto">
          Install a compliance pack. Every agent decision is logged as a Governance Authorization Artifact, mapped to a framework control, and exportable. Structural compliance — not documented after the fact.
        </p>
        <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
          <CtaLink className="rounded-xl bg-white text-indigo-600 px-7 py-3.5 text-base font-bold hover:bg-indigo-50 transition-colors w-full sm:w-auto text-center" />
          <a href="https://cal.com/sudhi-seshachala-pks7pd" target="_blank" rel="noopener" className="rounded-xl border border-white/40 text-white px-7 py-3.5 text-base font-semibold hover:bg-white/10 transition-colors w-full sm:w-auto text-center">
            Book a demo
          </a>
        </div>
        <p className="text-indigo-300 text-xs mt-5">Free tier · No infrastructure changes · Works in minutes</p>
      </div>
    </section>
  )
}
