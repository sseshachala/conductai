"use client"

export default function ToolsPage() {
  return (
    <div className="min-h-screen bg-white flex flex-col">
      <Nav />
      <main>
        <HeroSection />
        <GuardSection />
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
    <section className="flex flex-col items-center justify-center px-6 pt-16 pb-12 text-center">
      <div className="inline-flex items-center gap-2 bg-indigo-50 text-indigo-700 border border-indigo-100 text-xs font-semibold px-3 py-1.5 rounded-full mb-8 uppercase tracking-widest">
        Open Source · Built for teams
      </div>
      <h1 className="text-5xl sm:text-6xl font-bold text-stone-900 leading-[1.1] tracking-tight max-w-3xl">
        Set the rules once.{" "}
        <span className="text-indigo-600">Let your team move fast.</span>
      </h1>
      <p className="mt-6 text-xl text-stone-500 max-w-2xl leading-relaxed">
        ConductGuard lets you set policies for your whole team in one place.
        The tools below help every developer work faster — within those rules, automatically.
      </p>
    </section>
  )
}

/* ─── Guard ─────────────────────────────────────────────────────────────── */

function GuardSection() {
  return (
    <section className="px-6 py-16 bg-stone-50">
      <div className="max-w-5xl mx-auto">
        <div className="text-center mb-12">
          <div className="inline-flex items-center gap-2 bg-red-50 text-red-700 border border-red-100 text-xs font-semibold px-3 py-1.5 rounded-full mb-4 uppercase tracking-widest">
            ConductGuard · Inside Conduct
          </div>
          <h2 className="text-3xl font-bold text-stone-900 mb-4">
            One place to set the rules for your whole team
          </h2>
          <p className="text-stone-500 text-base max-w-2xl mx-auto leading-relaxed">
            You decide what your team&apos;s AI tools are allowed to do — how much they can spend,
            what actions they can take, what gets logged. Set it once in Conduct.
            It applies to every workflow and every developer on your team, automatically.
          </p>
        </div>

        <div className="grid sm:grid-cols-3 gap-6 mb-10">
          <div className="bg-white rounded-2xl border border-stone-200 p-6 flex flex-col gap-3">
            <div className="w-10 h-10 rounded-xl bg-red-50 flex items-center justify-center text-xl">💸</div>
            <p className="font-semibold text-stone-900">Spending limits</p>
            <p className="text-sm text-stone-500 leading-relaxed">
              Set a limit on how much any developer or workflow can spend in a day.
              Everyone on the team gets the same limit without any extra setup.
            </p>
          </div>
          <div className="bg-white rounded-2xl border border-stone-200 p-6 flex flex-col gap-3">
            <div className="w-10 h-10 rounded-xl bg-red-50 flex items-center justify-center text-xl">🚫</div>
            <p className="font-semibold text-stone-900">Block risky actions</p>
            <p className="text-sm text-stone-500 leading-relaxed">
              Decide which actions an AI agent is not allowed to take — like writing
              to production files or running certain commands. Blocked for everyone, everywhere.
            </p>
          </div>
          <div className="bg-white rounded-2xl border border-stone-200 p-6 flex flex-col gap-3">
            <div className="w-10 h-10 rounded-xl bg-red-50 flex items-center justify-center text-xl">📋</div>
            <p className="font-semibold text-stone-900">One audit log</p>
            <p className="text-sm text-stone-500 leading-relaxed">
              See exactly what every AI tool did, when, and who triggered it.
              One log for the whole team — not scattered across individual machines.
            </p>
          </div>
        </div>

        <div className="bg-white rounded-2xl border border-red-100 p-6 flex flex-col sm:flex-row items-start sm:items-center gap-6">
          <div className="flex-1">
            <p className="font-semibold text-stone-900 mb-1">Rules flow in two directions</p>
            <p className="text-sm text-stone-500 leading-relaxed">
              Every policy you set in Conduct flows automatically into your AI workflows
              <span className="text-stone-700 font-medium"> and </span>
              into every developer&apos;s local environment when they run{" "}
              <code className="font-mono text-xs bg-stone-100 px-1.5 py-0.5 rounded">conduct guard join</code>.
              Change a rule once — it updates everywhere.
            </p>
          </div>
          <a
            href="/dashboard"
            className="shrink-0 inline-flex items-center gap-2 rounded-xl bg-red-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-red-700 transition-colors"
          >
            Open Conduct →
          </a>
        </div>
      </div>
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

/* ─── Stack ─────────────────────────────────────────────────────────────── */

function StackSection() {
  return (
    <section className="bg-stone-900 px-6 py-20 mt-8">
      <div className="max-w-3xl mx-auto text-center">
        <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-3">The full picture</p>
        <h2 className="text-3xl font-bold text-white mb-4">
          How it all works together
        </h2>
        <p className="text-stone-400 text-sm max-w-xl mx-auto mb-12">
          Guard sits at the top — it sets the rules.
          The tools below help everyone work faster within those rules.
          Each layer builds on the one below it.
        </p>

        <div className="flex flex-col gap-2 text-left mb-4">
          <div className="rounded-xl border border-red-400 bg-red-950 px-6 py-4 flex items-center gap-4">
            <span className="text-2xl">🛡️</span>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold text-white">ConductGuard — inside Conduct</p>
              <p className="text-xs text-red-300">spending limits, blocked actions, audit log — one policy for the whole team</p>
            </div>
            <span className="ml-auto shrink-0 text-xs font-semibold text-red-300 bg-red-900 border border-red-700 px-2 py-0.5 rounded-full">Rules layer</span>
          </div>
        </div>

        <div className="flex items-center gap-3 mb-4 px-2">
          <div className="flex-1 border-t border-stone-700" />
          <p className="text-xs text-stone-500 whitespace-nowrap">tools work within these rules</p>
          <div className="flex-1 border-t border-stone-700" />
        </div>

        <div className="flex flex-col gap-3 text-left">
          <div className="rounded-xl border border-indigo-400 bg-indigo-900 px-6 py-4 flex items-center gap-4">
            <span className="text-2xl font-black text-indigo-300">◈</span>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold text-white">Agent Booster</p>
              <p className="text-xs text-indigo-300">sends less code, picks the right model, costs less to run</p>
            </div>
            <span className="ml-auto shrink-0 text-xs font-semibold text-indigo-300 bg-indigo-800 border border-indigo-600 px-2 py-0.5 rounded-full">Layer 3</span>
          </div>
          <div className="rounded-xl border border-violet-400 bg-violet-900 px-6 py-4 flex items-center gap-4">
            <span className="text-2xl font-black text-violet-300">⬡</span>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold text-white">Workspace Starter</p>
              <p className="text-xs text-violet-300">shared team setup, shortcuts, and checks out of the box</p>
            </div>
            <span className="ml-auto shrink-0 text-xs font-semibold text-violet-300 bg-violet-800 border border-violet-600 px-2 py-0.5 rounded-full">Layers 1–5</span>
          </div>
          <div className="rounded-xl border border-amber-600 bg-amber-950 px-6 py-4 flex items-center gap-4">
            <span className="text-2xl font-black text-amber-400">≋</span>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold text-white">RTK — Rust Token Killer</p>
              <p className="text-xs text-amber-300">shrinks what the AI reads from your terminal, 60–90% less</p>
            </div>
            <span className="ml-auto shrink-0 text-xs font-semibold text-amber-300 bg-amber-900 border border-amber-700 px-2 py-0.5 rounded-full">Layer 2</span>
          </div>
          <div className="rounded-xl border border-teal-600 bg-teal-950 px-6 py-4 flex items-center gap-4">
            <span className="text-2xl font-black text-teal-400">⊙</span>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold text-white">Prompt Caching</p>
              <p className="text-xs text-teal-300">reuses what the AI already read — 90% cheaper on repeated context</p>
            </div>
            <span className="ml-auto shrink-0 text-xs font-semibold text-teal-300 bg-teal-900 border border-teal-700 px-2 py-0.5 rounded-full">Layer 1</span>
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
      <h2 className="text-2xl font-bold text-stone-900 mb-3">Start with the rules. Then speed things up.</h2>
      <p className="text-stone-500 text-sm mb-8 max-w-md mx-auto">
        Set your team&apos;s policies in Conduct. Then give your developers the tools to move fast within them.
      </p>
      <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
        <a href="/dashboard" className="inline-flex items-center gap-2 rounded-xl bg-red-600 px-6 py-3 text-sm font-semibold text-white hover:bg-red-700 transition-colors">
          Set up Guard →
        </a>
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
