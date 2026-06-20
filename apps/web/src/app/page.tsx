"use client"

export default function HomePage() {
  return (
    <div className="min-h-screen bg-white flex flex-col">
      <Nav />
      <main className="flex-1">
        <AcquisitionBanner />
        <HeroSection />
        <TrustBarSection />
        <ProofStripSection />
        <ProblemSection />
        <TwoLanesSection />
        <GovernanceNarrativeSection />
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
    <header className="sticky top-0 bg-white/95 backdrop-blur-sm z-50 border-b border-stone-100">
      <div className="px-6 py-4 flex items-center justify-between max-w-6xl mx-auto w-full">
      <a href="/">
        <img src="/logo.png" alt="Conduct AI" className="h-10 w-auto" />
      </a>
      <nav className="hidden md:flex items-center gap-6">
        <ProductsDropdown />
        <a href="/playbooks" className="text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">Agent Templates</a>
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
      </div>
    </header>
  )
}

/* ─── Shared Nav Components ────────────────────────────────────────────── */

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
          <a href="/playbooks" className="flex items-center gap-3 px-4 py-2.5 text-sm text-stone-700 hover:bg-stone-50 transition-colors">
            <span>⚡</span>
            <div>
              <p className="font-semibold">Agent Templates</p>
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
  const chips = [
    "22 agent templates",
    "4 AI providers",
    "Real-time spend limits",
    "Full audit trail",
    "Zero infrastructure changes",
  ]
  return (
    <section className="max-w-5xl mx-auto px-6 pt-20 pb-16 text-center">
      <div className="inline-flex items-center gap-2 bg-indigo-50 text-indigo-700 px-4 py-1.5 rounded-full text-xs font-semibold uppercase tracking-widest mb-8">
        <span className="w-1.5 h-1.5 rounded-full bg-indigo-500 inline-block" />
        AI Operating Layer for Engineering Teams
      </div>
      <h1 className="text-5xl sm:text-6xl font-black tracking-tight text-stone-900 leading-[1.05] mb-6">
        Run AI agents.<br />
        <span className="bg-gradient-to-r from-indigo-600 to-violet-600 bg-clip-text text-transparent">Govern the risk.</span>
      </h1>
      <p className="text-xl text-stone-500 max-w-2xl mx-auto leading-relaxed mb-8">
        22 agent templates that automate your engineering workflows, with real-time spend limits, policy enforcement, and a full audit trail.
      </p>
      <div className="flex flex-wrap items-center justify-center gap-2 mb-10">
        {chips.map(chip => (
          <span key={chip} className="bg-stone-100 text-stone-700 rounded-full px-3 py-1 text-xs font-semibold">
            {chip}
          </span>
        ))}
      </div>
      <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
        <a href="/sign-up" className="rounded-xl bg-stone-900 text-white px-7 py-3.5 text-base font-semibold hover:bg-stone-700 transition-colors w-full sm:w-auto text-center">
          Start Free — See It Yourself
        </a>
        <a href="mailto:hello@conductai.ai" className="rounded-xl border border-stone-300 bg-white text-stone-700 px-7 py-3.5 text-base font-semibold hover:border-stone-400 hover:shadow-sm transition-all w-full sm:w-auto text-center">
          Book a Discovery Call
        </a>
      </div>
      <p className="text-xs text-stone-400 mt-4">Free tier · No infrastructure changes · Works in minutes</p>
    </section>
  )
}

/* ─── Trust Bar ────────────────────────────────────────────────────────── */

function TrustBarSection() {
  const integrations = ["GitHub", "Slack", "Linear", "Jira", "Claude", "GPT-4.1", "Gemini", "VS Code"]
  return (
    <div className="border-y border-stone-100 bg-stone-50 py-5 px-6">
      <div className="max-w-5xl mx-auto text-center">
        <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-4">
          Works with
        </p>
        <div className="flex flex-wrap items-center justify-center gap-x-8 gap-y-3">
          {integrations.map(name => (
            <span key={name} className="text-sm font-semibold text-stone-400">{name}</span>
          ))}
        </div>
      </div>
    </div>
  )
}

/* ─── Proof Strip ──────────────────────────────────────────────────────── */

