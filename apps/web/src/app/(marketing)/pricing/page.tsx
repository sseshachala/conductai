import Link from "next/link"

export const metadata = {
  title: "Pricing — Conduct",
  description:
    "One list price per governed agent identity. Same price whether you run Conduct on our cloud or your own. Free tier for up to 3 agents.",
}

type Tier = {
  name: string
  price: string
  cadence?: string
  cap: string
  tagline: string
  cta: { label: string; href: string }
  highlight?: boolean
  includes: string[]
}

const TIERS: Tier[] = [
  {
    name: "Free",
    price: "$0",
    cap: "Up to 3 agents",
    tagline: "For individual devs, POCs, and internal tinkering.",
    cta: { label: "Start free", href: "/sign-up" },
    includes: [
      "Full policy engine — allow, block, approve, prove",
      "Hash-chained audit trail",
      "MCP + proxy + CLI hook enforcement",
      "Community support (GitHub Discussions)",
    ],
  },
  {
    name: "Team",
    price: "$99",
    cadence: "per agent / month",
    cap: "Up to 25 agents",
    tagline: "For engineering teams governing their first fleet of agents.",
    cta: { label: "Start 14-day trial", href: "/sign-up" },
    highlight: true,
    includes: [
      "Everything in Free",
      "Slack + email approval fanout",
      "Signed evidence exports",
      "Slack + email support (business hours)",
      "SSO (Google, Microsoft, Okta)",
    ],
  },
  {
    name: "Business",
    price: "$79",
    cadence: "per agent / month",
    cap: "25–100 agents",
    tagline: "Volume pricing for orgs standardising governance across many agents.",
    cta: { label: "Talk to sales", href: "/book-demo" },
    includes: [
      "Everything in Team",
      "Priority support (24h response)",
      "Custom policy pack authoring",
      "Role-based access control (RBAC)",
      "Compliance evidence templates (SOC2, ISO, HIPAA)",
    ],
  },
  {
    name: "Enterprise",
    price: "Contact us",
    cap: "100+ agents · Self-hosted · Air-gapped",
    tagline: "For regulated industries, self-host, and design-partner engagements.",
    cta: { label: "Contact us", href: "/book-demo" },
    includes: [
      "Everything in Business",
      "Self-hosted deployment (Docker, Kubernetes, air-gapped)",
      "Signed SLA + dedicated success engineer",
      "Custom policy development",
      "Procurement, security review, and MSA support",
    ],
  },
]

const FAQ: { q: string; a: string }[] = [
  {
    q: "Is cond_agt_* priced per user or per bot?",
    a: "Per bot — per governed service identity. One human developer running three governed agents counts as three identities. The unit tracks value produced by the agents, not headcount using the tool.",
  },
  {
    q: "Does self-hosted include air-gapped deployments?",
    a: "Yes, on Enterprise. Docker, Kubernetes, and fully air-gapped installs all deploy from the same image and run the same policy engine. Same list price as SaaS — you\u2019re paying for enforcement and audit, not where the pods run.",
  },
  {
    q: "What if my agent count varies month to month?",
    a: "Billed on the peak count of active identities in each month. Spin agents up for a launch, retire them after, and you only pay for the month you actually ran them. No proration penalty for scaling down.",
  },
  {
    q: "Do you offer annual discounts?",
    a: "Yes — 15% off list price on all tiers when paid annually up front. Available on Team, Business, and Enterprise. Ask for the annual quote when you talk to us.",
  },
  {
    q: "What happens if I hit my tier cap?",
    a: "Soft alert at 90% of cap so you can plan the upgrade. If you hit 100%, agents keep working — we auto-upgrade you to the next tier and send a confirmation email. No hard stops, no surprise blocks, no missed enforcement.",
  },
]

