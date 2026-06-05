"use client"

import { useState } from "react"

export default function SecurityLoopPage() {
  return (
    <div className="min-h-screen bg-white flex flex-col">
      <Nav />
      <main>
        <HeroSection />
        <ProblemSection />
        <HowItWorksSection />
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

function Nav() {
  return (
    <header className="px-6 py-5 flex items-center justify-between max-w-6xl mx-auto w-full">
      <div className="flex items-center">
        <a href="/">
          <img src="/logo.png" alt="Conduct AI" className="h-10 w-auto" />
        </a>
      </div>
      <div className="flex items-center gap-4">
        <a
          href="/blog"
          className="flex items-center gap-1.5 text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors"
        >
          Blog
        </a>
        <a
          href="/marketplace"
          className="flex items-center gap-1.5 text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors"
        >
          Agent Templates
        </a>
        <a
          href="/tools"
          className="flex items-center gap-1.5 text-sm font-medium text-indigo-600 hover:text-indigo-900 transition-colors"
        >
          Tools
        </a>
        <a
          href="/benchmark"
          className="flex items-center gap-1.5 text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors"
        >
          Benchmark
        </a>
        <a
          href="/docs"
          className="flex items-center gap-1.5 text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors"
        >
          Docs
        </a>
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
    <section className="flex flex-col items-center justify-center px-6 pt-16 pb-24 text-center">
      <div className="inline-flex items-center gap-2 bg-indigo-50 text-indigo-700 border border-indigo-100 text-xs font-semibold px-3 py-1.5 rounded-full mb-8 uppercase tracking-widest">
        Security Loop · Early Access
      </div>

      <h1 className="text-5xl sm:text-6xl font-bold text-stone-900 leading-[1.1] tracking-tight max-w-3xl">
        AI finds the bug. Conduct{" "}
        <span className="text-indigo-600">closes the loop.</span>
      </h1>

      <p className="mt-6 text-xl text-stone-500 max-w-2xl leading-relaxed">
        Connect Claude Code, Codex, and Cursor to Conduct once. Every vulnerability they surface gets
        automatically triaged, fixed, and shipped as a PR — with a full audit trail.
      </p>

      <div className="mt-10 flex flex-col sm:flex-row items-center gap-4">
        <a
          href="mailto:sudhi@b2bsphere.com?subject=Security Loop Early Access"
          className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-6 py-3 text-sm font-semibold text-white hover:bg-indigo-700 transition-colors"
        >
          Join Early Access
        </a>
        <a
          href="#how-it-works"
          className="inline-flex items-center gap-2 rounded-xl border border-stone-200 bg-white px-6 py-3 text-sm font-semibold text-stone-700 hover:border-stone-300 hover:shadow-sm transition-all"
        >
          Read the spec →
        </a>
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
    bg: "bg-white",
  },
  {
    icon: "🧩",
    title: "No standard pipeline",
    desc: "Every tool has its own output format. Your team stitches together findings manually — if at all. There's no consistent triage, no severity tracking, no audit trail.",
    border: "border-amber-100",
    bg: "bg-white",
  },
  {
    icon: "⏱️",
    title: "Detection ≠ remediation",
    desc: "Finding a bug is 10% of the work. The other 90% — issue creation, triage, fix, PR, review — still happens manually. Mean time to fix stays in days.",
    border: "border-orange-100",
    bg: "bg-white",
  },
]

function ProblemSection() {
  return (
    <section className="bg-stone-50 px-6 py-20">
      <div className="max-w-5xl mx-auto">
        <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest text-center mb-3">The problem</p>
        <h2 className="text-3xl font-bold text-stone-900 text-center mb-4">
          The gap no one closes.
        </h2>
        <p className="text-center text-stone-500 text-sm max-w-2xl mx-auto mb-12">
          AI coding tools are getting better at finding vulnerabilities. But there&apos;s still no
          standard way to route those findings into a fix pipeline. They fall through the cracks.
        </p>

        <div className="grid sm:grid-cols-3 gap-6">
          {PAIN_CARDS.map(card => (
            <div key={card.title} className={`rounded-2xl border ${card.border} ${card.bg} px-7 py-7 flex flex-col gap-4`}>
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
  {
    n: "1",
    title: "AI surfaces a finding",
    desc: "Claude Code, Codex, Cursor, or Copilot detects a vulnerability",
    icon: "◈",
    color: "text-indigo-600",
    bg: "bg-indigo-50 border-indigo-200",
  },
  {
    n: "2",
    title: "Classify",
    desc: "Severity, type, file, and line number captured automatically",
    icon: "≋",
    color: "text-violet-600",
    bg: "bg-violet-50 border-violet-200",
  },
  {
    n: "3",
    title: "GitHub issue",
    desc: "Issue created with labels, structured body, and severity badge",
    icon: "◎",
    color: "text-blue-600",
    bg: "bg-blue-50 border-blue-200",
  },
  {
    n: "4",
    title: "Validate",
    desc: "Security scanner confirms the finding before any fix runs",
    icon: "⊙",
    color: "text-teal-600",
    bg: "bg-teal-50 border-teal-200",
  },
  {
    n: "5",
    title: "Fix on branch",
    desc: "Agent forks the repo and applies the fix on a dedicated branch",
    icon: "⟁",
    color: "text-emerald-600",
    bg: "bg-emerald-50 border-emerald-200",
  },
  {
    n: "6",
    title: "PR opened",
    desc: "Pull request opened back to the repo, ready for your review",
    icon: "◭",
    color: "text-amber-600",
    bg: "bg-amber-50 border-amber-200",
  },
  {
    n: "7",
    title: "Slack notification",
    desc: "Alert posted to #security channel with full context",
    icon: "◉",
    color: "text-rose-600",
    bg: "bg-rose-50 border-rose-200",
  },
  {
    n: "8",
    title: "Audit trail",
    desc: "Tool → finding → fix → PR → cost → duration, all recorded",
    icon: "⬡",
    color: "text-stone-600",
    bg: "bg-stone-50 border-stone-200",
  },
]

function HowItWorksSection() {
  return (
    <section id="how-it-works" className="px-6 py-20">
      <div className="max-w-6xl mx-auto">
        <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest text-center mb-3">How it works</p>
        <h2 className="text-3xl font-bold text-stone-900 text-center mb-12">
          From finding to PR — automatically.
        </h2>

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          {PIPELINE_STEPS.map((step, idx) => (
            <div key={step.n} className="flex flex-col items-center gap-0">
              <div className={`rounded-2xl border ${step.bg} px-4 py-5 flex flex-col items-center text-center w-full gap-3`}>
                <span className={`text-2xl font-black ${step.color}`}>{step.icon}</span>
                <div>
                  <p className="text-[10px] font-bold text-stone-400 uppercase tracking-widest mb-1">Step {step.n}</p>
                  <p className="text-sm font-semibold text-stone-900 mb-1">{step.title}</p>
                  <p className="text-xs text-stone-500 leading-relaxed">{step.desc}</p>
                </div>
              </div>
              {idx < PIPELINE_STEPS.length - 1 && (
                <div className="hidden sm:flex items-center justify-center w-full mt-2">
                  <span className="text-stone-300 text-sm">→</span>
                </div>
              )}
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
    color: "text-indigo-600",
    bg: "bg-indigo-50 border-indigo-200",
  },
  {
    title: "Tool-agnostic",
    desc: "Claude Code, Codex, Cursor, and GitHub Copilot. One workspace, one audit trail, regardless of which tool found it.",
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
        <h2 className="text-3xl font-bold text-stone-900 text-center mb-4">
          Built to close the loop, not just find the bug.
        </h2>
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
        <h2 className="text-3xl font-bold text-white text-center mb-12">
          Humans stay in control.
        </h2>

        <div className="rounded-2xl border border-indigo-400 bg-indigo-900 px-8 py-8 flex flex-col gap-6">
          <p className="text-indigo-100 text-sm leading-relaxed">
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
                  {idx < arr.length - 1 && (
                    <span className="text-stone-600">→</span>
                  )}
                </span>
              ))}
            </div>
          </div>

          <div className="flex items-start gap-3 bg-indigo-800 rounded-xl px-5 py-4 border border-indigo-600">
            <span className="text-lg shrink-0">🔐</span>
            <p className="text-sm text-indigo-200 leading-relaxed">
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
        <h2 className="text-3xl font-bold text-stone-900 text-center mb-4">
          Compliance evidence, built in.
        </h2>
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
          <div className="px-6 py-5">
            <div className="grid grid-cols-8 gap-4 items-center">
              <code className="font-mono text-xs text-indigo-700 font-semibold">SL-001</code>
              <p className="text-xs text-stone-700">claude-bughunter</p>
              <span className="inline-flex items-center text-[10px] font-semibold bg-red-50 text-red-700 border border-red-100 px-2 py-0.5 rounded-full">HIGH</span>
              <p className="text-xs text-stone-500">elementalsouls/cbh</p>
              <p className="text-xs text-stone-500">Jun 5 2026</p>
              <p className="text-xs text-stone-500">sudhi@</p>
              <a href="#" className="text-xs text-indigo-600 hover:text-indigo-800 transition-colors">PR #15</a>
              <span className="inline-flex items-center text-[10px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-100 px-2 py-0.5 rounded-full">Merged</span>
            </div>
          </div>
        </div>

        <p className="text-center text-xs text-stone-400 mt-4">
          Sample audit row — exported as CSV or JSON for SOC&nbsp;2 review.
        </p>
      </div>
    </section>
  )
}

/* ─── Footer CTA ───────────────────────────────────────────────────────── */

function FooterCTASection() {
  return (
    <section className="bg-stone-50 px-6 py-20 text-center">
      <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-4">Early Access</p>
      <h2 className="text-3xl font-bold text-stone-900 mb-4">
        Security Loop is in early access.
      </h2>
      <p className="text-stone-500 mb-8 max-w-lg mx-auto leading-relaxed">
        We&apos;re onboarding a small group of teams to validate the pipeline end-to-end.
        If your team uses Claude Code, Codex, or Cursor and wants findings to close automatically,
        get in touch.
      </p>

      <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
        <a
          href="mailto:sudhi@b2bsphere.com?subject=Security Loop Early Access"
          className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-6 py-3 text-sm font-semibold text-white hover:bg-indigo-700 transition-colors"
        >
          Get early access →
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
