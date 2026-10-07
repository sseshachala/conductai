"use client"

import { useState, useEffect, useRef } from "react"
import { CopyButton, GitHubIcon } from "./shared"

/* ─── Diagnostic Hero ──────────────────────────────────────────────────── */

type Segment = {
  text: string
  speed?: number   // ms per char
  pause?: number   // ms pause after this segment completes
  style?: "question" | "answer" | "code" | "stat" | "label"
}

const SCRIPT: Segment[] = [
  { text: "What AI tool are you on?\n", style: "question", speed: 28, pause: 520 },
  { text: "Probably Claude Code, that's where we see the most context waste.\n\n", style: "answer", speed: 22, pause: 680 },
  { text: "How big is your codebase?\n", style: "question", speed: 28, pause: 500 },
  { text: "Let's say medium, 50 to 500 files. That's the sweet spot where bloat really bites.\n\n", style: "answer", speed: 20, pause: 700 },
  { text: "What's leaking tokens?\n", style: "question", speed: 28, pause: 440 },
  { text: "Three things.\n\n", style: "answer", speed: 35, pause: 260 },
  { text: "File reads sending 800-line files when the model needed 40 lines.\n", style: "answer", speed: 18, pause: 180 },
  { text: "CLI output, pytest runs, git diffs, docker logs, flooding the context before you've done anything useful.\n", style: "answer", speed: 18, pause: 180 },
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

/* ─── Page Hook ────────────────────────────────────────────────────────── */

export function PageHook() {
  return (
    <section className="max-w-3xl mx-auto px-6 pt-16 pb-4 text-center">
      <p className="text-xs font-semibold uppercase tracking-widest text-indigo-500 mb-4">Two tools. One stack.</p>
      <h1 className="text-4xl sm:text-5xl font-black tracking-tight text-stone-900 leading-tight mb-4">
        Govern your AI agents.<br />
        <span className="bg-gradient-to-r from-indigo-600 to-violet-600 bg-clip-text text-transparent">
          Cut the cost of running them.
        </span>
      </h1>
      <p className="text-stone-500 leading-relaxed text-lg">
        <code className="font-mono bg-stone-100 text-stone-700 px-1.5 py-0.5 rounded text-sm">conduct-cli</code> manages your AI platform —
        agents, workflows, and Guard policies.{" "}
        <code className="font-mono bg-stone-100 text-stone-700 px-1.5 py-0.5 rounded text-sm">agent-booster</code> cuts token costs 5–15x
        by routing only the code that matters. They&apos;re independent packages that work better together.
      </p>
    </section>
  )
}

/* ─── Two-tool explainer ───────────────────────────────────────────────── */

export function TwoToolSection() {
  return (
    <section className="max-w-4xl mx-auto px-6 py-12">
      <div className="grid sm:grid-cols-2 gap-6">

        {/* conduct-cli */}
        <div className="border border-stone-200 rounded-2xl p-6 bg-white">
          <div className="flex items-center gap-2 mb-3">
            <span className="text-xs font-bold uppercase tracking-widest text-indigo-600 bg-indigo-50 px-2.5 py-1 rounded-full">conduct-cli</span>
          </div>
          <p className="text-stone-800 font-semibold text-lg mb-2">Platform CLI</p>
          <p className="text-stone-500 text-sm mb-4">
            Authenticate, install agents, trigger workflows, and enforce Guard policies — all from the terminal.
          </p>
          <ul className="space-y-1.5 text-sm text-stone-600 font-mono">
            <li><span className="text-indigo-400">$</span> conduct login</li>
            <li><span className="text-indigo-400">$</span> conduct install-all</li>
            <li><span className="text-indigo-400">$</span> conduct guard sync</li>
            <li><span className="text-indigo-400">$</span> conduct verify --strict</li>
            <li><span className="text-indigo-400">$</span> conduct test --all</li>
          </ul>
          <p className="mt-4 text-xs text-stone-400 font-mono">pip install conduct-cli</p>
        </div>

        {/* agent-booster */}
        <div className="border border-stone-200 rounded-2xl p-6 bg-white">
          <div className="flex items-center gap-2 mb-3">
            <span className="text-xs font-bold uppercase tracking-widest text-emerald-600 bg-emerald-50 px-2.5 py-1 rounded-full">agent-booster</span>
          </div>
          <p className="text-stone-800 font-semibold text-lg mb-2">Token Optimizer</p>
          <p className="text-stone-500 text-sm mb-4">
            Parses your codebase with tree-sitter, builds a symbol index, and returns only the functions and classes relevant to each task — instead of full files.
          </p>
          <ul className="space-y-1.5 text-sm text-stone-600 font-mono">
            <li><span className="text-emerald-400">$</span> booster init claude</li>
            <li><span className="text-emerald-400">$</span> booster index &amp;&amp; booster embed</li>
            <li><span className="text-emerald-400">$</span> booster serve</li>
            <li><span className="text-emerald-400">$</span> booster gain</li>
          </ul>

        </div>
      </div>

      {/* How they work together */}
      <div className="mt-6 bg-stone-950 rounded-2xl p-6 text-sm">
        <p className="text-stone-400 text-xs font-semibold uppercase tracking-widest mb-4">How they work together</p>
        <div className="flex flex-col sm:flex-row items-start sm:items-center gap-3 text-stone-300">
          <div className="bg-indigo-900/40 border border-indigo-800 rounded-xl px-4 py-3 text-xs font-mono flex-1">
            <p className="text-indigo-300 font-semibold mb-1">conduct-cli</p>
            <p className="text-stone-400">installs agents, enforces policies, triggers runs</p>
          </div>
          <span className="text-stone-600 text-lg hidden sm:block">+</span>
          <div className="bg-emerald-900/30 border border-emerald-800 rounded-xl px-4 py-3 text-xs font-mono flex-1">
            <p className="text-emerald-300 font-semibold mb-1">agent-booster</p>
            <p className="text-stone-400">routes only relevant symbols on every file read</p>
          </div>
          <span className="text-stone-600 text-lg hidden sm:block">=</span>
          <div className="bg-stone-800 border border-stone-700 rounded-xl px-4 py-3 text-xs flex-1">
            <p className="text-white font-semibold mb-1">Governed + cheap</p>
            <p className="text-stone-400">policies enforced, token costs down 5–15x</p>
          </div>
        </div>
      </div>
    </section>
  )
}

/* ─── Diagnostic Hero ──────────────────────────────────────────────────── */

export function DiagnosticHero() {
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


      {/* Chat window */}
      <div className="w-full max-w-2xl rounded-2xl bg-stone-950 border border-stone-800 overflow-hidden shadow-xl">
        {/* Title bar */}
        <div className="flex items-center gap-2 px-4 py-3 border-b border-stone-800 bg-stone-900">
          <span className="w-3 h-3 rounded-full bg-red-500/60" />
          <span className="w-3 h-3 rounded-full bg-yellow-500/60" />
          <span className="w-3 h-3 rounded-full bg-green-500/60" />
          <span className="ml-3 text-xs text-stone-500 font-mono">agent-booster, diagnostic</span>
          {!done && (
            <button
              onClick={skip}
              className="ml-auto text-[10px] text-stone-600 hover:text-stone-400 transition-colors font-mono cursor-pointer"
            >
              skip →
            </button>
          )}
        </div>

        {/* Content — capped + internally scrollable so the auto-typing
            scrollIntoView stays inside the chat pane and doesn't hijack
            the page scroll position. */}
        <div className="px-6 py-6 min-h-[320px] max-h-[60vh] overflow-y-auto flex flex-col gap-0.5">
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
            <code className="font-mono text-sm text-emerald-400">pip install conduct-cli</code>
            <CopyButton text="pip install conduct-cli" />
          </div>
          <a
            href="https://github.com/sseshachala/conduct-cli"
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
