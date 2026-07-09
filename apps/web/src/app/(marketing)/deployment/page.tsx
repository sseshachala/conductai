import { CtaLink } from "@/components/marketing/CtaLink"

export default function DeploymentPage() {
  return (
    <>
      <HeroSection />
      <TiersSection />
      <CompareSection />
      <HowItWorksSection />
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
        Flexible deployment
      </div>
      <h1 className="text-5xl sm:text-6xl font-black tracking-tight text-stone-900 leading-[1.05] mb-6">
        Deploy where your<br />
        <span className="bg-gradient-to-r from-indigo-600 to-violet-600 bg-clip-text text-transparent">security policy requires.</span>
      </h1>
      <p className="text-xl text-stone-500 max-w-2xl mx-auto leading-relaxed mb-4">
        ConductGuard runs as SaaS, inside your cloud account, or fully on-premise. Same policy engine, same CLI, same audit trail — wherever your data must stay.
      </p>
      <p className="text-base text-stone-500 italic max-w-2xl mx-auto leading-relaxed mb-8">
        The agent inherits the permission. It doesn&apos;t inherit the caution.
      </p>
      <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
        <CtaLink className="rounded-xl bg-stone-900 text-white px-7 py-3.5 text-base font-semibold hover:bg-stone-700 transition-colors w-full sm:w-auto text-center" />
        <a
          href="https://cal.com/sudhi-seshachala-pks7pd"
          target="_blank"
          rel="noopener"
          className="rounded-xl border border-stone-300 bg-white text-stone-700 px-7 py-3.5 text-base font-semibold hover:border-stone-400 hover:shadow-sm transition-all w-full sm:w-auto text-center"
        >
          Talk to us
        </a>
      </div>
    </section>
  )
}

/* ─── Three tiers ───────────────────────────────────────────────────────── */

const TIERS = [
  {
    tag: "Fastest to start",
    name: "SaaS",
    tagline: "Up in 10 minutes. Nothing to manage.",
    description:
      "Managed by Conduct. Policy engine, audit trail, dashboard, and proxy all hosted on conductai.ai. No infrastructure decisions.",
    bullets: [
      "pip install conduct-cli, then conduct guard sync",
      "Policy active across your team in minutes",
      "Automatic upgrades, zero ops overhead",
      "Free tier available",
    ],
    who: "Startups and engineering teams who want governance now, not in Q3.",
    cta: "Start free",
    ctaHref: "https://conductai.ai",
    accent: "indigo",
    dark: false,
  },
  {
    tag: "Enterprise preferred",
    name: "Cloud (BYOC)",
    tagline: "Your cloud account. Our software.",
    description:
      "Deploy ConductGuard into your own AWS, GCP, or Azure account. Audit trail, policy engine, and proxy run in your VPC. Data never leaves your environment.",
    bullets: [
      "Terraform module — up in one apply",
      "Works with your existing RDS, ElastiCache, and VPC",
      "CLI points at your instance: conduct guard join --url https://guard.yourco.com",
      "You control upgrades and data retention",
    ],
    who: "Financial services, healthcare, and any org with data residency requirements.",
    cta: "Book a call",
    ctaHref: "https://cal.com/sudhi-seshachala-pks7pd",
    accent: "violet",
    dark: true,
  },
  {
    tag: "Air-gapped",
    name: "On-Premise",
    tagline: "Fully inside your perimeter.",
    description:
      "Docker Compose or Helm chart. Runs on your servers, your Kubernetes cluster, or an air-gapped environment. No outbound calls to Conduct infrastructure.",
    bullets: [
      "Docker images delivered to your registry",
      "Helm chart for Kubernetes deployments",
      "Works fully air-gapped — no external dependencies",
      "Alembic migrations included — you own the schema",
    ],
    who: "Government, defence, and regulated enterprises with strict perimeter requirements.",
    cta: "Contact us",
    ctaHref: "https://cal.com/sudhi-seshachala-pks7pd",
    accent: "stone",
    dark: false,
  },
]

