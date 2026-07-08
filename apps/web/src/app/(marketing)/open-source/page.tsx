"use client"

import { useState } from "react"
import { CtaLink } from "@/components/marketing/CtaLink"

/* ─── Page ──────────────────────────────────────────────────────────────── */

export default function OpenSourcePage() {
  return (
    <>
      <HeroSection />
      <ProjectsSection />
      <CtaSection />
    </>
  )
}

/* ─── Hero ──────────────────────────────────────────────────────────────── */

function HeroSection() {
  return (
    <section className="max-w-5xl mx-auto px-6 pt-20 pb-12 text-center">
      <div className="inline-flex items-center gap-2 bg-stone-100 text-stone-600 px-4 py-1.5 rounded-full text-xs font-semibold uppercase tracking-widest mb-8">
        <span className="w-1.5 h-1.5 rounded-full bg-stone-400 inline-block" />
        Open Source
      </div>
      <h1 className="text-5xl sm:text-6xl font-black tracking-tight text-stone-900 leading-[1.05] mb-5">
        Open Source
      </h1>
      <p className="text-xl text-stone-500 max-w-2xl mx-auto leading-relaxed">
        The tools underneath ConductAI — free to use, inspect, and contribute to.
      </p>
    </section>
  )
}

/* ─── Projects ──────────────────────────────────────────────────────────── */

function ProjectsSection() {
  return (
    <section className="max-w-5xl mx-auto px-6 pb-20 flex flex-col gap-8">
      <ProjectCard
        name="Agent Booster"
        tagline="Context-efficient reads for Claude Code"
        description="Agent Booster intercepts Read and Grep calls and returns only the relevant symbol slices — cutting token usage 60-90% on large codebases."
        install="pip install agent-booster"
        githubUrl="https://github.com/sseshachala/agent-booster"
        guardRelation="Agent Booster runs inside your AI coding session. Guard governs what that session can do. Together: token-efficient AND policy-enforced."
        badgeColor="bg-violet-100 text-violet-700"
        badgeLabel="Python"
      />
      <ProjectCard
        name="RTK — Rust Token Killer"
        tagline="60-90% token savings on dev operations"
        description="A transparent CLI proxy that filters verbose command output (build errors, test results, git diffs) down to signal-only. Works with any AI coding tool."
        install={["cargo install rtk", "brew install rtk"]}
        githubUrl="https://github.com/sseshachala/rtk"
        guardRelation="RTK reduces the token surface area of every shell command. Guard enforces policy on every shell command. Complementary layers."
        badgeColor="bg-orange-100 text-orange-700"
        badgeLabel="Rust"
      />
    </section>
  )
}

function ProjectCard({
  name,
  tagline,
  description,
  install,
  githubUrl,
  guardRelation,
  badgeColor,
  badgeLabel,
}: {
  name: string
  tagline: string
  description: string
  install: string | string[]
  githubUrl: string
  guardRelation: string
  badgeColor: string
  badgeLabel: string
}) {
  const installLines = Array.isArray(install) ? install : [install]

  return (
    <div className="border border-stone-200 rounded-xl bg-white overflow-hidden">
      {/* Header */}
      <div className="px-8 pt-8 pb-6 border-b border-stone-100">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <div className="flex items-center gap-3 mb-1">
              <h2 className="text-2xl font-black text-stone-900 tracking-tight">{name}</h2>
              <span className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full ${badgeColor}`}>
                {badgeLabel}
              </span>
            </div>
            <p className="text-stone-500 text-sm font-medium">{tagline}</p>
          </div>
          <a
            href={githubUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 border border-stone-200 rounded-lg px-4 py-2 text-sm font-semibold text-stone-700 hover:border-stone-300 hover:shadow-sm transition-all flex-shrink-0"
          >
            <GitHubIcon />
            GitHub
          </a>
        </div>
      </div>

      {/* Body */}
      <div className="px-8 py-6 grid md:grid-cols-2 gap-8">
        <div className="flex flex-col gap-5">
          <p className="text-stone-600 text-sm leading-relaxed">{description}</p>

          <div>
            <p className="text-xs font-semibold uppercase tracking-widest text-stone-400 mb-2">Install</p>
            <div className="bg-stone-950 rounded-xl p-4 space-y-1.5">
              {installLines.map((line, i) => (
                <CopyableLine key={i} value={line} />
              ))}
            </div>
          </div>
        </div>

        <div className="border border-stone-200 rounded-xl bg-stone-50 p-5 flex flex-col gap-3">
          <div className="flex items-center gap-2">
            <span className="text-base">🛡️</span>
            <p className="text-xs font-semibold uppercase tracking-widest text-stone-500">How it relates to Guard</p>
          </div>
          <p className="text-sm text-stone-600 leading-relaxed">{guardRelation}</p>
        </div>
      </div>
    </div>
  )
}

function CopyableLine({ value }: { value: string }) {
  const [copied, setCopied] = useState(false)

  function copy() {
    navigator.clipboard.writeText(value).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1800)
    })
  }

  return (
    <div className="flex items-center justify-between gap-3 group">
      <code className="text-xs font-mono text-stone-300 flex-1">
        <span className="text-indigo-400">$ </span>
        {value}
      </code>
      <button
        onClick={copy}
        className="text-[10px] font-semibold text-stone-600 hover:text-stone-300 transition-colors opacity-0 group-hover:opacity-100 flex-shrink-0"
        aria-label={`Copy: ${value}`}
      >
        {copied ? "copied" : "copy"}
      </button>
    </div>
  )
}

function GitHubIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
      <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z" />
    </svg>
  )
}

/* ─── CTA ───────────────────────────────────────────────────────────────── */

function CtaSection() {
  return (
    <section className="border-t border-stone-200 bg-stone-50 px-6 py-14">
      <div className="max-w-5xl mx-auto text-center">
        <p className="text-stone-700 font-semibold text-lg mb-2">
          Built something on top of Guard, Booster, or RTK?
        </p>
        <p className="text-stone-500 text-sm mb-8">We&apos;d love to hear about it.</p>
        <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
          <a
            href="mailto:hello@conductai.ai"
            className="rounded-xl border border-stone-300 bg-white text-stone-700 px-7 py-3.5 text-sm font-semibold hover:border-stone-400 hover:shadow-sm transition-all w-full sm:w-auto text-center"
          >
            hello@conductai.ai
          </a>
          <a
            href="https://github.com/sseshachala"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center justify-center gap-2 rounded-xl border border-stone-300 bg-white text-stone-700 px-7 py-3.5 text-sm font-semibold hover:border-stone-400 hover:shadow-sm transition-all w-full sm:w-auto"
          >
            <GitHubIcon />
            GitHub
          </a>
        </div>
      </div>
    </section>
  )
}
