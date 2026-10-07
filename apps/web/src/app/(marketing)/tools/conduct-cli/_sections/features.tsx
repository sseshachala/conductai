import { InlineCodeBlock } from "./shared"

/* ─── What it covers ───────────────────────────────────────────────────── */

export function WhatItCoversSection() {
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
    {
      icon: "⊛",
      binary: "conduct verify --strict",
      title: "OWASP Agentic Top 10",
      desc: "Maps every guard event to the OWASP Agentic Top 10. Run in CI with --strict to exit 1 if any blocked events exist. JSON output for downstream tooling.",
      color: "text-rose-600",
      bg: "bg-rose-50 border-rose-200",
    },
    {
      icon: "◎",
      binary: "conduct guard discover",
      title: "Agent Discovery",
      desc: "Scans the local environment for AI agents and reports Guard coverage percentage. Add --register to bring discovered agents under Guard automatically.",
      color: "text-amber-600",
      bg: "bg-amber-50 border-amber-200",
    },
    {
      icon: "◬",
      binary: "advisory mode",
      title: "Advisory Mode",
      desc: "Log-all, block-nothing governance mode. Security admins enable it per workspace — violations are audited instead of blocked, so developers see a note but the tool call proceeds. Hash-chain audit log keeps every event tamper-evident.",
      color: "text-teal-600",
      bg: "bg-teal-50 border-teal-200",
    },
  ] as const

  return (
    <section className="bg-stone-50 px-6 py-20">
      <div className="max-w-5xl mx-auto">
        <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest text-center mb-3">
          What&apos;s included
        </p>
        <h2 className="text-3xl font-bold text-stone-900 text-center mb-4">
          One package. Six capabilities.
        </h2>
        <p className="text-center text-stone-500 text-sm max-w-xl mx-auto mb-12">
          conduct-cli ships the platform CLI, ConductGuard MCP, atomic workspace switching, OWASP
          Agentic Top 10 verification, agent discovery, and advisory mode &mdash; everything your
          team needs to run agents safely from the terminal.
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

/* ─── Hooks ────────────────────────────────────────────────────────────── */

export function HooksSection() {
  const hooks = [
    {
      name: "PreToolUse",
      status: "Shipped",
      statusColor: "text-emerald-600 bg-emerald-50 border-emerald-200",
      what: "Fires before every tool call",
      does: "Policy enforcement, PII/secret blocking, hard budget stops. Exit 2 cancels the tool entirely.",
    },
    {
      name: "PostToolUse",
      status: "Shipped",
      statusColor: "text-emerald-600 bg-emerald-50 border-emerald-200",
      what: "Fires after every tool call",
      does: "Token tracking per tool, threshold policies, rich audit events with actual tool output.",
    },
    {
      name: "Stop",
      status: "Shipped",
      statusColor: "text-emerald-600 bg-emerald-50 border-emerald-200",
      what: "Fires before final response delivery",
      does: "Team memory capture — transcript summarized by Haiku, vector-embedded, searchable by next dev.",
    },
    {
      name: "PreCompact",
      status: "Shipped",
      statusColor: "text-emerald-600 bg-emerald-50 border-emerald-200",
      what: "Fires before context compaction",
      does: "Memory flush to Guard before Claude compresses the conversation — nothing is lost.",
    },
    {
      name: "SessionStart",
      status: "Shipped",
      statusColor: "text-emerald-600 bg-emerald-50 border-emerald-200",
      what: "Fires when a session opens",
      does: "Session init alert, policy sync check, surfaces prior team context for the current repo.",
    },
  ] as const

  return (
    <section className="max-w-5xl mx-auto px-6 py-20">
      <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest text-center mb-3">
        Claude Code hooks
      </p>
      <h2 className="text-3xl font-bold text-stone-900 text-center mb-4">
        Every moment in the session. Covered.
      </h2>
      <p className="text-center text-stone-500 text-sm max-w-xl mx-auto mb-12">
        <code className="font-mono text-stone-700 bg-stone-100 px-1.5 py-0.5 rounded text-xs">conduct guard sync</code> wires
        all five Claude Code hook types automatically. No manual config.
      </p>

      <div className="overflow-x-auto rounded-2xl border border-stone-200">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-stone-50 border-b border-stone-200">
              <th className="text-left px-5 py-3 font-semibold text-stone-500 text-xs uppercase tracking-wider">Hook</th>
              <th className="text-left px-5 py-3 font-semibold text-stone-500 text-xs uppercase tracking-wider">When</th>
              <th className="text-left px-5 py-3 font-semibold text-stone-500 text-xs uppercase tracking-wider">What Guard does</th>
              <th className="text-left px-5 py-3 font-semibold text-stone-500 text-xs uppercase tracking-wider">Status</th>
            </tr>
          </thead>
          <tbody>
            {hooks.map((h, i) => (
              <tr key={h.name} className={i < hooks.length - 1 ? "border-b border-stone-100" : ""}>
                <td className="px-5 py-4">
                  <code className="font-mono text-xs font-bold text-indigo-600">{h.name}</code>
                </td>
                <td className="px-5 py-4 text-stone-500 text-xs">{h.what}</td>
                <td className="px-5 py-4 text-stone-700 text-xs max-w-xs">{h.does}</td>
                <td className="px-5 py-4">
                  <span className={`text-xs font-semibold px-2 py-0.5 rounded-full border ${h.statusColor}`}>
                    {h.status}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-center text-stone-400 text-xs mt-4">
        Hooks are Claude Code only. Cursor, Copilot, and Windsurf use the conductguard-mcp server instead.
      </p>
    </section>
  )
}

/* ─── Quickstart ───────────────────────────────────────────────────────── */

export function QuickstartSection() {
  return (
    <section className="bg-stone-50 px-6 py-20">
      <div className="max-w-2xl mx-auto">
        <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest text-center mb-3">Quickstart</p>
        <h2 className="text-3xl font-bold text-stone-900 text-center mb-12">
          Up and running in three commands.
        </h2>

        <div className="flex flex-col gap-5">
          <div>
            <p className="text-xs font-bold text-stone-400 uppercase tracking-widest mb-2">Step 1. Install Conduct CLI</p>
            <InlineCodeBlock comment="platform CLI, run agents, manage workspaces, enforce policies">pip install conduct-cli</InlineCodeBlock>
          </div>
          <div>
            <p className="text-xs font-bold text-stone-400 uppercase tracking-widest mb-2">Step 2. Start</p>
            <InlineCodeBlock comment="detects Claude/Cursor/Codex, wires hooks, indexes, starts daemon">booster start</InlineCodeBlock>
            <p className="mt-2 text-xs text-stone-400">Detects which AI tools are present (Claude Code, Cursor, Windsurf, Codex), wires each one automatically, indexes the project, and starts a background daemon. Fully reversible with <code className="font-mono bg-stone-100 px-1 rounded text-stone-600">booster remove claude</code>.</p>
          </div>
          <div>
            <p className="text-xs font-bold text-stone-400 uppercase tracking-widest mb-2">Then track savings</p>
            <InlineCodeBlock>booster gain</InlineCodeBlock>
          </div>
        </div>
      </div>
    </section>
  )
}

/* ─── Works with ───────────────────────────────────────────────────────── */

type WorksTool = {
  name: string
  icon: string
  color: string
  bg: string
  booster: string
  guard: string
  guardLabel?: string
  guardHosted?: boolean
}

const WORKS_WITH: WorksTool[] = [
  { name: "Claude Code",    icon: "◈", color: "text-orange-600", bg: "bg-orange-50 border-orange-200",   booster: "booster init claude",   guard: "conduct guard sync" },
  { name: "Cursor",         icon: "⊙", color: "text-blue-600",   bg: "bg-blue-50 border-blue-200",       booster: "booster init cursor",   guard: "conduct guard sync" },
  { name: "Windsurf",       icon: "◭", color: "text-violet-600", bg: "bg-violet-50 border-violet-200",   booster: "booster init windsurf", guard: "conduct guard sync" },
  { name: "OpenAI Codex",   icon: "◎", color: "text-emerald-600",bg: "bg-emerald-50 border-emerald-200", booster: "booster init codex",    guard: "conduct guard sync" },
  { name: "GitHub Copilot", icon: "✦", color: "text-stone-700",  bg: "bg-stone-100 border-stone-300",    booster: "booster init copilot",  guard: "api.conductai.ai/guard/mcp", guardLabel: "hosted MCP", guardHosted: true },
]

export function WorksWithSection() {
  return (
    <section className="bg-stone-50 px-6 py-20">
      <div className="max-w-4xl mx-auto">
        <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest text-center mb-3">Compatibility</p>
        <h2 className="text-3xl font-bold text-stone-900 text-center mb-4">
          Works with every major AI coding tool.
        </h2>
        <p className="text-center text-stone-500 text-sm mb-10">
          Both tools wire up with one command per platform — token savings and policy enforcement, everywhere.
        </p>

        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-5">
          {WORKS_WITH.map(tool => (
            <div key={tool.name} className={`rounded-2xl border ${tool.bg} px-5 py-5 flex flex-col items-center text-center gap-3`}>
              <span className={`text-3xl font-black ${tool.color}`}>{tool.icon}</span>
              <p className="font-semibold text-stone-900 text-sm">{tool.name}</p>
              <div className="w-full space-y-1.5">
                <div className="bg-white/70 rounded-lg px-2 py-1.5">
                  <p className="text-[10px] text-emerald-600 font-semibold uppercase tracking-wide mb-0.5">booster</p>
                  <code className="text-[10px] text-stone-600 font-mono">{tool.booster}</code>
                </div>
                <div className="bg-white/70 rounded-lg px-2 py-1.5">
                  <div className="flex items-center justify-center gap-1 mb-0.5">
                    <p className="text-[10px] text-indigo-600 font-semibold uppercase tracking-wide">{tool.guardLabel || "guard"}</p>
                    {tool.guardHosted && (
                      <span className="text-[8px] font-bold text-violet-600 bg-violet-100 px-1 rounded">HTTP</span>
                    )}
                  </div>
                  <code className="text-[10px] text-stone-600 font-mono break-all">{tool.guard}</code>
                </div>
              </div>
            </div>
          ))}
        </div>

        {/* Copilot hosted MCP callout */}
        <div className="mt-8 rounded-2xl border border-violet-200 bg-violet-50 px-6 py-5">
          <div className="flex items-start gap-3">
            <span className="text-violet-600 text-lg mt-0.5">✦</span>
            <div className="w-full">
              <p className="font-semibold text-stone-900 text-sm mb-1">GitHub Copilot — no install required</p>
              <p className="text-stone-600 text-xs mb-4">
                Copilot supports HTTP MCP servers. Add the URL below in VS Code MCP settings — one endpoint serves both Guard enforcement and Conduct agents/workflows/runs, with zero local setup.
              </p>
              <div>
                <p className="text-[10px] font-semibold text-indigo-600 uppercase tracking-wide mb-1">Guard + Conduct — one MCP</p>
                <div className="bg-white rounded-lg px-4 py-2.5 font-mono text-xs text-stone-700 break-all">
                  https://api.conductai.ai/guard/mcp
                </div>
              </div>
              <p className="text-stone-400 text-xs mt-3">
                Set <code className="font-mono bg-white/70 px-1 rounded">Authorization: Bearer YOUR_TOKEN</code> in the Headers field. Get your token from{" "}
                <span className="text-indigo-600">conductai.ai → Settings → API Keys</span>.
              </p>
            </div>
          </div>
        </div>

        <p className="text-center text-xs text-stone-400 mt-6">
          Run <code className="font-mono bg-stone-200 px-1 rounded">booster remove &lt;platform&gt;</code> to cleanly undo booster wiring.{" "}
          <code className="font-mono bg-stone-200 px-1 rounded">conduct guard sync</code> is the same command on every platform — one policy, enforced everywhere.
        </p>
      </div>
    </section>
  )
}
