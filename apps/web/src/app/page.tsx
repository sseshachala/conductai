"use client"

import BootSequence from "@/components/marketing/BootSequence"
import { CtaLink } from "@/components/marketing/CtaLink"

export default function HomePage() {
  return (
    <div className="min-h-screen bg-white flex flex-col">
      <Nav />
      <main className="flex-1">

        <HeroSection />
        <ControlPlaneSection />
        <CeoQuoteSection />
        <TrustBarSection />
        <ProofStripSection />
        <ProblemSection />
        <TwoLanesSection />
        <StackStripSection />
        <GovernanceNarrativeSection />
        <GuardLearnsTeaser />
        <PersonasSection />
        <DemoVideoSection />
        <DeploymentStripSection />
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
        <SolutionsDropdown />
        {/* ponytail: home page has its own inlined nav; keep in sync with (marketing)/layout.tsx until we extract shared components */}
        <a href="/use-cases" className="text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">Use cases</a>
        <a href="/team-os" className="text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">
          Team OS <span className="text-[10px] text-emerald-600 font-bold uppercase tracking-widest">Free</span>
        </a>
        <a href="/docs" className="text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">Docs</a>
        <a href="/blog" className="text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">Blog</a>
      </nav>
      <div className="flex items-center gap-3">
        <a href="https://cal.com/sudhi-seshachala-pks7pd" target="_blank" rel="noopener"
          className="rounded-lg border border-stone-300 text-stone-700 px-4 py-2 text-sm font-semibold hover:border-stone-400 transition-colors hidden sm:block">
          Book Demo
        </a>
        <CtaLink className="rounded-lg bg-stone-900 text-white px-4 py-2 text-sm font-semibold hover:bg-stone-700 transition-colors" />
      </div>
      </div>
    </header>
  )
}

/* ─── Shared Nav Components ────────────────────────────────────────────── */

function ProductsDropdown() {
  return (
    <div className="relative group">
      <a href="#" className="flex items-center gap-1 text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">
        Product
        <svg width="12" height="12" viewBox="0 0 12 12" fill="currentColor" className="opacity-40 mt-0.5"><path d="M2 4l4 4 4-4"/></svg>
      </a>
      <div className="absolute left-0 top-full pt-2 hidden group-hover:block z-50 min-w-[220px]">
        <div className="bg-white border border-stone-200 rounded-xl shadow-lg py-2">
          <a href="/team-os" className="flex items-center gap-3 px-4 py-2.5 text-sm text-stone-700 hover:bg-stone-50 transition-colors">
            <span>📄</span>
            <div>
              <p className="font-semibold">Team OS <span className="text-[10px] text-emerald-600 font-bold ml-1 uppercase tracking-widest">Free</span></p>
              <p className="text-xs text-stone-400">CLAUDE.md · REVIEW.md · Standards</p>
            </div>
          </a>
          <div className="border-t border-stone-100 my-1" />
          <a href="/guard" className="flex items-center gap-3 px-4 py-2.5 text-sm text-stone-700 hover:bg-stone-50 transition-colors">
            <span>🛡️</span>
            <div>
              <p className="font-semibold">Conduct Guard</p>
              <p className="text-xs text-stone-400">Runtime AI governance</p>
            </div>
          </a>
          <a href="/registry" className="flex items-center gap-3 px-4 py-2.5 text-sm text-stone-700 hover:bg-stone-50 transition-colors">
            <span>⚡</span>
            <div>
              <p className="font-semibold">Registry</p>
              <p className="text-xs text-stone-400">Compliance &amp; automation packs</p>
            </div>
          </a>
          <a href="/tools/conduct-cli" className="flex items-center gap-3 px-4 py-2.5 text-sm text-stone-700 hover:bg-stone-50 transition-colors">
            <span className="text-indigo-600 font-bold text-base">◈</span>
            <div>
              <p className="font-semibold">Conduct CLI</p>
              <p className="text-xs text-stone-400">Terminal governance + token savings</p>
            </div>
          </a>
          <div className="border-t border-stone-100 my-1" />
          <a href="/frameworks" className="flex items-center gap-3 px-4 py-2.5 text-sm text-stone-700 hover:bg-stone-50 transition-colors">
            <span>📐</span>
            <div>
              <p className="font-semibold">Compliance frameworks</p>
              <p className="text-xs text-stone-400">EU AI Act · NIST · ISO 42001 · OWASP</p>
            </div>
          </a>
        </div>
      </div>
    </div>
  )
}


