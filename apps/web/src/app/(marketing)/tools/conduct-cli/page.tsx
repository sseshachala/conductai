"use client"

import { useState, useEffect, useRef } from "react"

export default function ConductCliPage() {
  return (
    <div className="min-h-screen bg-white flex flex-col">
      <Nav />
      <main>
        <DiagnosticHero />
        <WhatItCoversSection />
        <QuickstartSection />
        <WorksWithSection />
        <UseCasesSection />
        <GuardInsightsCallout />
        <WhatsNewSection />
        <FaqSection />
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
        <a href="https://github.com/sseshachala/conductai" target="_blank" rel="noopener noreferrer" className="text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">GitHub</a>
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

/* ─── Shared components ────────────────────────────────────────────────── */

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

/* ─── Diagnostic Hero ──────────────────────────────────────────────────── */

type Segment = {
  text: string
  speed?: number   // ms per char
  pause?: number   // ms pause after this segment completes
  style?: "question" | "answer" | "code" | "stat" | "label"
}

const SCRIPT: Segment[] = [
  { text: "What AI tool are you on?\n", style: "question", speed: 28, pause: 520 },
  { text: "Probably Claude Code — that's where we see the most context waste.\n\n", style: "answer", speed: 22, pause: 680 },
  { text: "How big is your codebase?\n", style: "question", speed: 28, pause: 500 },
  { text: "Let's say medium — 50 to 500 files. That's the sweet spot where bloat really bites.\n\n", style: "answer", speed: 20, pause: 700 },
  { text: "What's leaking tokens?\n", style: "question", speed: 28, pause: 440 },
  { text: "Three things.\n\n", style: "answer", speed: 35, pause: 260 },
  { text: "File reads sending 800-line files when the model needed 40 lines.\n", style: "answer", speed: 18, pause: 180 },
  { text: "CLI output — pytest runs, git diffs, docker logs — flooding the context before you've done anything useful.\n", style: "answer", speed: 18, pause: 180 },
  { text: "And responses that are longer than they have to be.\n\n", style: "answer", speed: 20, pause: 700 },
  { text: "Here's what fixes all three:\n\n", style: "label", speed: 26, pause: 300 },
  { text: "$ pip install agent-booster[full]\n", style: "code", speed: 14, pause: 120 },
  { text: "$ booster start\n", style: "code", speed: 14, pause: 120 },
  { text: "$ booster verbosity full\n\n", style: "code", speed: 14, pause: 700 },
  { text: "INPUT tokens: RTK cuts CLI output 85–99%. Booster cuts file reads 50–77%.\n", style: "stat", speed: 18, pause: 220 },
  { text: "OUTPUT tokens: verbosity mode cuts responses ~75%.\n\n", style: "stat", speed: 18, pause: 700 },
  { text: "On a medium repo that's roughly 300–600k tokens saved per session.\n", style: "answer", speed: 20, pause: 260 },
  { text: "Run booster gain after your first session to see the real number.", style: "answer", speed: 20, pause: 0 },
]

function DiagnosticHero() {
  const [revealed, setRevealed] = useState("")
  const [done, setDone] = useState(false)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const bottomRef = useRef<HTMLDivElement | null>(null)

  function clearTimer() {
    if (timerRef.current) clearTimeout(timerRef.current)
  }

  function runScript(startRevealed = "") {
    clearTimer()
    setRevealed(startRevealed)
    setDone(false)

    // Build a flat sequence of {char, delay} pairs
    const frames: Array<{ char: string; delay: number }> = []

    // pause before first segment
    frames.push({ char: "", delay: 600 })

    for (const seg of SCRIPT) {
      const speed = seg.speed ?? 22
      const text = seg.text

      for (let i = 0; i < text.length; i++) {
        const ch = text[i]
        // natural pauses at punctuation
        let d = speed
        if (ch === "." || ch === "?" || ch === "!") d = speed + 120
        else if (ch === ",") d = speed + 60
        else if (ch === "\n") d = speed + 40
        frames.push({ char: ch, delay: d })
      }

      if (seg.pause && seg.pause > 0) {
        frames.push({ char: "", delay: seg.pause })
      }
    }

    let idx = 0
    let acc = startRevealed

    function tick() {
      if (idx >= frames.length) {
        setDone(true)
          return
      }
      const { char, delay } = frames[idx]
      if (char) {
        acc += char
        setRevealed(acc)
      }
      idx++
      timerRef.current = setTimeout(tick, delay)
    }

    timerRef.current = setTimeout(tick, 0)
  }

  useEffect(() => {
    runScript()
    return clearTimer
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // auto-scroll to bottom as text grows
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" })
  }, [revealed])

  function replay() {
    runScript()
  }

  function skip() {
    clearTimer()
    const full = SCRIPT.map(s => s.text).join("")
    setRevealed(full)
    setDone(true)
  }

  // Render revealed text with per-line styling
  const lines = revealed.split("\n")

  function renderLine(line: string, idx: number) {
    if (!line) return <div key={idx} className="h-4" />
    if (line.startsWith("$ ")) {
      return (
        <div key={idx} className="flex items-center gap-2 font-mono text-sm">
          <span className="text-stone-600 select-none">$</span>
          <span className="text-emerald-400">{line.slice(2)}</span>
        </div>
      )
    }
    if (line.endsWith("?")) {
      return (
        <p key={idx} className="text-stone-400 text-sm font-medium mt-3 first:mt-0">
          {line}
        </p>
      )
    }
    if (line.startsWith("INPUT tokens:") || line.startsWith("OUTPUT tokens:")) {
      const [label, ...rest] = line.split(":")
      return (
        <p key={idx} className="text-sm font-mono">
          <span className={label.startsWith("INPUT") ? "text-indigo-400 font-semibold" : "text-violet-400 font-semibold"}>
            {label}:
          </span>
          <span className="text-stone-400">{rest.join(":")}</span>
        </p>
      )
    }
    if (line.startsWith("Here's what fixes") || line.startsWith("Here's what") || line === "Here's what fixes all three:") {
      return <p key={idx} className="text-stone-500 text-xs uppercase tracking-widest font-semibold mt-4 mb-1">{line}</p>
    }
    return (
      <p key={idx} className="text-stone-200 text-sm leading-relaxed">
        {line}
      </p>
    )
  }

  return (
    <section className="flex flex-col items-center px-6 pt-16 pb-24">
      {/* Badge */}
      <div className="flex items-center gap-2 mb-8">
        <span className="text-indigo-400 font-black text-lg">◈</span>
        <span className="text-xs font-semibold text-stone-400 uppercase tracking-widest">Agent Booster v0.2.30</span>
        <span className="text-[10px] font-bold bg-emerald-900 text-emerald-300 border border-emerald-700 px-2 py-0.5 rounded-full uppercase tracking-widest">Free · MIT</span>
      </div>

      {/* Chat window */}
      <div className="w-full max-w-2xl rounded-2xl bg-stone-950 border border-stone-800 overflow-hidden shadow-xl">
        {/* Title bar */}
        <div className="flex items-center gap-2 px-4 py-3 border-b border-stone-800 bg-stone-900">
          <span className="w-3 h-3 rounded-full bg-red-500/60" />
          <span className="w-3 h-3 rounded-full bg-yellow-500/60" />
          <span className="w-3 h-3 rounded-full bg-green-500/60" />
          <span className="ml-3 text-xs text-stone-500 font-mono">agent-booster — diagnostic</span>
          {!done && (
            <button
              onClick={skip}
              className="ml-auto text-[10px] text-stone-600 hover:text-stone-400 transition-colors font-mono cursor-pointer"
            >
              skip →
            </button>
          )}
        </div>

        {/* Content */}
        <div className="px-6 py-6 min-h-[320px] flex flex-col gap-0.5">
          {lines.map((line, i) => renderLine(line, i))}
          {/* blinking cursor */}
          {!done && (
            <span className="inline-block w-2 h-4 bg-indigo-400 align-middle animate-pulse" />
          )}
          <div ref={bottomRef} />
        </div>
      </div>

      {/* CTA row */}
      {done && (
        <div className="mt-8 flex flex-col sm:flex-row items-center gap-4">
          <div className="flex items-center rounded-xl bg-stone-950 border border-stone-800 px-5 py-3">
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
          <button
            onClick={replay}
            className="text-xs text-stone-400 underline hover:text-stone-600 transition-colors cursor-pointer"
          >
            replay
          </button>
        </div>
      )}
    </section>
  )
}

/* ─── What it covers ───────────────────────────────────────────────────── */

function WhatItCoversSection() {
  const cards = [
    {
      icon: "◈",
      binary: "conduct",
      title: "Conduct CLI",
      desc: "Run agents, manage projects, switch workspaces, show runs. The daily driver for every developer on the Conduct platform.",
      color: "text-indigo-600",
      bg: "bg-indigo-50 border-indigo-200",
    },
    {
      icon: "⊙",
      binary: "conductguard-mcp",
      title: "ConductGuard MCP",
      desc: "MCP server that enforces AI usage policies set by your team lead. Every tool call Claude makes passes through Guard first.",
      color: "text-violet-600",
      bg: "bg-violet-50 border-violet-200",
    },
    {
      icon: "≋",
      binary: "conduct switch <workspace>",
      title: "Guard Policy Sync",
      desc: "Switch workspace and instantly re-sync Guard policies. No manual reconfiguration across multiple config files.",
      color: "text-emerald-600",
      bg: "bg-emerald-50 border-emerald-200",
    },
  ] as const

  return (
    <section className="bg-stone-50 px-6 py-20">
      <div className="max-w-5xl mx-auto">
        <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest text-center mb-3">
          What&apos;s included
        </p>
        <h2 className="text-3xl font-bold text-stone-900 text-center mb-4">
          One package. Three capabilities.
        </h2>
        <p className="text-center text-stone-500 text-sm max-w-xl mx-auto mb-12">
          conduct-cli ships the platform CLI, the ConductGuard MCP server, and atomic workspace
          switching &mdash; everything your team needs to run agents safely from the terminal.
        </p>

        <div className="grid sm:grid-cols-3 gap-6">
          {cards.map((card) => (
            <div
              key={card.title}
              className={`rounded-2xl border ${card.bg} px-7 py-7 flex flex-col gap-4`}
            >
              <span className={`text-3xl font-black ${card.color}`}>{card.icon}</span>
              <div>
                <code className={`font-mono text-xs font-semibold ${card.color} mb-2 block`}>
                  {card.binary}
                </code>
                <p className="text-base font-semibold text-stone-900 mb-2">{card.title}</p>
                <p className="text-sm text-stone-600 leading-relaxed">{card.desc}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

/* ─── Quickstart ───────────────────────────────────────────────────────── */

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

/* ─── Use Cases ────────────────────────────────────────────────────────── */

const USE_CASES = [
  {
    title: "Running an agent from the terminal",
    scenario:
      "You want to run the \u201cgithub-pr-review\u201d agent on a new PR without opening the browser.",
    without: {
      label: "Without CLI",
      steps: [
        "Open browser and navigate to Conduct",
        "Find the agent, fill in params, click Run",
        "Wait for the browser to show output",
      ],
      cost: "2 minutes of context-switching",
      color: "text-red-600",
      bg: "bg-red-50 border-red-200",
    },
    with: {
      label: "With conduct-cli",
      steps: [
        "conduct run github-pr-review --pr 142",
        "Agent fires immediately from the terminal",
        "Live output streams to your terminal, done",
      ],
      cost: "8 seconds from idea to result",
      color: "text-emerald-600",
      bg: "bg-emerald-50 border-emerald-200",
    },
    saving: "2 min \u2192 8 sec",
  },
  {
    title: "Enforcing AI policies across the team",
    scenario:
      "Your security lead sets a policy: Claude must not write to production config files.",
    without: {
      label: "Without Guard",
      steps: [
        "Policy lives in a doc no one reads",
        "Violations happen silently in developers\u2019 terminals",
        "No audit trail, no visibility for the team lead",
      ],
      cost: "0 violations caught",
      color: "text-red-600",
      bg: "bg-red-50 border-red-200",
    },
    with: {
      label: "With ConductGuard MCP",
      steps: [
        "Every file-write tool call Claude makes is checked against the policy",
        "Blocked calls are logged with who, what, and when",
        "Manager sees violations in the Guard Insights dashboard",
      ],
      cost: "0 violations slip through",
      color: "text-emerald-600",
      bg: "bg-emerald-50 border-emerald-200",
    },
    saving: "0 violations slip through",
  },
  {
    title: "Switching workspaces",
    scenario:
      "You work across a staging and production workspace. You need to switch contexts and run agents against staging.",
    without: {
      label: "Without CLI",
      steps: [
        "Edit ~/.conduct/config.json manually",
        "Edit ~/.conductguard/config.json manually",
        "Restart MCP server, hope you got both right",
      ],
      cost: "5 manual steps, easy to miss one",
      color: "text-red-600",
      bg: "bg-red-50 border-red-200",
    },
    with: {
      label: "With conduct switch",
      steps: [
        "conduct switch staging",
        "Both configs updated atomically",
        "Guard policies re-synced to the new workspace instantly",
      ],
      cost: "One command, always consistent",
      color: "text-emerald-600",
      bg: "bg-emerald-50 border-emerald-200",
    },
    saving: "5 steps \u2192 1 command",
  },
  {
    title: "Knowing who you are",
    scenario:
      "You forget which workspace your terminal is pointed at before running a destructive agent.",
    without: {
      label: "Without CLI",
      steps: [
        "Check two separate config files",
        "Cross-reference workspace IDs manually",
        "Still not sure if Guard is actually wired",
      ],
      cost: "Uncertainty before every run",
      color: "text-red-600",
      bg: "bg-red-50 border-red-200",
    },
    with: {
      label: "With conduct whoami",
      steps: [
        "conduct whoami",
        "Shows workspace name, server, Guard status (hook wired + policy count)",
        "Booster status included \u2014 full picture in one command",
      ],
      cost: "Instant context, zero doubt",
      color: "text-emerald-600",
      bg: "bg-emerald-50 border-emerald-200",
    },
    saving: "instant context check",
  },
] as const

function UseCasesSection() {
  const [active, setActive] = useState<number>(0)
  const uc = USE_CASES[active]

  return (
    <section className="px-6 py-20">
      <div className="max-w-5xl mx-auto">
        <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest text-center mb-3">
          Example use cases
        </p>
        <h2 className="text-3xl font-bold text-stone-900 text-center mb-4">
          See the difference on real tasks.
        </h2>
        <p className="text-center text-stone-500 text-sm max-w-xl mx-auto mb-10">
          These are actual patterns from everyday development workflows &mdash; not synthetic
          demos.
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
            <div className="shrink-0 text-right">
              <p className="text-base font-black text-indigo-600 whitespace-nowrap">{uc.saving}</p>
              <p className="text-xs text-stone-400 mt-0.5">time saved</p>
            </div>
          </div>

          {/* Comparison */}
          <div className="grid sm:grid-cols-2 divide-y sm:divide-y-0 sm:divide-x divide-stone-100">
            {[uc.without, uc.with].map((side) => (
              <div key={side.label} className="px-8 py-7 flex flex-col gap-4">
                <p
                  className={`text-xs font-bold uppercase tracking-widest ${side.color}`}
                >
                  {side.label}
                </p>
                <ul className="space-y-2.5">
                  {side.steps.map((step, i) => (
                    <li
                      key={i}
                      className="flex items-start gap-2.5 text-sm text-stone-600"
                    >
                      <span
                        className={`mt-0.5 w-4 h-4 rounded-full border flex items-center justify-center shrink-0 text-[10px] font-bold ${side.bg} ${side.color}`}
                      >
                        {side === uc.with ? "✓" : "✕"}
                      </span>
                      {step}
                    </li>
                  ))}
                </ul>
                <div className="mt-auto pt-4 border-t border-stone-100">
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

/* ─── Guard Insights Callout ───────────────────────────────────────────── */

function GuardInsightsCallout() {
  return (
    <section className="bg-stone-900 px-6 py-20">
      <div className="max-w-3xl mx-auto">
        <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest text-center mb-3">
          Guard Insights
        </p>
        <h2 className="text-3xl font-bold text-white text-center mb-8">
          See what every developer&apos;s AI is doing.
        </h2>

        <div className="flex flex-col gap-3 mb-10">
          {[
            "Every blocked tool call logged with who, what, and when",
            "Coverage table: which developers have Guard wired",
            "Events feed: real-time stream of policy enforcement",
          ].map((point) => (
            <div
              key={point}
              className="rounded-2xl border border-stone-700 bg-stone-800 px-6 py-4 flex items-start gap-3"
            >
              <span className="mt-0.5 w-4 h-4 rounded-full bg-indigo-900 border border-indigo-600 text-indigo-400 flex items-center justify-center shrink-0 text-[10px] font-bold">
                ✓
              </span>
              <p className="text-sm text-stone-300 leading-relaxed">{point}</p>
            </div>
          ))}
        </div>

        <div className="text-center">
          <a
            href="/guard/insights"
            className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-6 py-3 text-sm font-semibold text-white hover:bg-indigo-700 transition-colors"
          >
            Open Guard Insights &rarr;
          </a>
        </div>
      </div>
    </section>
  )
}

/* ─── What's New ───────────────────────────────────────────────────────── */

const WHATS_NEW_ITEMS = [
  {
    icon: "🤝",
    title: "Shared team index",
    tag: "v0.2.30",
    desc: "booster index-push uploads your symbol index to the team workspace via the Guard sync channel. Teammates run booster index-pull (or just conduct guard sync) to merge it locally — no re-indexing the same repo twice. Uses the same auth as guard sync, zero new config.",
    color: "text-indigo-600",
    bg: "bg-indigo-50 border-indigo-200",
  },
  {
    icon: "🎓",
    title: "booster learn",
    tag: "v0.2.28",
    desc: "Mines your local read history and Guard failed run traces to extract patterns — hot files, files that resist smart_read, turn limit failures. Writes corrections directly to CLAUDE.md under a dedicted block. Run booster learn --dry-run to preview first.",
    color: "text-emerald-600",
    bg: "bg-emerald-50 border-emerald-200",
  },
  {
    icon: "🗜️",
    title: "SmartCrusher",
    tag: "v0.2.27",
    desc: "Compression pass on every smart_read and search_context result before it reaches the model. JSON arrays: keeps first 5 + last 3 entries, drops middle duplicates. Repeated lines: collapsed into '… N identical lines omitted'. Kicks in above 2KB — small results pass through untouched.",
    color: "text-rose-600",
    bg: "bg-rose-50 border-rose-200",
  },
  {
    icon: "⚡",
    title: "Cache alignment",
    tag: "v0.2.26",
    desc: "Tools are now returned alphabetically with deterministically sorted schema keys on every request. Anthropic users get free KV cache hits on the tools prefix — same tool list every session means the prefix is already cached. Auto-detected from ANTHROPIC_API_KEY, no config needed. booster gain shows cache alignment status.",
    color: "text-amber-600",
    bg: "bg-amber-50 border-amber-200",
  },
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
            v0.2.16 – v0.2.30
          </span>
        </div>
        <h2 className="text-3xl font-bold text-stone-900 text-center mb-4">
          SmartCrusher, cache alignment, booster learn, and shared team index.
        </h2>
        <p className="text-center text-stone-500 text-sm max-w-2xl mx-auto mb-12">
          Four new releases. The result: booster cuts costs at every layer — elimination, compression, caching, and learning from every session,
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

/* ─── Footer CTA ───────────────────────────────────────────────────────── */

function FooterCTASection() {
  return (
    <section className="px-6 py-20 text-center">
      <h2 className="text-3xl font-bold text-stone-900 mb-4">
        Your terminal. Your team&apos;s rules.{" "}
        <span className="text-indigo-600">One CLI.</span>
      </h2>
      <p className="text-stone-500 mb-8 max-w-lg mx-auto">
        Run agents, enforce policies, switch workspaces, and know exactly what context your
        terminal is operating in &mdash; all from a single command.
      </p>

      <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
        <div className="flex items-center rounded-xl bg-stone-950 px-5 py-3">
          <code className="font-mono text-sm text-emerald-400">pip install conduct-cli</code>
          <CopyButton text="pip install conduct-cli" />
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
      <p className="mt-4 text-xs text-stone-400">Python 3.10+ &middot; MIT licensed</p>
    </section>
  )
}

/* ─── Page Footer ──────────────────────────────────────────────────────── */

function PageFooter() {
  return (
    <footer className="border-t border-stone-100 py-8 text-center text-xs text-stone-400 space-y-2">
      <div className="flex items-center justify-center gap-3 flex-wrap">
        <span>&copy; {new Date().getFullYear()} Conduct</span>
        <span>&middot;</span>
        <a
          href="https://github.com/sseshachala/conductai"
          target="_blank"
          rel="noopener noreferrer"
          className="hover:text-stone-600 transition-colors"
        >
          GitHub
        </a>
        <span>&middot;</span>
        <span>MIT licensed</span>
        <span>&middot;</span>
        <a href="/" className="hover:text-stone-600 transition-colors">
          Conduct AI
        </a>
        <span>&middot;</span>
        <a href="/marketplace" className="hover:text-stone-600 transition-colors">
          Agent Templates
        </a>
        <span>&middot;</span>
        <a href="/docs" className="hover:text-stone-600 transition-colors">
          Docs
        </a>
        <span>&middot;</span>
        <a href="/about" className="hover:text-stone-600 transition-colors">
          About
        </a>
        <span>&middot;</span>
        <a href="/privacy" className="hover:text-stone-600 transition-colors">
          Privacy
        </a>
        <span>&middot;</span>
        <a href="/terms" className="hover:text-stone-600 transition-colors">
          Terms
        </a>
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
