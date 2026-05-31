"use client"

export default function ToolsPage() {
  return (
    <div className="min-h-screen bg-white flex flex-col">
      <Nav />
      <main>
        <HeroSection />
        <ToolsSection />
        <StackSection />
        <FooterCTASection />
      </main>
      <PageFooter />
    </div>
  )
}

/* ─── Nav ──────────────────────────────────────────────────────────────── */

function Nav() {
  return (
    <header className="px-6 py-5 flex items-center justify-between max-w-6xl mx-auto w-full">
      <div className="flex items-center">
        <a href="/">
          <img src="/logo.png" alt="Conduct AI" className="h-10 w-auto" />
        </a>
      </div>
      <div className="flex items-center gap-4">
        <a href="/blog" className="flex items-center gap-1.5 text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">Blog</a>
        <a href="/marketplace" className="flex items-center gap-1.5 text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">Playbooks</a>
        <a href="/tools" className="flex items-center gap-1.5 text-sm font-medium text-indigo-600 hover:text-indigo-900 transition-colors">Tools</a>
        <a href="/benchmark" className="flex items-center gap-1.5 text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">Benchmark</a>
        <a href="/docs" className="flex items-center gap-1.5 text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">Docs</a>
        <a
          href="https://github.com/sseshachala/conductai"
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-1.5 text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors"
        >
          <GitHubIcon />
          GitHub
        </a>
      </div>
    </header>
  )
}

/* ─── Hero ─────────────────────────────────────────────────────────────── */

function HeroSection() {
  return (
    <section className="flex flex-col items-center justify-center px-6 pt-16 pb-16 text-center">
      <div className="inline-flex items-center gap-2 bg-indigo-50 text-indigo-700 border border-indigo-100 text-xs font-semibold px-3 py-1.5 rounded-full mb-8 uppercase tracking-widest">
        Open Source Developer Tools
      </div>
      <h1 className="text-5xl sm:text-6xl font-bold text-stone-900 leading-[1.1] tracking-tight max-w-3xl">
        Tools that make AI coding{" "}
        <span className="text-indigo-600">faster and cheaper.</span>
      </h1>
      <p className="mt-6 text-xl text-stone-500 max-w-2xl leading-relaxed">
        Free, open-source utilities built from running Claude Code at scale.
        Each one solves a real problem — workspace setup, token costs, model routing.
      </p>
    </section>
  )
}

/* ─── Tools ─────────────────────────────────────────────────────────────── */