function TiersSection() {
  return (
    <section className="max-w-6xl mx-auto px-6 py-20">
      <div className="grid md:grid-cols-3 gap-6">
        {TIERS.map((tier) => (
          <div
            key={tier.name}
            className={`rounded-2xl border p-8 flex flex-col gap-5 ${
              tier.dark
                ? "bg-stone-950 border-stone-800 text-white"
                : "bg-white border-stone-200 text-stone-900"
            }`}
          >
            <div>
              <span
                className={`text-[10px] font-bold uppercase tracking-widest ${
                  tier.dark ? "text-indigo-400" : "text-indigo-600"
                }`}
              >
                {tier.tag}
              </span>
              <h2
                className={`text-2xl font-black mt-1 mb-1 ${
                  tier.dark ? "text-white" : "text-stone-900"
                }`}
              >
                {tier.name}
              </h2>
              <p
                className={`text-sm font-semibold ${
                  tier.dark ? "text-stone-300" : "text-stone-600"
                }`}
              >
                {tier.tagline}
              </p>
            </div>

            <p className={`text-sm leading-relaxed ${tier.dark ? "text-stone-400" : "text-stone-500"}`}>
              {tier.description}
            </p>

            <ul className="flex flex-col gap-2.5">
              {tier.bullets.map((b) => (
                <li key={b} className="flex items-start gap-2.5">
                  <span className={`mt-[3px] text-xs ${tier.dark ? "text-indigo-400" : "text-indigo-500"}`}>✓</span>
                  <span className={`text-sm ${tier.dark ? "text-stone-300" : "text-stone-600"}`}>{b}</span>
                </li>
              ))}
            </ul>

            <div
              className={`rounded-xl px-4 py-3 text-xs leading-relaxed mt-auto ${
                tier.dark
                  ? "bg-stone-900 border border-stone-800 text-stone-400"
                  : "bg-stone-50 border border-stone-100 text-stone-500"
              }`}
            >
              <span className="font-semibold">Best for: </span>{tier.who}
            </div>

            <a
              href={tier.ctaHref}
              target={tier.ctaHref.startsWith("http") ? "_blank" : undefined}
              rel="noopener"
              className={`w-full text-center rounded-xl px-6 py-3 text-sm font-bold transition-colors ${
                tier.dark
                  ? "bg-indigo-600 text-white hover:bg-indigo-700"
                  : "bg-stone-900 text-white hover:bg-stone-700"
              }`}
            >
              {tier.cta}
            </a>
          </div>
        ))}
      </div>
    </section>
  )
}

/* ─── Comparison table ──────────────────────────────────────────────────── */

const ROWS = [
  { cap: "Time to first policy",         saas: "10 minutes",    byoc: "~1 day",           onprem: "~2 days"          },
  { cap: "Infrastructure managed by",    saas: "Conduct",       byoc: "You (your cloud)",  onprem: "You (on-site)"    },
  { cap: "Data residency",               saas: "conductai.ai",  byoc: "Your VPC",          onprem: "Your servers"     },
  { cap: "Audit trail location",         saas: "Conduct cloud", byoc: "Your RDS",          onprem: "Your DB"          },
  { cap: "Air-gap support",              saas: false,           byoc: false,               onprem: true               },
  { cap: "Automatic upgrades",           saas: true,            byoc: "Optional",          onprem: "Manual"           },
  { cap: "Custom domain",                saas: false,           byoc: true,                onprem: true               },
  { cap: "Terraform module",             saas: false,           byoc: true,                onprem: true               },
  { cap: "Helm / Docker Compose",        saas: false,           byoc: true,                onprem: true               },
  { cap: "Free tier",                    saas: true,            byoc: false,               onprem: false              },
  { cap: "CLI works identically",        saas: true,            byoc: true,                onprem: true               },
  { cap: "Same policy engine",           saas: true,            byoc: true,                onprem: true               },
]

function Cell({ val }: { val: boolean | string }) {
  if (val === true)  return <span className="text-emerald-500 font-bold">✓</span>
  if (val === false) return <span className="text-stone-300">—</span>
  return <span className="text-stone-500 text-xs">{val}</span>
}