function ProofStripSection() {
  return (
    <section className="bg-stone-950 border-y border-stone-800 py-6 px-6">
      <div className="max-w-5xl mx-auto">
        <p className="text-center text-[10px] font-semibold uppercase tracking-widest text-stone-500 mb-5">
          Real data · 1 developer · 18 days · annualized
        </p>
        <div className="flex flex-wrap items-start justify-center gap-x-12 gap-y-5">

          {/* AI Spend */}
          <div className="flex flex-col items-center gap-1">
            <span className="text-2xl font-black text-white tracking-tight">$84K/year</span>
            <span className="text-xs text-stone-400">projected AI spend</span>
            <span className="text-[10px] text-stone-600">from $4,170 in 18 days</span>
          </div>

          {/* Prod deploy gates — expanded treatment */}
          <div className="flex flex-col items-center gap-1 border border-stone-700 rounded-xl px-5 py-3 bg-stone-900">
            <span className="text-2xl font-black text-red-400 tracking-tight">$50K+</span>
            <span className="text-xs text-stone-300 font-semibold">potential cost per unreviewed deploy</span>
            <span className="text-[10px] text-stone-500 mt-1">6 intercepted · 18 days · 1 developer</span>
            <span className="text-[10px] text-indigo-400 mt-1">→ 1,200/year across a 10-person team</span>
          </div>

          {/* PII */}
          <div className="flex flex-col items-center gap-1">
            <span className="text-2xl font-black text-white tracking-tight">12,000/year</span>
            <span className="text-xs text-stone-400">PII events screened</span>
            <span className="text-[10px] text-stone-600">from 589 in 18 days</span>
          </div>

          {/* Savings */}
          <div className="flex flex-col items-center gap-1">
            <span className="text-2xl font-black text-white tracking-tight">$4,700/year</span>
            <span className="text-xs text-stone-400">tooling savings</span>
            <span className="text-[10px] text-stone-600">from $235 in 18 days</span>
          </div>

        </div>
      </div>
    </section>
  )
}

/* ─── Problem ──────────────────────────────────────────────────────────── */

interface ProblemCard {
  num: string
  icon: string
  headline: string
  detail: string
}