export default function PricingPage() {
  return (
    <div className="min-h-screen bg-white">
      <main className="max-w-6xl mx-auto px-6">
        {/* Hero */}
        <section className="pt-20 pb-14 text-center">
          <p className="text-xs font-mono font-bold uppercase tracking-widest text-stone-400 mb-4">
            Pricing
          </p>
          <h1 className="text-4xl sm:text-5xl font-black tracking-tight text-stone-900 leading-[1.05] mb-6">
            One list. Priced per governed agent.
          </h1>
          <p className="text-lg text-stone-500 max-w-2xl mx-auto leading-relaxed">
            Every tier includes the full policy engine, hash-chained audit trail, and every
            enforcement surface — MCP, proxy, and CLI hook. You pay for how many agent
            identities you govern, not which features you unlock.
          </p>
        </section>

        {/* Tier grid */}
        <section className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-14">
          {TIERS.map((t) => (
            <div
              key={t.name}
              className={`flex flex-col rounded-2xl p-6 border ${
                t.highlight
                  ? "border-stone-900 bg-stone-50 shadow-sm"
                  : "border-stone-200 bg-white"
              }`}
            >
              <div className="mb-5">
                <p className="text-xs font-mono font-bold uppercase tracking-widest text-stone-400 mb-2">
                  {t.name}
                </p>
                <div className="flex items-baseline gap-1.5 mb-1">
                  <span className="text-3xl font-black text-stone-900">{t.price}</span>
                  {t.cadence && (
                    <span className="text-xs text-stone-500">{t.cadence}</span>
                  )}
                </div>
                <p className="text-xs font-mono text-stone-500">{t.cap}</p>
              </div>

              <p className="text-sm text-stone-600 leading-relaxed mb-5">{t.tagline}</p>

              <ul className="text-sm text-stone-600 space-y-2 mb-6">
                {t.includes.map((line) => (
                  <li key={line} className="flex items-start gap-2 leading-relaxed">
                    <span className="text-stone-300 shrink-0 mt-0.5">·</span>
                    <span>{line}</span>
                  </li>
                ))}
              </ul>

              <Link
                href={t.cta.href}
                className={`mt-auto inline-block text-center rounded-xl px-4 py-2.5 text-sm font-semibold transition-colors ${
                  t.highlight
                    ? "bg-stone-900 text-white hover:bg-stone-700"
                    : "border border-stone-200 bg-white text-stone-700 hover:bg-stone-50"
                }`}
              >
                {t.cta.label}
              </Link>
            </div>
          ))}
        </section>

        {/* Self-host clarity */}
        <section className="mb-14 rounded-2xl border border-stone-200 bg-stone-50 p-8">
          <h2 className="text-lg font-bold text-stone-900 mb-2">
            Self-hosted? Same list price. Same features.
          </h2>
          <p className="text-sm text-stone-600 leading-relaxed max-w-3xl">
            Self-hosted deployments (Docker, Kubernetes, air-gapped) are available on Enterprise.
            The list price is the same — you're paying for policy enforcement, audit, and support,
            not for where the pods run. Deploy where your compliance boundary needs it, keep the
            same commercial terms.
          </p>
        </section>

        {/* Feature parity note */}
        <section className="mb-14 grid grid-cols-1 sm:grid-cols-3 gap-4 text-sm">
          {[
            {
              title: "One engine — every surface",
              body: "MCP tool interception, LLM proxy, and CLI hooks all run through the same policy engine and write to the same audit chain.",
            },
            {
              title: "One agent identity",
              body: "Every governed agent gets a cond_agt_* identity with RBAC, TTL, rate + spend caps. That identity is the unit you pay for.",
            },
            {
              title: "Bring your own LLM",
              body: "100+ providers — Anthropic, OpenAI, Bedrock, Azure, Ollama, self-host — through one gateway. No provider markup.",
            },
          ].map((f) => (
            <div key={f.title} className="rounded-xl border border-stone-200 bg-white p-5">
              <p className="font-semibold text-stone-900 mb-2 text-sm">{f.title}</p>
              <p className="text-stone-500 leading-relaxed text-[13px]">{f.body}</p>
            </div>
          ))}
        </section>

        {/* FAQ */}
        <section className="mb-14">
          <h2 className="text-2xl font-bold text-stone-900 mb-2">
            Answers to the five questions every buyer asks.
          </h2>
          <p className="text-sm text-stone-500 mb-8 max-w-2xl leading-relaxed">
            Direct answers so you don't need a sales call to scope the deal. If your situation
            doesn't fit one of these, reach out and we'll answer the same way.
          </p>
          <div className="space-y-3">
            {FAQ.map((f) => (
              <div
                key={f.q}
                className="rounded-2xl border border-stone-200 bg-white p-6"
              >
                <p className="font-semibold text-stone-900 mb-2 text-[15px]">{f.q}</p>
                <p className="text-sm text-stone-600 leading-relaxed">{f.a}</p>
              </div>
            ))}
          </div>
        </section>

        {/* CTA */}
        <section className="mb-20 text-center border-t border-stone-100 pt-14">
          <h2 className="text-2xl font-bold text-stone-900 mb-4">
            Not sure which tier fits?
          </h2>
          <p className="text-stone-500 max-w-xl mx-auto mb-6 leading-relaxed">
            Start on Free — govern up to 3 agents in an afternoon. Upgrade when your fleet grows,
            or talk to us about design-partner terms if you're deploying at scale early.
          </p>
          <div className="flex flex-wrap justify-center gap-3">
            <Link
              href="/sign-up"
              className="inline-block rounded-xl bg-stone-900 text-white px-6 py-3 text-sm font-semibold hover:bg-stone-700 transition-colors"
            >
              Start free
            </Link>
            <Link
              href="/book-demo"
              className="inline-block rounded-xl border border-stone-200 bg-white text-stone-700 px-6 py-3 text-sm font-semibold hover:bg-stone-50 transition-colors"
            >
              Talk to sales →
            </Link>
          </div>
        </section>
      </main>
    </div>
  )
}