function SolutionsDropdown() {
  return (
    <div className="relative group">
      <a href="#" className="flex items-center gap-1 text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">
        Solutions
        <svg width="12" height="12" viewBox="0 0 12 12" fill="currentColor" className="opacity-40 mt-0.5"><path d="M2 4l4 4 4-4"/></svg>
      </a>
      <div className="absolute left-0 top-full pt-2 hidden group-hover:block z-50 min-w-[260px]">
        <div className="bg-white border border-stone-200 rounded-xl shadow-lg py-2">
          <p className="px-4 pt-2 pb-1 text-[10px] font-bold uppercase tracking-widest text-stone-400">By role</p>
          <a href="/solutions/engineering-leaders" className="flex items-center gap-3 px-4 py-2 text-sm text-stone-700 hover:bg-stone-50 transition-colors">
            <div>
              <p className="font-semibold">Engineering leaders</p>
            </div>
          </a>
          <a href="/solutions/security-compliance" className="flex items-center gap-3 px-4 py-2 text-sm text-stone-700 hover:bg-stone-50 transition-colors">
            <div>
              <p className="font-semibold">Security &amp; compliance</p>
            </div>
          </a>

          <div className="my-1 border-t border-stone-100" />

          <p className="px-4 pt-2 pb-1 text-[10px] font-bold uppercase tracking-widest text-stone-400">By outcome</p>
          <a href="/solutions/security-loop" className="flex items-center gap-3 px-4 py-2 text-sm text-stone-700 hover:bg-stone-50 transition-colors">
            <div>
              <p className="font-semibold">Security Loop</p>
              <p className="text-xs text-stone-400">Scan to fix, closed</p>
            </div>
          </a>
          <a href="/solutions/action-governance" className="flex items-center gap-3 px-4 py-2 text-sm text-stone-700 hover:bg-stone-50 transition-colors">
            <div>
              <p className="font-semibold">Action governance</p>
              <p className="text-xs text-stone-400">Policy in front of every action</p>
            </div>
          </a>
          <a href="/solutions/memory-hardening" className="flex items-center gap-3 px-4 py-2 text-sm text-stone-700 hover:bg-stone-50 transition-colors">
            <div>
              <p className="font-semibold">Memory hardening</p>
              <p className="text-xs text-stone-400">OWASP ASI06 at the wire</p>
            </div>
          </a>
          <a href="/solutions/okta-plus-conduct" className="flex items-center gap-3 px-4 py-2 text-sm text-stone-700 hover:bg-stone-50 transition-colors">
            <div>
              <p className="font-semibold">Okta + Conduct</p>
              <p className="text-xs text-stone-400">Identity plus runtime governance</p>
            </div>
          </a>

          <div className="my-1 border-t border-stone-100" />

          <p className="px-4 pt-2 pb-1 text-[10px] font-bold uppercase tracking-widest text-stone-400">By industry</p>
          <a href="/solutions/financial-services" className="flex items-center gap-3 px-4 py-2 text-sm text-stone-700 hover:bg-stone-50 transition-colors">
            <div>
              <p className="font-semibold">Financial services</p>
              <p className="text-xs text-stone-400">SR 11-7 interim controls</p>
            </div>
          </a>
          <a href="/solutions/life-sciences" className="flex items-center gap-3 px-4 py-2 text-sm text-stone-700 hover:bg-stone-50 transition-colors">
            <div>
              <p className="font-semibold">Life sciences</p>
              <p className="text-xs text-stone-400">FDA CSA + GMLP + GAMP 5</p>
            </div>
          </a>

          <div className="my-1 border-t border-stone-100" />

          <a href="/use-cases" className="flex items-center gap-3 px-4 py-2 text-sm text-stone-700 hover:bg-stone-50 transition-colors">
            <div>
              <p className="font-semibold">All use cases</p>
              <p className="text-xs text-stone-400">Nine surfaces we operate in</p>
            </div>
          </a>
          <a href="/deployment" className="flex items-center gap-3 px-4 py-2 text-sm text-stone-700 hover:bg-stone-50 transition-colors">
            <div>
              <p className="font-semibold">Deployment options</p>
              <p className="text-xs text-stone-400">SaaS · Cloud · On-premise</p>
            </div>
          </a>
        </div>
      </div>
    </div>
  )
}

