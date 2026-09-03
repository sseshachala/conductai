import Link from "next/link"

export const metadata = {
  title: "Open Source — Conduct",
  description:
    "The components that matter most for trust are open. Four Apache-2.0 components: conduct-cli, Guard runtime core, Playbook DSL compiler, and Agent Booster MCP.",
}

const OSS_COMPONENTS = [
  {
    name: "conduct-cli",
    license: "Apache-2.0",
    repo: "github.com/conductai/conduct",
    path: "packages/conduct-cli/",
    pypi: "conduct-cli",
    purpose: "Agent lifecycle management, Guard sync, policy testing. Runs on developer machines and in CI/CD.",
  },
  {
    name: "Guard runtime core",
    license: "Apache-2.0",
    repo: "github.com/conductai/conduct",
    path: "apps/api/app/guard/",
    pypi: null,
    purpose: "Core enforcement engine: rule evaluation, decision scoring, hash-chained audit trail. Runs inside the Conduct API server.",
  },
  {
    name: "Playbook DSL compiler",
    license: "Apache-2.0",
    repo: "github.com/conductai/conduct",
    path: "apps/api/app/compiler/",
    pypi: null,
    purpose: "Compiles YAML playbook definitions into executable DAG runs. Shared by all 39 shipped playbooks.",
  },
  {
    name: "Agent Booster MCP",
    license: "Apache-2.0",
    repo: "github.com/conductai/conduct",
    path: "tools/booster/",
    pypi: null,
    purpose: "Developer productivity tools (semantic search, smart read, test coverage) for Claude Code and Cursor. Runs locally or on Vercel.",
  },
]

export default function OpenSourcePage() {
  return (
    <div className="min-h-screen bg-white">
      <main className="max-w-5xl mx-auto px-6">

        {/* Hero */}
        <section className="pt-20 pb-16 text-center">
          <p className="text-xs font-mono font-bold uppercase tracking-widest text-stone-400 mb-4">
            Open Source
          </p>
          <h1 className="text-4xl sm:text-5xl font-black tracking-tight text-stone-900 leading-[1.05] mb-6">
            Open where trust matters.
          </h1>
          <p className="text-lg text-stone-500 max-w-2xl mx-auto leading-relaxed mb-10">
            The components that determine whether Guard is trustworthy are open. The enforcement engine,
            the audit trail, and the CLI are Apache-2.0 — readable, auditable, and forkable.
          </p>
          <div className="flex flex-wrap justify-center gap-3">
            <a
              href="https://github.com/conductai/conduct"
              className="inline-block rounded-xl bg-stone-900 text-white px-6 py-3 text-sm font-semibold hover:bg-stone-700 transition-colors"
            >
              View the open-source runtime →
            </a>
            <Link
              href="/sign-up"
              className="inline-block rounded-xl border border-stone-200 bg-white text-stone-700 px-6 py-3 text-sm font-semibold hover:bg-stone-50 transition-colors"
            >
              Start Discovery — 14 days free
            </Link>
          </div>
        </section>

        {/* Component table */}
        <section className="mb-20">
          <h2 className="text-2xl font-bold text-stone-900 mb-3">4 open-source components</h2>
          <p className="text-stone-500 text-sm leading-relaxed mb-8 max-w-2xl">
            These are the exact components open-sourced as of the last audit (2026-09-01). All four are Apache-2.0.
            The hosted product (SaaS at conductai.ai) runs the same code.
          </p>

          {/* Desktop table */}
          <div className="hidden sm:block border border-stone-200 rounded-2xl overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-stone-50 border-b border-stone-200">
                  <th className="text-left px-5 py-3 text-xs font-mono font-bold uppercase tracking-widest text-stone-400 w-1/4">Component</th>
                  <th className="text-left px-5 py-3 text-xs font-mono font-bold uppercase tracking-widest text-stone-400 w-24">Licence</th>
                  <th className="text-left px-5 py-3 text-xs font-mono font-bold uppercase tracking-widest text-stone-400 w-1/4">Repository path</th>
                  <th className="text-left px-5 py-3 text-xs font-mono font-bold uppercase tracking-widest text-stone-400">Purpose</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-stone-100">
                {OSS_COMPONENTS.map((c) => (
                  <tr key={c.name} className="hover:bg-stone-50 transition-colors">
                    <td className="px-5 py-4 font-mono font-bold text-stone-900 text-xs align-top">
                      {c.name}
                      {c.pypi && (
                        <p className="text-[10px] text-stone-400 font-normal mt-0.5">PyPI: {c.pypi}</p>
                      )}
                    </td>
                    <td className="px-5 py-4 align-top">
                      <span className="text-xs font-mono border border-emerald-200 bg-emerald-50 text-emerald-700 rounded px-2 py-0.5">
                        {c.license}
                      </span>
                    </td>
                    <td className="px-5 py-4 font-mono text-xs text-stone-500 align-top break-all">
                      {c.path}
                    </td>
                    <td className="px-5 py-4 text-xs text-stone-600 leading-relaxed align-top">
                      {c.purpose}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Mobile cards */}
          <div className="sm:hidden space-y-4">
            {OSS_COMPONENTS.map((c) => (
              <div key={c.name} className="border border-stone-200 rounded-xl p-5 bg-white">
                <div className="flex items-start justify-between gap-2 mb-3">
                  <p className="font-mono font-bold text-stone-900 text-sm">{c.name}</p>
                  <span className="text-[10px] font-mono border border-emerald-200 bg-emerald-50 text-emerald-700 rounded px-2 py-0.5 shrink-0">
                    {c.license}
                  </span>
                </div>
                <p className="text-[11px] font-mono text-stone-400 mb-2">{c.path}</p>
                <p className="text-xs text-stone-600 leading-relaxed">{c.purpose}</p>
                {c.pypi && (
                  <p className="text-[10px] text-stone-400 mt-2">PyPI: {c.pypi}</p>
                )}
              </div>
            ))}
          </div>
        </section>

        {/* What open means */}
        <section className="mb-20 border border-stone-200 rounded-2xl p-8 bg-stone-50">
          <h2 className="text-lg font-bold text-stone-900 mb-4">What open means here</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-6 text-sm text-stone-600 leading-relaxed">
            <div>
              <p className="font-semibold text-stone-900 mb-2">Apache-2.0</p>
              <p>
                The entire repository — CLI, Guard runtime, compiler, web UI, and API — is Apache-2.0.
                The SaaS product runs this source. There is no closed core.
              </p>
            </div>
            <div>
              <p className="font-semibold text-stone-900 mb-2">Self-hosted</p>
              <p>
                Run Guard on your own infrastructure using Docker Compose. The same policy engine
                and audit trail, on hardware you control. Kubernetes support is in preview.
              </p>
            </div>
          </div>
        </section>

        {/* CTA */}
        <section className="mb-20 text-center border-t border-stone-100 pt-16">
          <h2 className="text-2xl font-bold text-stone-900 mb-4">Start with the source.</h2>
          <div className="flex flex-wrap justify-center gap-3">
            <a
              href="https://github.com/conductai/conduct"
              className="inline-block rounded-xl bg-stone-900 text-white px-6 py-3 text-sm font-semibold hover:bg-stone-700 transition-colors"
            >
              View on GitHub →
            </a>
            <Link
              href="/deployment"
              className="inline-block rounded-xl border border-stone-200 bg-white text-stone-700 px-6 py-3 text-sm font-semibold hover:bg-stone-50 transition-colors"
            >
              Deployment options →
            </Link>
          </div>
        </section>

      </main>
    </div>
  )
}
