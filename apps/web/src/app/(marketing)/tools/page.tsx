"use client"

export default function ToolsPage() {
  return (
    <div className="min-h-screen bg-white flex flex-col">
      <Nav />
      <main>
        <HeroSection />
        <ToolsSection />
        <GuardTogetherSection />
        <OnboardingSection />
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
        <a href="/marketplace" className="flex items-center gap-1.5 text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">Agent Templates</a>
        <div className="relative group">
          <a href="/tools" className="flex items-center gap-1 text-sm font-medium text-indigo-600 hover:text-indigo-900 transition-colors">
            Tools
            <svg width="12" height="12" viewBox="0 0 12 12" fill="currentColor" className="opacity-50 mt-0.5"><path d="M2 4l4 4 4-4"/></svg>
          </a>
          <div className="absolute left-0 top-full pt-2 hidden group-hover:block z-50">
            <div className="bg-white border border-stone-200 rounded-xl shadow-lg py-1.5 min-w-[160px]">
              <a href="/tools/agent-booster" className="flex items-center gap-2 px-4 py-2 text-sm text-stone-700 hover:bg-stone-50 transition-colors">
                <span className="text-indigo-600 font-bold">◈</span> Agent Booster
              </a>
              <a href="/tools/conduct-cli" className="flex items-center gap-2 px-4 py-2 text-sm text-stone-700 hover:bg-stone-50 transition-colors">
                <span className="text-violet-600 font-bold">⬡</span> Conduct CLI
              </a>
              <a href="/tools/security-loop" className="flex items-center gap-2 px-4 py-2 text-sm text-stone-700 hover:bg-stone-50 transition-colors">
                <span className="text-rose-600 font-bold">🔐</span> Security Loop
              </a>
              <a href="/tools/session-report" className="flex items-center gap-2 px-4 py-2 text-sm text-stone-700 hover:bg-stone-50 transition-colors">
                <span className="text-amber-600 font-bold">📊</span> Session Report
              </a>
            </div>
          </div>
        </div>
        <a href="/sdd" className="flex items-center gap-1.5 text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">SDD</a>
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

        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-8">

          {/* Agent Booster */}
          <div className="rounded-2xl border border-stone-200 bg-white px-8 py-8 flex flex-col gap-5 hover:border-indigo-200 hover:shadow-sm transition-all">
            <div className="flex items-start justify-between">
              <div>
                <span className="inline-flex items-center gap-1.5 text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-100 px-2.5 py-1 rounded-full mb-3">
                  v0.2.25 · PyPI
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

            <a href="/tools/agent-booster" className="block rounded-xl border border-stone-200 bg-stone-50 p-1.5 hover:border-indigo-200 transition-colors">
              <img
                src="/tools/agent-booster-demo.gif"
                alt="Agent Booster CLI demo: booster init claude then booster gain showing token savings"
                className="w-full rounded-lg"
                loading="lazy"
              />
            </a>

            <div className="flex flex-col gap-2">
              <p className="text-xs font-bold text-stone-400 uppercase tracking-widest">What it does</p>
              <ul className="space-y-1.5">
                {[
                  "Sends only the relevant code — not the whole file",
                  "Finds the right code by meaning, not just keywords",
                  "Picks the cheapest model that can handle the task",
                  "booster verbosity: cuts output tokens 30–75% across Claude Code, Cursor, Codex",
                  "booster compress: shrinks memory files via haiku — keeps context lean",
                  "booster gain: shows real input + output savings from actual session data",
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

          {/* Conduct CLI */}
          <div className="rounded-2xl border border-stone-200 bg-white px-8 py-8 flex flex-col gap-5 hover:border-violet-200 hover:shadow-sm transition-all">
            <div className="flex items-start justify-between">
              <div>
                <span className="inline-flex items-center gap-1.5 text-xs font-semibold bg-violet-50 text-violet-700 border border-violet-100 px-2.5 py-1 rounded-full mb-3">
                  v0.4.93 · PyPI
                </span>
                <h2 className="text-2xl font-bold text-stone-900">Conduct CLI</h2>
                <p className="text-sm text-stone-500 mt-1">Run agents. Enforce policies. Switch workspaces.</p>
              </div>
              <span className="text-3xl font-black text-violet-600">⬡</span>
            </div>

            <p className="text-sm text-stone-600 leading-relaxed">
              The daily driver for Conduct users. Run agents from the terminal, switch workspaces in one command,
              and enforce AI usage policies across the team with ConductGuard MCP — every tool call Claude makes
              passes through Guard first.
            </p>

            <a href="/tools/conduct-cli" className="block rounded-xl border border-stone-200 bg-stone-50 p-1.5 hover:border-violet-200 transition-colors">
              <img
                src="/tools/conduct-cli-demo.gif"
                alt="Conduct CLI demo: whoami, switch workspaces with Guard policy sync, and run an agent"
                className="w-full rounded-lg"
                loading="lazy"
              />
            </a>

            <div className="flex flex-col gap-2">
              <p className="text-xs font-bold text-stone-400 uppercase tracking-widest">What it does</p>
              <ul className="space-y-1.5">
                {[
                  "Run any agent from the terminal — picks up the right context automatically",
                  "conduct switch: swap workspaces + re-sync policies atomically",
                  "ConductGuard MCP enforces team AI policies on every tool call",
                  "conduct whoami: instant view of workspace, Guard, and Booster status",
                  "Preflight: shows actual files and realistic turn estimates before a run",
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
                href="/tools/conduct-cli"
                className="inline-flex items-center gap-1.5 rounded-lg bg-violet-600 px-4 py-2 text-sm font-semibold text-white hover:bg-violet-700 transition-colors"
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
              <code className="font-mono text-xs text-stone-400 bg-stone-50 px-2 py-1 rounded">pip install conduct-cli</code>
            </div>
          </div>

          {/* Security Loop */}
          <div className="rounded-2xl border border-stone-200 bg-white px-8 py-8 flex flex-col gap-5 hover:border-indigo-200 hover:shadow-sm transition-all">
            <div className="flex items-start justify-between">
              <div>
                <span className="inline-flex items-center gap-1.5 text-xs font-semibold bg-rose-50 text-rose-700 border border-rose-100 px-2.5 py-1 rounded-full mb-3">
                  v0.4 · Shipped
                </span>
                <h2 className="text-2xl font-bold text-stone-900">Security Loop</h2>
                <p className="text-sm text-stone-500 mt-1">Finding to PR, automatically</p>
              </div>
              <span className="text-3xl font-black text-indigo-600">🔐</span>
            </div>

            <p className="text-sm text-stone-600 leading-relaxed">
              Connect Claude Code, Codex, Cursor, or Windsurf to Conduct once. Every vulnerability
              they surface gets captured automatically, triaged, and routed through a fix pipeline —
              GitHub issue, agent fix, PR, Slack alert, full audit trail.
            </p>

            <div className="flex flex-col gap-2">
              <p className="text-xs font-bold text-stone-400 uppercase tracking-widest">What it does</p>
              <ul className="space-y-1.5">
                {[
                  "Passive hook captures findings from every tool call — zero developer action",
                  "BugHunter Active Scan runs 8 targeted hunt skills on demand",
                  "GitHub issue created with severity, labels, and suggested fix",
                  "Fix agent branches, patches, and opens a PR — you review, you merge",
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
                href="/tools/security-loop"
                className="inline-flex items-center gap-1.5 rounded-lg bg-rose-600 px-4 py-2 text-sm font-semibold text-white hover:bg-rose-700 transition-colors"
              >
                Learn more →
              </a>
              <a
                href="/secure"
                className="inline-flex items-center gap-1.5 rounded-lg border border-stone-200 px-4 py-2 text-sm font-medium text-stone-600 hover:border-stone-300 transition-colors"
              >
                Open Security console →
              </a>
            </div>
          </div>

          {/* Session Report */}
          <div className="rounded-2xl border border-stone-200 bg-white px-8 py-8 flex flex-col gap-5 hover:border-amber-200 hover:shadow-sm transition-all">
            <div className="flex items-start justify-between">
              <div>
                <span className="inline-flex items-center gap-1.5 text-xs font-semibold bg-amber-50 text-amber-700 border border-amber-100 px-2.5 py-1 rounded-full mb-3">
                  v0.4.68 · New
                </span>
                <h2 className="text-2xl font-bold text-stone-900">Session Report</h2>
                <p className="text-sm text-stone-500 mt-1">Dev profile from your AI coding sessions</p>
              </div>
              <span className="text-3xl font-black text-amber-600">📊</span>
            </div>

            <p className="text-sm text-stone-600 leading-relaxed">
              Run one command. Conduct analyses your local Claude Code transcripts using paxel,
              builds your builder profile — archetype, competency scores, signature moves —
              and sends the report straight to your admin. No data leaves your machine until you hit send.
            </p>

            <div className="flex flex-col gap-2">
              <p className="text-xs font-bold text-stone-400 uppercase tracking-widest">What it does</p>
              <ul className="space-y-1.5">
                {[
                  "Analyses local ~/.claude/projects transcripts — fully offline",
                  "Computes builder archetype: Execution · Planning · Engineering scores",
                  "Sends a formatted report to your admin via Slack",
                  "No install needed — paxel downloads on first run",
                ].map(item => (
                  <li key={item} className="flex items-start gap-2 text-sm text-stone-600">
                    <span className="text-amber-500 mt-0.5 shrink-0">✓</span>
                    {item}
                  </li>
                ))}
              </ul>
            </div>

            <div className="mt-auto pt-4 border-t border-stone-100 flex items-center gap-3 flex-wrap">
              <code className="font-mono text-xs bg-stone-900 text-emerald-400 px-3 py-1.5 rounded-lg">conduct session-report</code>
              <code className="font-mono text-xs text-stone-400 bg-stone-50 px-2 py-1 rounded">pip install conduct-cli==0.4.72</code>
            </div>
          </div>

          {/* Claude Code Team Kit */}
          <div className="rounded-2xl border border-stone-200 bg-white px-8 py-8 flex flex-col gap-5 hover:border-violet-200 hover:shadow-sm transition-all">
            <div className="flex items-start justify-between">
              <div>
                <span className="inline-flex items-center gap-1.5 text-xs font-semibold bg-violet-50 text-violet-700 border border-violet-100 px-2.5 py-1 rounded-full mb-3">
                  Free · MIT
                </span>
                <h2 className="text-2xl font-bold text-stone-900">Claude Code Team Kit</h2>
                <p className="text-sm text-stone-500 mt-1">Shared Claude Code setup for your whole team</p>
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
                href="https://github.com/sseshachala/claude-code-team-kit"
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

/* ─── Guard + Tools Together ────────────────────────────────────────────── */

function GuardTogetherSection() {
  return (
    <section className="bg-stone-900 px-6 py-20">
      <div className="max-w-5xl mx-auto">
        <div className="text-center mb-14">
          <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-3">Guard + tools together</p>
          <h2 className="text-3xl font-bold text-white mb-4">
            Ship AI at scale — without blowing<br />your budget or hitting rate limits.
          </h2>
          <p className="text-stone-400 text-sm max-w-2xl mx-auto leading-relaxed">
            Guard gives your team lead one place to set the rules — how much any developer can spend,
            which actions are off limits, which AI tools are approved. These tools make sure every
            developer runs as efficiently as possible within those rules. The combination means your
            team can run dozens of AI workflows a day without budget surprises or rate limit failures.
          </p>
        </div>

        <div className="grid sm:grid-cols-2 gap-5 mb-10">
          {[
            {
              guard: "Guard sets a spend limit per developer per day",
              tool: "Agent Booster cuts per-request cost by up to 15×",
              outcome: "The same budget covers 10× more workflow runs — every developer stays inside the limit without thinking about it.",
              color: "border-indigo-500",
              toolColor: "text-indigo-300",
            },
            {
              guard: "Guard blocks unapproved AI tools team-wide",
              tool: "Claude Code Team Kit makes approved tools the default for everyone",
              outcome: "Developers get a ready-to-go setup that already matches Guard's approved tool list — zero friction, zero policy violations.",
              color: "border-violet-500",
              toolColor: "text-violet-300",
            },
            {
              guard: "Guard logs every AI action across the whole team",
              tool: "RTK shrinks what the AI reads — 60–90% fewer tokens per run",
              outcome: "Fewer tokens means less to log, less rate limit pressure, and a cleaner audit trail — every run is faster and cheaper.",
              color: "border-amber-500",
              toolColor: "text-amber-300",
            },
            {
              guard: "Guard pushes approved model tiers to every workflow",
              tool: "Agent Booster routes each task to the cheapest model that works",
              outcome: "Guard sets the ceiling. Agent Booster makes sure you never pay for a more expensive model than the task needs.",
              color: "border-teal-500",
              toolColor: "text-teal-300",
            },
            {
              guard: "Guard wires PreCompact + SessionStart hooks into Claude Code",
              tool: "Agent Booster uses RRF fusion — vector + keyword ranks merged for every search",
              outcome: "Session context (budget, branch, policies) survives conversation compaction. Searches return better symbol matches by combining two ranking strategies automatically.",
              color: "border-emerald-500",
              toolColor: "text-emerald-300",
            },
          ].map(({ guard, tool, outcome, color, toolColor }) => (
            <div key={guard} className={`rounded-2xl border ${color} bg-stone-800 p-6 flex flex-col gap-4`}>
              <div className="flex flex-col gap-2">
                <div className="flex items-start gap-2">
                  <span className="shrink-0 mt-0.5 w-4 h-4 rounded-full bg-red-900 border border-red-600 flex items-center justify-center">
                    <span className="text-[8px] text-red-300 font-bold">G</span>
                  </span>
                  <p className="text-xs text-stone-300 leading-relaxed">{guard}</p>
                </div>
                <div className="flex items-start gap-2">
                  <span className="shrink-0 mt-0.5 w-4 h-4 rounded-full bg-stone-700 border border-stone-500 flex items-center justify-center">
                    <span className="text-[8px] text-stone-300 font-bold">T</span>
                  </span>
                  <p className={`text-xs leading-relaxed ${toolColor}`}>{tool}</p>
                </div>
              </div>
              <div className="border-t border-stone-700 pt-4">
                <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-1.5">Result</p>
                <p className="text-sm text-white leading-relaxed">{outcome}</p>
              </div>
            </div>
          ))}
        </div>

        <div className="rounded-2xl border border-stone-600 bg-stone-800 px-8 py-6 flex flex-col sm:flex-row items-center gap-6 text-center sm:text-left">
          <div className="flex-1">
            <p className="text-white font-semibold mb-1">Ready to set this up for your team?</p>
            <p className="text-stone-400 text-sm">
              Start with Guard in Conduct — set your team&apos;s policies in minutes.
              Then give your developers these tools and they&apos;ll stay under budget automatically.
            </p>
          </div>
          <div className="flex flex-col sm:flex-row gap-3 shrink-0">
            <a href="/dashboard" className="inline-flex items-center gap-2 rounded-xl bg-white text-stone-900 px-5 py-2.5 text-sm font-semibold hover:bg-stone-100 transition-colors">
              Set up Guard →
            </a>
            <a href="/tools/agent-booster" className="inline-flex items-center gap-2 rounded-xl border border-stone-600 text-stone-300 px-5 py-2.5 text-sm font-semibold hover:border-stone-400 hover:text-white transition-colors">
              Agent Booster docs →
            </a>
          </div>
        </div>
      </div>
    </section>
  )
}

/* ─── Onboarding ────────────────────────────────────────────────────────── */

function OnboardingSection() {
  return (
    <section className="px-6 py-20 bg-stone-50">
      <div className="max-w-5xl mx-auto">
        <div className="text-center mb-14">
          <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-3">How to get started</p>
          <h2 className="text-3xl font-bold text-stone-900 mb-4">
            Three steps. Three minutes.<br />Your whole team, in sync.
          </h2>
          <p className="text-stone-500 text-sm max-w-xl mx-auto leading-relaxed">
            One person sets the rules. Everyone else joins with a single command.
            The tools stay in sync automatically.
          </p>
        </div>

        <div className="grid sm:grid-cols-3 gap-6 mb-10">

          {/* Step 1 — Manager */}
          <div className="relative bg-white rounded-2xl border border-stone-200 p-7 flex flex-col gap-4">
            <div className="flex items-center justify-between mb-1">
              <span className="inline-flex items-center gap-1.5 text-[10px] font-bold text-red-700 bg-red-50 border border-red-100 px-2.5 py-1 rounded-full uppercase tracking-widest">
                Team lead
              </span>
              <span className="text-xs font-bold text-stone-300">Step 1</span>
            </div>
            <div>
              <p className="text-lg font-bold text-stone-900 mb-2">Set the policies</p>
              <p className="text-sm text-stone-500 leading-relaxed">
                Log into Conduct, open Guard, and configure your team&apos;s rules —
                daily spend limit, approved AI tools, blocked actions.
                Takes about five minutes. Only needs to happen once.
              </p>
            </div>
            <ul className="space-y-1.5 mt-auto">
              {[
                "Set daily spend limit per developer",
                "Choose approved AI tools for the team",
                "Block risky actions across all workflows",
                "Invite team members by email",
              ].map(item => (
                <li key={item} className="flex items-start gap-2 text-xs text-stone-500">
                  <span className="text-red-400 mt-0.5 shrink-0">✓</span>
                  {item}
                </li>
              ))}
            </ul>
            <div className="mt-4 pt-4 border-t border-stone-100">
              <a href="/dashboard" className="inline-flex items-center gap-1.5 text-xs font-semibold text-red-700 hover:text-red-900 transition-colors">
                Open Conduct → Guard →
              </a>
            </div>
          </div>

          {/* Step 2 — Developer */}
          <div className="relative bg-white rounded-2xl border border-stone-200 p-7 flex flex-col gap-4">
            <div className="flex items-center justify-between mb-1">
              <span className="inline-flex items-center gap-1.5 text-[10px] font-bold text-indigo-700 bg-indigo-50 border border-indigo-100 px-2.5 py-1 rounded-full uppercase tracking-widest">
                Developer
              </span>
              <span className="text-xs font-bold text-stone-300">Step 2</span>
            </div>
            <div>
              <p className="text-lg font-bold text-stone-900 mb-2">Join and pull policies</p>
              <p className="text-sm text-stone-500 leading-relaxed">
                Accept the invite, run one command. Conduct downloads
                your team&apos;s Guard policies and applies them to your local
                environment automatically. Nothing to configure manually.
              </p>
            </div>
            <div className="mt-auto bg-stone-950 rounded-xl px-4 py-3 font-mono text-xs">
              <p className="text-stone-500 mb-1"># One command to join</p>
              <p className="text-emerald-400">conduct guard join</p>
              <p className="text-stone-500 mt-2 mb-1"># Policies pulled automatically</p>
              <p className="text-white">✓ spend limit applied</p>
              <p className="text-white">✓ approved tools configured</p>
              <p className="text-white">✓ blocked actions enforced</p>
            </div>
          </div>

          {/* Step 3 — Tools sync */}
          <div className="relative bg-white rounded-2xl border border-stone-200 p-7 flex flex-col gap-4">
            <div className="flex items-center justify-between mb-1">
              <div className="flex items-center gap-2">
                <span className="inline-flex items-center gap-1.5 text-[10px] font-bold text-violet-700 bg-violet-50 border border-violet-100 px-2.5 py-1 rounded-full uppercase tracking-widest">
                  Tools
                </span>
                <span className="inline-flex items-center gap-1 text-[9px] font-bold text-amber-700 bg-amber-50 border border-amber-100 px-2 py-0.5 rounded-full uppercase tracking-widest">
                  Coming soon
                </span>
              </div>
              <span className="text-xs font-bold text-stone-300">Step 3</span>
            </div>
            <div>
              <p className="text-lg font-bold text-stone-900 mb-2">Tools stay in sync</p>
              <p className="text-sm text-stone-500 leading-relaxed">
                Agent Booster and other tools will optionally connect to
                the Guard policy server. When the team lead updates a rule,
                it propagates to every developer&apos;s tools automatically —
                no one needs to reconfigure anything.
              </p>
            </div>
            <ul className="space-y-1.5 mt-auto">
              {[
                "Agent Booster respects spend limits automatically",
                "Model routing follows Guard's approved tiers",
                "Policy updates propagate in under 60 seconds",
                "No manual reconfiguration for developers",
              ].map(item => (
                <li key={item} className="flex items-start gap-2 text-xs text-stone-400">
                  <span className="text-stone-300 mt-0.5 shrink-0">◦</span>
                  {item}
                </li>
              ))}
            </ul>
            <div className="mt-4 pt-4 border-t border-stone-100">
              <p className="text-xs text-stone-400">Today: join + pull works. Tool sync on the roadmap.</p>
            </div>
          </div>

        </div>

        {/* Change propagation callout */}
        <div className="rounded-2xl border border-indigo-100 bg-indigo-50 px-8 py-6 flex flex-col sm:flex-row items-center gap-6">
          <div className="text-3xl shrink-0">🔄</div>
          <div className="flex-1">
            <p className="font-semibold text-stone-900 mb-1">Change a rule once. It updates everywhere.</p>
            <p className="text-sm text-stone-500 leading-relaxed">
              When the team lead lowers the spend limit or adds a new blocked action,
              every developer gets the update the next time they sync — no Slack messages,
              no manual steps, no one left on an old policy.
            </p>
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
          href="https://github.com/sseshachala/claude-code-team-kit"
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-2 rounded-xl border border-stone-200 bg-white px-6 py-3 text-sm font-semibold text-stone-700 hover:border-stone-300 hover:shadow-sm transition-all"
        >
          <GitHubIcon />
          Claude Code Team Kit
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
        <a href="/marketplace" className="hover:text-stone-600 transition-colors">Agent Templates</a>
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
