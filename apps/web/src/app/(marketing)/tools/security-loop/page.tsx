"use client"

export default function SecurityLoopPage() {
  return (
    <div className="min-h-screen bg-white flex flex-col">
      <Nav />
      <main>
        <HeroSection />
        <ProblemSection />
        <HowItWorksSection />
        <EntryPointsSection />
        <SetupSection />
        <FeaturesSection />
        <SafetySection />
        <AuditSection />
        <FooterCTASection />
      </main>
      <PageFooter />
    </div>
  )
}

/* ─── Nav ──────────────────────────────────────────────────────────────── */

function ProductsDropdown() {
  return (
    <div className="relative group">
      <a href="/sign-up" className="flex items-center gap-1 text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">
        Products
        <svg width="12" height="12" viewBox="0 0 12 12" fill="currentColor" className="opacity-40 mt-0.5"><path d="M2 4l4 4 4-4"/></svg>
      </a>
      <div className="absolute left-0 top-full pt-2 hidden group-hover:block z-50 min-w-[220px]">
        <div className="bg-white border border-stone-200 rounded-xl shadow-lg py-2">
          <a href="/guard-landing" className="flex items-center gap-3 px-4 py-2.5 text-sm text-stone-700 hover:bg-stone-50 transition-colors">
            <span>🛡️</span>
            <div>
              <p className="font-semibold">Conduct Guard</p>
              <p className="text-xs text-stone-400">AI session governance</p>
            </div>
          </a>
          <a href="/tools/security-loop" className="flex items-center gap-3 px-4 py-2.5 text-sm text-stone-700 hover:bg-stone-50 transition-colors">
            <span>🔒</span>
            <div>
              <p className="font-semibold">Security Loop</p>
              <p className="text-xs text-stone-400">Automated PR scanning</p>
            </div>
          </a>
          <a href="/playbooks" className="flex items-center gap-3 px-4 py-2.5 text-sm text-stone-700 hover:bg-stone-50 transition-colors">
            <span>⚡</span>
            <div>
              <p className="font-semibold">Playbooks</p>
              <p className="text-xs text-stone-400">Pre-built AI automations</p>
            </div>
          </a>
          <a href="/tools/conduct-cli" className="flex items-center gap-3 px-4 py-2.5 text-sm text-stone-700 hover:bg-stone-50 transition-colors">
            <span className="text-indigo-600 font-bold text-base">◈</span>
            <div>
              <p className="font-semibold">Conduct CLI</p>
              <p className="text-xs text-stone-400">Terminal governance + token savings</p>
            </div>
          </a>
        </div>
      </div>
    </div>
  )
}

function Nav() {
  return (
    <header className="px-6 py-4 flex items-center justify-between max-w-6xl mx-auto w-full sticky top-0 bg-white/95 backdrop-blur-sm z-50 border-b border-stone-100">
      <a href="/">
        <img src="/logo.png" alt="Conduct AI" className="h-10 w-auto" />
      </a>
      <nav className="hidden md:flex items-center gap-6">
        <ProductsDropdown />
        <a href="/playbooks" className="text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">Playbooks</a>
        <a href="/blog" className="text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">Blog</a>
        <a href="/docs" className="text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">Docs</a>
        <a href="https://pypi.org/project/conduct-cli/" target="_blank" rel="noopener noreferrer" className="text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">PyPI</a>
      </nav>
      <div className="flex items-center gap-3">
        <a href="mailto:hello@conductai.ai" className="text-sm font-medium text-stone-600 hover:text-stone-900 transition-colors hidden sm:block">Talk to Us</a>
        <a href="/sign-up" className="rounded-lg bg-stone-900 text-white px-4 py-2 text-sm font-semibold hover:bg-stone-700 transition-colors">
          Start Free
        </a>
      </div>
    </header>
  )
}

/* ─── Hero ─────────────────────────────────────────────────────────────── */

