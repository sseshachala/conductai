"use client"

import { useState } from "react"

export default function ConductCliPage() {
  return (
    <div className="min-h-screen bg-white flex flex-col">
      <Nav />
      <main>
        <HeroSection />
        <WhatItCoversSection />
        <UseCasesSection />
        <ClaudePluginSection />
        <SessionsSection />
        <CliReferenceSection />
        <GuardInsightsCallout />
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
              <a href="/tools/agent-booster" className="flex items-center gap-2 px-4 py-2 text-sm text-stone-700 hover:bg-stone-50 transition-colors">
                <span className="text-indigo-600 font-bold">◈</span> Agent Booster
              </a>
              <a href="/tools/conduct-cli" className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-violet-600 bg-violet-50 transition-colors">
                <span className="font-bold">⬡</span> Conduct CLI
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

/* ─── Hero ─────────────────────────────────────────────────────────────── */

function HeroSection() {
  return (
    <section className="flex flex-col items-center justify-center px-6 pt-16 pb-24 text-center">
      <div className="inline-flex items-center gap-2 bg-indigo-50 text-indigo-700 border border-indigo-100 text-xs font-semibold px-3 py-1.5 rounded-full mb-8 uppercase tracking-widest">
        Open Source &middot; v0.4.67
      </div>

      <h1 className="text-5xl sm:text-6xl font-bold text-stone-900 leading-[1.1] tracking-tight max-w-3xl">
        Your AI team&apos;s{" "}
        <span className="text-indigo-600">command centre.</span>
      </h1>

      <p className="mt-6 text-xl text-stone-500 max-w-2xl leading-relaxed">
        conduct-cli connects your terminal to the Conduct platform &mdash; run agents, manage
        projects, enforce AI usage policies with ConductGuard, and switch workspaces in one
        command.
      </p>

      <div className="mt-10 flex flex-col sm:flex-row items-center gap-4">
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
      <p className="mt-4 text-xs text-stone-400">
        Python 3.10+ &middot; MIT licensed &middot; v0.4.67
      </p>

      <div className="mt-14 w-full max-w-3xl">
        <div className="rounded-2xl border border-stone-200 bg-stone-50 p-2 shadow-sm">
          <img
            src="/tools/conduct-cli-demo.gif"
            alt="Conduct CLI demo: conduct whoami, switch workspaces with Guard policy sync, and run an agent from the terminal"
            className="w-full rounded-xl"
            loading="lazy"
          />
        </div>
        <p className="mt-3 text-xs text-stone-400">
          One CLI: run agents, enforce Guard policies, and switch workspaces — your rules travel with you.
        </p>
      </div>
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

/* ─── Claude Plugin ────────────────────────────────────────────────────── */

function ClaudePluginSection() {
  return (
    <section className="bg-stone-50 px-6 py-20">
      <div className="max-w-3xl mx-auto">
        <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest text-center mb-3">
          Claude Code Plugin
        </p>
        <h2 className="text-3xl font-bold text-stone-900 text-center mb-4">
          Install as a Claude Code Plugin.
        </h2>
        <p className="text-center text-stone-500 text-sm max-w-xl mx-auto mb-12">
          conduct-cli is available as an official Claude Code plugin. One slash command installs
          the CLI, wires the ConductGuard MCP server, and you&apos;re live.
        </p>

        <div className="rounded-2xl border border-indigo-200 bg-indigo-50 px-8 py-8 flex flex-col gap-6">
          {/* Install command */}
          <div>
            <p className="text-xs font-bold text-stone-400 uppercase tracking-widest mb-2">
              Install via Claude Code
            </p>
            <InlineCodeBlock>/plugin marketplace add sseshachala/conductai</InlineCodeBlock>
          </div>

          {/* What it does */}
          <div className="grid sm:grid-cols-3 gap-4">
            {[
              {
                icon: "◈",
                title: "conduct CLI",
                desc: "Wires the conduct binary so you can run agents, switch workspaces, and check run history directly from Claude Code.",
                color: "text-indigo-600",
                bg: "bg-white border-indigo-200",
              },
              {
                icon: "⊙",
                title: "ConductGuard MCP",
                desc: "Registers conductguard-mcp as an MCP server &mdash; policy enforcement fires on every tool call Claude makes.",
                color: "text-violet-600",
                bg: "bg-white border-violet-200",
              },
              {
                icon: "≋",
                title: "Policy sync",
                desc: "Guard policies sync automatically when you switch workspaces. No manual config edits required.",
                color: "text-emerald-600",
                bg: "bg-white border-emerald-200",
              },
            ].map((item) => (
              <div
                key={item.title}
                className={`rounded-xl border ${item.bg} px-5 py-4 flex flex-col gap-2`}
              >
                <span className={`text-xl font-black ${item.color}`}>{item.icon}</span>
                <p className="text-sm font-semibold text-stone-900">{item.title}</p>
                <p
                  className="text-xs text-stone-500 leading-relaxed"
                  dangerouslySetInnerHTML={{ __html: item.desc }}
                />
              </div>
            ))}
          </div>

          {/* Post-install step */}
          <div className="border-t border-indigo-200 pt-5">
            <p className="text-xs font-bold text-stone-400 uppercase tracking-widest mb-2">
              Then verify the install
            </p>
            <InlineCodeBlock>conduct whoami</InlineCodeBlock>
            <p className="mt-2 text-xs text-stone-400">
              Shows your active workspace, Guard status, and Booster status in one command.
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

/* ─── CLI Reference ────────────────────────────────────────────────────── */

const CLI_COMMANDS = [
  {
    cmd: "conduct run <agent>",
    when: "Daily",
    what: "Run a named agent. Streams output to terminal.",
  },
  {
    cmd: "conduct list agents",
    when: "Exploring",
    what: "List all agents available in the active workspace.",
  },
  {
    cmd: "conduct list runs",
    when: "Debugging",
    what: "Show recent runs with status and duration.",
  },
  {
    cmd: "conduct switch",
    when: "Context switch",
    what: "List workspaces (current marked with *).",
  },
  {
    cmd: "conduct switch <name>",
    when: "Context switch",
    what: "Switch workspace + re-sync Guard policies atomically.",
  },
  {
    cmd: "conduct whoami",
    when: "Before any run",
    what: "Show workspace, server, Guard status, Booster status.",
  },
  {
    cmd: "conduct guard status",
    when: "Debugging",
    what: "Show Guard hook wiring, policy count, last sync time.",
  },
  {
    cmd: "conductguard-mcp",
    when: "Auto",
    what: "MCP server started by Claude Code. Enforces policies on every tool call.",
  },
  {
    cmd: "conduct-mcp",
    when: "Auto",
    what: "Conduct platform MCP server \u2014 exposes run/list/status as MCP tools.",
  },
] as const

/* ─── Sessions ──────────────────────────────────────────────────────── */

const SESSIONS_TABS = [
  {
    id: "table",
    label: "conduct sessions",
    command: "conduct sessions",
    description: "Instant snapshot of every active Claude Code and Codex session — project, model, context window usage, tokens, turn count, and Guard status. No API key needed, reads local session files.",
    img: "/conduct-sessions/table.png",
    alt: "conduct sessions table view showing CC sessions with context bars",
  },
  {
    id: "tui",
    label: "--tui (live)",
    command: "conduct sessions --tui",
    description: "Full-screen live TUI. Context pressure panel alerts you when any session exceeds 60% — prompts you to /compact before the session degrades. Refreshes every 5s. Ctrl+C to quit.",
    img: "/conduct-sessions/tui.png",
    alt: "conduct sessions --tui showing sessions table with context pressure warning",
  },
  {
    id: "tui-full",
    label: "--tui (full)",
    command: "conduct sessions --tui",
    description: "Three panels in one screen: your local coding sessions, all platform agent runs with status and duration, and team Guard activity grouped by developer. Everything you need to know about your AI fleet at a glance.",
    img: "/conduct-sessions/tui-full.png",
    alt: "conduct sessions --tui full view with My Sessions, Agent Runs, and Team Activity panels",
  },
] as const

function SessionsSection() {
  const [active, setActive] = useState<number>(0)
  const tab = SESSIONS_TABS[active]

  return (
    <section className="bg-stone-50 px-6 py-20">
      <div className="max-w-5xl mx-auto">
        <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest text-center mb-3">conduct sessions</p>
        <h2 className="text-3xl font-bold text-stone-900 text-center mb-4">
          Your entire AI fleet in one command.
        </h2>
        <p className="text-center text-stone-500 text-sm max-w-xl mx-auto mb-10">
          Stop flying blind across terminal windows. <code className="font-mono bg-stone-200 px-1 rounded text-stone-700">conduct sessions</code> shows
          every active Claude Code and Codex session — context usage, tokens, Guard status, agent runs, and team activity — all in one place.
        </p>

        {/* Tab selector */}
        <div className="flex flex-wrap gap-2 justify-center mb-8">
          {SESSIONS_TABS.map((t, i) => (
            <button
              key={t.id}
              onClick={() => setActive(i)}
              className={`rounded-full px-4 py-2 text-xs font-semibold transition-all border font-mono ${
                active === i
                  ? "bg-stone-900 text-emerald-400 border-stone-900"
                  : "bg-white text-stone-600 border-stone-200 hover:border-stone-400"
              }`}
            >
              {t.command}
            </button>
          ))}
        </div>

        {/* Screenshot */}
        <div className="rounded-2xl overflow-hidden border border-stone-800 shadow-2xl bg-stone-950">
          <div className="flex items-center gap-1.5 px-4 py-3 bg-stone-900 border-b border-stone-800">
            <span className="w-3 h-3 rounded-full bg-red-500/70" />
            <span className="w-3 h-3 rounded-full bg-yellow-500/70" />
            <span className="w-3 h-3 rounded-full bg-green-500/70" />
            <code className="ml-3 text-xs text-stone-400 font-mono">{tab.command}</code>
          </div>
          <img
            src={tab.img}
            alt={tab.alt}
            className="w-full block"
          />
        </div>

        {/* Description */}
        <p className="mt-5 text-sm text-stone-500 text-center max-w-2xl mx-auto leading-relaxed">
          {tab.description}
        </p>

        {/* Feature pills */}
        <div className="mt-8 flex flex-wrap gap-3 justify-center">
          {[
            "Claude Code + Codex",
            "Context window bars",
            "Agent runs + status",
            "Team Guard activity",
            "Context pressure alerts",
            "Refreshes every 5s",
          ].map(f => (
            <span key={f} className="inline-flex items-center gap-1.5 text-xs font-medium bg-white border border-stone-200 text-stone-600 px-3 py-1.5 rounded-full">
              <span className="text-emerald-500">✓</span> {f}
            </span>
          ))}
        </div>
      </div>
    </section>
  )
}

function CliReferenceSection() {
  return (
    <section className="px-6 py-20">
      <div className="max-w-5xl mx-auto">
        <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest text-center mb-3">
          CLI Reference
        </p>
        <h2 className="text-3xl font-bold text-stone-900 text-center mb-4">
          Every command, and when to use it.
        </h2>
        <p className="text-center text-stone-500 text-sm max-w-xl mx-auto mb-12">
          Most of the time you only need three:{" "}
          <code className="font-mono bg-stone-200 px-1 rounded">conduct run</code>,{" "}
          <code className="font-mono bg-stone-200 px-1 rounded">conduct switch</code>, and{" "}
          <code className="font-mono bg-stone-200 px-1 rounded">conduct whoami</code>.
        </p>

        <div className="flex flex-col divide-y divide-stone-200 rounded-2xl border border-stone-200 bg-white overflow-hidden">
          {CLI_COMMANDS.map((c) => (
            <div
              key={c.cmd}
              className="grid grid-cols-1 sm:grid-cols-[2fr_1fr_3fr] gap-2 sm:gap-6 px-6 py-5 items-start"
            >
              <code className="font-mono text-sm font-semibold text-indigo-700 bg-indigo-50 px-2 py-1 rounded self-start">
                {c.cmd}
              </code>
              <p className="text-xs text-stone-400 italic pt-1">{c.when}</p>
              <p className="text-sm text-stone-700">{c.what}</p>
            </div>
          ))}
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

/* ─── Also By ──────────────────────────────────────────────────────────── */

function AlsoBySection() {
  return (
    <section className="px-6 py-16 bg-stone-50 border-t border-stone-100">
      <div className="max-w-4xl mx-auto">
        <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-2 text-center">
          Also by Conduct
        </p>
        <h2 className="text-2xl font-bold text-stone-900 text-center mb-10">
          More free tools for AI coding
        </h2>

        <div className="grid sm:grid-cols-2 gap-6">
          {/* Agent Booster */}
          <div className="rounded-2xl border border-stone-200 bg-white px-7 py-6 flex flex-col gap-4 hover:border-indigo-200 hover:shadow-sm transition-all">
            <div className="flex items-start justify-between">
              <div>
                <span className="inline-flex items-center text-xs font-semibold bg-indigo-50 text-indigo-700 border border-indigo-100 px-2.5 py-1 rounded-full mb-3">
                  Free &middot; MIT
                </span>
                <h3 className="text-lg font-bold text-stone-900">Agent Booster</h3>
                <p className="text-sm text-stone-500 mt-1">
                  60&ndash;90% token savings on AI coding
                </p>
              </div>
              <span className="text-2xl font-black text-indigo-600">◈</span>
            </div>
            <p className="text-sm text-stone-600 leading-relaxed">
              AST-level symbol routing, semantic vector search, and MCP integration. Routes only
              the relevant symbols and functions to the model instead of full files.
            </p>
            <div className="mt-auto pt-4 border-t border-stone-100 flex items-center gap-3">
              <a
                href="/tools/agent-booster"
                className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-700 transition-colors"
              >
                Learn more &rarr;
              </a>
              <code className="font-mono text-xs text-stone-400 bg-stone-50 px-2 py-1 rounded border border-stone-100">
                pip install agent-booster
              </code>
            </div>
          </div>

          {/* Security Loop */}
          <div className="rounded-2xl border border-stone-200 bg-white px-7 py-6 flex flex-col gap-4 hover:border-red-100 hover:shadow-sm transition-all">
            <div className="flex items-start justify-between">
              <div>
                <span className="inline-flex items-center text-xs font-semibold bg-red-50 text-red-700 border border-red-100 px-2.5 py-1 rounded-full mb-3">
                  Free &middot; MIT
                </span>
                <h3 className="text-lg font-bold text-stone-900">Security Loop</h3>
                <p className="text-sm text-stone-500 mt-1">
                  Automated AI security scanning for every push
                </p>
              </div>
              <span className="text-2xl font-black text-red-500">⬡</span>
            </div>
            <p className="text-sm text-stone-600 leading-relaxed">
              CLI emitter &rarr; Guard &rarr; API &rarr; Security dashboard &rarr; draft agents
              &rarr; Slack. Continuous policy enforcement wired into your CI loop.
            </p>
            <div className="mt-auto pt-4 border-t border-stone-100 flex items-center gap-3">
              <a
                href="https://github.com/sseshachala/conductai"
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 rounded-lg border border-stone-200 px-4 py-2 text-sm font-medium text-stone-700 hover:border-stone-300 transition-colors"
              >
                <GitHubIcon />
                View on GitHub
              </a>
            </div>
          </div>
        </div>

        <p className="text-center mt-8 text-sm text-stone-400">
          All tools are free, MIT licensed, and live on{" "}
          <a
            href="https://github.com/sseshachala/conductai"
            target="_blank"
            rel="noopener noreferrer"
            className="text-indigo-600 hover:text-indigo-800"
          >
            GitHub
          </a>
          .{" "}See the full list at{" "}
          <a href="/tools" className="text-indigo-600 hover:text-indigo-800">
            /tools
          </a>
          .
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