function ToolsSection() {
  return (
    <section className="px-6 py-12">
      <div className="max-w-5xl mx-auto grid sm:grid-cols-2 gap-8">

        {/* Agent Booster */}
        <div className="rounded-2xl border border-stone-200 bg-white px-8 py-8 flex flex-col gap-5 hover:border-indigo-200 hover:shadow-sm transition-all">
          <div className="flex items-start justify-between">
            <div>
              <span className="inline-flex items-center gap-1.5 text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-100 px-2.5 py-1 rounded-full mb-3">
                v0.2.3 · PyPI
              </span>
              <h2 className="text-2xl font-bold text-stone-900">Agent Booster</h2>
              <p className="text-sm text-stone-500 mt-1">Cut token costs 5–15x</p>
            </div>
            <span className="text-3xl font-black text-indigo-600">◈</span>
          </div>

          <p className="text-sm text-stone-600 leading-relaxed">
            AST + vector index of your codebase. Instead of sending full files to the model,
            routes only the functions and classes relevant to the task.
            Three hooks enforce it automatically — Read gate, Grep nudge, and auto model routing on every turn.
          </p>

          <div className="flex flex-col gap-2">
            <p className="text-xs font-bold text-stone-400 uppercase tracking-widest">What it does</p>
            <ul className="space-y-1.5">
              {[
                "smart_read — returns only relevant symbol slices",
                "search_context — semantic search across all indexed symbols",
                "route_model — recommends haiku / sonnet / opus per task",
                "booster gain — tracks token savings over time",
              ].map(item => (
                <li key={item} className="flex items-start gap-2 text-sm text-stone-600">
                  <span className="text-emerald-500 mt-0.5 shrink-0">✓</span>
                  {item}
                </li>
              ))}
            </ul>
          </div>

          <div className="mt-auto pt-4 border-t border-stone-100 flex items-center gap-3 flex-wrap">
            <a
              href="/tools/agent-booster"
              className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-700 transition-colors"
            >
              Learn more →
            </a>
            <a
              href="https://github.com/sseshachala/conductai"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 rounded-lg border border-stone-200 px-4 py-2 text-sm font-medium text-stone-600 hover:border-stone-300 transition-colors"
            >
              <GitHubIcon />
              GitHub
            </a>
            <code className="font-mono text-xs text-stone-400 bg-stone-50 px-2 py-1 rounded">pip install agent-booster</code>
          </div>
        </div>

        {/* Workspace Starter */}
        <div className="rounded-2xl border border-stone-200 bg-white px-8 py-8 flex flex-col gap-5 hover:border-violet-200 hover:shadow-sm transition-all">
          <div className="flex items-start justify-between">
            <div>
              <span className="inline-flex items-center gap-1.5 text-xs font-semibold bg-violet-50 text-violet-700 border border-violet-100 px-2.5 py-1 rounded-full mb-3">
                Free · MIT
              </span>
              <h2 className="text-2xl font-bold text-stone-900">Workspace Starter</h2>
              <p className="text-sm text-stone-500 mt-1">Claude Code scaffold for any team</p>
            </div>
            <span className="text-3xl font-black text-violet-600">⬡</span>
          </div>

          <p className="text-sm text-stone-600 leading-relaxed">
            Production-ready Claude Code setup across all 5 layers — CLAUDE.md, skills, hooks,
            subagents, and plugins — pre-configured for three personas: Enterprise, SMB, and Startup.
            One <code className="font-mono text-xs bg-stone-100 px-1 rounded">install.sh</code> and you&apos;re running.
          </p>

          <div className="flex flex-col gap-2">
            <p className="text-xs font-bold text-stone-400 uppercase tracking-widest">What&apos;s inside</p>
            <ul className="space-y-1.5">
              {[
                "CLAUDE.md — your agent's constitution, per team type",
                "Skills — compliance, shipping, cost-optimization and more",
                "Hooks — secrets blocker, audit log, deploy guard",
                "Subagents — security officer, PM, founding engineer",
              ].map(item => (
                <li key={item} className="flex items-start gap-2 text-sm text-stone-600">
                  <span className="text-violet-500 mt-0.5 shrink-0">✓</span>
                  {item}
                </li>
              ))}
            </ul>
          </div>

          <div className="mt-auto pt-4 border-t border-stone-100 flex items-center gap-3 flex-wrap">
            <a
              href="https://github.com/sseshachala/claude-code-workspace-starter"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 rounded-lg bg-violet-600 px-4 py-2 text-sm font-semibold text-white hover:bg-violet-700 transition-colors"
            >
              <GitHubIcon />
              View on GitHub
            </a>
            <code className="font-mono text-xs text-stone-400 bg-stone-50 px-2 py-1 rounded">bash install.sh</code>
          </div>
        </div>

      </div>
    </section>
  )
}

/* ─── Stack ─────────────────────────────────────────────────────────────── */

