"use client"

export default function ToolsPage() {
  return (
    <div className="min-h-screen bg-white flex flex-col">
      <Nav />
      <main>
        <HeroSection />
        <ToolsSection />
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
    <section className="flex flex-col items-center justify-center px-6 pt-16 pb-12 text-center">
      <div className="inline-flex items-center gap-2 bg-indigo-50 text-indigo-700 border border-indigo-100 text-xs font-semibold px-3 py-1.5 rounded-full mb-8 uppercase tracking-widest">
        Open Source · Built for teams
      </div>
      <h1 className="text-5xl sm:text-6xl font-bold text-stone-900 leading-[1.1] tracking-tight max-w-3xl">
        Open source tools that{" "}
        <span className="text-indigo-600">cut AI costs.</span>
      </h1>
      <p className="mt-6 text-xl text-stone-500 max-w-2xl leading-relaxed">
        These tools help every developer on your team spend less and move faster when working with AI assistants.
        They are free, open source, and work alongside whatever platform your team already uses.
      </p>
    </section>
  )
}

/* ─── Tools ─────────────────────────────────────────────────────────────── */

function ToolsSection() {
  return (
    <section className="px-6 py-16">
      <div className="max-w-5xl mx-auto">
        <div className="text-center mb-10">
          <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-3">Open source tools</p>
          <h2 className="text-2xl font-bold text-stone-900 mb-3">Help your team work faster</h2>
          <p className="text-stone-500 text-sm max-w-xl mx-auto">
            These tools cut the cost and time of running AI assistants.
            They work on their own — and work within whatever rules Guard sets.
          </p>
        </div>

        <div className="grid sm:grid-cols-2 gap-8">

          {/* Agent Booster */}
          <div className="rounded-2xl border border-stone-200 bg-white px-8 py-8 flex flex-col gap-5 hover:border-indigo-200 hover:shadow-sm transition-all">
            <div className="flex items-start justify-between">
              <div>
                <span className="inline-flex items-center gap-1.5 text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-100 px-2.5 py-1 rounded-full mb-3">
                  v0.2.8 · PyPI
                </span>
                <h2 className="text-2xl font-bold text-stone-900">Agent Booster</h2>
                <p className="text-sm text-stone-500 mt-1">Cut AI running costs by up to 15×</p>
              </div>
              <span className="text-3xl font-black text-indigo-600">◈</span>
            </div>

            <p className="text-sm text-stone-600 leading-relaxed">
              Instead of sending your whole codebase to the AI on every question,
              Agent Booster sends only the parts that matter. Less sent means less spent.
              It also picks the right AI model for the job — no more using the expensive
              one when a cheaper one would do.
            </p>

            <div className="flex flex-col gap-2">
              <p className="text-xs font-bold text-stone-400 uppercase tracking-widest">What it does</p>
              <ul className="space-y-1.5">
                {[
                  "Sends only the relevant code — not the whole file",
                  "Finds the right code by meaning, not just keywords",
                  "Picks the cheapest model that can handle the task",
                  "Shows you how much you've saved over time",
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
                className="inline-flex items-center gap-2 rounded-lg border border-stone-200 px-4 py-2 text-sm font-medium text-stone-600 hover:border-stone-300 transition-colors"
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
                <p className="text-sm text-stone-500 mt-1">Get your team set up in minutes</p>
              </div>
              <span className="text-3xl font-black text-violet-600">⬡</span>
            </div>

            <p className="text-sm text-stone-600 leading-relaxed">
              A ready-to-use setup for teams using Claude Code. Instead of every
              developer configuring things from scratch, this gives the whole team
              a shared starting point — the same rules, the same shortcuts, the same checks.
            </p>

            <div className="flex flex-col gap-2">
              <p className="text-xs font-bold text-stone-400 uppercase tracking-widest">What&apos;s inside</p>
              <ul className="space-y-1.5">
                {[
                  "Shared instructions so the AI knows how your team works",
                  "Pre-built shortcuts for common tasks",
                  "Automatic checks that run before risky actions",
                  "Roles for different team types — startup, SMB, enterprise",
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
      </div>
    </section>
  )
}

/* ─── Footer CTA ────────────────────────────────────────────────────────── */

function FooterCTASection() {
  return (
    <section className="px-6 py-20 text-center">
      <h2 className="text-2xl font-bold text-stone-900 mb-3">Pick a tool. Start saving today.</h2>
      <p className="text-stone-500 text-sm mb-8 max-w-md mx-auto">
        Both tools are free and open source. Install one, try it, and see the savings.
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
        <a href="/" className="inline-flex items-center gap-2 rounded-xl border border-stone-200 bg-white px-6 py-3 text-sm font-semibold text-stone-700 hover:border-stone-300 hover:shadow-sm transition-all">
          Learn about Conduct →
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
