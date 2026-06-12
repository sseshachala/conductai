"use client"

import { useState } from "react"


export default function AgentBoosterPage() {
  return (
    <div className="min-h-screen bg-white flex flex-col">
      <Nav />
      <main>
        <DiagnosticHero />
        <InspirationSection />
        <QuickstartSection />
        <WorksWithSection />
        <WhatsNewSection />
        <FaqSection />
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

/* ─── Diagnostic Hero ──────────────────────────────────────────────────── */

type Tool = "Claude Code" | "Cursor" | "Codex" | "Windsurf" | "Multiple tools" | "Not sure yet"
type Size = "Small — under 50 files" | "Medium — 50 to 500 files" | "Large — 500+ files"
type Pain =
  | "Context window fills up too fast"
  | "AI tool costs are climbing"
  | "CI and build logs flood everything"
  | "Just want to see what's possible"

type Answers = {
  tool: Tool | null
  size: Size | null
  pain: Pain | null
}

type FollowUpKey =
  | "What's the catch?"
  | "Does anything leave my machine?"
  | "How is this different from just using the model directly?"
  | "What's RTK?"
  | "How does verbosity work?"
  | "Will this slow down my editor?"
  | "How do I see my savings?"
  | "Does it need an account?"

const FOLLOW_UP_ANSWERS: Record<FollowUpKey, string> = {
  "What's the catch?":
    "Needs Python 3.10+. First index takes 10–30 seconds depending on repo size. Verbosity mode changes your CLAUDE.md — you can turn it off with `booster verbosity off`. Everything else is invisible once installed.",
  "Does anything leave my machine?":
    "Nothing. Index lives in `.booster/` in your project root. Stats in `.booster/stats.db`. Hooks wire into your local Claude/Cursor settings. No telemetry, no cloud sync, no account.",
  "How is this different from just using the model directly?":
    "The model reads what you give it. Booster changes what you give it — symbol slices instead of full files, relevant functions instead of 800-line modules. The model gets better context, not just less context.",
  "What's RTK?":
    "Rust Token Killer — a CLI proxy that filters command output before it hits your context. `rtk git diff` instead of `git diff` — same output, 80% fewer tokens. Works for pytest, docker, npm, grep, everything.",
  "How does verbosity work?":
    "`booster verbosity full` injects a conciseness instruction into your CLAUDE.md. The model gives shorter responses — same quality, less ceremony. 30–75% output token reduction. `booster verbosity off` removes it.",
  "Will this slow down my editor?":
    "No. The daemon runs as a background process, keeps the index warm. File reads that hit the index are faster than cold reads. Grep calls get intercepted but return in the same time window.",
  "How do I see my savings?":
    "Run `booster gain` from your project root after one session. Shows tokens saved, savings rate, top files. Resets nothing — cumulative across all sessions.",
  "Does it need an account?":
    "No. Fully local. No signup, no API key, no cloud. If you later want team-wide visibility, that's Conduct Guard — but it's optional and separate.",
}

const FOLLOW_UPS_BY_PAIN: Record<Pain, FollowUpKey[]> = {
  "Context window fills up too fast": [
    "What's the catch?",
    "Does anything leave my machine?",
    "How is this different from just using the model directly?",
  ],
  "AI tool costs are climbing": [
    "How does verbosity work?",
    "How do I see my savings?",
    "Does it need an account?",
  ],
  "CI and build logs flood everything": [
    "What's RTK?",
    "Will this slow down my editor?",
    "Does anything leave my machine?",
  ],
  "Just want to see what's possible": [
    "What's the catch?",
    "Does it need an account?",
    "How do I see my savings?",
  ],
}

function getDiagnosis(pain: Pain): string {
  const map: Record<Pain, string> = {
    "Context window fills up too fast":
      "You're sending full files when the model needs 40 lines. On a large repo that's 800-line files, 60–80% waste per read. Across a session: easily 1M+ tokens gone before you've done anything useful.",
    "AI tool costs are climbing":
      "Two separate leaks: file reads sending way more context than needed, and responses that are longer than they have to be. RTK handles CLI output. Booster handles file reads. Verbosity mode handles responses. Stack all three.",
    "CI and build logs flood everything":
      "Raw CI output is brutal — a failed pytest run is 4,000 lines when you need 12. RTK filters to failures only. Same for git diff, docker logs, npm install. 85–99% reduction on every command.",
    "Just want to see what's possible":
      "Three tools, one problem: too many tokens. RTK cuts CLI output. Booster cuts file reads. Verbosity cuts responses. None of them require an account. All run locally. Here's where to start:",
  }
  return map[pain]
}

function getSavingsEstimate(size: Size): string {
  const map: Record<Size, string> = {
    "Small — under 50 files": "~50–150k tokens/session",
    "Medium — 50 to 500 files": "~300–600k tokens/session",
    "Large — 500+ files": "~1M+ tokens/session (we observed 1.2M in 6 days)",
  }
  return map[size]
}

function getInitCommand(tool: Tool): string {
  const map: Record<Tool, string> = {
    "Claude Code": "booster init claude",
    "Cursor": "booster init cursor",
    "Codex": "booster init codex",
    "Windsurf": "booster init windsurf",
    "Multiple tools": "booster init --all",
    "Not sure yet": "booster init claude",
  }
  return map[tool]
}

function DiagnosticHero() {
  const [answers, setAnswers] = useState<Answers>({ tool: null, size: null, pain: null })
  const [step, setStep] = useState<1 | 2 | 3 | 4>(1)
  const [visible, setVisible] = useState(true)
  const [pulsing, setPulsing] = useState<string | null>(null)
  const [thinking, setThinking] = useState(false)
  const [openFollowUp, setOpenFollowUp] = useState<FollowUpKey | null>(null)

  function transition(next: 1 | 2 | 3 | 4, updateAnswers: () => void) {
    setVisible(false)
    setTimeout(() => {
      updateAnswers()
      setStep(next)
      if (next === 4) {
        setThinking(true)
        setTimeout(() => {
          setThinking(false)
          setVisible(true)
        }, 300)
      } else {
        setVisible(true)
      }
    }, 200)
  }

  function pickTool(tool: Tool) {
    setPulsing(tool)
    setTimeout(() => {
      setPulsing(null)
      transition(2, () => setAnswers(a => ({ ...a, tool })))
    }, 150)
  }

  function pickSize(size: Size) {
    setPulsing(size)
    setTimeout(() => {
      setPulsing(null)
      transition(3, () => setAnswers(a => ({ ...a, size })))
    }, 150)
  }

  function pickPain(pain: Pain) {
    setPulsing(pain)
    setTimeout(() => {
      setPulsing(null)
      transition(4, () => setAnswers(a => ({ ...a, pain })))
    }, 150)
  }

  function reset() {
    setVisible(false)
    setTimeout(() => {
      setAnswers({ tool: null, size: null, pain: null })
      setStep(1)
      setThinking(false)
      setOpenFollowUp(null)
      setVisible(true)
    }, 200)
  }

  const chipBase =
    "border border-stone-200 rounded-full px-5 py-2.5 text-sm font-medium text-stone-700 hover:border-indigo-400 hover:text-indigo-700 hover:bg-indigo-50 transition-all cursor-pointer select-none"
  const chipSelected = "border-indigo-500 bg-indigo-50 text-indigo-700"

  const followUpChipBase =
    "border border-stone-200 rounded-full px-4 py-2 text-xs font-medium text-stone-700 hover:border-indigo-400 hover:text-indigo-700 hover:bg-indigo-50 transition-all cursor-pointer select-none"

  return (
    <section className="flex flex-col items-center justify-center px-6 pt-16 pb-24 text-center min-h-[500px]">
      {/* Progress dots */}
      <div className="flex items-center gap-2 mb-10">
        {([1, 2, 3] as const).map(dot => (
          <div
            key={dot}
            className={`w-2 h-2 rounded-full transition-all duration-300 ${
              step > dot
                ? "bg-indigo-500"
                : step === dot
                ? "bg-indigo-400"
                : "bg-stone-300"
            }`}
          />
        ))}
      </div>

      <div
        className="w-full max-w-2xl transition-opacity duration-200"
        style={{ opacity: visible ? 1 : 0 }}
      >
        {/* Step 1 */}
        {step === 1 && (
          <div>
            <h2 className="text-3xl font-semibold text-stone-900">What are you working with?</h2>
            <p className="text-stone-400 text-sm mt-2">Pick the AI coding tool you use most.</p>
            <div className="flex flex-wrap justify-center gap-3 mt-8">
              {(["Claude Code", "Cursor", "Codex", "Windsurf", "Multiple tools", "Not sure yet"] as Tool[]).map(
                chip => (
                  <button
                    key={chip}
                    onClick={() => pickTool(chip)}
                    className={`${chipBase} ${pulsing === chip ? "scale-95" : ""} ${
                      answers.tool === chip ? chipSelected : ""
                    }`}
                  >
                    {chip}
                  </button>
                )
              )}
            </div>
          </div>
        )}

        {/* Step 2 */}
        {step === 2 && (
          <div>
            <h2 className="text-3xl font-semibold text-stone-900">How big is your codebase?</h2>
            <p className="text-stone-400 text-sm mt-2">Rough estimate is fine.</p>
            <div className="flex flex-wrap justify-center gap-3 mt-8">
              {(["Small — under 50 files", "Medium — 50 to 500 files", "Large — 500+ files"] as Size[]).map(
                chip => (
                  <button
                    key={chip}
                    onClick={() => pickSize(chip)}
                    className={`${chipBase} ${pulsing === chip ? "scale-95" : ""} ${
                      answers.size === chip ? chipSelected : ""
                    }`}
                  >
                    {chip}
                  </button>
                )
              )}
            </div>
          </div>
        )}

        {/* Step 3 */}
        {step === 3 && (
          <div>
            <h2 className="text-3xl font-semibold text-stone-900">What&apos;s hurting most?</h2>
            <p className="text-stone-400 text-sm mt-2">Pick the one that stings the most right now.</p>
            <div className="flex flex-wrap justify-center gap-3 mt-8">
              {([
                "Context window fills up too fast",
                "AI tool costs are climbing",
                "CI and build logs flood everything",
                "Just want to see what's possible",
              ] as Pain[]).map(chip => (
                <button
                  key={chip}
                  onClick={() => pickPain(chip)}
                  className={`${chipBase} ${pulsing === chip ? "scale-95" : ""} ${
                    answers.pain === chip ? chipSelected : ""
                  }`}
                >
                  {chip}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Step 4 — Result */}
        {step === 4 && (
          <div>
            <div className="bg-stone-950 rounded-2xl p-8 max-w-2xl mx-auto text-left">
              {thinking ? (
                <span className="font-mono text-stone-400 text-sm animate-pulse">_</span>
              ) : answers.pain && answers.size && answers.tool ? (
                <>
                  {/* Diagnosis */}
                  <p className="text-white text-base leading-relaxed mb-6">
                    {getDiagnosis(answers.pain)}
                  </p>

                  {/* Token flow header */}
                  <p className="font-mono text-xs text-stone-500 uppercase tracking-widest mb-4">Where tokens go</p>

                  {/* INPUT section */}
                  <div className="mb-5">
                    <div className="flex items-center gap-3 mb-2">
                      <span className="font-mono text-xs font-bold text-indigo-400 uppercase tracking-wider">Input</span>
                      <div className="flex-1 h-px bg-stone-800" />
                    </div>
                    <div className="space-y-2 pl-1">
                      <div className="grid grid-cols-[80px_1fr_auto] gap-x-3 items-baseline font-mono text-sm">
                        <span className="text-stone-300 font-semibold">RTK</span>
                        <span className="text-stone-500 text-xs">CLI output (git / test / build / docker)</span>
                        <span className="text-emerald-400 font-semibold">85–99%</span>
                      </div>
                      <div className="grid grid-cols-[80px_1fr_auto] gap-x-3 items-baseline font-mono text-sm">
                        <span className="text-stone-300 font-semibold">Booster</span>
                        <span className="text-stone-500 text-xs">File reads → symbol slices, not full files</span>
                        <span className="text-emerald-400 font-semibold">50–77%</span>
                      </div>
                    </div>
                  </div>

                  {/* OUTPUT section */}
                  <div className="mb-6">
                    <div className="flex items-center gap-3 mb-2">
                      <span className="font-mono text-xs font-bold text-violet-400 uppercase tracking-wider">Output</span>
                      <div className="flex-1 h-px bg-stone-800" />
                    </div>
                    <div className="pl-1">
                      <div className="grid grid-cols-[80px_1fr_auto] gap-x-3 items-baseline font-mono text-sm">
                        <span className="text-stone-300 font-semibold">Verbosity</span>
                        <span className="text-stone-500 text-xs">Response compression — built in, or use <a href="https://github.com/JuliusBrussee/caveman" target="_blank" rel="noopener noreferrer" className="text-stone-400 hover:text-stone-300 transition-colors">Caveman ↗</a></span>
                        <span className="text-violet-400 font-semibold">~75%</span>
                      </div>
                      <p className="font-mono text-xs text-stone-600 ml-[76px] mt-1">$ booster verbosity full</p>
                    </div>
                  </div>

                  {/* Divider */}
                  <div className="h-px bg-stone-800 mb-5" />

                  {/* Install */}
                  <div className="space-y-1 mb-5">
                    <p className="font-mono text-xs text-stone-500 uppercase tracking-widest mb-3">Install</p>
                    <p className="font-mono text-emerald-400 text-sm">$ pip install agent-booster</p>
                    <p className="font-mono text-emerald-400 text-sm">$ {getInitCommand(answers.tool)}</p>
                    <p className="font-mono text-emerald-400 text-sm">$ booster verbosity full</p>
                  </div>

                  {/* Savings */}
                  <p className="font-mono text-amber-400 text-sm">
                    Est. savings on your setup: {getSavingsEstimate(answers.size)}
                  </p>
                </>
              ) : null}
            </div>

            {/* Follow-up chips */}
            {!thinking && answers.pain && (
              <div className="mt-8">
                {openFollowUp ? (
                  <div className="max-w-2xl mx-auto text-left">
                    <p className="text-stone-700 text-sm leading-relaxed">{FOLLOW_UP_ANSWERS[openFollowUp]}</p>
                    <button
                      onClick={() => setOpenFollowUp(null)}
                      className="mt-4 text-stone-400 text-xs underline cursor-pointer hover:text-stone-600 transition-colors"
                    >
                      back
                    </button>
                  </div>
                ) : (
                  <div className="flex flex-wrap justify-center gap-3">
                    {FOLLOW_UPS_BY_PAIN[answers.pain].map(chip => (
                      <button
                        key={chip}
                        onClick={() => setOpenFollowUp(chip)}
                        className={followUpChipBase}
                      >
                        {chip}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Start over */}
            {!thinking && (
              <button
                onClick={reset}
                className="mt-8 text-stone-400 text-xs underline cursor-pointer hover:text-stone-600 transition-colors"
              >
                Start over
              </button>
            )}
          </div>
        )}
      </div>
    </section>
  )
}

/* ─── What's New ───────────────────────────────────────────────────────── */

const WHATS_NEW_ITEMS = [
  {
    icon: "🛑",
    title: "Output token tracking",
    tag: "v0.2.25",
    desc: "booster-stop.py fires on every Claude Code session end and captures actual output tokens from the stop event. Stores baseline vs. actual in .booster/stats.db. booster gain now shows real savings — not estimates.",
    color: "text-rose-600",
    bg: "bg-rose-50 border-rose-200",
  },
  {
    icon: "🔇",
    title: "Verbosity modes",
    tag: "v0.2.24",
    desc: "booster verbosity lite|full|ultra injects a conciseness block into CLAUDE.md, AGENTS.md, .cursorrules, and .windsurfrules. booster verbosity off removes it. Cuts output token count by 30–75% across all AI coding tools.",
    color: "text-purple-600",
    bg: "bg-purple-50 border-purple-200",
  },
  {
    icon: "🗜️",
    title: "Memory compression",
    tag: "v0.2.24",
    desc: "booster compress rewrites every file in memory/ through claude-haiku to strip filler and cut token count by ~60%. booster compress --dry-run previews savings without writing. Keeps project memory lean as it grows.",
    color: "text-teal-600",
    bg: "bg-teal-50 border-teal-200",
  },
  {
    icon: "⚡",
    title: "Background daemon",
    tag: "v0.2.18",
    desc: "booster start launches a persistent Unix socket process that keeps the embedding model loaded. search_context drops from 2–3 s cold-start to ~50 ms. Daemon survives editor restarts — it's not tied to any terminal.",
    color: "text-amber-600",
    bg: "bg-amber-50 border-amber-200",
  },
  {
    icon: "◎",
    title: "File watcher",
    tag: "v0.2.17",
    desc: "watchdog monitors the project for writes. Changed files are re-indexed within 2 seconds of a save — no manual booster index during a coding session. Daemon handles this automatically.",
    color: "text-blue-600",
    bg: "bg-blue-50 border-blue-200",
  },
  {
    icon: "≋",
    title: "Delta indexing",
    tag: "v0.2.16",
    desc: "SHA-256 hash and mtime stored per file in the SQLite index. Full re-index skips unchanged files entirely. Large repos that took seconds now finish in milliseconds. Use --force to override.",
    color: "text-violet-600",
    bg: "bg-violet-50 border-violet-200",
  },
  {
    icon: "◈",
    title: "Asymmetric embeddings",
    tag: "v0.2.16",
    desc: "Index-time vectors use a passage: prefix; query-time vectors use query:. Follows the E5 paper's asymmetric retrieval approach. Retrieval accuracy improves meaningfully over symmetric embeddings, especially for short function names.",
    color: "text-indigo-600",
    bg: "bg-indigo-50 border-indigo-200",
  },
  {
    icon: "✦",
    title: "booster start does everything",
    tag: "v0.2.18",
    desc: "One command bootstraps the full stack: detects installed AI tools (Claude Code, Cursor, Windsurf, Codex), wires each one that isn't already wired, indexes the project, builds embeddings, and starts the daemon. On subsequent runs it just wakes the daemon.",
    color: "text-emerald-600",
    bg: "bg-emerald-50 border-emerald-200",
  },
]

function WhatsNewSection() {
  return (
    <section className="px-6 py-20 bg-stone-50">
      <div className="max-w-5xl mx-auto">
        <div className="flex items-center justify-center gap-3 mb-3">
          <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest">What&apos;s new</p>
          <span className="text-[10px] font-bold bg-emerald-100 text-emerald-700 border border-emerald-200 px-2 py-0.5 rounded-full uppercase tracking-widest">
            v0.2.16 – v0.2.25
          </span>
        </div>
        <h2 className="text-3xl font-bold text-stone-900 text-center mb-4">
          Daemon, verbosity modes, and output token tracking.
        </h2>
        <p className="text-center text-stone-500 text-sm max-w-2xl mx-auto mb-12">
          Three releases shipped together. The result: booster start is the only command you need,
          search is instant after the first run, and re-indexing costs nothing on unchanged files.
        </p>

        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {WHATS_NEW_ITEMS.map((item) => (
            <div key={item.title} className={`rounded-2xl border ${item.bg} px-6 py-6 flex flex-col gap-3`}>
              <div className="flex items-start justify-between gap-2">
                <span className={`text-2xl font-black ${item.color}`}>{item.icon}</span>
                <span className="text-[10px] font-semibold text-stone-400 bg-white border border-stone-200 px-2 py-0.5 rounded-full font-mono mt-1">
                  {item.tag}
                </span>
              </div>
              <p className="text-sm font-bold text-stone-900">{item.title}</p>
              <p className="text-xs text-stone-600 leading-relaxed">{item.desc}</p>
            </div>
          ))}

          {/* Changelog link card */}
          <div className="rounded-2xl border border-stone-200 bg-white px-6 py-6 flex flex-col gap-3 justify-between">
            <div>
              <p className="text-sm font-bold text-stone-900 mb-2">Full changelog</p>
              <p className="text-xs text-stone-500 leading-relaxed">
                Every commit, diff, and release note lives in the GitHub repo. PRs welcome.
              </p>
            </div>
            <a
              href="https://github.com/sseshachala/conductai/commits/main/tools/booster"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 text-xs font-semibold text-indigo-600 hover:text-indigo-800 transition-colors mt-2"
            >
              <GitHubIcon />
              View commits →
            </a>
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
          Up and running in two commands.
        </h2>

        <div className="flex flex-col gap-5">
          <div>
            <p className="text-xs font-bold text-stone-400 uppercase tracking-widest mb-2">Step 1 — Install</p>
            <InlineCodeBlock comment="includes embeddings + file watcher">pip install agent-booster[full]</InlineCodeBlock>
          </div>
          <div>
            <p className="text-xs font-bold text-stone-400 uppercase tracking-widest mb-2">Step 2 — Start</p>
            <InlineCodeBlock comment="detects Claude/Cursor/Codex, wires hooks, indexes, starts daemon">booster start</InlineCodeBlock>
            <p className="mt-2 text-xs text-stone-400">Detects which AI tools are present (Claude Code, Cursor, Windsurf, Codex), wires each one automatically, indexes the project, and starts a background daemon that keeps the model warm and auto-re-indexes on every file save. Fully reversible with <code className="font-mono bg-stone-100 px-1 rounded text-stone-600">booster remove claude</code>.</p>
          </div>
          <div>
            <p className="text-xs font-bold text-stone-400 uppercase tracking-widest mb-2">That&apos;s it — then track savings</p>
            <InlineCodeBlock>booster gain</InlineCodeBlock>
          </div>
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
    a: "When you run booster index (or booster start on first run), we walk every .py / .ts / .tsx / .js / .jsx file with tree-sitter, extract all function and class nodes, and store name, kind, file path, start/end line, and signature into .booster/symbols.db. Delta indexing skips unchanged files — each file's SHA-256 hash and mtime are stored, so only modified files are re-parsed. Use booster index --force to bypass the delta cache and re-index everything.",
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
    a: "No code, no prompts, no file content ever leaves your machine. The symbol index, vector store, and stats database are all local — stored in .booster/ inside your project. The MCP server runs as a local stdio process. No network calls, no telemetry, no structured events phoned home. The only external call is the one-time model download from HuggingFace when you first run booster embed.",
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
    a: "Yes — once per developer, once per project. Each developer runs pip install 'agent-booster[full]' then booster start inside the project. booster start wires the AI tools it detects, indexes the codebase, builds embeddings, and starts the daemon — nothing manual. The symbol index is gitignored so each developer builds their own locally. For teams, the Sentinel integration (coming) will push the setup automatically to every developer's workspace.",
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
          <code className="font-mono text-sm text-emerald-400">pip install agent-booster[full]</code>
          <CopyButton text="pip install 'agent-booster[full]'" />
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
        Embeddings, file watcher, and daemon all included in the <code className="font-mono bg-stone-100 px-1.5 py-0.5 rounded text-stone-600">[full]</code> extra.
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