function CompareSection() {
  return (
    <section className="bg-stone-50 border-y border-stone-200 px-6 py-20">
      <div className="max-w-5xl mx-auto">
        <p className="text-xs font-semibold uppercase tracking-widest text-indigo-600 mb-3 text-center">Compare tiers</p>
        <h2 className="text-3xl font-black text-stone-900 tracking-tight text-center mb-10">
          Same governance. Your choice of where it runs.
        </h2>
        <div className="overflow-x-auto rounded-xl border border-stone-200 bg-white">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-stone-100">
                <th className="px-5 py-4 text-left text-stone-400 font-semibold w-64">Capability</th>
                <th className="px-5 py-4 text-center text-stone-700 font-semibold">SaaS</th>
                <th className="px-5 py-4 text-center text-indigo-600 font-semibold bg-indigo-50">Cloud (BYOC)</th>
                <th className="px-5 py-4 text-center text-stone-700 font-semibold">On-Premise</th>
              </tr>
            </thead>
            <tbody>
              {ROWS.map((row, i) => (
                <tr key={row.cap} className={`border-b border-stone-50 ${i % 2 === 0 ? "bg-white" : "bg-stone-50/60"}`}>
                  <td className="px-5 py-3.5 text-stone-600 font-medium">{row.cap}</td>
                  <td className="px-5 py-3.5 text-center"><Cell val={row.saas} /></td>
                  <td className="px-5 py-3.5 text-center bg-indigo-50/40"><Cell val={row.byoc} /></td>
                  <td className="px-5 py-3.5 text-center"><Cell val={row.onprem} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  )
}

/* ─── How it works ──────────────────────────────────────────────────────── */

function HowItWorksSection() {
  return (
    <section className="bg-stone-950 px-6 py-20">
      <div className="max-w-4xl mx-auto">
        <p className="text-xs font-semibold uppercase tracking-widest text-indigo-400 mb-3 text-center">One CLI. Any deployment.</p>
        <h2 className="text-3xl font-black text-white tracking-tight text-center mb-4">
          Switching deployment model is one flag.
        </h2>
        <p className="text-stone-400 text-center mb-12 max-w-xl mx-auto">
          The CLI reads <code className="text-indigo-300">api_url</code> from your Guard config. Point it at your instance and everything — hooks, proxy, MCP, audit trail — follows automatically.
        </p>

        <div className="grid md:grid-cols-3 gap-4">
          {[
            {
              label: "SaaS",
              code: `# Default — no config needed\npip install conduct-cli\nconduct guard sync`,
            },
            {
              label: "Cloud (BYOC)",
              code: `# Join your cloud instance\nconduct guard join \\\n  --url https://guard.yourco.com \\\n  --token cond_live_xxx`,
            },
            {
              label: "On-Premise",
              code: `# Deploy then join\ndocker compose up -d\nconduct guard join \\\n  --url https://guard.internal \\\n  --token cond_live_xxx`,
            },
          ].map((item) => (
            <div key={item.label} className="rounded-xl border border-stone-800 bg-stone-900 p-5">
              <p className="text-xs font-bold uppercase tracking-widest text-indigo-400 mb-3">{item.label}</p>
              <pre className="text-xs font-mono text-stone-300 leading-relaxed whitespace-pre">{item.code}</pre>
            </div>
          ))}
        </div>

        <p className="text-stone-600 text-xs text-center mt-8">
          Policy engine, proxy, MCP server, and audit trail work identically across all three tiers.
        </p>
      </div>
    </section>
  )
}

/* ─── CTA ───────────────────────────────────────────────────────────────── */

function CtaSection() {
  return (
    <section className="py-24 px-6 bg-gradient-to-br from-indigo-600 to-violet-600">
      <div className="max-w-3xl mx-auto text-center">
        <h2 className="text-3xl sm:text-4xl font-black text-white tracking-tight leading-tight mb-4">
          Not sure which tier fits?
        </h2>
        <p className="text-indigo-200 text-lg leading-relaxed mb-10 max-w-xl mx-auto">
          Start with SaaS. Migrate to BYOC or on-premise when your compliance team asks. The CLI command is the same either way.
        </p>
        <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
          <CtaLink className="rounded-xl bg-white text-indigo-600 px-7 py-3.5 text-base font-bold hover:bg-indigo-50 transition-colors w-full sm:w-auto text-center" />
          <a
            href="https://cal.com/sudhi-seshachala-pks7pd"
            target="_blank"
            rel="noopener"
            className="rounded-xl border border-white/40 text-white px-7 py-3.5 text-base font-semibold hover:bg-white/10 transition-colors w-full sm:w-auto text-center"
          >
            Talk to us
          </a>
        </div>
        <p className="text-indigo-300 text-xs mt-5">Free tier · No infrastructure changes · Works in minutes</p>
      </div>
    </section>
  )
}
