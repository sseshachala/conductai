"use client"

import { useState } from "react"


export default function AgentBoosterPage() {
  return (
    <div className="min-h-screen bg-white flex flex-col">
      <Nav />
      <main>
        <HeroSection />
        <InspirationSection />
        <ProblemSection />
        <HowItWorksSection />
        <ThreeLayersSection />
        <QuickstartSection />
        <ClaudePluginSection />
        <UseCasesSection />
        <McpToolsSection />
        <CliReferenceSection />
        <WorksWithSection />
        <FaqSection />
        <AlsoBySection />
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
        <div className="relative group">
          <a href="/tools" className="flex items-center gap-1 text-sm font-medium text-indigo-600 hover:text-indigo-900 transition-colors">
            Tools
            <svg width="12" height="12" viewBox="0 0 12 12" fill="currentColor" className="opacity-50 mt-0.5"><path d="M2 4l4 4 4-4"/></svg>
          </a>
          <div className="absolute left-0 top-full pt-2 hidden group-hover:block z-50">
            <div className="bg-white border border-stone-200 rounded-xl shadow-lg py-1.5 min-w-[160px]">
              <a href="/tools/agent-booster" className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-indigo-600 bg-indigo-50 transition-colors">
                <span className="font-bold">◈</span> Agent Booster
              </a>
              <a href="/tools/conduct-cli" className="flex items-center gap-2 px-4 py-2 text-sm text-stone-700 hover:bg-stone-50 transition-colors">
                <span className="text-violet-600 font-bold">⬡</span> Conduct CLI
              </a>
            </div>
          </div>
        </div>
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

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)
  const handleCopy = () => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }
  return (
    <button
      onClick={handleCopy}
      aria-label="Copy to clipboard"
      className="ml-3 shrink-0 rounded-md border border-stone-600 px-2.5 py-1 text-xs font-medium text-stone-300 hover:border-stone-400 hover:text-white transition-colors"
    >
      {copied ? "Copied" : "Copy"}
    </button>
  )
}

function HeroSection() {
  return (
    <section className="flex flex-col items-center justify-center px-6 pt-16 pb-24 text-center">
      {/* Badge */}
      <div className="inline-flex items-center gap-2 bg-indigo-50 text-indigo-700 border border-indigo-100 text-xs font-semibold px-3 py-1.5 rounded-full mb-8 uppercase tracking-widest">
        Open Source Developer Tool
      </div>

      <h1 className="text-5xl sm:text-6xl font-bold text-stone-900 leading-[1.1] tracking-tight max-w-3xl">
        Every token you don&apos;t send is a token{" "}
        <span className="text-indigo-600">you don&apos;t pay for.</span>
      </h1>

      <p className="mt-6 text-xl text-stone-500 max-w-2xl leading-relaxed">
        Swarm-style AI development costs up to $2,500/day — not because models are expensive,
        but because the same architecture docs, source files, and conversation history get
        resent on every single call. Agent Booster fixes the information flow.
      </p>

      <div className="mt-10 flex flex-col sm:flex-row items-center gap-4">
        <div className="flex items-center rounded-xl bg-stone-950 px-5 py-3">
          <code className="font-mono text-sm text-emerald-400">pip install agent-booster</code>
          <CopyButton text="pip install agent-booster" />
        </div>
        <a
          href="https://github.com/sseshachala/conductai"
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-2 rounded-xl border border-stone-200 bg-white px-6 py-3 text-sm font-semibold text-stone-700 hover:border-stone-300 hover:shadow-sm transition-all"
        >
          <GitHubIcon />
          View on GitHub
        </a>
      </div>
      <p className="mt-4 text-xs text-stone-400">
        Python 3.10+ · MIT licensed · v0.2.15
      </p>
    </section>
  )
}

/* ─── The problem ──────────────────────────────────────────────────────── */

