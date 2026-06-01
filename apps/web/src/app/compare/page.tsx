import type { Metadata } from "next"
import FeatureMatrix from "./FeatureMatrix.client"
import { TOOLS, DECISION_GUIDE } from "./compare-data"

export const metadata: Metadata = {
  title: "AI Engineering Tools Compared | Conduct AI",
  description: "Honest side-by-side comparison of Conduct AI, GitHub Copilot, Devin, CodeRabbit, LinearB, Bito, Amazon Q, and xHawk — features, trade-offs, and which tool fits your team.",
  openGraph: {
    title: "AI Engineering Tools Compared | Conduct AI",
    description: "Honest side-by-side comparison of the leading AI engineering tools. Features, trade-offs, and decision guide.",
    url: "https://conductai.ai/compare",
    siteName: "Conduct AI",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "AI Engineering Tools Compared | Conduct AI",
    description: "Honest side-by-side comparison of the leading AI engineering tools.",
  },
}

export default function ComparePage() {
  return (
    <div className="min-h-screen bg-white flex flex-col">

      {/* Nav */}
      <header className="px-6 py-5 flex items-center justify-between max-w-6xl mx-auto w-full border-b border-stone-100">
        <a href="/" className="flex items-center">
          <img src="/logo.png" alt="Conduct AI" className="h-10 w-auto" />
        </a>
        <div className="flex items-center gap-4">
          <a href="/marketplace" className="text-sm text-stone-500 hover:text-stone-900 transition-colors">Marketplace</a>
          <a href="https://narratr.ai/blog/conductai" target="_blank" rel="noopener noreferrer" className="text-sm text-stone-500 hover:text-stone-900 transition-colors">Blog</a>
          <a href="https://github.com/sseshachala/conductai" target="_blank" rel="noopener noreferrer" className="text-sm text-stone-500 hover:text-stone-900 transition-colors">GitHub</a>
          <a href="/sign-in" className="text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">Sign in →</a>
        </div>
      </header>

      {/* Hero */}
      <section className="px-6 py-16 text-center max-w-4xl mx-auto w-full">
        <div className="inline-flex items-center gap-2 bg-stone-100 text-stone-600 text-xs font-medium px-3 py-1.5 rounded-full mb-6">
          Last updated May 2026 · Based on public documentation
        </div>
        <h1 className="text-4xl sm:text-5xl font-bold text-stone-900 leading-tight tracking-tight mb-4">
          AI engineering tools,<br />
          <span className="text-indigo-600">compared honestly.</span>
        </h1>
        <p className="text-lg text-stone-500 max-w-2xl mx-auto leading-relaxed">
          There are excellent tools in this space. Each one makes different trade-offs.
          This page breaks down what each tool actually does, who it is built for, and where
          the differences matter — so you can pick what fits your team.
        </p>
        <p className="mt-4 text-sm text-stone-400 max-w-xl mx-auto">
          We built Conduct. We are clearly not neutral. We have tried to be as fair and accurate as possible —
          if anything here is wrong, <a href="https://github.com/sseshachala/conductai/issues" target="_blank" rel="noopener noreferrer" className="underline hover:text-stone-600">open an issue</a> and we will fix it.
        </p>
      </section>

      {/* Competitor cards */}
      <section className="px-6 pb-16">
        <div className="max-w-6xl mx-auto">
          <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest text-center mb-10">Tools in this comparison</p>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {TOOLS.map(t => (
              <a key={t.id} href={`#${t.id}`}
                className="bg-white rounded-2xl border border-stone-200 p-5 flex flex-col gap-3 hover:border-stone-300 hover:shadow-sm transition-all group">
                <div className="flex items-center justify-between">
                  <span className="text-2xl">{t.emoji}</span>
                  <span className={`text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-full ${t.categoryColor}`}>{t.category}</span>
                </div>
                <div>
                  <p className="font-bold text-stone-900 text-sm group-hover:text-indigo-600 transition-colors">{t.name}</p>
                  <p className="text-xs text-stone-500 mt-0.5">{t.maker}</p>
                </div>
                <p className="text-xs text-stone-500 leading-relaxed">{t.oneLiner}</p>
              </a>
            ))}
          </div>
        </div>
      </section>

      {/* Feature matrix */}
      <section className="px-4 pb-20 bg-stone-50">
        <div className="max-w-6xl mx-auto pt-16">
          <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest text-center mb-3">Feature matrix</p>
          <h2 className="text-2xl font-bold text-stone-900 text-center mb-2">Side-by-side comparison</h2>
          <p className="text-sm text-stone-500 text-center mb-10 max-w-xl mx-auto">
            ✅ = available &nbsp;·&nbsp; 🟡 = partial or limited &nbsp;·&nbsp; ❌ = not available &nbsp;·&nbsp; Based on public documentation as of May 2026.
          </p>
          <FeatureMatrix />
        </div>
      </section>

      {/* Detailed per-tool sections */}
      <section className="px-6 py-20">
        <div className="max-w-4xl mx-auto space-y-16">
          <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest text-center mb-0">In depth</p>
          {TOOLS.map(t => <ToolDetail key={t.id} tool={t} />)}
        </div>
      </section>

      {/* Who should use what */}
      <section className="bg-stone-50 px-6 py-20">
        <div className="max-w-4xl mx-auto">
          <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest text-center mb-3">Decision guide</p>
          <h2 className="text-2xl font-bold text-stone-900 text-center mb-10">Which tool fits your situation?</h2>
          <div className="space-y-4">
            {DECISION_GUIDE.map(d => (
              <div key={d.situation} className="bg-white rounded-2xl border border-stone-200 p-6 flex flex-col sm:flex-row gap-4">
                <div className="shrink-0">
                  <span className="text-2xl">{d.icon}</span>
                </div>
                <div className="flex-1">
                  <p className="font-semibold text-stone-900 mb-1">{d.situation}</p>
                  <p className="text-sm text-stone-500 leading-relaxed mb-3">{d.detail}</p>
                  <div className="flex flex-wrap gap-2">
                    {d.picks.map(p => (
                      <span key={p.name} className={`text-xs font-semibold px-2.5 py-1 rounded-full ${p.highlight ? "bg-indigo-600 text-white" : "bg-stone-100 text-stone-700"}`}>
                        {p.name}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Bottom CTA */}
      <section className="px-6 py-20 text-center">
        <h2 className="text-3xl font-bold text-stone-900 mb-4">Try Conduct free</h2>
        <p className="text-stone-500 mb-8 max-w-md mx-auto text-sm leading-relaxed">
          Sign in with Google, connect a GitHub repo, and install your first playbook from the Marketplace. Running in under 5 minutes.
        </p>
        <a
          href="/sign-in"
          className="inline-flex items-center gap-2 bg-stone-900 hover:bg-stone-700 text-white font-semibold px-7 py-3.5 rounded-xl text-sm transition-colors"
        >
          Get started — it&apos;s free →
        </a>
        <p className="text-xs text-stone-400 mt-4">No credit card · Connect your existing tools · Sign in with Google</p>
      </section>

      <footer className="border-t border-stone-100 py-8 text-center text-xs text-stone-400 space-y-2">
        <div className="flex items-center justify-center gap-3 flex-wrap">
          <span>© {new Date().getFullYear()} Conduct</span>
          <span>·</span>
          <a href="https://github.com/sseshachala/conductai" target="_blank" rel="noopener noreferrer" className="hover:text-stone-600 transition-colors">GitHub</a>
          <span>·</span>
          <a href="https://narratr.ai/blog/conductai" target="_blank" rel="noopener noreferrer" className="hover:text-stone-600 transition-colors">Blog</a>
          <span>·</span>
          <a href="/privacy" className="hover:text-stone-600 transition-colors">Privacy</a>
          <span>·</span>
          <a href="/terms" className="hover:text-stone-600 transition-colors">Terms</a>
        </div>
        <p className="text-stone-300">Envisioned, designed and developed with 💕 from Houston</p>
      </footer>
    </div>
  )
}

function ToolDetail({ tool }: { tool: typeof TOOLS[number] }) {
  return (
    <div id={tool.id} className="scroll-mt-8">
      <div className="flex items-start gap-4 mb-5">
        <span className="text-4xl">{tool.emoji}</span>
        <div>
          <div className="flex items-center gap-2 flex-wrap">
            <h2 className="text-xl font-bold text-stone-900">{tool.name}</h2>
            <span className="text-xs text-stone-400">by {tool.maker}</span>
            <span className={`text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-full ${tool.categoryColor}`}>{tool.category}</span>
          </div>
          <a href={tool.url} target="_blank" rel="noopener noreferrer" className="text-xs text-stone-400 hover:text-indigo-600 transition-colors mt-0.5 block">
            {tool.url} ↗
          </a>
        </div>
      </div>

      <p className="text-stone-600 leading-relaxed mb-6">{tool.description}</p>

      <div className="grid sm:grid-cols-2 gap-4 mb-6">
        <div className="bg-emerald-50 border border-emerald-100 rounded-xl p-4">
          <p className="text-xs font-bold text-emerald-700 uppercase tracking-wider mb-2">Strengths</p>
          <ul className="space-y-1.5">
            {tool.strengths.map(s => (
              <li key={s} className="text-sm text-stone-700 flex items-start gap-2">
                <span className="text-emerald-500 mt-0.5 shrink-0">✓</span>{s}
              </li>
            ))}
          </ul>
        </div>
        <div className="bg-amber-50 border border-amber-100 rounded-xl p-4">
          <p className="text-xs font-bold text-amber-700 uppercase tracking-wider mb-2">Trade-offs</p>
          <ul className="space-y-1.5">
            {tool.tradeoffs.map(t => (
              <li key={t} className="text-sm text-stone-700 flex items-start gap-2">
                <span className="text-amber-500 mt-0.5 shrink-0">–</span>{t}
              </li>
            ))}
          </ul>
        </div>
      </div>

      <div className="bg-stone-50 rounded-xl border border-stone-200 p-4">
        <p className="text-xs font-bold text-stone-500 uppercase tracking-wider mb-1.5">Best for</p>
        <p className="text-sm text-stone-700 leading-relaxed">{tool.bestFor}</p>
      </div>
    </div>
  )
}
