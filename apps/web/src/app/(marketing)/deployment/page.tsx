import Link from "next/link"

export const metadata = {
  title: "Deployment — Conduct",
  description:
    "Deploy Guard where your controls need to live. SaaS, Docker, Kubernetes preview, or air-gapped.",
}

type Status = "SHIPPED" | "PREVIEW" | "PLANNED"

const OPTIONS: {
  name: string
  status: Status
  tagline: string
  description: string
  bullets: string[]
}[] = [
  {
    name: "SaaS",
    status: "SHIPPED",
    tagline: "conductai.ai",
    description:
      "Hosted at conductai.ai. Same CLI, same audit trail. Zero infrastructure to run — fastest path from install to first blocked action.",
    bullets: [
      "US and EU regions",
      "Free tier + 14-day Discovery trial",
      "Rolling updates managed by Conduct",
    ],
  },
  {
    name: "Docker",
    status: "SHIPPED",
    tagline: "Self-hosted",
    description:
      "Single-container image. Runs on your servers, in your VPC, wherever Docker runs. No outbound calls to Conduct infrastructure required.",
    bullets: [
      "docker-compose.yml provided",
      "Postgres + Redis dependencies",
      "Full policy engine parity with SaaS",
    ],
  },
  {
    name: "Kubernetes",
    status: "PREVIEW",
    tagline: "Helm chart",
    description:
      "Helm chart for production Kubernetes clusters. HPA, PDB, and network policies included. Preview — reach out for pilot access.",
    bullets: [
      "values.yaml customization",
      "Prometheus scrape targets",
      "Service mesh compatible",
    ],
  },
  {
    name: "Air-gapped",
    status: "PLANNED",
    tagline: "No outbound",
    description:
      "Fully isolated rollout for regulated or classified environments. Manual audit chain export, offline update bundles. Design partners engaged.",
    bullets: [
      "No outbound calls",
      "Offline update bundles",
      "Manifest hash verification",
    ],
  },
]

const STATUS_STYLE: Record<Status, string> = {
  SHIPPED: "bg-emerald-50 text-emerald-700 border-emerald-200",
  PREVIEW: "bg-amber-50 text-amber-700 border-amber-200",
  PLANNED: "bg-stone-50 text-stone-500 border-stone-200",
}

export default function DeploymentPage() {
  return (
    <div className="min-h-screen bg-white">
      <main className="max-w-5xl mx-auto px-6 py-20">
        <section className="mb-16 text-center">
          <p className="text-xs font-mono font-bold uppercase tracking-widest text-stone-400 mb-4">
            Rollout
          </p>
          <h1 className="text-4xl sm:text-5xl font-black tracking-tight text-stone-900 leading-[1.05] mb-6">
            Deploy Guard where your controls need to live.
          </h1>
          <p className="text-lg text-stone-500 max-w-2xl mx-auto leading-relaxed">
            Same policy engine, same CLI, same audit trail — wherever your data must stay.
          </p>
        </section>

        <section className="mb-20 grid grid-cols-1 md:grid-cols-2 gap-6">
          {OPTIONS.map((opt) => (
            <div
              key={opt.name}
              className="border border-stone-200 rounded-2xl p-6 bg-white flex flex-col"
            >
              <div className="flex items-center justify-between mb-2">
                <h2 className="text-xl font-bold text-stone-900">{opt.name}</h2>
                <span
                  className={`text-[10px] font-mono font-bold uppercase tracking-wider border rounded px-2 py-0.5 ${STATUS_STYLE[opt.status]}`}
                >
                  {opt.status}
                </span>
              </div>
              <p className="text-xs font-mono text-stone-400 uppercase tracking-wider mb-4">
                {opt.tagline}
              </p>
              <p className="text-sm text-stone-600 leading-relaxed mb-5">
                {opt.description}
              </p>
              <ul className="text-sm text-stone-500 space-y-1.5 mt-auto">
                {opt.bullets.map((b) => (
                  <li key={b} className="flex items-start gap-2">
                    <span className="text-stone-300 shrink-0">·</span>
                    <span>{b}</span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </section>

        <section className="text-center border-t border-stone-100 pt-16">
          <p className="text-lg text-stone-600 max-w-xl mx-auto leading-relaxed mb-6">
            Not sure which fits? Start on SaaS, migrate to Docker or Kubernetes when compliance asks.
          </p>
          <Link
            href="/sign-up"
            className="inline-block rounded-xl bg-stone-900 text-white px-6 py-3 text-sm font-semibold hover:bg-stone-700 transition-colors"
          >
            Start Discovery — 14 days free
          </Link>
        </section>
      </main>
    </div>
  )
}