function StackSection() {
  return (
    <section className="bg-stone-900 px-6 py-20 mt-8">
      <div className="max-w-3xl mx-auto text-center">
        <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-3">Better together</p>
        <h2 className="text-3xl font-bold text-white mb-4">
          They stack.
        </h2>
        <p className="text-stone-400 text-sm max-w-xl mx-auto mb-12">
          Workspace Starter sets up how Claude Code behaves.
          Agent Booster cuts what it costs to run.
          Use both for a fully optimized AI coding environment.
        </p>

        <div className="flex flex-col gap-3 text-left">
          <div className="rounded-xl border border-indigo-400 bg-indigo-900 px-6 py-4 flex items-center gap-4">
            <span className="text-2xl font-black text-indigo-300">◈</span>
            <div>
              <p className="text-sm font-semibold text-white">Agent Booster</p>
              <p className="text-xs text-indigo-300">token costs, smart reads, model routing</p>
            </div>
            <span className="ml-auto text-xs font-semibold text-indigo-300 bg-indigo-800 border border-indigo-600 px-2 py-0.5 rounded-full">Layer 3</span>
          </div>
          <div className="rounded-xl border border-violet-400 bg-violet-900 px-6 py-4 flex items-center gap-4">
            <span className="text-2xl font-black text-violet-300">⬡</span>
            <div>
              <p className="text-sm font-semibold text-white">Workspace Starter</p>
              <p className="text-xs text-violet-300">CLAUDE.md, skills, hooks, subagents, plugins</p>
            </div>
            <span className="ml-auto text-xs font-semibold text-violet-300 bg-violet-800 border border-violet-600 px-2 py-0.5 rounded-full">Layers 1–5</span>
          </div>
          <div className="rounded-xl border border-amber-600 bg-amber-950 px-6 py-4 flex items-center gap-4">
            <span className="text-2xl font-black text-amber-400">≋</span>
            <div>
              <p className="text-sm font-semibold text-white">RTK — Rust Token Killer</p>
              <p className="text-xs text-amber-300">CLI output compression, 60–90% token savings</p>
            </div>
            <span className="ml-auto text-xs font-semibold text-amber-300 bg-amber-900 border border-amber-700 px-2 py-0.5 rounded-full">Layer 2</span>
          </div>
          <div className="rounded-xl border border-teal-600 bg-teal-950 px-6 py-4 flex items-center gap-4">
            <span className="text-2xl font-black text-teal-400">⊙</span>
            <div>
              <p className="text-sm font-semibold text-white">Prompt Caching</p>
              <p className="text-xs text-teal-300">stable context reuse at 90% discount</p>
            </div>
            <span className="ml-auto text-xs font-semibold text-teal-300 bg-teal-900 border border-teal-700 px-2 py-0.5 rounded-full">Layer 1</span>
          </div>
        </div>
      </div>
    </section>
  )
}

/* ─── Footer CTA ────────────────────────────────────────────────────────── */

function FooterCTASection() {
  return (
    <section className="px-6 py-20 text-center">
      <h2 className="text-2xl font-bold text-stone-900 mb-3">Free. Open source. No sign-up.</h2>
      <p className="text-stone-500 text-sm mb-8 max-w-md mx-auto">
        Both tools are MIT licensed and live on GitHub. Install them in any project, any team size.
      </p>
      <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
        <a href="/tools/agent-booster" className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-6 py-3 text-sm font-semibold text-white hover:bg-indigo-700 transition-colors">
          Agent Booster docs →
        </a>
        <a
          href="https://github.com/sseshachala/claude-code-workspace-starter"
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-2 rounded-xl border border-stone-200 bg-white px-6 py-3 text-sm font-semibold text-stone-700 hover:border-stone-300 hover:shadow-sm transition-all"
        >
          <GitHubIcon />
          Workspace Starter
        </a>
      </div>
    </section>
  )
}

/* ─── Footer ────────────────────────────────────────────────────────────── */

function PageFooter() {
  return (
    <footer className="border-t border-stone-100 py-8 text-center text-xs text-stone-400 space-y-2">
      <div className="flex items-center justify-center gap-3 flex-wrap">
        <span>© {new Date().getFullYear()} Conduct</span>
        <span>·</span>
        <a href="https://github.com/sseshachala/conductai" target="_blank" rel="noopener noreferrer" className="hover:text-stone-600 transition-colors">GitHub</a>
        <span>·</span>
        <span>MIT licensed</span>
        <span>·</span>
        <a href="/" className="hover:text-stone-600 transition-colors">Conduct AI</a>
        <span>·</span>
        <a href="/marketplace" className="hover:text-stone-600 transition-colors">Playbooks</a>
        <span>·</span>
        <a href="/tools" className="hover:text-stone-600 transition-colors">Tools</a>
        <span>·</span>
        <a href="/docs" className="hover:text-stone-600 transition-colors">Docs</a>
        <span>·</span>
        <a href="/about" className="hover:text-stone-600 transition-colors">About</a>
      </div>
      <p className="text-stone-300">Envisioned, designed and developed with love from Houston</p>
    </footer>
  )
}

/* ─── Icons ─────────────────────────────────────────────────────────────── */

function GitHubIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
      <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0 0 16 8c0-4.42-3.58-8-8-8z" />
    </svg>
  )
}