/* ─── Hero ─────────────────────────────────────────────────────────────── */

function HeroSection() {
  const chips = [
    "22 agent templates",
    "4 AI providers",
    "Shadow AI discovery",
    "Real-time spend limits",
    "Full audit trail",
    "Zero infrastructure changes",
  ]
  return (
    <section className="max-w-5xl mx-auto px-6 pt-20 pb-16 text-center">
      <BootSequence />
      <div className="inline-flex items-center gap-2 bg-indigo-50 text-indigo-700 px-4 py-1.5 rounded-full text-xs font-semibold uppercase tracking-widest mb-8">
        <span className="w-1.5 h-1.5 rounded-full bg-indigo-500 inline-block" />
        What your agent does. Not just what it can.
      </div>
      <h1 className="text-5xl sm:text-6xl font-black tracking-tight text-stone-900 leading-[1.05] mb-6">
        Your AI agents are taking real actions. Nobody is watching.
      </h1>
      <p className="text-xl text-stone-500 max-w-3xl mx-auto leading-relaxed mb-6">
        Your agent can call any tool. Conduct decides which calls actually run. Across Claude Code, Claude.ai, Codex, ChatGPT, Cursor, Copilot, Windsurf.
      </p>
      <p className="text-base text-stone-500 max-w-3xl mx-auto leading-relaxed mb-8 italic">
        Your identity provider tells you who your agents are. Guard governs what they do.
      </p>
      <p className="font-mono text-sm sm:text-base text-stone-700 max-w-3xl mx-auto mb-8">
        What the agent tried. What Guard allowed. What the reviewer signed. What the chain proves.
      </p>
      <div className="flex flex-wrap items-center justify-center gap-2 mb-10">
        {chips.map(chip => (
          <span key={chip} className="bg-stone-100 text-stone-700 rounded-full px-3 py-1 text-xs font-semibold">
            {chip}
          </span>
        ))}
      </div>
      <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
        <CtaLink className="rounded-xl bg-stone-900 text-white px-7 py-3.5 text-base font-semibold hover:bg-stone-700 transition-colors w-full sm:w-auto text-center" />
        <a href="https://cal.com/sudhi-seshachala-pks7pd" target="_blank" rel="noopener" className="rounded-xl border border-stone-300 bg-white text-stone-700 px-7 py-3.5 text-base font-semibold hover:border-stone-400 hover:shadow-sm transition-all w-full sm:w-auto text-center">
          Book a Demo
        </a>
      </div>
      <p className="text-xs text-stone-400 mt-4">Free tier · No infrastructure changes · Works in minutes</p>
    </section>
  )
}

/* ─── Control Plane Diagram ────────────────────────────────────────────── */

function ControlPlaneSection() {
  return (
    <section className="py-14 px-6 border-y border-stone-100 bg-stone-50">
      <div className="max-w-2xl mx-auto text-center">
        <p className="text-xs font-semibold uppercase tracking-widest text-stone-400 mb-8">Where Conduct sits</p>
        <div className="flex flex-col items-center gap-1 font-mono text-sm">
          <div className="bg-white border border-stone-200 rounded-xl px-8 py-3 text-stone-700 font-semibold shadow-sm w-64">
            AI Agents + Developers
          </div>
          <div className="text-stone-300 text-lg">↓</div>
          <div className="bg-stone-900 text-white rounded-xl px-8 py-3 font-bold shadow-md w-64">
            ConductGuard
          </div>
          <div className="text-xs text-stone-400 mt-1 mb-1">Every tool call · Every LLM request · Every workflow</div>
          <div className="text-stone-300 text-lg">↓</div>
          <div className="bg-white border border-stone-200 rounded-xl px-8 py-3 text-stone-700 font-semibold shadow-sm w-64">
            Foundation Models
          </div>
        </div>
        <p className="text-sm text-stone-500 mt-8 max-w-md mx-auto">
          Conduct makes compliance structural. Not documented after the fact. Enforced before execution.
        </p>
      </div>
    </section>
  )
}