function HeroSection() {
  return (
    <section className="flex flex-col items-center justify-center px-6 pt-16 pb-24 text-center">
      <div className="inline-flex items-center gap-2 bg-rose-50 text-rose-700 border border-rose-100 text-xs font-semibold px-3 py-1.5 rounded-full mb-8 uppercase tracking-widest">
        Security Loop · v0.4 · Shipped
      </div>

      <h1 className="text-5xl sm:text-6xl font-bold text-stone-900 leading-[1.1] tracking-tight max-w-3xl">
        AI finds the bug. Conduct{" "}
        <span className="text-rose-600">closes the loop.</span>
      </h1>

      <p className="mt-6 text-xl text-stone-500 max-w-2xl leading-relaxed">
        Connect Claude Code, Codex, Cursor, or Windsurf once. Every vulnerability they surface
        gets automatically captured, triaged, fixed on a branch, and shipped as a PR —
        with a full audit trail.
      </p>

      <div className="mt-10 flex flex-col sm:flex-row items-center gap-4">
        <a
          href="/secure"
          className="inline-flex items-center gap-2 rounded-xl bg-rose-600 px-6 py-3 text-sm font-semibold text-white hover:bg-rose-700 transition-colors"
        >
          Open Security console →
        </a>
        <a
          href="#how-it-works"
          className="inline-flex items-center gap-2 rounded-xl border border-stone-200 bg-white px-6 py-3 text-sm font-semibold text-stone-700 hover:border-stone-300 hover:shadow-sm transition-all"
        >
          See how it works →
        </a>
      </div>

      <div className="mt-10 flex items-center gap-6 flex-wrap justify-center">
        {["Claude Code", "Codex", "Cursor", "Windsurf"].map(tool => (
          <span key={tool} className="inline-flex items-center gap-1.5 text-xs font-medium text-stone-500 bg-stone-50 border border-stone-200 px-3 py-1.5 rounded-full">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 shrink-0" />
            {tool}
          </span>
        ))}
      </div>
    </section>
  )
}

/* ─── Problem ──────────────────────────────────────────────────────────── */

const PAIN_CARDS = [
  {
    icon: "🔍",
    title: "Findings disappear",
    desc: "Claude Code prints to terminal. Codex surfaces inline. Cursor shows suggestions. None of them route findings anywhere. A vulnerability found Thursday afternoon may never become a ticket.",
    border: "border-red-100",
  },
  {
    icon: "🧩",
    title: "No standard pipeline",
    desc: "Every tool has its own output format. Your team stitches together findings manually — if at all. There's no consistent triage, no severity tracking, no audit trail.",
    border: "border-amber-100",
  },
  {
    icon: "⏱️",
    title: "Detection ≠ remediation",
    desc: "Finding a bug is 10% of the work. The other 90% — issue creation, triage, fix, PR, review — still happens manually. Mean time to fix stays in days.",
    border: "border-orange-100",
  },
]