function ProblemSection() {
  const problems: ProblemCard[] = [
    {
      num: "01",
      icon: "🕳️",
      headline: "No visibility into what agents ran",
      detail: "Agent activity is trapped inside individual tools. You can't see what Copilot reviewed, what Claude generated, or how many tokens your team burned.",
    },
    {
      num: "02",
      icon: "💸",
      headline: "Spend is invisible until the invoice arrives",
      detail: "Per-user token costs accumulate silently. By the time the bill lands, the sprint is over and the budget conversation is already awkward.",
    },
    {
      num: "03",
      icon: "📄",
      headline: "Policies live in Notion, not at runtime",
      detail: "You have an AI usage policy. It exists in a doc. It is not enforced at the moment an agent actually runs. That is the only moment that matters.",
    },
    {
      num: "04",
      icon: "🔁",
      headline: "Every automation is a one-off",
      detail: "PR review prompts, security scans, release notes. Each lives as a private script in someone's terminal. They drift, they break, and they leave when that person does.",
    },
  ]
  return (
    <section className="bg-stone-900 py-24 px-6">
      <div className="max-w-5xl mx-auto">
        <p className="text-xs font-semibold uppercase tracking-widest text-indigo-400 mb-4">The Problem</p>
        <h2 className="text-3xl sm:text-4xl font-bold text-white tracking-tight leading-tight mb-4 max-w-3xl">
          AI agents ship code. Nobody sees what they actually did.
        </h2>
        <p className="text-stone-400 leading-relaxed mb-12 max-w-2xl">
          Your team is already using Copilot, Claude, Cursor, and Codex. But when something breaks, there&apos;s no trail, no policy, no audit log, no budget control.
        </p>
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-5">
          {problems.map(p => (
            <div key={p.num} className="bg-white/5 border border-white/8 rounded-2xl p-5 flex flex-col gap-3">
              <div className="flex items-center justify-between">
                <span className="text-2xl">{p.icon}</span>
                <span className="text-xs font-mono font-bold text-stone-600">{p.num}</span>
              </div>
              <h3 className="text-sm font-bold text-white leading-snug">{p.headline}</h3>
              <p className="text-xs text-stone-400 leading-relaxed">{p.detail}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

/* ─── Two Lanes ────────────────────────────────────────────────────────── */

function TwoLanesSection() {
  return (
    <section className="py-24 px-6 bg-white">
      <div className="max-w-5xl mx-auto">
        <div className="text-center mb-14">
          <p className="text-xs font-semibold uppercase tracking-widest text-indigo-500 mb-3">The solution</p>
          <h2 className="text-3xl sm:text-4xl font-bold text-stone-900 tracking-tight mb-4">
            Two problems. One platform.
          </h2>
          <p className="text-stone-500 max-w-xl mx-auto leading-relaxed">
            Conduct ships both layers: automate the work, govern the risk. Your team moves fast with a safety net under every agent.
          </p>
        </div>
        <div className="grid md:grid-cols-2 gap-5">

          {/* Automate — indigo/light */}
          <div className="rounded-2xl bg-indigo-50 border border-indigo-100 p-8 flex flex-col gap-5">
            <span className="inline-flex px-3 py-1 rounded-full bg-indigo-600 text-white text-xs font-bold uppercase tracking-wider w-fit">
              ⚡ Automate
            </span>
            <div>
              <h3 className="text-2xl font-bold text-stone-900 tracking-tight mb-2">Ship faster with agent templates</h3>
              <p className="text-stone-600 leading-relaxed text-sm">
                22 agent templates cover every engineering workflow: PR review, security scanning, release notes, incident response. Install one in under a minute.
              </p>
            </div>
            <ul className="space-y-2.5 flex-1">
              {[
                "PR review · autopilot fix · security scan",
                "CI failure triage · flaky test detection",
                "Release notes · postmortem drafter · docs drift",
                "YAML you own, no vendor lock-in",
                "Runs on Claude, GPT-4.1, or Gemini",
              ].map(f => (
                <li key={f} className="flex items-center gap-2.5 text-sm text-stone-700">
                  <span className="w-5 h-5 rounded-full bg-indigo-600 text-white flex items-center justify-center text-xs font-bold flex-shrink-0">✓</span>
                  {f}
                </li>
              ))}
            </ul>
            <a href="/marketplace" className="mt-auto rounded-xl bg-stone-900 text-white px-6 py-3 text-sm font-semibold hover:bg-stone-700 transition-colors text-center">
              Browse templates →
            </a>
          </div>

          {/* Guard — dark */}
          <div className="rounded-2xl bg-stone-900 border border-stone-800 p-8 flex flex-col gap-5">
            <span className="inline-flex px-3 py-1 rounded-full bg-white/10 text-stone-300 text-xs font-bold uppercase tracking-wider w-fit">
              🛡️ Guard
            </span>
            <div>
              <h3 className="text-2xl font-bold text-white tracking-tight mb-2">Govern every agent at runtime</h3>
              <p className="text-stone-400 leading-relaxed text-sm">
                Real-time policy enforcement, per-developer spend limits, and a full audit trail applied at the moment the agent runs, not after.
              </p>
            </div>
            <ul className="space-y-2.5 flex-1">
              {[
                "Per-user monthly spend limits with auto-block",
                "OWASP Top 10 policy pack, enabled by default",
                "Full audit log: who ran what, when, and why",
                "Slack alerts on policy violations or budget spikes",
                "DORA metrics · cost analytics · agent scorecards",
              ].map(f => (
                <li key={f} className="flex items-center gap-2.5 text-sm text-stone-300">
                  <span className="w-5 h-5 rounded-full bg-white/15 text-white flex items-center justify-center text-xs font-bold flex-shrink-0">✓</span>
                  {f}
                </li>
              ))}
            </ul>
            <a href="/guard" className="mt-auto rounded-xl border border-white/20 text-white px-6 py-3 text-sm font-semibold hover:bg-white/10 transition-colors text-center">
              Explore Guard →
            </a>
          </div>

        </div>
      </div>
    </section>
  )
}

/* ─── Governance Narrative ─────────────────────────────────────────────── */

function GovernanceNarrativeSection() {
  const incidents = [
    {
      rule: "approve-prod-deploy",
      headline: "Force-deploy to production — intercepted",
      detail: "AI attempted vercel deploy --prod --force at 3:11pm on a Friday. Guard blocked it before it executed.",
      badge: "BLOCKED",
      badgeColor: "bg-red-500",
    },
    {
      rule: "no-secret-in-commit-msg",
      headline: "Secret embedded in git commit — caught",
      detail: "AI tried to commit code with a credential token in the commit message. Fired twice in the same session.",
      badge: "BLOCKED",
      badgeColor: "bg-red-500",
    },
    {
      rule: "pii-redact",
      headline: "971 PII events in a single day",
      detail: "Jun 19 spiked 30× the 32/day baseline. Without Guard, every one of those calls would have sent raw credentials to an LLM.",
      badge: "WARNED",
      badgeColor: "bg-amber-500",
    },
  ]

  const kpis = [
    { value: "$4,170", label: "AI spend", color: "text-indigo-600" },
    { value: "6", label: "Deploys", color: "text-violet-600" },
    { value: "589", label: "PII events", color: "text-red-500" },
    { value: "$235", label: "Saved", color: "text-emerald-600" },
  ]

  return (
    <section className="py-24 px-6 bg-white border-b border-stone-100">
      <div className="max-w-5xl mx-auto">
        <p className="text-xs font-semibold uppercase tracking-widest text-indigo-500 mb-4">What governance actually tells you</p>
        <h2 className="text-3xl sm:text-4xl font-bold text-stone-900 tracking-tight leading-tight mb-4 max-w-2xl">
          Every AI session, explained in plain English.
        </h2>
        <p className="text-stone-500 leading-relaxed mb-12 max-w-2xl">
          Guard watches every tool call across every AI session. At the end of each day, it surfaces one sentence that tells your team what happened, what was blocked, and what it cost.
        </p>

        {/* AI Narrative Card */}
        <div className="rounded-2xl border border-stone-200 bg-white p-6 mb-8 shadow-sm">
          {/* Card header */}
          <div className="flex items-center justify-between mb-4 pb-4 border-b border-stone-100">
            <div className="flex items-center gap-2">
              <span className="text-indigo-600 font-bold">✦</span>
              <span className="text-xs font-semibold text-stone-500">Guard · AI Narrative</span>
              <span className="text-xs text-stone-400">sudhi@b2bsphere.com</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-emerald-500 inline-block" />
              <span className="text-xs font-semibold text-emerald-600">Live</span>
            </div>
          </div>

          {/* Narrative text */}
          <p className="text-sm text-stone-700 leading-relaxed mb-6">
            You spent $245/day on AI this period across claude-code, codex, and cursor. Guard intercepted 6 production deploys before they ran unreviewed, warned on 2 destructive commands, and screened 589 events for PII before they reached any LLM. Claude Code dominates at 96% of total spend. RTK and Booster offset $235 — 5.6% back.
          </p>

          {/* KPIs */}
          <div className="grid grid-cols-4 gap-4 mb-4">
            {kpis.map(k => (
              <div key={k.label} className="text-center">
                <p className={`text-2xl font-black tracking-tight ${k.color}`}>{k.value}</p>
                <p className="text-xs text-stone-400 mt-0.5">{k.label}</p>
              </div>
            ))}
          </div>

          {/* Card footer */}
          <div className="pt-4 border-t border-stone-100 flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 inline-block" />
            <span className="text-[10px] text-stone-400">Generated Jun 19, 2026 · 5,985 events · 25 sessions</span>
          </div>
        </div>

        {/* Incident cards */}
        <div className="grid md:grid-cols-3 gap-5 mb-12">
          {incidents.map(inc => (
            <div key={inc.rule} className="rounded-2xl border border-stone-200 p-6 flex flex-col gap-3 hover:border-stone-300 hover:shadow-sm transition-all">
              <div className="flex items-center gap-2">
                <span className={`inline-block px-2 py-0.5 rounded-full text-[10px] font-bold text-white tracking-wider ${inc.badgeColor}`}>
                  {inc.badge}
                </span>
                <span className="text-[10px] font-mono text-stone-400">{inc.rule}</span>
              </div>
              <h3 className="text-sm font-bold text-stone-900 leading-snug">{inc.headline}</h3>
              <p className="text-xs text-stone-500 leading-relaxed">{inc.detail}</p>
            </div>
          ))}
        </div>

        <div className="rounded-2xl bg-indigo-50 border border-indigo-100 px-8 py-6 flex flex-col sm:flex-row items-start sm:items-center gap-4">
          <div className="flex-1">
            <p className="text-sm font-semibold text-stone-900 mb-1">
              What would have happened without Guard?
            </p>
            <p className="text-sm text-stone-500 leading-relaxed">
              The production deploy would have executed. Average cost of a prod incident at a mid-market company: $15K–$50K.
              $235 saved on tooling is nice. $50K in a prevented outage is a different conversation.
            </p>
          </div>
          <a
            href="/sign-up"
            className="flex-shrink-0 rounded-xl bg-indigo-600 text-white px-6 py-3 text-sm font-bold hover:bg-indigo-700 transition-colors whitespace-nowrap"
          >
            Start Free
          </a>
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
    desc: "You're responsible for how AI gets used across your engineering organisation. Right now you have no visibility and no controls. Conduct changes that without adding process overhead.",
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
          <p className="text-xs font-semibold uppercase tracking-widest text-stone-400 mb-3">Built for the people responsible for how AI gets used.</p>
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
            Start Free — See It Yourself
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
              { heading: "Solutions", links: [["Conduct Guard", "/solutions#guard"], ["Secure", "/solutions#secure"], ["Agentic Workflows", "/solutions#workflows"]] as [string, string][] },
              { heading: "Company", links: [["About", "/about"], ["Partners", "/partners"], ["Blog", "/blog"]] as [string, string][] },
              { heading: "Resources", links: [["Docs", "/docs"], ["Agent Templates", "/marketplace"], ["GitHub", "https://github.com/sseshachala/conductai"]] as [string, string][] },
              { heading: "Legal", links: [["Privacy", "/privacy"], ["Terms", "/terms"]] as [string, string][] },
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
