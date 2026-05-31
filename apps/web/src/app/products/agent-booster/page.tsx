"use client"

import { useState } from "react"


export default function AgentBoosterPage() {
  return (
    <div className="min-h-screen bg-white flex flex-col">
      <Nav />
      <main>
        <HeroSection />
        <ProblemSection />
        <HowItWorksSection />
        <ThreeLayersSection />
        <QuickstartSection />
        <McpToolsSection />
        <WorksWithSection />
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
          href="/marketplace"
          className="flex items-center gap-1.5 text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors"
        >
          Playbooks
        </a>
        <a
          href="/products/agent-booster"
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
        Cut AI coding costs{" "}
        <span className="text-indigo-600">5–15x</span>
      </h1>

      <p className="mt-6 text-xl text-stone-500 max-w-2xl leading-relaxed">
        Agent Booster routes only the code that matters to the model — instead of
        sending full files, it sends only the functions and classes relevant to
        your task.
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
        Python 3.10+ · MIT licensed · v0.1.5
      </p>
    </section>
  )
}

/* ─── The problem ──────────────────────────────────────────────────────── */

function ProblemSection() {
  const oldWay = [
    "Architecture docs",
    "Source files",
    "Tool definitions",
    "Conversation history",
  ]
  const boosterWay = [
    "AST nodes",
    "Symbols",
    "Dependencies",
    "Structural diffs",
    "Semantic context",
  ]

  return (
    <section className="bg-stone-50 px-6 py-20">
      <div className="max-w-5xl mx-auto">
        <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest text-center mb-3">The problem</p>
        <h2 className="text-3xl font-bold text-stone-900 text-center mb-12">
          Full files are expensive. Symbols are cheap.
        </h2>

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
              <p className="text-sm font-semibold text-red-600">High token replay $$$</p>
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
              <p className="text-sm font-semibold text-emerald-600">Minimal token transmission $</p>
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
    desc: "Sonnet for most work, Opus only when needed",
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
            <InlineCodeBlock comment="add [embed] for semantic search">pip install agent-booster</InlineCodeBlock>
          </div>
          <div>
            <p className="text-xs font-bold text-stone-400 uppercase tracking-widest mb-2">Step 2 — Index your codebase</p>
            <InlineCodeBlock comment="add --embed to build semantic vectors">booster index</InlineCodeBlock>
          </div>
          <div>
            <p className="text-xs font-bold text-stone-400 uppercase tracking-widest mb-2">Step 3 — Wire to your tool</p>
            <InlineCodeBlock comment="or cursor, codex, all">booster init claude</InlineCodeBlock>
          </div>
          <div>
            <p className="text-xs font-bold text-stone-400 uppercase tracking-widest mb-2">Step 4 — Track savings</p>
            <InlineCodeBlock>booster gain</InlineCodeBlock>
          </div>
        </div>
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
    desc: "Semantic vector search across the full codebase — finds relevant symbols by meaning, not just keyword match. Falls back to keyword search if embeddings aren't built.",
    color: "text-violet-700",
    bg: "bg-violet-50 border-violet-200",
  },
  {
    name: "smart_read",
    signature: "smart_read(file, task)",
    desc: "Returns only the relevant slice of a file — the functions and classes that match the task. Logs token savings to booster gain.",
    color: "text-emerald-700",
    bg: "bg-emerald-50 border-emerald-200",
  },
]

function McpToolsSection() {
  return (
    <section className="px-6 py-20">
      <div className="max-w-5xl mx-auto">
        <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest text-center mb-3">MCP Tools</p>
        <h2 className="text-3xl font-bold text-stone-900 text-center mb-4">
          Three tools. Massive context savings.
        </h2>
        <p className="text-center text-stone-500 text-sm max-w-xl mx-auto mb-12">
          Agent Booster exposes three MCP tools that replace whole-file reads with
          targeted symbol lookups — the model sees exactly what it needs and nothing else.
        </p>

        <div className="grid sm:grid-cols-3 gap-5">
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

/* ─── Works with ───────────────────────────────────────────────────────── */

const WORKS_WITH = [
  {
    name: "Claude Code",
    icon: "◈",
    color: "text-orange-600",
    bg: "bg-orange-50 border-orange-200",
    desc: "Native MCP integration via booster init claude",
  },
  {
    name: "Cursor",
    icon: "⊙",
    color: "text-blue-600",
    bg: "bg-blue-50 border-blue-200",
    desc: "Drop-in via booster init cursor",
  },
  {
    name: "OpenAI Codex",
    icon: "◎",
    color: "text-emerald-600",
    bg: "bg-emerald-50 border-emerald-200",
    desc: "Full support via booster init codex",
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

        <div className="grid sm:grid-cols-3 gap-5">
          {WORKS_WITH.map(tool => (
            <div key={tool.name} className={`rounded-2xl border ${tool.bg} px-6 py-6 flex flex-col items-center text-center gap-3`}>
              <span className={`text-3xl font-black ${tool.color}`}>{tool.icon}</span>
              <div>
                <p className="font-semibold text-stone-900 mb-1">{tool.name}</p>
                <p className="text-xs text-stone-500">{tool.desc}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

/* ─── Footer CTA ───────────────────────────────────────────────────────── */

function FooterCTASection() {
  return (
    <section className="px-6 py-20 text-center">
      <h2 className="text-3xl font-bold text-stone-900 mb-4">
        Start saving tokens today.
      </h2>
      <p className="text-stone-500 mb-8 max-w-md mx-auto">
        Open source, MIT licensed. File issues and contribute on GitHub.
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
        <a href="/marketplace" className="hover:text-stone-600 transition-colors">Playbooks</a>
        <span>·</span>
        <a href="/docs" className="hover:text-stone-600 transition-colors">Docs</a>
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
