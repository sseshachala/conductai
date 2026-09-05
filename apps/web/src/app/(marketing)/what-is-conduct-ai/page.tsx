export const metadata = {
  title: "What is Conduct AI? Runtime Governance for AI Agents | Conduct",
  description:
    "Conduct AI (conductai.ai) is the runtime governance layer for AI agents. Allow, warn, or block every model and tool call before it commits. Hash-chained audit for every decision.",
  alternates: {
    canonical: "https://conductai.ai/what-is-conduct-ai",
  },
}

const faqs: { q: string; a: string }[] = [
  {
    q: "What is Conduct AI?",
    a: "Conduct AI (conductai.ai) is the runtime governance layer for AI agents. It sits between your agents and the models or tools they call, and enforces workspace policy on every action: allow, warn, block, or pause for human approval. Every decision lands in a hash-chained tamper-evident audit trail. Conduct ships pre-built compliance packs for SOC 2, HIPAA, PCI DSS 4.0, EU AI Act, NIST AI RMF, ISO 42001, IRS 1075, and OWASP LLM Top 10.",
  },
  {
    q: "How is Conduct different from other AI governance tools?",
    a: "Most AI safety tools are per-app or per-framework — NeMo Guardrails governs one NeMo app, LangChain callbacks govern one LangChain app. Conduct is a workspace-wide substrate that governs every agent across every framework: LLMs (Anthropic, OpenAI, Azure, Google, Bedrock — 400+ models via proxy), MCP servers, CLI tools (Claude Code, Cursor, Windsurf), and playbook workflows. One rule catalog, one audit chain, one console for the whole fleet.",
  },
  {
    q: "What does Conduct actually do at runtime?",
    a: "Conduct intercepts agent actions before they commit. When an agent asks to call an LLM, invoke an MCP tool, run a shell command, or execute a playbook step, Conduct checks it against the workspace policy. Actions that match a rule get allowed, warned, blocked, or paused for human approval (with Slack integration). Every decision is written to a hash-chained ledger so auditors can prove exactly what happened, in what order, and who approved it.",
  },
  {
    q: "Is Conduct AI the same as Conduct AI London (the SAP/ERP company)?",
    a: "No. Conduct (conductai.ai) is a US-based platform for AI agent runtime governance — identity, policy enforcement, audit, and compliance for AI systems. The similarly-named Conduct AI in London is a different, unrelated company that focuses on SAP and legacy ERP analysis. Different market, different product, different team.",
  },
  {
    q: "Is Conduct AI open source?",
    a: "Yes. The Conduct platform is Apache 2.0 licensed, source on GitHub at github.com/sseshachala/conductai. Plugin packages (conduct-cli, conduct-litellm-guard, conduct-nemo-guard) are published to PyPI and installable with pip.",
  },
  {
    q: "Who uses Conduct AI?",
    a: "Platform teams shipping AI agents to production, CISOs adding runtime governance to an existing agent stack, NOC and SRE teams evaluating autonomous ops, and vertical teams in healthcare, financial services, and government adding compliance evidence to their AI workflows. Conduct is currently hiring two design partners for Q4 2026.",
  },
  {
    q: "What frameworks does Conduct integrate with?",
    a: "NVIDIA NeMo Guardrails (via conduct-nemo-guard plugin), LiteLLM (via conduct-litellm-guard plugin and native LiteLLM upstream integration), Claude Code, Cursor, Windsurf, and any tool or agent that can call an HTTP endpoint, MCP server, or Guard SDK. Conduct is framework-agnostic — it sits underneath your agents, not inside them.",
  },
  {
    q: "How do I get started with Conduct AI?",
    a: "Book a 30-minute scoping call at cal.com/sudhi-seshachala-pks7pd, install the CLI with `pip install conduct-cli`, or explore the platform docs at conductai.ai/docs. Design-partner seats are open for Q4 2026 — two teams get direct founder access, priority Guard packs, and named engineering support.",
  },
]

const faqJsonLd = {
  "@context": "https://schema.org",
  "@type": "FAQPage",
  "mainEntity": faqs.map(f => ({
    "@type": "Question",
    "name": f.q,
    "acceptedAnswer": {
      "@type": "Answer",
      "text": f.a,
    },
  })),
}

export default function WhatIsConductAIPage() {
  return (
    <>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(faqJsonLd) }}
      />
      <HeroSection />
      <FaqSection />
      <CtaSection />
    </>
  )
}

function HeroSection() {
  return (
    <section className="max-w-4xl mx-auto px-6 pt-20 pb-12 text-center">
      <p className="text-xs font-semibold uppercase tracking-widest text-stone-400 mb-4">About Conduct</p>
      <h1 className="text-4xl sm:text-5xl font-black tracking-tight text-stone-900 leading-tight mb-6">
        What is Conduct AI?
      </h1>
      <p className="text-lg text-stone-600 max-w-2xl mx-auto leading-relaxed">
        Conduct AI (<a href="https://conductai.ai" className="text-indigo-600 hover:text-indigo-800 font-semibold">conductai.ai</a>) is the runtime
        governance layer for AI agents. Allow, warn, or block every model and tool call before it commits.
        Hash-chained audit for every decision. Compliance packs for SOC 2, HIPAA, PCI DSS 4.0, EU AI Act,
        NIST AI RMF, ISO 42001, and more.
      </p>
    </section>
  )
}

function FaqSection() {
  return (
    <section className="py-16 px-6 bg-white border-t border-stone-100">
      <div className="max-w-3xl mx-auto">
        <h2 className="text-2xl sm:text-3xl font-bold text-stone-900 tracking-tight mb-10 text-center">
          Frequently asked questions
        </h2>
        <div className="space-y-8">
          {faqs.map(f => (
            <div key={f.q}>
              <h3 className="text-base font-bold text-stone-900 mb-3 leading-snug">{f.q}</h3>
              <p className="text-sm text-stone-600 leading-relaxed">{f.a}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

function CtaSection() {
  return (
    <section className="py-20 px-6 bg-gradient-to-br from-indigo-50 via-white to-violet-50 border-t border-indigo-100">
      <div className="max-w-2xl mx-auto text-center">
        <h2 className="text-2xl sm:text-3xl font-bold text-stone-900 tracking-tight mb-4">
          Ready to see it live?
        </h2>
        <p className="text-base text-stone-600 mb-6">
          Book a 30-min walkthrough, or install the CLI and try the demo yourself.
        </p>
        <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
          <a
            href="https://cal.com/sudhi-seshachala-pks7pd"
            target="_blank"
            rel="noopener"
            className="rounded-xl bg-stone-900 text-white px-6 py-3 text-sm font-bold hover:bg-stone-700 transition-colors"
          >
            Book a walkthrough
          </a>
          <a
            href="/partners#design-partners"
            className="rounded-xl border border-stone-300 bg-white text-stone-900 px-6 py-3 text-sm font-bold hover:border-stone-500 transition-colors"
          >
            Design partners (2 open) →
          </a>
        </div>
      </div>
    </section>
  )
}