/* ─── Trust Bar ────────────────────────────────────────────────────────── */

function CeoQuoteSection() {
  return (
    <section className="max-w-3xl mx-auto px-6 py-12">
      <blockquote className="border-l-4 border-indigo-500 pl-6 py-2">
        <p className="text-xl text-stone-700 leading-relaxed italic mb-4">
          &ldquo;What impressed me most about Conduct AI is that it approaches AI governance
          as a business capability, not just a technical feature. By bringing together cost
          management, security controls, and compliance oversight in a scalable architecture,
          it addresses a need that many enterprises are actively trying to solve.&rdquo;
        </p>
        <footer className="text-sm text-stone-500">
          <span className="font-semibold text-stone-700">Ram Prasad</span>
          {" · "}
          CEO, Delence
        </footer>
      </blockquote>
    </section>
  )
}

function TrustBarSection() {
  const integrations = ["GitHub", "Slack", "Linear", "Jira", "Claude", "GPT", "Gemini", "VS Code"]
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
      headline: "Your team shipped a Friday deploy that an AI forced through unreviewed.",
      detail: "You found out on Monday. The AI ran the command at 3pm. Nobody saw it.",
    },
    {
      num: "02",
      icon: "💸",
      headline: "Finance asked what AI cost last quarter. Engineering had no answer.",
      detail: "The bill arrived. The sprint was over. The conversation was already awkward.",
    },
    {
      num: "03",
      icon: "📄",
      headline: "You have an AI usage policy. It didn't stop anything.",
      detail: "It exists in a doc. It wasn't running at the moment the agent acted. That's the only moment that matters. Without runtime enforcement, agents experience permission drift, accumulating authority across tool calls that no single approval authorised.",
    },
    {
      num: "04",
      icon: "🔁",
      headline: "The PR review script broke when the engineer who wrote it left.",
      detail: "It lived in their terminal. It drifted. It broke. It left with them.",
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
          Your team is already using Claude, Codex, ChatGPT, Cursor, Copilot, and Windsurf. But when something breaks, there&apos;s no trail, no policy, no audit log, no budget control.
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
            One platform. Every AI action, governed.
          </h2>
          <p className="text-stone-500 max-w-xl mx-auto leading-relaxed">
            Guard covers both surfaces you need. A registry of ready-to-run agents, and wire enforcement that makes every call a policy decision. Same platform, same audit chain.
          </p>
        </div>
        <div className="grid md:grid-cols-2 gap-5">

          {/* Automate — indigo/light */}
          <div className="rounded-2xl bg-indigo-50 border border-indigo-100 p-8 flex flex-col gap-5">
            <span className="inline-flex px-3 py-1 rounded-full bg-indigo-600 text-white text-xs font-bold uppercase tracking-wider w-fit">
              ⚡ Automate
            </span>
            <a href="/sdd" className="flex items-center gap-2 text-xs font-semibold text-indigo-600 hover:text-indigo-800 transition-colors">
              <span>📐</span> Start with a spec →
            </a>
            <div>
              <h3 className="text-2xl font-bold text-stone-900 tracking-tight mb-2">Ship faster with agent templates</h3>
              <p className="text-stone-600 leading-relaxed text-sm">
                The PR review that used to wait for a senior engineer now runs in 90 seconds. The security scan that lived in one person&apos;s terminal now runs on every push. 22 templates, ready to install.
              </p>
            </div>
            <ul className="space-y-2.5 flex-1">
              {[
                "PR review · autopilot fix · security scan",
                "CI failure triage · flaky test detection",
                "Release notes · postmortem drafter · docs drift",
                "YAML you own, no vendor lock-in",
                "Runs on Claude, GPT, or Gemini",
              ].map(f => (
                <li key={f} className="flex items-center gap-2.5 text-sm text-stone-700">
                  <span className="w-5 h-5 rounded-full bg-indigo-600 text-white flex items-center justify-center text-xs font-bold flex-shrink-0">✓</span>
                  {f}
                </li>
              ))}
            </ul>
            <a href="/registry" className="mt-auto rounded-xl bg-stone-900 text-white px-6 py-3 text-sm font-semibold hover:bg-stone-700 transition-colors text-center">
              Browse the Registry →
            </a>
          </div>

          {/* Guard — dark */}
          <div className="rounded-2xl bg-stone-900 border border-stone-800 p-8 flex flex-col gap-5">
            <span className="inline-flex px-3 py-1 rounded-full bg-white/10 text-stone-300 text-xs font-bold uppercase tracking-wider w-fit">
              🛡️ Guard
            </span>
            <div>
              <h3 className="text-2xl font-bold text-white tracking-tight mb-2">Every agent action is structurally governed</h3>
              <p className="text-stone-400 leading-relaxed text-sm">
                One env var routes every LLM call through Guard, regardless of framework, language, or developer discipline. Actions Guard denies are not unlikely. They are structurally impossible. Guard enforces policy at the execution boundary: one layer below the agent, one layer above the enterprise system.
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

/* ─── Stack Strip ──────────────────────────────────────────────────────── */

function StackStripSection() {
  const steps = [
    {
      step: "01",
      label: "Team OS",
      href: "/team-os",
      badge: "Free",
      badgeColor: "bg-emerald-100 text-emerald-700",
      icon: "📄",
      title: "Write down your standards",
      desc: "CLAUDE.md gives agents project memory. REVIEW.md sets the quality bar. Standards encode how your team handles auth, security, and migrations.",
      cta: "Get the templates →",
    },
    {
      step: "02",
      label: "SDD",
      href: "/sdd",
      badge: "Spec first",
      badgeColor: "bg-indigo-100 text-indigo-700",
      icon: "📐",
      title: "Spec before you build",
      desc: "Generate a SPEC.md before agents touch code. Every decision has a why. Drift detection tells you when implementation diverges from intent.",
      cta: "Generate your spec →",
    },
    {
      step: "03",
      label: "Guard",
      href: "/guard",
      badge: "Enforcement",
      badgeColor: "bg-stone-200 text-stone-700",
      icon: "🛡️",
      title: "Enforce it at the MCP layer",
      desc: "Guard intercepts every AI tool call before it runs. One policy across Claude Code, Cursor, Copilot, and every MCP client. Blocks, logs, audits automatically.",
      cta: "Explore Guard →",
    },
  ]

  return (
    <section className="bg-stone-50 border-y border-stone-100 py-16 px-6">
      <div className="max-w-5xl mx-auto">
        <div className="text-center mb-10">
          <p className="text-xs font-semibold uppercase tracking-widest text-stone-400 mb-3">The full stack</p>
          <h2 className="text-2xl sm:text-3xl font-bold text-stone-900 tracking-tight">
            From standards to enforcement: three layers, one platform.
          </h2>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          {steps.map((s) => (
            <a key={s.step} href={s.href} className="group rounded-2xl bg-white border border-stone-200 p-6 hover:border-stone-400 hover:shadow-md transition-all flex flex-col gap-4">
              <div className="flex items-center justify-between">
                <span className="text-2xl">{s.icon}</span>
                <div className="flex items-center gap-2">
                  <span className="text-xs font-bold text-stone-300">{s.step}</span>
                  <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${s.badgeColor}`}>{s.badge}</span>
                </div>
              </div>
              <div>
                <p className="text-xs font-bold uppercase tracking-widest text-stone-400 mb-1">{s.label}</p>
                <h3 className="font-bold text-stone-900 text-base mb-2">{s.title}</h3>
                <p className="text-sm text-stone-500 leading-relaxed">{s.desc}</p>
              </div>
              <p className="text-xs font-semibold text-stone-700 group-hover:text-stone-900 transition-colors mt-auto">{s.cta}</p>
            </a>
          ))}
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
      headline: "Force-deploy to production, intercepted",
      detail: "AI attempted vercel deploy --prod --force at 3:11pm on a Friday. Guard blocked it before it executed.",
      badge: "BLOCKED",
      badgeColor: "bg-red-500",
    },
    {
      rule: "no-secret-in-commit-msg",
      headline: "Secret embedded in git commit, caught",
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

        {/* Two-column: left = text + chips, right = narrative card */}
        <div className="grid md:grid-cols-2 gap-12 items-center mb-16">

          {/* Left */}
          <div>
            <p className="text-xs font-semibold uppercase tracking-widest text-indigo-500 mb-4">What governance actually tells you</p>
            <h2 className="text-3xl sm:text-4xl font-bold text-stone-900 tracking-tight leading-tight mb-4">
              Every AI session, explained in plain English.
            </h2>
            <p className="text-stone-500 leading-relaxed mb-8">
              Guard watches every tool call across every AI session: Claude Code, Claude.ai, Claude Desktop, Codex CLI, Codex Desktop, ChatGPT, Cursor, Copilot, Windsurf. At the end of each day, it surfaces one sentence that tells your team what happened, what was blocked, and what it cost.
            </p>
            <div className="flex flex-wrap gap-2 mb-6">
              <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-red-50 border border-red-100 text-xs font-semibold text-red-600">🚫 6 deploys intercepted</span>
              <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-amber-50 border border-amber-100 text-xs font-semibold text-amber-600">⚠ 2 destructive commands warned</span>
              <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-indigo-50 border border-indigo-100 text-xs font-semibold text-indigo-600">🔒 589 PII events screened</span>
              <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-emerald-50 border border-emerald-100 text-xs font-semibold text-emerald-600">⚡ $235 saved by tooling</span>
            </div>
            <a href="/guard" className="text-sm font-semibold text-indigo-600 hover:text-indigo-700 transition-colors">
              See the full Insights tab →
            </a>
            <p className="mt-6 text-xs text-stone-400 leading-relaxed border-t border-stone-100 pt-4">
              Whatever your team runs in Claude, whether a diligence desk, a security audit OS, or an engineering autopilot, ConductGuard is the enforcement layer that makes it safe to hand to an executive.
            </p>
          </div>

          {/* Right — narrative card */}
          <div className="rounded-2xl border border-stone-200 bg-white p-6 shadow-sm">
            <div className="flex items-center justify-between mb-4 pb-4 border-b border-stone-100">
              <div className="flex items-center gap-2">
                <span className="text-indigo-600 font-bold">✦</span>
                <div>
                  <p className="text-xs font-semibold text-stone-500">Guard · AI Narrative</p>
                  <p className="text-[10px] text-stone-400">dev@yourteam.com</p>
                </div>
              </div>
              <div className="flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full bg-emerald-500 inline-block animate-pulse" />
                <span className="text-xs font-semibold text-emerald-600">Live</span>
              </div>
            </div>
            <p className="text-sm text-stone-700 leading-relaxed mb-6">
              You spent <strong>$245/day</strong> on AI this period across <span className="text-indigo-600 font-medium">claude-code</span>, <span className="text-indigo-600 font-medium">codex</span>, and <span className="text-indigo-600 font-medium">cursor</span>. Guard intercepted <strong>6 production deploys</strong> before they ran unreviewed, warned on <strong>2 destructive commands</strong>, and screened <strong>589 events for PII</strong> before they reached any LLM. Claude Code dominates at <strong>96% of total spend</strong>. RTK and Booster offset <strong>$235</strong>, 5.6% back.
            </p>
            <div className="grid grid-cols-4 gap-3 mb-4">
              {kpis.map(k => (
                <div key={k.label} className="text-center">
                  <p className={`text-xl font-black tracking-tight ${k.color}`}>{k.value}</p>
                  <p className="text-[10px] text-stone-400 mt-0.5">{k.label}</p>
                </div>
              ))}
            </div>
            <div className="pt-4 border-t border-stone-100 flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 inline-block" />
              <span className="text-[10px] text-stone-400">Generated Jun 19, 2026 · 5,985 events · 25 sessions</span>
            </div>
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
            <p className="text-sm font-semibold text-stone-900 mb-1">What would have happened without Guard?</p>
            <p className="text-sm text-stone-500 leading-relaxed">
              The production deploy would have executed. Average cost of a prod incident at a mid-market company: $15K–$50K. $235 saved on tooling is nice. $50K in a prevented outage is a different conversation.
            </p>
          </div>
          <CtaLink className="flex-shrink-0 rounded-xl bg-indigo-600 text-white px-6 py-3 text-sm font-bold hover:bg-indigo-700 transition-colors whitespace-nowrap" />
        </div>

      </div>
    </section>
  )
}

/* ─── Personas ─────────────────────────────────────────────────────────── */

const personas = [
  {
    role: "Engineering Leaders",
    title: "Your team is using 4 AI tools. You don't know which ones, what they cost, or what they did.",
    desc: "Conduct gives you a single view across every tool, every developer, every session, without adding any process to your team's workflow.",
    outcomes: [
      "See every AI tool your team uses, in one dashboard",
      "Know what AI is costing you, by person and by project",
      "Enforce your engineering standards automatically",
      "Answer security and compliance questions on demand",
    ],
  },
  {
    role: "IT & Security Leaders",
    title: "Your AI usage policy exists in a doc. It has never once stopped an agent.",
    desc: "Conduct enforces policy at the layer where agents actually run. Not in a review meeting, not in a Notion page. At the moment the tool call happens.",
    outcomes: [
      "One policy layer across Claude, Codex, ChatGPT, Cursor, Copilot, Windsurf. Every surface your team uses.",
      "No infrastructure changes. Works with your existing stack",
      "Role-based policies for different teams and access levels",
      "Spend budgets per developer, per tool, per project",
    ],
  },
  {
    role: "Security & Compliance",
    title: "Compliance asked for an AI audit trail. You had nothing to show them.",
    desc: "Every tool call, every decision, every developer, logged from day one. Export the audit trail in 30 seconds. Answer any question on demand.",
    outcomes: [
      "Credentials and PII blocked before they reach any LLM",
      "Every tool call logged with decision, rule, and developer identity",
      "Security scanning on every PR, automatic not manual",
      "Compliance audit trail exportable on demand",
    ],
  },
]

/* ─── Guard Learns Teaser ──────────────────────────────────────────────── */

function GuardLearnsTeaser() {
  return (
    <div className="bg-stone-50 border-y border-stone-100 py-8 px-6">
      <div className="max-w-5xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-4">
        <p className="text-sm text-stone-600 leading-relaxed">
          <span className="font-semibold text-stone-900">Guard learns as it runs.</span>{" "}
          Every session makes the next one more accurate for your team.
        </p>
        <a href="/guard" className="flex-shrink-0 text-sm font-semibold text-indigo-600 hover:text-indigo-700 transition-colors whitespace-nowrap">
          See how it works →
        </a>
      </div>
    </div>
  )
}

/* ─── Personas ─────────────────────────────────────────────────────────── */

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

function DemoVideoSection() {
  return (
    <section className="py-24 px-6 bg-stone-950">
      <div className="max-w-4xl mx-auto text-center">
        <p className="text-xs font-semibold uppercase tracking-widest text-indigo-400 mb-3">See it in action</p>
        <h2 className="text-3xl sm:text-4xl font-black text-white tracking-tight leading-tight mb-10">
          Watch ConductGuard block a privilege escalation in real time
        </h2>
        <div className="relative w-full" style={{ paddingBottom: "56.25%" }}>
          <iframe
            className="absolute inset-0 w-full h-full rounded-2xl"
            src="https://www.youtube.com/embed/zY8JzniqzG8"
            title="ConductGuard blocks privilege escalation"
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
            allowFullScreen
          />
        </div>
      </div>
    </section>
  )
}

function DeploymentStripSection() {
  const tiers = [
    { icon: "☁️", name: "SaaS", desc: "Up in minutes. No infra." },
    { icon: "🏢", name: "Cloud (BYOC)", desc: "Your AWS / GCP / Azure account." },
    { icon: "🔒", name: "On-premise", desc: "Air-gapped. Your data never leaves." },
  ]
  return (
    <section className="py-16 px-6 bg-stone-50 border-y border-stone-100">
      <div className="max-w-4xl mx-auto text-center">
        <p className="text-xs font-semibold uppercase tracking-widest text-stone-400 mb-6">Flexible deployment</p>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-8">
          {tiers.map(t => (
            <div key={t.name} className="bg-white rounded-2xl border border-stone-200 px-6 py-5 text-left">
              <div className="text-2xl mb-2">{t.icon}</div>
              <p className="font-bold text-stone-900 text-sm">{t.name}</p>
              <p className="text-stone-500 text-xs mt-1">{t.desc}</p>
            </div>
          ))}
        </div>
        <a href="/deployment" className="text-sm font-semibold text-indigo-600 hover:text-indigo-700 transition-colors">
          Compare deployment options →
        </a>
      </div>
    </section>
  )
}

function FinalCTASection() {
  return (
    <section className="py-24 px-6 bg-gradient-to-br from-indigo-600 to-violet-600">
      <div className="max-w-3xl mx-auto text-center">
        <h2 className="text-3xl sm:text-4xl font-black text-white tracking-tight leading-tight mb-4">
          Your team is already<br />using AI agents.<br />Conduct is how you<br />run them and govern them.
        </h2>
        <p className="text-indigo-200 text-lg leading-relaxed mb-10 max-w-xl mx-auto">
          GitHub gives the CISO a setting. ConductGuard gives them enforcement.
        </p>
        <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
          <CtaLink className="rounded-xl bg-white text-indigo-600 px-7 py-3.5 text-base font-bold hover:bg-indigo-50 transition-colors w-full sm:w-auto text-center" />
          <a href="https://cal.com/sudhi-seshachala-pks7pd" target="_blank" rel="noopener" className="rounded-xl border border-white/40 text-white px-7 py-3.5 text-base font-semibold hover:bg-white/10 transition-colors w-full sm:w-auto text-center">
            Book a Demo
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
            <p className="text-sm text-stone-400 max-w-xs leading-relaxed">Runtime AI Governance for Engineering Teams. Platform or partnership. You choose how.</p>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-8">
            {[
              { heading: "Product", links: [["Team OS", "/team-os"], ["Guard", "/guard"], ["Use cases", "/use-cases"], ["Registry", "/registry"], ["CLI", "/tools/conduct-cli"], ["Frameworks", "/frameworks"]] as [string, string][] },
              { heading: "Solutions", links: [["Engineering leaders", "/solutions/engineering-leaders"], ["Security & compliance", "/solutions/security-compliance"], ["Security Loop", "/solutions/security-loop"], ["Action governance", "/solutions/action-governance"], ["Memory hardening", "/solutions/memory-hardening"], ["Okta + Conduct", "/solutions/okta-plus-conduct"], ["Financial services", "/solutions/financial-services"], ["Life sciences", "/solutions/life-sciences"], ["All use cases", "/use-cases"], ["Deployment options", "/deployment"]] as [string, string][] },
              { heading: "Company", links: [["About", "/about"], /* ["Partners", "/partners"], */ ["Blog", "/blog"]] as [string, string][] },
              { heading: "Resources", links: [["Docs", "/docs"], ["Open source", "/open-source"], ["GitHub", "https://github.com/sseshachala/conduct-cli"]] as [string, string][] },
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
        <div className="border-t border-stone-100 pt-6 flex flex-col sm:flex-row justify-between items-center gap-4 text-xs text-stone-400">
          <span>© {new Date().getFullYear()} Conduct AI. All rights reserved. · Patent Pending (US 64/109,502)</span>
          <div className="flex items-center gap-4">
            <a href="https://www.linkedin.com/company/conductai/" target="_blank" rel="noopener noreferrer" className="hover:text-stone-700 transition-colors" aria-label="LinkedIn">
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="w-4 h-4"><path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433a2.062 2.062 0 0 1-2.063-2.065 2.064 2.064 0 1 1 2.063 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z"/></svg>
            </a>
            <a href="https://www.youtube.com/@Conductai" target="_blank" rel="noopener noreferrer" className="hover:text-stone-700 transition-colors" aria-label="YouTube">
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="w-4 h-4"><path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"/></svg>
            </a>
            <span>Envisioned, designed and developed with love from Houston</span>
          </div>
        </div>
      </div>
    </footer>
  )
}
