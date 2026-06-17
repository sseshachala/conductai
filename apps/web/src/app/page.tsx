"use client"

export default function HomePage() {
  return (
    <div className="min-h-screen bg-white flex flex-col">
      <Nav />
      <main className="flex-1">
        <AcquisitionBanner />
        <HeroSection />
        <ToolsStripSection />
        <ProblemSection />
        <SolutionsSection />
        <TwoTracksSection />
        <PersonasSection />
        <FinalCTASection />
      </main>
      <PageFooter />
    </div>
  )
}

/* ─── Nav ──────────────────────────────────────────────────────────────── */

function Nav() {
  return (
    <header className="px-6 py-4 flex items-center justify-between max-w-6xl mx-auto w-full sticky top-0 bg-white/95 backdrop-blur-sm z-50 border-b border-stone-100">
      <a href="/">
        <img src="/logo.png" alt="Conduct AI" className="h-10 w-auto" />
      </a>
      <nav className="hidden md:flex items-center gap-6">
        <SolutionsDropdown />
        <ToolsDropdown />
        <a href="/playbooks" className="text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">Automations</a>
        <a href="/partners" className="text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">Partners</a>
        <a href="/docs" className="text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">Docs</a>
        <a href="/blog" className="text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">Blog</a>
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

/* ─── Shared Nav Components ────────────────────────────────────────────── */

function SolutionsDropdown() {
  return (
    <div className="relative group">
      <a href="/solutions" className="flex items-center gap-1 text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">
        Solutions
        <svg width="12" height="12" viewBox="0 0 12 12" fill="currentColor" className="opacity-40 mt-0.5"><path d="M2 4l4 4 4-4"/></svg>
      </a>
      <div className="absolute left-0 top-full pt-2 hidden group-hover:block z-50 min-w-[220px]">
        <div className="bg-white border border-stone-200 rounded-xl shadow-lg py-2">
          <a href="/solutions#guard" className="flex items-center gap-3 px-4 py-2.5 text-sm text-stone-700 hover:bg-stone-50 transition-colors">
            <span>🛡️</span>
            <div>
              <p className="font-semibold">Conduct Guard</p>
              <p className="text-xs text-stone-400">AI session governance</p>
            </div>
          </a>
          <a href="/solutions#secure" className="flex items-center gap-3 px-4 py-2.5 text-sm text-stone-700 hover:bg-stone-50 transition-colors">
            <span>🔒</span>
            <div>
              <p className="font-semibold">Secure</p>
              <p className="text-xs text-stone-400">Automated security enforcement</p>
            </div>
          </a>
          <a href="/solutions#workflows" className="flex items-center gap-3 px-4 py-2.5 text-sm text-stone-700 hover:bg-stone-50 transition-colors">
            <span>⚡</span>
            <div>
              <p className="font-semibold">Agentic Workflows</p>
              <p className="text-xs text-stone-400">Governed AI automations</p>
            </div>
          </a>
          <a href="/solutions#sdd" className="flex items-center gap-3 px-4 py-2.5 text-sm text-stone-700 hover:bg-stone-50 transition-colors">
            <span>📐</span>
            <div>
              <p className="font-semibold">Spec-Driven Dev</p>
              <p className="text-xs text-stone-400">Intent-first AI coding</p>
            </div>
          </a>
          <a href="/playbooks" className="flex items-center gap-3 px-4 py-2.5 text-sm text-stone-700 hover:bg-stone-50 transition-colors">
            <span>📦</span><div><p className="font-semibold">Playbooks</p><p className="text-xs text-stone-400">Pre-built AI automations</p></div>
          </a>
          <div className="border-t border-stone-100 mt-1 pt-1">
            <a href="/solutions" className="flex items-center gap-2 px-4 py-2 text-xs font-semibold text-indigo-600 hover:text-indigo-800 transition-colors">
              View all solutions →
            </a>
          </div>
        </div>
      </div>
    </div>
  )
}

function ToolsDropdown() {
  return (
    <div className="relative group">
      <a href="/tools" className="flex items-center gap-1 text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">
        Tools
        <svg width="12" height="12" viewBox="0 0 12 12" fill="currentColor" className="opacity-40 mt-0.5"><path d="M2 4l4 4 4-4"/></svg>
      </a>
      <div className="absolute left-0 top-full pt-2 hidden group-hover:block z-50 min-w-[200px]">
        <div className="bg-white border border-stone-200 rounded-xl shadow-lg py-2">
          <a href="/tools/agent-booster" className="flex items-center gap-3 px-4 py-2.5 text-sm text-stone-700 hover:bg-stone-50 transition-colors">
            <span className="text-indigo-600 font-bold text-base">◈</span>
            <div>
              <p className="font-semibold">Agent Booster</p>
              <p className="text-xs text-stone-400">Cut AI costs 3–15×</p>
            </div>
          </a>
          <a href="/tools/conduct-cli" className="flex items-center gap-3 px-4 py-2.5 text-sm text-stone-700 hover:bg-stone-50 transition-colors">
            <span className="text-violet-600 font-bold text-base">⬡</span>
            <div>
              <p className="font-semibold">Conduct CLI</p>
              <p className="text-xs text-stone-400">Govern from the terminal</p>
            </div>
          </a>
          <a href="/tools/security-loop" className="flex items-center gap-3 px-4 py-2.5 text-sm text-stone-700 hover:bg-stone-50 transition-colors">
            <span className="text-rose-600 font-bold text-base">🔐</span>
            <div>
              <p className="font-semibold">Security Loop</p>
              <p className="text-xs text-stone-400">Automated PR scanning</p>
            </div>
          </a>
        </div>
      </div>
    </div>
  )
}

/* ─── Hero ─────────────────────────────────────────────────────────────── */

/* ─── Acquisition Banner ───────────────────────────────────────────────── */

function AcquisitionBanner() {
  return (
    <div className="bg-stone-900 text-white text-center px-4 py-2.5 text-sm flex items-center justify-center gap-3 flex-wrap">
      <span className="font-semibold">Cursor was just acquired for $60B.</span>
      <span className="text-stone-300">Your codebase governance should stay independent.</span>
      <a href="/compare" className="underline underline-offset-2 text-indigo-300 hover:text-indigo-200 font-medium whitespace-nowrap">
        See how Conduct stays neutral →
      </a>
    </div>
  )
}

/* ─── Hero ─────────────────────────────────────────────────────────────── */

function HeroSection() {
  return (
    <section className="max-w-5xl mx-auto px-6 pt-20 pb-16 text-center">
      <div className="inline-flex items-center gap-2 bg-indigo-50 text-indigo-700 px-4 py-1.5 rounded-full text-xs font-semibold uppercase tracking-widest mb-8">
        <span className="w-1.5 h-1.5 rounded-full bg-indigo-500 inline-block" />
        Provider-agnostic AI Governance
      </div>
      <h1 className="text-5xl sm:text-6xl font-black tracking-tight text-stone-900 leading-[1.05] mb-6">
        Your team already<br />
        runs on AI.<br />
        <span className="bg-gradient-to-r from-indigo-600 to-violet-600 bg-clip-text text-transparent">Now govern it.</span>
      </h1>
      <p className="text-xl text-stone-500 max-w-2xl mx-auto leading-relaxed mb-10">
        Conduct AI is the independent governance layer between your engineering team and their AI tools —
        not owned by Anthropic, Microsoft, or any AI lab. Protect sessions, enforce security, and run the workflows that used to take human hours.
      </p>
      <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
        <a href="/sign-up" className="rounded-xl bg-stone-900 text-white px-7 py-3.5 text-base font-semibold hover:bg-stone-700 transition-colors w-full sm:w-auto text-center">
          Start Free — Deploy in Minutes
        </a>
        <a href="mailto:hello@conductai.ai" className="rounded-xl border border-stone-300 bg-white text-stone-700 px-7 py-3.5 text-base font-semibold hover:border-stone-400 hover:shadow-sm transition-all w-full sm:w-auto text-center">
          Talk to Us — We'll Run It For You
        </a>
      </div>
      <p className="text-xs text-stone-400 mt-4">No credit card required · Free tier for up to 5 developers · Works with tools your team already uses</p>
    </section>
  )
}

/* ─── Tools Strip ──────────────────────────────────────────────────────── */

function ToolsStripSection() {
  const tools = [
    { label: "Claude Code", note: null },
    { label: "Cursor", note: "works post-acquisition" },
    { label: "GitHub Copilot", note: null },
    { label: "Claude.ai", note: null },
    { label: "Codex", note: null },
    { label: "Any MCP Client", note: null },
  ]
  return (
    <div className="border-y border-stone-100 bg-stone-50 py-5 px-6">
      <div className="max-w-5xl mx-auto text-center">
        <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-4">
          Independent governance — works with the tools your team already uses
        </p>
        <div className="flex flex-wrap items-center justify-center gap-x-8 gap-y-3">
          {tools.map(t => (
            <div key={t.label} className="flex flex-col items-center gap-0.5">
              <span className="text-sm font-semibold text-stone-400">{t.label}</span>
              {t.note && (
                <span className="text-[10px] font-medium text-indigo-400 uppercase tracking-wider">{t.note}</span>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

/* ─── Problem ──────────────────────────────────────────────────────────── */

function ProblemSection() {
  const symptoms = [
    { icon: "🔑", text: "Developers paste API keys and credentials into AI prompts — nobody knows until an incident." },
    { icon: "📊", text: "Finance asks what AI is costing the team. Engineering leadership has no answer." },
    { icon: "🔍", text: "Security can't audit AI sessions. Compliance asks questions nobody can answer." },
    { icon: "🤖", text: "AI agents run workflows without policy enforcement. No audit trail. No controls." },
    { icon: "🛡️", text: "Vulnerabilities ship in AI-generated code because security review happens too late." },
  ]
  return (
    <section className="bg-stone-900 py-24 px-6">
      <div className="max-w-5xl mx-auto">
        <p className="text-xs font-semibold uppercase tracking-widest text-indigo-400 mb-4">The Problem</p>
        <div className="grid md:grid-cols-2 gap-12 items-start">
          <div>
            <h2 className="text-3xl sm:text-4xl font-bold text-white tracking-tight leading-tight mb-6">
              AI tools are everywhere in engineering.<br />Nobody owns what they do.
            </h2>
            <p className="text-stone-400 leading-relaxed mb-4">
              Claude Code. Cursor. Copilot. Codex. Your team is using all of them — every day — without controls, visibility, or an audit trail.
            </p>
            <p className="text-stone-400 leading-relaxed mb-4">
              <span className="text-white font-semibold">Governance was supposed to solve this.</span> Instead it became documentation — policies nobody reads and reviews nobody enforces.
            </p>
            <p className="text-stone-400 leading-relaxed">
              Conduct makes governance infrastructure. Enforcement that runs at the same layer as your AI tools, not above them.
            </p>
          </div>
          <div className="flex flex-col gap-3">
            {symptoms.map((s, i) => (
              <div key={i} className="flex items-start gap-3 bg-white/5 border border-white/8 rounded-xl px-4 py-3.5">
                <span className="text-lg flex-shrink-0 mt-0.5">{s.icon}</span>
                <span className="text-sm text-stone-300 leading-relaxed">{s.text}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  )
}

/* ─── Solutions ────────────────────────────────────────────────────────── */

const solutions = [
  {
    icon: "🛡️",
    iconBg: "bg-indigo-50",
    label: "Conduct Guard",
    title: "Protect Every Developer Session",
    desc: "Real-time policy enforcement on every AI session. Blocks risky actions before they execute. Logs every tool call. Tracks spend across your entire team.",
    pain: "A developer pasted a production API key into Claude. It reached the model, the log, and the audit trail.",
    outcome: "Blocked before it hit the LLM. Redacted from the audit log. Security notified automatically.",
    href: "/solutions#guard",
    cta: "See how Guard works",
  },
  {
    icon: "🔒",
    iconBg: "bg-emerald-50",
    label: "Secure",
    title: "Security That Runs Itself",
    desc: "Every PR scanned. Every vulnerability flagged before it merges. Security policies enforced continuously — not as a gate, but as a layer built into how code gets reviewed.",
    pain: "A hardcoded password sat in the repo for 14 months. Three security reviews missed it.",
    outcome: "Caught on the next commit. Flagged with file, line, and remediation. No human review needed.",
    href: "/solutions#secure",
    cta: "See how Secure works",
  },
  {
    icon: "⚡",
    iconBg: "bg-amber-50",
    label: "Agentic Workflows",
    title: "Workflows That Inherit Your Governance",
    desc: "AI agents built as YAML playbooks — triggered by the events that matter, with Guard and security policies enforced on every action. No workflow escapes governance.",
    pain: "A GitHub issue was filed at 2am. The fix needed to ship before market open. Nobody was on call.",
    outcome: "PR open by 9am. Engineer woke up to a fix ready for review — no pages, no lost sleep.",
    href: "/solutions#workflows",
    cta: "See how Workflows work",
  },
]

function SolutionsSection() {
  return (
    <section className="py-24 px-6 bg-stone-50">
      <div className="max-w-5xl mx-auto">
        <div className="text-center mb-14">
          <p className="text-xs font-semibold uppercase tracking-widest text-stone-400 mb-3">How It Works</p>
          <h2 className="text-3xl sm:text-4xl font-bold text-stone-900 tracking-tight mb-4">Three solutions. One governance platform.</h2>
          <p className="text-stone-500 max-w-xl mx-auto leading-relaxed">
            Guard protects your developer sessions. Secure enforces policy in your code.
            Workflows automate your engineering processes — with governance baked into every run.
          </p>
        </div>
        <div className="grid md:grid-cols-3 gap-5">
          {solutions.map((s) => (
            <div key={s.label} className="bg-white rounded-2xl border border-stone-200 p-6 flex flex-col gap-4 hover:border-stone-300 hover:shadow-md transition-all">
              <div className={`w-11 h-11 rounded-xl ${s.iconBg} flex items-center justify-center text-xl`}>
                {s.icon}
              </div>
              <div>
                <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-1">{s.label}</p>
                <h3 className="text-lg font-bold text-stone-900 tracking-tight leading-snug">{s.title}</h3>
              </div>
              <p className="text-sm text-stone-500 leading-relaxed">{s.desc}</p>
              <div className="bg-stone-50 rounded-xl border border-stone-100 p-4 flex flex-col gap-2 mt-auto">
                <p className="text-xs text-stone-400 leading-relaxed">
                  <span className="font-semibold text-stone-500">⚠ Pain: </span>{s.pain}
                </p>
                <p className="text-xs text-emerald-700 font-medium leading-relaxed">
                  <span className="font-semibold">✓ Outcome: </span>{s.outcome}
                </p>
              </div>
              <a href={s.href} className="text-sm font-semibold text-indigo-600 hover:text-indigo-800 transition-colors">
                {s.cta} →
              </a>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

/* ─── Two Tracks ───────────────────────────────────────────────────────── */

function TwoTracksSection() {
  return (
    <section className="py-24 px-6 bg-white">
      <div className="max-w-5xl mx-auto">
        <div className="text-center mb-14">
          <p className="text-xs font-semibold uppercase tracking-widest text-stone-400 mb-3">Two Ways to Work With Us</p>
          <h2 className="text-3xl sm:text-4xl font-bold text-stone-900 tracking-tight mb-4">
            Platform or partnership.<br />You choose how.
          </h2>
          <p className="text-stone-500 max-w-xl mx-auto leading-relaxed">
            In the AI era, software alone is not enough. We offer the platform for teams that move fast —
            and the expertise for organizations that need governance done right.
          </p>
        </div>
        <div className="grid md:grid-cols-2 gap-5">

          {/* Platform */}
          <div className="rounded-2xl bg-indigo-50 border border-indigo-100 p-8 flex flex-col gap-5">
            <span className="inline-flex px-3 py-1 rounded-full bg-indigo-600 text-white text-xs font-bold uppercase tracking-wider w-fit">
              Platform
            </span>
            <div>
              <h3 className="text-2xl font-bold text-stone-900 tracking-tight mb-2">Use the platform yourself.</h3>
              <p className="text-stone-600 leading-relaxed text-sm">
                Install in minutes. Connect your team's AI tools. Policies live immediately.
                Start with the free tier — no infrastructure changes required.
              </p>
            </div>
            <ul className="space-y-2.5">
              {[
                "Deploy Guard policies in one command",
                "22+ production-ready workflow playbooks",
                "Security scanning on every PR — automatic",
                "Full audit log from day one",
                "Free tier for up to 5 developers",
              ].map(f => (
                <li key={f} className="flex items-center gap-2.5 text-sm text-stone-700">
                  <span className="w-5 h-5 rounded-full bg-indigo-600 text-white flex items-center justify-center text-xs font-bold flex-shrink-0">✓</span>
                  {f}
                </li>
              ))}
            </ul>
            <a href="/sign-up" className="mt-auto rounded-xl bg-stone-900 text-white px-6 py-3 text-sm font-semibold hover:bg-stone-700 transition-colors text-center">
              Start Free — No Credit Card
            </a>
          </div>

          {/* Solutions */}
          <div className="rounded-2xl bg-stone-900 border border-stone-800 p-8 flex flex-col gap-5">
            <span className="inline-flex px-3 py-1 rounded-full bg-white/10 text-stone-300 text-xs font-bold uppercase tracking-wider w-fit">
              Solutions
            </span>
            <div>
              <h3 className="text-2xl font-bold text-white tracking-tight mb-2">Let us run it for you.</h3>
              <p className="text-stone-400 leading-relaxed text-sm">
                We scope your AI governance posture, implement policies, build custom workflows for your
                engineering processes, and operate the governance layer for you.
              </p>
            </div>
            <ul className="space-y-2.5">
              {[
                "AI governance audit and policy design",
                "Guard deployment across your team",
                "Custom workflow builds for your processes",
                "Ongoing monitoring and tuning",
                "Dedicated engineering point of contact",
              ].map(f => (
                <li key={f} className="flex items-center gap-2.5 text-sm text-stone-300">
                  <span className="w-5 h-5 rounded-full bg-white/15 text-white flex items-center justify-center text-xs font-bold flex-shrink-0">✓</span>
                  {f}
                </li>
              ))}
            </ul>
            <a href="mailto:hello@conductai.ai" className="mt-auto rounded-xl border border-white/20 text-white px-6 py-3 text-sm font-semibold hover:bg-white/10 transition-colors text-center">
              Book a Discovery Call
            </a>
          </div>

        </div>
      </div>
    </section>
  )
}

/* ─── Personas ─────────────────────────────────────────────────────────── */

const personas = [
  {
    role: "Engineering Leaders",
    title: "Visibility and control — without slowing your team down.",
    desc: "You're responsible for how AI gets used across your engineering organization. Right now you have no visibility and no controls. Conduct changes that without adding process overhead.",
    outcomes: [
      "See every AI tool your team uses — in one dashboard",
      "Know what AI is costing you, by person and by project",
      "Enforce your engineering standards automatically",
      "Answer security and compliance questions on demand",
    ],
  },
  {
    role: "IT Managers & Directors",
    title: "Policy enforcement that works without blocking productivity.",
    desc: "You need governance that actually runs — not documentation that developers ignore. Conduct deploys in minutes, works with every AI tool already in use, and gives you one audit trail.",
    outcomes: [
      "One policy layer across Claude Code, Cursor, Copilot, and more",
      "No infrastructure changes — works with your existing stack",
      "Role-based policies for different teams and access levels",
      "Spend budgets per developer, per tool, per project",
    ],
  },
  {
    role: "Security Analysts",
    title: "Governance at the layer where AI actually operates.",
    desc: "You need AI sessions audited, credentials protected, vulnerabilities caught before production, and compliance evidence on demand. Conduct makes all of this the default — not the exception.",
    outcomes: [
      "Credentials and PII blocked before they reach any LLM",
      "Every tool call logged with decision, rule, and developer identity",
      "Security scanning on every PR — automatic, not manual",
      "Compliance audit trail exportable on demand",
    ],
  },
]

function PersonasSection() {
  return (
    <section className="py-24 px-6 bg-stone-50">
      <div className="max-w-5xl mx-auto">
        <div className="text-center mb-14">
          <p className="text-xs font-semibold uppercase tracking-widest text-stone-400 mb-3">Who It's For</p>
          <h2 className="text-3xl sm:text-4xl font-bold text-stone-900 tracking-tight">
            Built for the people responsible<br />for how AI gets used.
          </h2>
        </div>
        <div className="grid md:grid-cols-3 gap-5">
          {personas.map(p => (
            <div key={p.role} className="bg-white rounded-2xl border border-stone-200 p-6 hover:border-stone-300 hover:shadow-sm transition-all">
              <p className="text-xs font-bold text-indigo-600 uppercase tracking-widest mb-3">{p.role}</p>
              <h3 className="text-base font-bold text-stone-900 leading-snug mb-3">{p.title}</h3>
              <p className="text-sm text-stone-500 leading-relaxed mb-4">{p.desc}</p>
              <ul className="space-y-2">
                {p.outcomes.map(o => (
                  <li key={o} className="text-sm text-stone-600 flex items-start gap-2">
                    <span className="text-indigo-500 font-bold flex-shrink-0 mt-0.5">→</span>
                    {o}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

/* ─── Final CTA ────────────────────────────────────────────────────────── */

function FinalCTASection() {
  return (
    <section className="py-24 px-6 bg-gradient-to-br from-indigo-600 to-violet-600">
      <div className="max-w-3xl mx-auto text-center">
        <h2 className="text-3xl sm:text-4xl font-black text-white tracking-tight leading-tight mb-4">
          Stop governing AI<br />with documentation.<br />Start governing it<br />with infrastructure.
        </h2>
        <p className="text-indigo-200 text-lg leading-relaxed mb-10 max-w-xl mx-auto">
          Platform for teams that move fast. Partnership for teams that need it done right.
          Either way — your AI layer gets governed.
        </p>
        <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
          <a href="/sign-up" className="rounded-xl bg-white text-indigo-600 px-7 py-3.5 text-base font-bold hover:bg-indigo-50 transition-colors w-full sm:w-auto text-center">
            Start Free — No Credit Card
          </a>
          <a href="mailto:hello@conductai.ai" className="rounded-xl border border-white/40 text-white px-7 py-3.5 text-base font-semibold hover:bg-white/10 transition-colors w-full sm:w-auto text-center">
            Book a Discovery Call
          </a>
        </div>
        <p className="text-indigo-300 text-xs mt-5">Free tier · No infrastructure changes · Works in minutes</p>
      </div>
    </section>
  )
}

/* ─── Footer ───────────────────────────────────────────────────────────── */

function PageFooter() {
  return (
    <footer className="border-t border-stone-100 py-10 px-6 bg-white">
      <div className="max-w-5xl mx-auto">
        <div className="flex flex-col md:flex-row justify-between gap-8 mb-10">
          <div>
            <img src="/logo.png" alt="Conduct AI" className="h-8 w-auto mb-3" />
            <p className="text-sm text-stone-400 max-w-xs leading-relaxed">AI Governance for Engineering Teams. Platform or partnership — you choose how.</p>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-8">
            {[
              { heading: "Solutions", links: [["Conduct Guard", "/solutions#guard"], ["Secure", "/solutions#secure"], ["Agentic Workflows", "/solutions#workflows"]] },
              { heading: "Company", links: [["About", "/about"], ["Partners", "/partners"], ["Blog", "/blog"]] },
              { heading: "Resources", links: [["Docs", "/docs"], ["Playbooks", "/marketplace"], ["GitHub", "https://github.com/sseshachala/conductai"]] },
              { heading: "Legal", links: [["Privacy", "/privacy"], ["Terms", "/terms"]] },
            ].map(col => (
              <div key={col.heading}>
                <p className="text-xs font-bold uppercase tracking-widest text-stone-400 mb-3">{col.heading}</p>
                <ul className="space-y-2">
                  {col.links.map(([label, href]) => (
                    <li key={label}>
                      <a href={href} className="text-sm text-stone-500 hover:text-stone-900 transition-colors">{label}</a>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </div>
        <div className="border-t border-stone-100 pt-6 flex flex-col sm:flex-row justify-between items-center gap-2 text-xs text-stone-400">
          <span>© {new Date().getFullYear()} Conduct AI. All rights reserved.</span>
          <span>Envisioned, designed and developed with love from Houston</span>
        </div>
      </div>
    </footer>
  )
}