function ProblemSection() {
  return (
    <section className="bg-stone-50 px-6 py-20">
      <div className="max-w-5xl mx-auto">
        <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest text-center mb-3">The problem</p>
        <h2 className="text-3xl font-bold text-stone-900 text-center mb-4">The gap no one closes.</h2>
        <p className="text-center text-stone-500 text-sm max-w-2xl mx-auto mb-12">
          AI coding tools are getting better at finding vulnerabilities. But there&apos;s still no
          standard way to route those findings into a fix pipeline. They fall through the cracks.
        </p>

        <div className="grid sm:grid-cols-3 gap-6">
          {PAIN_CARDS.map(card => (
            <div key={card.title} className={`rounded-2xl border ${card.border} bg-white px-7 py-7 flex flex-col gap-4`}>
              <span className="text-3xl">{card.icon}</span>
              <div>
                <h3 className="text-base font-semibold text-stone-900 mb-2">{card.title}</h3>
                <p className="text-sm text-stone-500 leading-relaxed">{card.desc}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

/* ─── How it works ─────────────────────────────────────────────────────── */

const PIPELINE_STEPS = [
  { n: "1", title: "Finding captured", desc: "Passive hook or BugHunter Active Scan surfaces a vulnerability", icon: "◈", color: "text-rose-600", bg: "bg-rose-50 border-rose-200" },
  { n: "2", title: "Classify", desc: "Severity, type, file, and line number recorded automatically", icon: "≋", color: "text-violet-600", bg: "bg-violet-50 border-violet-200" },
  { n: "3", title: "Slack alert", desc: "Instant notification to your #security channel with full context", icon: "◉", color: "text-blue-600", bg: "bg-blue-50 border-blue-200" },
  { n: "4", title: "GitHub issue", desc: "Issue created with severity label, structured body, and suggested fix", icon: "◎", color: "text-teal-600", bg: "bg-teal-50 border-teal-200" },
  { n: "5", title: "Validate", desc: "Security scanner confirms the finding before any fix runs", icon: "⊙", color: "text-emerald-600", bg: "bg-emerald-50 border-emerald-200" },
  { n: "6", title: "Fix on branch", desc: "Agent forks the repo and applies the fix on a dedicated branch", icon: "⟁", color: "text-amber-600", bg: "bg-amber-50 border-amber-200" },
  { n: "7", title: "PR opened", desc: "Pull request opened back to the repo, ready for your review", icon: "◭", color: "text-orange-600", bg: "bg-orange-50 border-orange-200" },
  { n: "8", title: "Audit trail", desc: "Tool → finding → fix → PR → cost → duration, all recorded", icon: "⬡", color: "text-stone-600", bg: "bg-stone-50 border-stone-200" },
]

function HowItWorksSection() {
  return (
    <section id="how-it-works" className="px-6 py-20">
      <div className="max-w-6xl mx-auto">
        <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest text-center mb-3">How it works</p>
        <h2 className="text-3xl font-bold text-stone-900 text-center mb-12">From finding to PR — automatically.</h2>

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          {PIPELINE_STEPS.map((step) => (
            <div key={step.n} className={`rounded-2xl border ${step.bg} px-4 py-5 flex flex-col items-center text-center gap-3`}>
              <span className={`text-2xl font-black ${step.color}`}>{step.icon}</span>
              <div>
                <p className="text-[10px] font-bold text-stone-400 uppercase tracking-widest mb-1">Step {step.n}</p>
                <p className="text-sm font-semibold text-stone-900 mb-1">{step.title}</p>
                <p className="text-xs text-stone-500 leading-relaxed">{step.desc}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

/* ─── Entry Points ─────────────────────────────────────────────────────── */

function EntryPointsSection() {
  return (
    <section className="bg-stone-50 px-6 py-20">
      <div className="max-w-5xl mx-auto">
        <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest text-center mb-3">Three ways to feed it</p>
        <h2 className="text-3xl font-bold text-stone-900 text-center mb-4">One feed, three entry points.</h2>
        <p className="text-center text-stone-500 text-sm max-w-2xl mx-auto mb-12">
          However your team surfaces findings — passively via hooks, actively via BugHunter, or manually from
          the CLI — everything lands in the same security feed with the same audit trail.
        </p>

        <div className="grid sm:grid-cols-3 gap-6">
          {/* Passive */}
          <div className="rounded-2xl border border-emerald-200 bg-white px-7 py-7 flex flex-col gap-4">
            <div className="flex items-center gap-3">
              <span className="w-8 h-8 rounded-lg bg-emerald-50 border border-emerald-200 flex items-center justify-center text-sm font-bold text-emerald-700">P</span>
              <div>
                <p className="text-xs font-bold text-stone-400 uppercase tracking-widest">Always on</p>
                <h3 className="text-base font-semibold text-stone-900">Passive hook</h3>
              </div>
            </div>
            <p className="text-sm text-stone-500 leading-relaxed">
              Guard&apos;s PostToolUse hook classifies every AI tool response in the background.
              Secrets, path traversal, injection patterns, OWASP keywords — caught automatically
              with zero developer action.
            </p>
            <div className="rounded-xl bg-stone-950 px-4 py-3 font-mono text-xs mt-auto">
              <p className="text-stone-500 mb-1"># Enable once in Guard settings</p>
              <p className="text-emerald-400">Security Emit → ON</p>
              <p className="text-stone-400 mt-2">Every tool call classified automatically</p>
            </div>
            <div className="flex flex-wrap gap-2">
              {["sk-* keys", "AKIA* keys", "eval(", "verify=False", "SQL injection", "XSS"].map(p => (
                <span key={p} className="text-[10px] font-mono bg-stone-100 text-stone-600 px-2 py-0.5 rounded">{p}</span>
              ))}
            </div>
          </div>

          {/* BugHunter */}
          <div className="rounded-2xl border border-violet-200 bg-white px-7 py-7 flex flex-col gap-4">
            <div className="flex items-center gap-3">
              <span className="w-8 h-8 rounded-lg bg-violet-50 border border-violet-200 flex items-center justify-center text-sm font-bold text-violet-700">A</span>
              <div>
                <p className="text-xs font-bold text-stone-400 uppercase tracking-widest">On demand</p>
                <h3 className="text-base font-semibold text-stone-900">BugHunter Active Scan</h3>
              </div>
            </div>
            <p className="text-sm text-stone-500 leading-relaxed">
              Install the BugHunter playbook from Marketplace and point it at any repo.
              8 targeted hunt skills run — LLM injection, JWT confusion, SSRF, supply chain,
              race conditions, and more. Findings flow straight into the security feed.
            </p>
            <div className="rounded-xl bg-stone-950 px-4 py-3 font-mono text-xs mt-auto">
              <p className="text-stone-500 mb-1"># Run from CLI or canvas</p>
              <p className="text-violet-400">conduct run &quot;BugHunter Active Scan&quot; \</p>
              <p className="text-violet-400">  --input target_repo=owner/repo</p>
            </div>
            <div className="flex flex-wrap gap-2">
              {["hunt-llm-injection", "hunt-jwt-confusion", "hunt-ssrf-cloud", "hunt-supply-chain"].map(s => (
                <span key={s} className="text-[10px] font-mono bg-violet-50 text-violet-700 border border-violet-100 px-2 py-0.5 rounded">{s}</span>
              ))}
            </div>
          </div>

          {/* Manual */}
          <div className="rounded-2xl border border-stone-200 bg-white px-7 py-7 flex flex-col gap-4">
            <div className="flex items-center gap-3">
              <span className="w-8 h-8 rounded-lg bg-stone-50 border border-stone-200 flex items-center justify-center text-sm font-bold text-stone-600">M</span>
              <div>
                <p className="text-xs font-bold text-stone-400 uppercase tracking-widest">Power user</p>
                <h3 className="text-base font-semibold text-stone-900">CLI emit</h3>
              </div>
            </div>
            <p className="text-sm text-stone-500 leading-relaxed">
              Pipe any tool output through the fast-path classifier directly from your terminal.
              Useful for custom scripts, CI pipelines, or one-off scans outside the normal flow.
            </p>
            <div className="rounded-xl bg-stone-950 px-4 py-3 font-mono text-xs mt-auto">
              <p className="text-stone-500 mb-1"># Pipe output from any source</p>
              <p className="text-stone-400">cat scan-output.json | \</p>
              <p className="text-emerald-400">  conduct emit finding --from-stdin</p>
            </div>
            <p className="text-xs text-stone-400 mt-1">Works with any tool output. Normalised before storage.</p>
          </div>
        </div>
      </div>
    </section>
  )
}

/* ─── Setup ────────────────────────────────────────────────────────────── */

function SetupSection() {
  return (
    <section className="px-6 py-20">
      <div className="max-w-4xl mx-auto">
        <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest text-center mb-3">Get started</p>
        <h2 className="text-3xl font-bold text-stone-900 text-center mb-4">Three steps to full coverage.</h2>
        <p className="text-center text-stone-500 text-sm max-w-xl mx-auto mb-12">
          Works with your existing Conduct + ConductGuard setup. No new tools to install.
        </p>

        <div className="flex flex-col gap-4">
          {[
            {
              step: "1",
              title: "Install the Conduct CLI and log in",
              code: ["pip install conduct-cli", "conduct login"],
              desc: "Wires Guard hooks into Claude Code and Codex automatically. Token tracking, policy enforcement, and the security classifier all start running immediately.",
              color: "border-rose-200 bg-rose-50",
              textColor: "text-rose-700",
            },
            {
              step: "2",
              title: "Enable Security Emit in Guard settings",
              code: ["Guard settings → Security → Security Emit → ON", "Security Slack Alerts → ON  (optional)"],
              desc: "Turns on the passive classifier. Every tool call response is scanned in the background — findings POST to /security-findings automatically.",
              color: "border-violet-200 bg-violet-50",
              textColor: "text-violet-700",
            },
            {
              step: "3",
              title: "Install BugHunter from Marketplace (optional)",
              code: ["Marketplace → Agent Templates → BugHunter Active Scan → Install"],
              desc: "Adds on-demand deep scanning on top of the always-on passive hook. Run it against any repo whenever you want a full sweep.",
              color: "border-emerald-200 bg-emerald-50",
              textColor: "text-emerald-700",
            },
          ].map(({ step, title, code, desc, color, textColor }) => (
            <div key={step} className={`rounded-2xl border ${color} px-8 py-6 flex flex-col sm:flex-row gap-6`}>
              <div className="flex items-start gap-4 flex-1">
                <span className={`text-2xl font-black ${textColor} shrink-0 mt-0.5`}>{step}</span>
                <div className="flex-1">
                  <h3 className="text-base font-semibold text-stone-900 mb-2">{title}</h3>
                  <p className="text-sm text-stone-500 leading-relaxed mb-3">{desc}</p>
                </div>
              </div>
              <div className="rounded-xl bg-stone-950 px-5 py-4 font-mono text-xs shrink-0 sm:w-80">
                {code.map((line, i) => (
                  <p key={i} className={i === 0 ? "text-emerald-400" : "text-stone-400 mt-1.5"}>{line}</p>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

/* ─── Features ─────────────────────────────────────────────────────────── */

const FEATURE_CARDS = [
  {
    title: "Zero-drop coverage",
    desc: "Every finding from every AI tool enters the same pipeline. Nothing gets lost in terminal output.",
    icon: "◎",
    color: "text-rose-600",
    bg: "bg-rose-50 border-rose-200",
  },
  {
    title: "Tool-agnostic",
    desc: "Claude Code, Codex, Cursor, and Windsurf. One workspace, one audit trail, regardless of which tool found it.",
    icon: "⬡",
    color: "text-violet-600",
    bg: "bg-violet-50 border-violet-200",
  },
  {
    title: "Finding → PR in minutes",
    desc: "The fix pipeline runs automatically. You review a PR, not a backlog. Mean time to fix drops from days to minutes.",
    icon: "⟁",
    color: "text-emerald-600",
    bg: "bg-emerald-50 border-emerald-200",
  },
  {
    title: "Compliance-ready",
    desc: "Every finding has a traceable run with timestamps, approver identity, PR link, and cost. Exportable for SOC 2 and internal audits.",
    icon: "⊙",
    color: "text-amber-600",
    bg: "bg-amber-50 border-amber-200",
  },
]

function FeaturesSection() {
  return (
    <section className="bg-stone-50 px-6 py-20">
      <div className="max-w-5xl mx-auto">
        <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest text-center mb-3">What makes it different</p>
        <h2 className="text-3xl font-bold text-stone-900 text-center mb-4">Built to close the loop, not just find the bug.</h2>
        <p className="text-center text-stone-500 text-sm max-w-2xl mx-auto mb-12">
          Other tools surface findings. Security Loop routes them through a full remediation pipeline
          — automatically, with a complete audit trail at every step.
        </p>

        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-5">
          {FEATURE_CARDS.map(card => (
            <div key={card.title} className={`rounded-2xl border ${card.bg} px-6 py-6 flex flex-col gap-3`}>
              <span className={`text-2xl font-black ${card.color}`}>{card.icon}</span>
              <div>
                <h3 className="text-sm font-semibold text-stone-900 mb-2">{card.title}</h3>
                <p className="text-sm text-stone-600 leading-relaxed">{card.desc}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

/* ─── Safety ───────────────────────────────────────────────────────────── */

function SafetySection() {
  return (
    <section className="bg-stone-900 px-6 py-20">
      <div className="max-w-3xl mx-auto">
        <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest text-center mb-3">Human control</p>
        <h2 className="text-3xl font-bold text-white text-center mb-12">Humans stay in control.</h2>

        <div className="rounded-2xl border border-rose-400 bg-rose-950 px-8 py-8 flex flex-col gap-6">
          <p className="text-rose-100 text-sm leading-relaxed">
            Security Loop never merges code. Every finding surfaces as a draft agent — you review
            before anything runs. The agent opens the PR. Your team decides when to merge. Worst
            case is a PR that gets rejected. Nothing ships to main without a human.
          </p>

          <div className="rounded-xl bg-stone-950 px-6 py-5">
            <p className="text-[10px] font-bold text-stone-500 uppercase tracking-widest mb-3">Pipeline</p>
            <div className="flex flex-wrap items-center gap-2 font-mono text-xs">
              {[
                "Finding captured",
                "Draft agent created",
                "You click Run",
                "Fix applied",
                "PR opened",
                "You merge",
              ].map((step, idx, arr) => (
                <span key={step} className="flex items-center gap-2">
                  <span className="text-emerald-400">{step}</span>
                  {idx < arr.length - 1 && <span className="text-stone-600">→</span>}
                </span>
              ))}
            </div>
          </div>

          <div className="flex items-start gap-3 bg-rose-900 rounded-xl px-5 py-4 border border-rose-700">
            <span className="text-lg shrink-0">🔐</span>
            <p className="text-sm text-rose-200 leading-relaxed">
              The agent acts on your behalf only when you explicitly click Run. No autonomous
              code changes happen without your confirmation. Every action is logged.
            </p>
          </div>
        </div>
      </div>
    </section>
  )
}

/* ─── Audit ────────────────────────────────────────────────────────────── */

function AuditSection() {
  return (
    <section className="px-6 py-20">
      <div className="max-w-5xl mx-auto">
        <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest text-center mb-3">Compliance</p>
        <h2 className="text-3xl font-bold text-stone-900 text-center mb-4">Compliance evidence, built in.</h2>
        <p className="text-center text-stone-500 text-sm max-w-xl mx-auto mb-12">
          Every finding. Every fix. Every approver. Exportable for SOC&nbsp;2.
        </p>

        <div className="rounded-2xl border border-stone-200 bg-white overflow-hidden">
          <div className="px-6 py-4 bg-stone-50 border-b border-stone-200">
            <div className="grid grid-cols-8 gap-4">
              {["ID", "Agent", "Severity", "Repo", "Date", "Approver", "PR", "Status"].map(col => (
                <p key={col} className="text-[10px] font-bold text-stone-400 uppercase tracking-widest">{col}</p>
              ))}
            </div>
          </div>
          <div className="divide-y divide-stone-100">
            {[
              { id: "SL-001", agent: "claude-bughunter", sev: "HIGH", sevColor: "bg-red-50 text-red-700 border-red-100", repo: "org/api", date: "Jun 5 2026", approver: "sudhi@", pr: "PR #15", status: "Merged", statusColor: "bg-emerald-50 text-emerald-700 border-emerald-100" },
              { id: "SL-002", agent: "passive-hook", sev: "CRITICAL", sevColor: "bg-red-100 text-red-800 border-red-200", repo: "org/web", date: "Jun 7 2026", approver: "alex@", pr: "PR #22", status: "Open", statusColor: "bg-amber-50 text-amber-700 border-amber-100" },
              { id: "SL-003", agent: "bughunter-scan", sev: "HIGH", sevColor: "bg-red-50 text-red-700 border-red-100", repo: "org/api", date: "Jun 8 2026", approver: "—", pr: "—", status: "Triaging", statusColor: "bg-stone-50 text-stone-600 border-stone-200" },
            ].map(row => (
              <div key={row.id} className="px-6 py-4">
                <div className="grid grid-cols-8 gap-4 items-center">
                  <code className="font-mono text-xs text-rose-700 font-semibold">{row.id}</code>
                  <p className="text-xs text-stone-700">{row.agent}</p>
                  <span className={`inline-flex items-center text-[10px] font-semibold border px-2 py-0.5 rounded-full ${row.sevColor}`}>{row.sev}</span>
                  <p className="text-xs text-stone-500">{row.repo}</p>
                  <p className="text-xs text-stone-500">{row.date}</p>
                  <p className="text-xs text-stone-500">{row.approver}</p>
                  <p className="text-xs text-indigo-600">{row.pr}</p>
                  <span className={`inline-flex items-center text-[10px] font-semibold border px-2 py-0.5 rounded-full ${row.statusColor}`}>{row.status}</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        <p className="text-center text-xs text-stone-400 mt-4">
          Sample audit rows — exported as CSV or JSON for SOC&nbsp;2 review.
        </p>
      </div>
    </section>
  )
}

/* ─── Footer CTA ───────────────────────────────────────────────────────── */

function FooterCTASection() {
  return (
    <section className="bg-stone-50 px-6 py-20 text-center">
      <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-4">Get started</p>
      <h2 className="text-3xl font-bold text-stone-900 mb-4">Security Loop is live.</h2>
      <p className="text-stone-500 mb-8 max-w-lg mx-auto leading-relaxed">
        Install the CLI, enable Security Emit in Guard settings, and your team&apos;s findings
        start flowing in automatically. No new tools. No new process.
      </p>

      <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
        <a
          href="/secure"
          className="inline-flex items-center gap-2 rounded-xl bg-rose-600 px-6 py-3 text-sm font-semibold text-white hover:bg-rose-700 transition-colors"
        >
          Open Security console →
        </a>
        <a
          href="/marketplace"
          className="inline-flex items-center gap-2 rounded-xl border border-stone-200 bg-white px-6 py-3 text-sm font-semibold text-stone-700 hover:border-stone-300 hover:shadow-sm transition-all"
        >
          Install BugHunter →
        </a>
        <a
          href="/tools"
          className="inline-flex items-center gap-2 rounded-xl border border-stone-200 bg-white px-6 py-3 text-sm font-semibold text-stone-700 hover:border-stone-300 hover:shadow-sm transition-all"
        >
          All tools →
        </a>
      </div>
    </section>
  )
}

/* ─── Page footer ──────────────────────────────────────────────────────── */

function PageFooter() {
  return (
    <footer className="border-t border-stone-100 py-8 text-center text-xs text-stone-400 space-y-2">
      <div className="flex items-center justify-center gap-3 flex-wrap">
        <span>© {new Date().getFullYear()} Conduct</span>
        <span>·</span>
        <a href="https://github.com/sseshachala/conductai" target="_blank" rel="noopener noreferrer" className="hover:text-stone-600 transition-colors">GitHub</a>
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
        <span>·</span>
        <a href="/privacy" className="hover:text-stone-600 transition-colors">Privacy</a>
        <span>·</span>
        <a href="/terms" className="hover:text-stone-600 transition-colors">Terms</a>
      </div>
      <p className="text-stone-300">Envisioned, designed and developed with love from Houston</p>
    </footer>
  )
}

/* ─── Icons ────────────────────────────────────────────────────────────── */

function GitHubIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
      <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0 0 16 8c0-4.42-3.58-8-8-8z" />
    </svg>
  )
}