function ProblemSection() {
  const oldWay = [
    "Architecture docs",
    "ADRs",
    "Source files",
    "Tool definitions",
    "Repo state",
    "Conversation history",
  ]
  const boosterWay = [
    "AST nodes",
    "Symbols",
    "Dependencies",
    "Structural diffs",
    "Semantic context",
    "Task-specific info only",
  ]

  return (
    <section className="bg-stone-50 px-6 py-20">
      <div className="max-w-5xl mx-auto">
        <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest text-center mb-3">The problem</p>
        <h2 className="text-3xl font-bold text-stone-900 text-center mb-4">
          The biggest cost isn&apos;t the model. It&apos;s context replay.
        </h2>
        <p className="text-center text-stone-500 text-sm max-w-2xl mx-auto mb-12">
          Most autonomous coding systems keep resending the same files over and over.
          Agent Booster operates at the AST and semantic level — routing only the pieces that actually matter to the task.
        </p>

        <div className="grid sm:grid-cols-2 gap-6">
          {/* Old way */}
          <div className="rounded-2xl border border-red-100 bg-white px-7 py-7 flex flex-col gap-5">
            <div className="flex items-center gap-2">
              <span className="text-xl">X</span>
              <h3 className="text-lg font-semibold text-stone-900">The old way</h3>
            </div>
            <ul className="space-y-3">
              {oldWay.map(item => (
                <li key={item} className="flex items-center gap-3 text-sm text-stone-600">
                  <span className="w-5 h-5 rounded-full bg-red-50 border border-red-200 text-red-500 flex items-center justify-center shrink-0 text-xs font-bold">✕</span>
                  {item}
                </li>
              ))}
            </ul>
            <div className="mt-auto pt-4 border-t border-stone-100">
              <p className="text-sm font-semibold text-red-600">~$2,500/day. High token replay.</p>
            </div>
          </div>

          {/* Booster way */}
          <div className="rounded-2xl border border-emerald-200 bg-white px-7 py-7 flex flex-col gap-5">
            <div className="flex items-center gap-2">
              <span className="text-xl text-emerald-500">✦</span>
              <h3 className="text-lg font-semibold text-stone-900">The Booster way</h3>
            </div>
            <ul className="space-y-3">
              {boosterWay.map(item => (
                <li key={item} className="flex items-center gap-3 text-sm text-stone-600">
                  <span className="w-5 h-5 rounded-full bg-emerald-50 border border-emerald-200 text-emerald-600 flex items-center justify-center shrink-0 text-xs font-bold">✓</span>
                  {item}
                </li>
              ))}
            </ul>
            <div className="mt-auto pt-4 border-t border-emerald-100">
              <p className="text-sm font-semibold text-emerald-600">3–15x lower cost. Same output quality.</p>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}

/* ─── How it works ─────────────────────────────────────────────────────── */

const HOW_IT_WORKS_STEPS = [
  {
    n: "1",
    title: "Parse & Understand",
    desc: "tree-sitter extracts symbols, functions, dependencies",
    icon: "◈",
    color: "text-indigo-600",
    bg: "bg-indigo-50 border-indigo-200",
  },
  {
    n: "2",
    title: "Semantic Diff",
    desc: "Detect what changed and what's relevant",
    icon: "≋",
    color: "text-violet-600",
    bg: "bg-violet-50 border-violet-200",
  },
  {
    n: "3",
    title: "Symbol Retrieval",
    desc: "Pull only matching symbols from the index",
    icon: "◎",
    color: "text-blue-600",
    bg: "bg-blue-50 border-blue-200",
  },
  {
    n: "4",
    title: "Prompt Caching",
    desc: "Stable context cached at 90% discount",
    icon: "⊙",
    color: "text-emerald-600",
    bg: "bg-emerald-50 border-emerald-200",
  },
  {
    n: "5",
    title: "Smart Model Routing",
    desc: "route_model picks haiku, sonnet, or opus — ~4x savings on routine tasks",
    icon: "⟁",
    color: "text-amber-600",
    bg: "bg-amber-50 border-amber-200",
  },
]

function HowItWorksSection() {
  return (
    <section className="px-6 py-20">
      <div className="max-w-6xl mx-auto">
        <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest text-center mb-3">How it works</p>
        <h2 className="text-3xl font-bold text-stone-900 text-center mb-12">
          Five layers of savings, applied automatically.
        </h2>

        {/* Horizontal flow for larger screens, stacked on mobile */}
        <div className="grid grid-cols-1 sm:grid-cols-5 gap-4">
          {HOW_IT_WORKS_STEPS.map((step, idx) => (
            <div key={step.n} className="flex sm:flex-col items-start sm:items-center gap-4 sm:gap-0">
              <div className={`rounded-2xl border ${step.bg} px-4 py-5 flex flex-col items-center text-center w-full gap-3`}>
                <span className={`text-2xl font-black ${step.color}`}>{step.icon}</span>
                <div>
                  <p className="text-[10px] font-bold text-stone-400 uppercase tracking-widest mb-1">Step {step.n}</p>
                  <p className="text-sm font-semibold text-stone-900 mb-1">{step.title}</p>
                  <p className="text-xs text-stone-500 leading-relaxed">{step.desc}</p>
                </div>
              </div>
              {/* Connector arrow — only between steps, not after last */}
              {idx < HOW_IT_WORKS_STEPS.length - 1 && (
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

/* ─── Three layers ─────────────────────────────────────────────────────── */

function ThreeLayersSection() {
  return (
    <section className="bg-stone-900 px-6 py-20">
      <div className="max-w-3xl mx-auto">
        <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest text-center mb-3">Architecture</p>
        <h2 className="text-3xl font-bold text-white text-center mb-12">
          Three compounding layers of token savings.
        </h2>

        <div className="flex flex-col gap-3">
          {/* Layer 3 — highlighted */}
          <div className="rounded-2xl border border-indigo-400 bg-indigo-900 px-6 py-5 relative">
            <div className="absolute top-4 right-4">
              <span className="text-[10px] font-semibold text-indigo-300 bg-indigo-800 border border-indigo-600 px-2 py-0.5 rounded-full uppercase tracking-widest">
                What we add
              </span>
            </div>
            <p className="text-[10px] font-bold text-indigo-400 uppercase tracking-widest mb-1">Layer 3</p>
            <p className="text-base font-semibold text-white mb-1">Agent Booster</p>
            <p className="text-sm text-indigo-200">
              AST + semantic routing, smart file reads — routes only the relevant symbols and functions to the model instead of full files.
            </p>
          </div>

          {/* Layer 2 */}
          <div className="rounded-2xl border border-stone-700 bg-stone-800 px-6 py-5">
            <p className="text-[10px] font-bold text-stone-400 uppercase tracking-widest mb-1">Layer 2</p>
            <p className="text-base font-semibold text-white mb-1">RTK — Rust Token Killer</p>
            <p className="text-sm text-stone-400">
              Token compression on tool output — strips noise from CLI, git, build, and test output before it reaches the context window.
            </p>
          </div>

          {/* Layer 1 */}
          <div className="rounded-2xl border border-stone-700 bg-stone-800 px-6 py-5">
            <p className="text-[10px] font-bold text-stone-400 uppercase tracking-widest mb-1">Layer 1</p>
            <p className="text-base font-semibold text-white mb-1">Prompt caching</p>
            <p className="text-sm text-stone-400">
              Stable context reuse — native to Claude Code and the Anthropic API. Repeated stable prefixes are cached at a 90% discount.
            </p>
          </div>
        </div>
      </div>
    </section>
  )
}

/* ─── Quickstart ───────────────────────────────────────────────────────── */

function InlineCodeBlock({ children, comment }: { children: string; comment?: string }) {
  const [copied, setCopied] = useState(false)
  const handleCopy = () => {
    navigator.clipboard.writeText(children).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }
  return (
    <div className="rounded-xl bg-stone-950 px-5 py-4 flex items-center justify-between gap-4">
      <div className="font-mono text-sm">
        {comment && <p className="text-stone-500 text-xs mb-2"># {comment}</p>}
        <p className="text-emerald-400">{children}</p>
      </div>
      <button
        onClick={handleCopy}
        aria-label="Copy to clipboard"
        className="shrink-0 rounded-md border border-stone-600 px-2.5 py-1 text-xs font-medium text-stone-400 hover:border-stone-400 hover:text-white transition-colors"
      >
        {copied ? "Copied" : "Copy"}
      </button>
    </div>
  )
}

function QuickstartSection() {
  return (
    <section className="bg-stone-50 px-6 py-20">
      <div className="max-w-2xl mx-auto">
        <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest text-center mb-3">Quickstart</p>
        <h2 className="text-3xl font-bold text-stone-900 text-center mb-12">
          Up and running in three commands.
        </h2>

        <div className="flex flex-col gap-5">
          <div>
            <p className="text-xs font-bold text-stone-400 uppercase tracking-widest mb-2">Step 1 — Install</p>
            <InlineCodeBlock comment="[embed] adds semantic vector search">pip install agent-booster[embed]</InlineCodeBlock>
          </div>
          <div>
            <p className="text-xs font-bold text-stone-400 uppercase tracking-widest mb-2">Step 2 — Wire to your tool</p>
            <InlineCodeBlock comment="claude · cursor · windsurf · codex · all — shows what changes, asks to confirm">booster init claude</InlineCodeBlock>
            <p className="mt-2 text-xs text-stone-400">Writes .mcp.json, CLAUDE.md rules, and three hooks: Read gate, Grep nudge, and auto route_model on every turn. Run once per project — hooks fire in <strong>every</strong> Claude Code session opened in this directory, any terminal. Fully reversible with <code className="font-mono bg-stone-100 px-1 rounded text-stone-600">booster remove claude</code>.</p>
          </div>
          <div>
            <p className="text-xs font-bold text-stone-400 uppercase tracking-widest mb-2">Step 3 — Index your codebase</p>
            <InlineCodeBlock comment="builds symbol index + semantic vectors">booster index &amp;&amp; booster embed</InlineCodeBlock>
          </div>
          <div>
            <p className="text-xs font-bold text-stone-400 uppercase tracking-widest mb-2">Step 4 — Route to the right model</p>
            <InlineCodeBlock comment="haiku · sonnet · opus — auto-selected">booster route &quot;your task description&quot;</InlineCodeBlock>
          </div>
          <div>
            <p className="text-xs font-bold text-stone-400 uppercase tracking-widest mb-2">Step 5 — Track savings</p>
            <InlineCodeBlock>booster gain</InlineCodeBlock>
          </div>
        </div>
      </div>
    </section>
  )
}

/* ─── Use Cases ────────────────────────────────────────────────────────── */

const USE_CASES = [
  {
    title: "Fixing a bug in a large service file",
    scenario: "You need to fix a validation bug in one function inside a 1,800-line API router.",
    without: {
      label: "Without Booster",
      steps: [
        "Claude reads the full 1,800-line file",
        "~450 tokens just to locate the function",
        "Full file re-sent on every follow-up turn",
      ],
      cost: "~450 tokens per read",
      color: "text-red-600",
      bg: "bg-red-50 border-red-200",
    },
    with: {
      label: "With Booster",
      steps: [
        "smart_read(file, \"fix validation in create_order\") returns 42 lines",
        "Only the matching function + its direct dependencies",
        "Same slice reused across follow-up turns via prompt cache",
      ],
      cost: "~12 tokens per read",
      color: "text-emerald-600",
      bg: "bg-emerald-50 border-emerald-200",
    },
    saving: "97%",
  },
  {
    title: "Finding where an interface is implemented",
    scenario: "You ask Claude to find all implementations of a PaymentProvider interface across a monorepo.",
    without: {
      label: "Without Booster",
      steps: [
        "Claude Greps recursively — returns 40+ files with matches",
        "Reads several files in full to find the right ones",
        "Often re-reads files it already saw in a previous turn",
      ],
      cost: "~1,200 tokens across reads",
      color: "text-red-600",
      bg: "bg-red-50 border-red-200",
    },
    with: {
      label: "With Booster",
      steps: [
        "search_context(\"PaymentProvider implementation\") returns top 6 matching symbols",
        "Each result includes file, line, and signature — no full reads needed",
        "Claude acts on symbols directly, zero redundant file reads",
      ],
      cost: "~80 tokens",
      color: "text-emerald-600",
      bg: "bg-emerald-50 border-emerald-200",
    },
    saving: "93%",
  },
  {
    title: "Routine task on a well-understood file",
    scenario: "Claude is asked to add a log statement to a utility function it has seen many times this session.",
    without: {
      label: "Without routing",
      steps: [
        "Defaults to Claude Sonnet or Opus for every task",
        "A 30-second task costs full Sonnet pricing",
        "Model capacity wasted on trivial edits",
      ],
      cost: "Sonnet input price",
      color: "text-red-600",
      bg: "bg-red-50 border-red-200",
    },
    with: {
      label: "With route_model",
      steps: [
        "route_model detects low complexity: single file, no architecture signals",
        "Recommends Haiku — 25× cheaper than Opus, same output quality",
        "Claude Code routes the task to Haiku automatically",
      ],
      cost: "Haiku input price (~4× cheaper)",
      color: "text-emerald-600",
      bg: "bg-emerald-50 border-emerald-200",
    },
    saving: "75%",
  },
  {
    title: "Explaining an unfamiliar module",
    scenario: "A new developer asks Claude to explain how the auth middleware works across 12 files.",
    without: {
      label: "Without Booster",
      steps: [
        "Claude reads each file in full to map the flow",
        "Most lines are unrelated — imports, comments, other routes",
        "Context window fills fast, forcing a new session",
      ],
      cost: "~6,000 tokens",
      color: "text-red-600",
      bg: "bg-red-50 border-red-200",
    },
    with: {
      label: "With Booster",
      steps: [
        "get_symbols() maps all auth-related functions across files instantly",
        "smart_read() returns only the relevant slices per file",
        "Full auth flow explained from 480 lines instead of 3,400",
      ],
      cost: "~120 tokens",
      color: "text-emerald-600",
      bg: "bg-emerald-50 border-emerald-200",
    },
    saving: "98%",
  },
]

function UseCasesSection() {
  const [active, setActive] = useState(0)
  const uc = USE_CASES[active]

  return (
    <section className="bg-stone-50 px-6 py-20">
      <div className="max-w-5xl mx-auto">
        <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest text-center mb-3">Example use cases</p>
        <h2 className="text-3xl font-bold text-stone-900 text-center mb-4">
          See the difference on real tasks.
        </h2>
        <p className="text-center text-stone-500 text-sm max-w-xl mx-auto mb-10">
          These are actual patterns from everyday coding sessions — not synthetic benchmarks.
        </p>

        {/* Tab selector */}
        <div className="flex flex-wrap gap-2 justify-center mb-10">
          {USE_CASES.map((u, i) => (
            <button
              key={i}
              onClick={() => setActive(i)}
              className={`rounded-full px-4 py-2 text-xs font-semibold transition-all border ${
                active === i
                  ? "bg-indigo-600 text-white border-indigo-600"
                  : "bg-white text-stone-600 border-stone-200 hover:border-stone-300"
              }`}
            >
              {u.title}
            </button>
          ))}
        </div>

        {/* Active case */}
        <div className="rounded-2xl border border-stone-200 bg-white overflow-hidden">
          {/* Header */}
          <div className="px-8 py-6 border-b border-stone-100 flex items-start justify-between gap-4">
            <div>
              <p className="text-lg font-bold text-stone-900 mb-1">{uc.title}</p>
              <p className="text-sm text-stone-500">{uc.scenario}</p>
            </div>
            <div className="shrink-0 text-center">
              <p className="text-3xl font-black text-indigo-600">{uc.saving}</p>
              <p className="text-xs text-stone-400 mt-0.5">token savings</p>
            </div>
          </div>

          {/* Comparison */}
          <div className="grid sm:grid-cols-2 divide-y sm:divide-y-0 sm:divide-x divide-stone-100">
            {[uc.without, uc.with].map((side) => (
              <div key={side.label} className={`px-8 py-7 flex flex-col gap-4`}>
                <p className={`text-xs font-bold uppercase tracking-widest ${side.color}`}>{side.label}</p>
                <ul className="space-y-2.5">
                  {side.steps.map((step, i) => (
                    <li key={i} className="flex items-start gap-2.5 text-sm text-stone-600">
                      <span className={`mt-0.5 w-4 h-4 rounded-full border flex items-center justify-center shrink-0 text-[10px] font-bold ${side.bg} ${side.color}`}>
                        {side === uc.with ? "✓" : "✕"}
                      </span>
                      {step}
                    </li>
                  ))}
                </ul>
                <div className={`mt-auto pt-4 border-t border-stone-100`}>
                  <p className={`text-sm font-semibold ${side.color}`}>{side.cost}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  )
}

/* ─── Claude Plugin ────────────────────────────────────────────────────── */

function ClaudePluginSection() {
  return (
    <section className="px-6 py-20">
      <div className="max-w-3xl mx-auto">
        <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest text-center mb-3">Claude Code Plugin</p>
        <h2 className="text-3xl font-bold text-stone-900 text-center mb-4">
          One command to install everything.
        </h2>
        <p className="text-center text-stone-500 text-sm max-w-xl mx-auto mb-12">
          Agent Booster is available as an official Claude Code plugin. One slash command installs
          the MCP server, wires the context skill, and you&apos;re live.
        </p>

        <div className="rounded-2xl border border-indigo-200 bg-indigo-50 px-8 py-8 flex flex-col gap-6">
          {/* Install command */}
          <div>
            <p className="text-xs font-bold text-stone-400 uppercase tracking-widest mb-2">Install via Claude Code</p>
            <InlineCodeBlock>/plugin marketplace add sseshachala/conductai</InlineCodeBlock>
          </div>

          {/* What it does */}
          <div className="grid sm:grid-cols-3 gap-4">
            {[
              {
                icon: "◈",
                title: "MCP server",
                desc: "Wires booster serve as an MCP server — smart_read, search_context, get_symbols, route_model available immediately.",
                color: "text-indigo-600",
                bg: "bg-white border-indigo-200",
              },
              {
                icon: "✦",
                title: "Context skill",
                desc: "Adds the booster-context skill so Claude prefers smart_read and search_context over native Read/Grep.",
                color: "text-violet-600",
                bg: "bg-white border-violet-200",
              },
              {
                icon: "⊙",
                title: "Zero config",
                desc: "No manual .mcp.json edits. Works in every Claude Code session opened in this directory.",
                color: "text-emerald-600",
                bg: "bg-white border-emerald-200",
              },
            ].map(item => (
              <div key={item.title} className={`rounded-xl border ${item.bg} px-5 py-4 flex flex-col gap-2`}>
                <span className={`text-xl font-black ${item.color}`}>{item.icon}</span>
                <p className="text-sm font-semibold text-stone-900">{item.title}</p>
                <p className="text-xs text-stone-500 leading-relaxed">{item.desc}</p>
              </div>
            ))}
          </div>

          {/* Post-install step */}
          <div className="border-t border-indigo-200 pt-5">
            <p className="text-xs font-bold text-stone-400 uppercase tracking-widest mb-2">Then index your project (once per repo)</p>
            <InlineCodeBlock>booster index && booster embed</InlineCodeBlock>
            <p className="mt-2 text-xs text-stone-400">
              Requires <code className="font-mono bg-white px-1 rounded">pip install agent-booster[embed]</code> first.
            </p>
          </div>
        </div>

        {/* Submission note */}
        <p className="text-center text-xs text-stone-400 mt-6">
          Plugin is pending review at the{" "}
          <a
            href="https://clau.de/plugin-directory-submission"
            target="_blank"
            rel="noopener noreferrer"
            className="text-indigo-500 hover:text-indigo-700"
          >
            Anthropic plugin directory
          </a>
          . Until then, install directly from{" "}
          <a
            href="https://github.com/sseshachala/conductai"
            target="_blank"
            rel="noopener noreferrer"
            className="text-indigo-500 hover:text-indigo-700"
          >
            GitHub
          </a>
          .
        </p>
      </div>
    </section>
  )
}

/* ─── MCP Tools ────────────────────────────────────────────────────────── */

const MCP_TOOLS = [
  {
    name: "get_symbols",
    signature: "get_symbols(file)",
    desc: "Returns all functions and classes for a file from the booster index — no file read required.",
    color: "text-blue-700",
    bg: "bg-blue-50 border-blue-200",
  },
  {
    name: "search_context",
    signature: "search_context(task)",
    desc: "RRF-fused search across the full codebase — merges vector similarity and keyword ranks using Reciprocal Rank Fusion so strong keyword matches surface even when embeddings are weak. Falls back to keyword-only if embeddings aren't built.",
    color: "text-violet-700",
    bg: "bg-violet-50 border-violet-200",
  },
  {
    name: "smart_read",
    signature: "smart_read(file, task)",
    desc: "Returns only the relevant AST symbol slices for a task using RRF-ranked selection. Applies a 5 KB gate — if matched symbols exceed 5 KB, trims to the top-3 ranked symbols with a truncation notice. Logs token savings to booster gain.",
    color: "text-emerald-700",
    bg: "bg-emerald-50 border-emerald-200",
  },
  {
    name: "route_model",
    signature: "route_model(task, files?)",
    desc: "Recommends haiku, sonnet, or opus based on task complexity — keyword signals, file count, and symbol count. Saves ~4x on routine tasks by skipping unnecessary Opus calls.",
    color: "text-amber-700",
    bg: "bg-amber-50 border-amber-200",
  },
]

function McpToolsSection() {
  return (
    <section className="px-6 py-20">
      <div className="max-w-5xl mx-auto">
        <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest text-center mb-3">MCP Tools</p>
        <h2 className="text-3xl font-bold text-stone-900 text-center mb-4">
          Four tools. Massive context savings.
        </h2>
        <p className="text-center text-stone-500 text-sm max-w-xl mx-auto mb-12">
          Agent Booster exposes four MCP tools — targeted symbol lookups, semantic search,
          smart file reads, and automatic model routing. The model sees exactly what it needs and nothing else.
        </p>

        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-5">
          {MCP_TOOLS.map(tool => (
            <div key={tool.name} className={`rounded-2xl border ${tool.bg} px-6 py-6 flex flex-col gap-3`}>
              <div>
                <code className={`font-mono text-sm font-semibold ${tool.color}`}>{tool.signature}</code>
              </div>
              <p className="text-sm text-stone-600 leading-relaxed">{tool.desc}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

/* ─── CLI Reference ────────────────────────────────────────────────────── */

const CLI_COMMANDS = [
  {
    cmd: "booster init <platform>",
    when: "Once per project, after install",
    what: "Writes MCP config, rules file, and hooks for claude, cursor, windsurf, or codex. For Claude Code: Read gate, Grep nudge, and auto route_model on every turn. Shows what will change, asks for confirmation.",
    note: "booster init claude --yes  to skip prompt",
  },
  {
    cmd: "booster remove <platform>",
    when: "When you want to uninstall",
    what: "Cleanly removes everything init wrote — MCP entry, rules block, hook script. No residue.",
    note: null,
  },
  {
    cmd: "booster index",
    when: "After install, and after large refactors",
    what: "Parses all .py / .ts / .tsx / .js / .jsx files with tree-sitter, stores symbols in .booster/symbols.db.",
    note: "Skips .next/, dist/, build/, node_modules, .venv",
  },
  {
    cmd: "booster embed",
    when: "After booster index",
    what: "Builds sentence-transformer vector embeddings for all symbols. Required for semantic search_context calls.",
    note: "Needs pip install agent-booster[embed]",
  },
  {
    cmd: "booster route \"<task>\"",
    when: "Before starting a non-trivial task",
    what: "Recommends haiku, sonnet, or opus based on task complexity — keyword signals, file count, symbol count.",
    note: null,
  },
  {
    cmd: "booster search \"<query>\"",
    when: "To explore the index from the terminal",
    what: "Keyword search across all indexed symbols. Same as search_context but run from the CLI.",
    note: null,
  },
  {
    cmd: "booster gain",
    when: "Any time, to see ROI",
    what: "Reports total smart_read calls, tokens served vs. saved, savings rate, and top files.",
    note: null,
  },
  {
    cmd: "booster serve",
    when: "Automatic — you rarely run this directly",
    what: "Starts the MCP stdio server. Called automatically by Claude Code / Cursor / Windsurf / Codex.",
    note: null,
  },
]

function CliReferenceSection() {
  return (
    <section className="px-6 py-20 bg-stone-50">
      <div className="max-w-5xl mx-auto">
        <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest text-center mb-3">CLI Reference</p>
        <h2 className="text-3xl font-bold text-stone-900 text-center mb-4">
          Every command, and when to use it.
        </h2>
        <p className="text-center text-stone-500 text-sm max-w-xl mx-auto mb-12">
          Most of the time you only need three: <code className="font-mono bg-stone-200 px-1 rounded">init</code>, <code className="font-mono bg-stone-200 px-1 rounded">index &amp;&amp; embed</code>, and <code className="font-mono bg-stone-200 px-1 rounded">gain</code>.
        </p>

        <div className="flex flex-col divide-y divide-stone-200 rounded-2xl border border-stone-200 bg-white overflow-hidden">
          {CLI_COMMANDS.map((c) => (
            <div key={c.cmd} className="grid grid-cols-1 sm:grid-cols-[2fr_1fr_3fr] gap-2 sm:gap-6 px-6 py-5 items-start">
              <code className="font-mono text-sm font-semibold text-indigo-700 bg-indigo-50 px-2 py-1 rounded self-start">{c.cmd}</code>
              <p className="text-xs text-stone-400 italic pt-1">{c.when}</p>
              <div>
                <p className="text-sm text-stone-700">{c.what}</p>
                {c.note && <p className="mt-1 text-xs text-stone-400 font-mono">{c.note}</p>}
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

/* ─── Works with ───────────────────────────────────────────────────────── */

const WORKS_WITH = [
  {
    name: "Claude Code",
    icon: "◈",
    color: "text-orange-600",
    bg: "bg-orange-50 border-orange-200",
    desc: "booster init claude",
  },
  {
    name: "Cursor",
    icon: "⊙",
    color: "text-blue-600",
    bg: "bg-blue-50 border-blue-200",
    desc: "booster init cursor",
  },
  {
    name: "Windsurf",
    icon: "◭",
    color: "text-violet-600",
    bg: "bg-violet-50 border-violet-200",
    desc: "booster init windsurf",
  },
  {
    name: "OpenAI Codex",
    icon: "◎",
    color: "text-emerald-600",
    bg: "bg-emerald-50 border-emerald-200",
    desc: "booster init codex",
  },
]

function WorksWithSection() {
  return (
    <section className="bg-stone-50 px-6 py-20">
      <div className="max-w-4xl mx-auto">
        <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest text-center mb-3">Compatibility</p>
        <h2 className="text-3xl font-bold text-stone-900 text-center mb-12">
          Works with every major AI coding tool.
        </h2>

        <div className="grid sm:grid-cols-4 gap-5">
          {WORKS_WITH.map(tool => (
            <div key={tool.name} className={`rounded-2xl border ${tool.bg} px-6 py-6 flex flex-col items-center text-center gap-3`}>
              <span className={`text-3xl font-black ${tool.color}`}>{tool.icon}</span>
              <div>
                <p className="font-semibold text-stone-900 mb-1">{tool.name}</p>
                <code className="text-xs text-stone-500 font-mono">{tool.desc}</code>
              </div>
            </div>
          ))}
        </div>

        <p className="text-center text-xs text-stone-400 mt-6">
          Each command shows exactly what files will change and asks for confirmation before writing anything.
          Run <code className="font-mono bg-stone-200 px-1 rounded">booster remove &lt;platform&gt;</code> to cleanly undo.
        </p>
      </div>
    </section>
  )
}

/* ─── FAQ ──────────────────────────────────────────────────────────────── */

const FAQS = [
  {
    q: "What is an AST and why does it matter?",
    a: "AST stands for Abstract Syntax Tree — a structured representation of source code. Instead of treating code as raw text, we parse it into a tree of nodes: functions, classes, parameters, and their relationships. This lets us extract just the symbols relevant to a task (say, 3 functions out of 1,800 lines) rather than sending the entire file. We use tree-sitter to parse Python and TypeScript files.",
  },
  {
    q: "How does the symbol index work?",
    a: "When you run booster index, we walk every .py file in your project using tree-sitter, extract all function_definition and class_definition nodes, and store their name, kind, file path, start/end line, and signature into a local SQLite database at .booster/symbols.db. Re-indexing is safe — we clear and rebuild the table each run, skipping worktrees, node_modules, .venv, and __pycache__.",
  },
  {
    q: "How does semantic search work?",
    a: "When you run booster index --embed (or booster embed), we load each symbol's name + signature into the all-MiniLM-L6-v2 model from sentence-transformers, encode them into 384-dimensional vectors, L2-normalize them, and save the matrix to .booster/vectors.npy. At query time we encode the task description the same way and compute cosine similarity (a dot product since both sides are unit-normalized) to find the top-K matching symbols. If the vector files don't exist, search automatically falls back to keyword matching.",
  },
  {
    q: "What happens when Claude reads a file through Booster?",
    a: "The MCP smart_read tool receives the file path and a task description. It uses RRF (Reciprocal Rank Fusion) to merge two ranked lists — a vector similarity search and a keyword LIKE search — using the formula score = Σ 1/(60 + rank). This surfaces symbols that score well on either or both strategies, instead of relying on embeddings alone. The result is AST symbol slices (source lines for matching functions/classes) with a header showing name and line range. A 5 KB gate caps output — if matched symbols exceed 5 KB, only the top-3 RRF-ranked symbols are returned with a truncation notice. Every call is logged to .booster/stats.db so booster gain can report real token savings.",
  },
  {
    q: "How does token savings tracking work?",
    a: "Each smart_read call records three things in .booster/stats.db: the full file text size, the slice size returned, and the task description. Token count is estimated as len(text) // 4 (a standard rough approximation). booster gain reads this database and reports total tokens served vs. tokens that would have been sent without Booster, broken down by file.",
  },
  {
    q: "What does booster init actually change on my machine?",
    a: "For Claude Code, booster init claude writes six things: .mcp.json (registers the MCP server), CLAUDE.md (appends a rules block), .claude/settings.json (wires three hooks), and three hook scripts — booster-gate.py (blocks Read on indexed files and forces smart_read), booster-grep-nudge.py (detects semantic Grep patterns and suggests search_context instead), and booster-route.py (fires on every user message and recommends haiku/sonnet/opus before Claude starts work). Before writing anything, it prints a full list of changes and asks for confirmation. Run booster remove claude to undo everything cleanly. No residue.",
  },
  {
    q: "Does Booster send my code anywhere?",
    a: "No. Everything runs locally on your machine. The symbol index, vector store, and stats database are all stored in .booster/ inside your project. The MCP server runs as a local stdio process — no network calls, no telemetry. The only external call is the one-time model download from HuggingFace when you first run booster embed.",
  },
  {
    q: "Does it work with TypeScript and other languages?",
    a: "Yes. Booster indexes Python (.py) and TypeScript/TSX/JS/JSX files. We use tree-sitter-python for Python and tree-sitter-typescript for TypeScript — extracting functions, classes, methods, interfaces, and named arrow functions. Build artifacts (.next/, dist/, build/) are automatically excluded from indexing so minified bundles never pollute the symbol index.",
  },
  {
    q: "How is this different from just using prompt caching?",
    a: "Prompt caching (Layer 1) reuses stable prefixes that have already been sent — it reduces cost on repeated context. Booster (Layer 3) prevents that context from being sent in the first place. A 1,800-line file cached still costs full price on the first read of a session. Booster routes only the relevant 80 lines every time, whether or not caching is active. The two stack: Booster reduces what you send, caching reduces the cost of what you sent previously.",
  },
  {
    q: "Does it work across multiple terminal sessions on the same machine?",
    a: "Yes. The hooks and MCP server are wired via .claude/settings.json and .mcp.json at the project root — not tied to any specific terminal window or session. Every Claude Code session you open inside the project directory (any terminal, same machine) automatically gets the Read gate, Grep nudge, and route_model hook. The MCP server starts fresh per session but the index is shared (it's just .booster/symbols.db on disk). The only requirement: run booster init claude once per project, not once per session.",
  },
  {
    q: "Does each developer on my team need to run booster init?",
    a: "Yes — once per developer, once per project. booster init writes files into the project directory (.mcp.json, .claude/settings.json, hook scripts). If you commit those files to the repo, teammates who clone it get the hooks automatically but still need to run pip install agent-booster[embed] and booster index && booster embed locally since the symbol index is gitignored. For teams, the Sentinel integration (coming) will push the init automatically to every developer's workspace.",
  },
]

function FaqSection() {
  const [open, setOpen] = useState<number | null>(null)

  return (
    <section className="px-6 py-20">
      <div className="max-w-3xl mx-auto">
        <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest text-center mb-3">Under the hood</p>
        <h2 className="text-3xl font-bold text-stone-900 text-center mb-12">
          How it&apos;s actually built.
        </h2>

        <div className="flex flex-col divide-y divide-stone-100">
          {FAQS.map((faq, idx) => (
            <div key={idx} className="py-5">
              <button
                onClick={() => setOpen(open === idx ? null : idx)}
                className="w-full flex items-start justify-between gap-4 text-left"
              >
                <span className="text-sm font-semibold text-stone-900">{faq.q}</span>
                <span className="shrink-0 mt-0.5 text-stone-400 text-lg leading-none">
                  {open === idx ? "−" : "+"}
                </span>
              </button>
              {open === idx && (
                <p className="mt-3 text-sm text-stone-500 leading-relaxed">{faq.a}</p>
              )}
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

/* ─── Inspiration ──────────────────────────────────────────────────────── */

function InspirationSection() {
  return (
    <section className="bg-stone-50 px-6 py-20">
      <div className="max-w-3xl mx-auto">
        <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest text-center mb-3">Inspiration</p>
        <h2 className="text-3xl font-bold text-stone-900 text-center mb-12">
          Standing on the shoulders of sharp thinkers.
        </h2>

        <div className="rounded-2xl border border-stone-200 bg-white px-8 py-8 flex flex-col gap-6">
          {/* Attribution header */}
          <div className="flex items-start gap-4">
            <div className="w-12 h-12 rounded-full bg-stone-100 border border-stone-200 flex items-center justify-center shrink-0 text-lg font-bold text-stone-500">
              RC
            </div>
            <div>
              <p className="font-semibold text-stone-900">Reuven Cohen</p>
              <p className="text-sm text-stone-500">Agentic Engineer · Founder @ Cognitum.One</p>
            </div>
          </div>

          {/* Pull quote */}
          <blockquote className="border-l-4 border-indigo-300 pl-5 text-stone-600 text-sm leading-relaxed space-y-3">
            <p>
              &ldquo;The going rate for a single developer running Claude Code using a swarm style development
              is around $2.5k/day or $75k/month via Anthropic enterprise API.&rdquo;
            </p>
            <p>
              &ldquo;The biggest cost in agentic development isn&apos;t the model. It&apos;s the constant replay of context.
              Most autonomous coding systems keep resending the same architecture documents, ADRs, source files,
              tool definitions, and conversation history over and over. That&apos;s where the money goes.&rdquo;
            </p>
            <p>
              &ldquo;We&apos;re not optimizing models. We&apos;re optimizing information flow.&rdquo;
            </p>
          </blockquote>

          {/* Infographic */}
          <div className="rounded-xl overflow-hidden border border-stone-200">
            <img
              src="/reuven-cohen-agent-booster.png"
              alt="Cut Claude Code Costs by 3x–15x — infographic by Reuven Cohen"
              className="w-full"
            />
          </div>

          {/* Context note */}
          <p className="text-xs text-stone-400 leading-relaxed">
            Reuven&apos;s post articulated the problem precisely. Agent Booster is our open-source implementation
            of that insight — AST-level symbol routing, semantic vector search, and MCP integration built
            directly into your coding workflow. The concept of operating at the AST and semantic level rather
            than treating code as raw text comes directly from this framing.
          </p>
        </div>
      </div>
    </section>
  )
}

/* ─── Also By ──────────────────────────────────────────────────────────── */

function AlsoBySection() {
  return (
    <section className="px-6 py-16 bg-stone-50 border-t border-stone-100">
      <div className="max-w-4xl mx-auto">
        <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-2 text-center">Also by Conduct</p>
        <h2 className="text-2xl font-bold text-stone-900 text-center mb-10">
          More free tools for AI coding
        </h2>

        <div className="grid sm:grid-cols-2 gap-6">
          {/* Claude Code Team Kit */}
          <div className="rounded-2xl border border-stone-200 bg-white px-7 py-6 flex flex-col gap-4 hover:border-violet-200 hover:shadow-sm transition-all">
            <div className="flex items-start justify-between">
              <div>
                <span className="inline-flex items-center text-xs font-semibold bg-violet-50 text-violet-700 border border-violet-100 px-2.5 py-1 rounded-full mb-3">
                  Free · MIT
                </span>
                <h3 className="text-lg font-bold text-stone-900">Claude Code Team Kit</h3>
                <p className="text-sm text-stone-500 mt-1">Claude Code scaffold for any team</p>
              </div>
              <span className="text-2xl font-black text-violet-600">⬡</span>
            </div>
            <p className="text-sm text-stone-600 leading-relaxed">
              Production-ready Claude Code setup across all 5 layers — CLAUDE.md, skills, hooks,
              subagents, and plugins — pre-configured for Enterprise, SMB, and Startup personas.
            </p>
            <div className="mt-auto pt-4 border-t border-stone-100 flex items-center gap-3">
              <a
                href="https://github.com/sseshachala/claude-code-team-kit"
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 rounded-lg bg-violet-600 px-4 py-2 text-sm font-semibold text-white hover:bg-violet-700 transition-colors"
              >
                <GitHubIcon />
                View on GitHub
              </a>
              <code className="font-mono text-xs text-stone-400 bg-stone-50 px-2 py-1 rounded border border-stone-100">bash install.sh</code>
            </div>
          </div>

          {/* RTK */}
          <div className="rounded-2xl border border-stone-200 bg-white px-7 py-6 flex flex-col gap-4 hover:border-stone-300 hover:shadow-sm transition-all">
            <div className="flex items-start justify-between">
              <div>
                <span className="inline-flex items-center text-xs font-semibold bg-stone-100 text-stone-600 border border-stone-200 px-2.5 py-1 rounded-full mb-3">
                  Free · MIT
                </span>
                <h3 className="text-lg font-bold text-stone-900">RTK — Rust Token Killer</h3>
                <p className="text-sm text-stone-500 mt-1">CLI output compression, 60–90% savings</p>
              </div>
              <span className="text-2xl font-black text-stone-400">≋</span>
            </div>
            <p className="text-sm text-stone-600 leading-relaxed">
              A transparent CLI proxy that strips token noise from git, build, test, and package
              manager output before it reaches the model. Just prefix any command with <code className="font-mono text-xs bg-stone-100 px-1 rounded">rtk</code>.
            </p>
            <div className="mt-auto pt-4 border-t border-stone-100 flex items-center gap-3">
              <a
                href="/blog/rtk-how-we-cut-93-percent-of-cli-tokens"
                className="inline-flex items-center gap-1.5 rounded-lg border border-stone-200 px-4 py-2 text-sm font-medium text-stone-700 hover:border-stone-300 transition-colors"
              >
                Read the post →
              </a>
            </div>
          </div>
        </div>

        <p className="text-center mt-8 text-sm text-stone-400">
          All tools are free, MIT licensed, and live on{" "}
          <a href="https://github.com/sseshachala/conductai" target="_blank" rel="noopener noreferrer" className="text-indigo-600 hover:text-indigo-800">GitHub</a>.
          {" "}See the full list at{" "}
          <a href="/tools" className="text-indigo-600 hover:text-indigo-800">/tools</a>.
        </p>
      </div>
    </section>
  )
}

/* ─── Footer CTA ───────────────────────────────────────────────────────── */

function FooterCTASection() {
  return (
    <section className="px-6 py-20 text-center">
      <h2 className="text-3xl font-bold text-stone-900 mb-4">
        We&apos;re not optimizing models.<br />We&apos;re optimizing information flow.
      </h2>
      <p className="text-stone-500 mb-8 max-w-lg mx-auto">
        A workflow that costs $2,500/day with brute-force context replay can often be reduced
        by several multiples — while maintaining comparable output quality.
        Every token you don&apos;t send is a token you don&apos;t pay for.
      </p>

      <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
        <div className="flex items-center rounded-xl bg-stone-950 px-5 py-3">
          <code className="font-mono text-sm text-emerald-400">pip install agent-booster</code>
          <CopyButton text="pip install agent-booster" />
        </div>
        <a
          href="https://github.com/sseshachala/conductai"
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-2 rounded-xl border border-stone-200 bg-white px-6 py-3 text-sm font-semibold text-stone-700 hover:border-stone-300 hover:shadow-sm transition-all"
        >
          <GitHubIcon />
          View on GitHub
        </a>
      </div>
      <p className="mt-6 text-xs text-stone-400">
        + semantic search: <code className="font-mono bg-stone-100 px-1.5 py-0.5 rounded text-stone-600">pip install agent-booster[embed]</code>
      </p>
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
        <span>MIT licensed</span>
        <span>·</span>
        <a href="/" className="hover:text-stone-600 transition-colors">Conduct AI</a>
        <span>·</span>
        <a href="/marketplace" className="hover:text-stone-600 transition-colors">Agent Templates</a>
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
