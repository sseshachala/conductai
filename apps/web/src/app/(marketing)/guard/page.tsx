"use client"

import { useState } from "react"
import { CtaLink } from "@/components/marketing/CtaLink"

export default function GuardLandingPage() {
  return (
    <>
      <HeroSection />
      <ProofStripSection />
      <ToolsSection />
      <EnforcementLayerSection />
      <ProxySection />
      <ProxyCompareSection />
      <GitHubEnterpriseSection />
      <Phase1Section />
      <Phase2Section />
      <Phase3Section />
      <MCPSection />
      <AgentIdentitySection />
      <EnterpriseGradeSection />
      <GatewayVsGuardSection />
      <FoundationLayerSection />
      <FinalCTASection />
    </>
  )
}



/* ─── Hero ─────────────────────────────────────────────────────────────── */

function HeroSection() {
  return (
    <section className="max-w-5xl mx-auto px-6 pt-20 pb-16 text-center">
      <div className="inline-flex items-center gap-2 bg-indigo-50 text-indigo-700 px-4 py-1.5 rounded-full text-xs font-semibold uppercase tracking-widest mb-8">
        <span className="w-1.5 h-1.5 rounded-full bg-indigo-500 inline-block" />
        AI Governance that compounds
      </div>
      <h1 className="text-5xl sm:text-6xl font-black tracking-tight text-stone-900 leading-[1.05] mb-6">
        Your team is already using AI agents.<br />
        <span className="bg-gradient-to-r from-indigo-600 to-violet-600 bg-clip-text text-transparent">Guard is how you govern them.</span>
      </h1>
      <p className="text-xl text-stone-500 max-w-2xl mx-auto leading-relaxed mb-4">
        Most governance stops at day one. Guard gets smarter every session. It learns your codebase, your team&apos;s patterns, and your risk profile over time.
      </p>
      <p className="text-base text-stone-600 max-w-2xl mx-auto leading-relaxed mb-3">
        Other AI governance tools want you to import an SDK and wrap every model call. Guard installs in 10 minutes. One policy enforces across every AI tool your team already uses — Claude Code, Claude.ai, Claude Desktop, Codex CLI, Codex Desktop, ChatGPT, Cursor, Copilot, and Windsurf.
      </p>
      <p className="text-base text-indigo-600 italic max-w-2xl mx-auto leading-relaxed mb-3">
        GitHub gives the CISO a setting. ConductGuard gives them enforcement.
      </p>
      <p className="text-base text-stone-500 italic max-w-2xl mx-auto leading-relaxed mb-4">
        The agent inherits the permission. It doesn&apos;t inherit the caution.
      </p>
      <p className="text-base text-stone-500 max-w-2xl mx-auto leading-relaxed mb-8">
        Guard evaluates runtime admissibility before every agent action executes — applying refusal rails at the execution boundary, not in a policy document. Without runtime enforcement, agents experience permission drift, accumulating authority across tool calls that no single approval authorised.
      </p>
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

/* ─── Tools — Works everywhere ────────────────────────────────────────── */

const TOOLS = [
  { name: "Claude Code",      icon: "⬡", install: "conduct guard sync" },
  { name: "Claude.ai",        icon: "⬡", install: "MCP server" },
  { name: "Claude Desktop",   icon: "⬡", install: "MCP server" },
  { name: "Codex CLI",        icon: "⬡", install: "conduct guard sync" },
  { name: "Codex Desktop",    icon: "⬡", install: "MCP server" },
  { name: "ChatGPT",          icon: "⬡", install: "MCP server" },
  { name: "Cursor",           icon: "⬡", install: "conduct guard sync --cursor" },
  { name: "VS Code + Copilot",icon: "⬡", install: "code --add-mcp '{...}'" },
  { name: "Windsurf",         icon: "⬡", install: "conduct guard sync --windsurf" },
]

function ToolsSection() {
  return (
    <section className="max-w-5xl mx-auto px-6 py-16">
      <div className="text-center mb-10">
        <p className="text-xs font-semibold uppercase tracking-widest text-indigo-600 mb-3">One policy. Every AI tool.</p>
        <h2 className="text-3xl sm:text-4xl font-black text-stone-900 tracking-tight mb-4">
          Works where your team already codes.
        </h2>
        <p className="text-stone-500 text-lg max-w-xl mx-auto">
          Install once. ConductGuard enforces the same policy across every AI coding tool — no per-tool config, no gaps.
        </p>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4 mb-8">
        {([
          { name: "Claude Code",       badge: "hook + MCP" },
          { name: "Claude.ai",         badge: "MCP" },
          { name: "Claude Desktop",    badge: "MCP" },
          { name: "Codex CLI",         badge: "hook" },
          { name: "Codex Desktop",     badge: "MCP" },
          { name: "ChatGPT",           badge: "MCP" },
          { name: "Cursor",            badge: "MCP" },
          { name: "VS Code + Copilot", badge: "MCP" },
          { name: "Windsurf",          badge: "MCP" },
        ] as {name:string,badge:string}[]).map((tool) => (
          <div key={tool.name} className="border border-stone-200 rounded-xl p-4 text-center bg-white shadow-sm">
            <p className="font-semibold text-stone-800 text-sm mb-1">{tool.name}</p>
            <span className="text-[10px] font-semibold uppercase tracking-widest text-indigo-500 bg-indigo-50 px-2 py-0.5 rounded-full">
              {tool.badge}
            </span>
          </div>
        ))}
      </div>

      <div className="bg-stone-950 rounded-2xl p-6 text-sm font-mono text-stone-300 max-w-xl mx-auto">
        <p className="text-stone-500 text-xs mb-3"># Install, sync, discover, validate</p>
        <p><span className="text-indigo-400">$</span> pip install conduct-cli</p>
        <p><span className="text-indigo-400">$</span> conduct guard sync</p>
        <p className="text-stone-500 text-xs">↳ hook installed · MCP registered · policy active</p>
        <p className="mt-2"><span className="text-indigo-400">$</span> conduct guard discover</p>
        <p className="text-stone-500 text-xs">↳ Guard covers 9 of 11 agents · 2 uncovered (instructions shown)</p>
        <p className="mt-2"><span className="text-indigo-400">$</span> conduct guard lint</p>
        <p className="text-stone-500 text-xs">↳ 12 rules · no issues · policy is valid</p>
      </div>

      <p className="text-center text-xs text-stone-400 mt-6">
        Also discoverable via the{" "}
        <a href="https://registry.modelcontextprotocol.io" className="text-indigo-500 hover:underline" target="_blank" rel="noopener noreferrer">
          MCP Registry
        </a>
        {" "}— install directly from VS Code or any MCP-compatible client.
      </p>
    </section>
  )
}

/* ─── Enforcement Layer ────────────────────────────────────────────────── */

function EnforcementLayerSection() {
  return (
    <section className="bg-stone-950 px-6 py-20">
      <div className="max-w-4xl mx-auto">
        <div className="grid md:grid-cols-2 gap-12 items-center">

          <div>
            <p className="text-xs font-semibold uppercase tracking-widest text-indigo-400 mb-4">The enforcement layer</p>
            <h2 className="text-3xl sm:text-4xl font-black text-white tracking-tight leading-tight mb-5">
              Whatever your team runs in Claude, Guard sits in front of it.
            </h2>
            <p className="text-stone-400 leading-relaxed mb-6">
              Teams are building operating systems inside Claude — deal desks, security audits, engineering autopilots. The prompts are good. The reviewer is a suggestion.
            </p>
            <p className="text-stone-300 leading-relaxed mb-4">
              ConductGuard is structural enforcement. Policies are evaluated against real rules, not prompt instructions. A block exits with code 2 — Claude stops. The audit trail is in your dashboard, not the chat history.
            </p>
            <p className="text-stone-400 leading-relaxed mb-8">
              Segregation of duties only holds at the moment an agent acts. ConductGuard is the only governance layer that enforces it at runtime — not in a quarterly review, not in a policy doc.
            </p>
            <a href="/guard" className="inline-flex items-center gap-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-semibold px-5 py-2.5 rounded-lg transition-colors">
              See how Guard enforces →
            </a>
          </div>

          <div className="space-y-3">
            {[
              { label: "Prompt-based reviewer", desc: "Model can ignore it or hallucinate compliance", bad: true },
              { label: "ConductGuard policy", desc: "Refusal rails evaluated against real rule set — block exits with code 2. Refusal conditions are structural, not advisory.", bad: false },
              { label: "Chat history audit", desc: "No structured search, no team visibility", bad: true },
              { label: "Conduct audit log", desc: "Every run, every block, every output — searchable", bad: false },
              { label: "Spend as an afterthought", desc: "You see the bill at end of month", bad: true },
              { label: "Guard spend limits", desc: "Hard stops per user, per project, enforced in real time", bad: false },
            ].map((item) => (
              <div key={item.label} className={`flex items-start gap-3 rounded-xl px-4 py-3 border ${item.bad ? "border-stone-700 bg-stone-900" : "border-indigo-800 bg-indigo-950"}`}>
                <span className={`mt-0.5 text-sm ${item.bad ? "text-stone-600" : "text-indigo-400"}`}>{item.bad ? "✕" : "✓"}</span>
                <div>
                  <p className={`text-sm font-semibold ${item.bad ? "text-stone-500 line-through" : "text-white"}`}>{item.label}</p>
                  <p className="text-xs text-stone-500 mt-0.5">{item.desc}</p>
                </div>
              </div>
            ))}
          </div>

        </div>
      </div>
    </section>
  )
}

/* ─── Proxy ─────────────────────────────────────────────────────────────── */

function ProxySection() {
  return (
    <section className="bg-white px-6 py-20">
      <div className="max-w-4xl mx-auto">
        <p className="text-xs font-semibold uppercase tracking-widest text-indigo-600 mb-3 text-center">Guard Proxy</p>
        <h2 className="text-3xl sm:text-4xl font-black text-stone-900 tracking-tight leading-tight mb-4 text-center">
          One env var. Enforcement on every LLM call.
        </h2>
        <p className="text-stone-500 text-lg leading-relaxed mb-12 text-center max-w-2xl mx-auto">
          Point your AI tools at the Guard Proxy instead of Anthropic or OpenAI. Policies apply before the request forwards. Nothing changes in your code.
        </p>

        <div className="grid md:grid-cols-2 gap-10 items-start">

          {/* Code block */}
          <div className="rounded-xl bg-stone-950 p-6 font-mono text-sm leading-relaxed overflow-x-auto">
            <p className="text-stone-500 text-xs mb-4 uppercase tracking-widest">Before</p>
            <p className="text-stone-400 break-all">ANTHROPIC_BASE_URL=<span className="text-rose-400">https://api.anthropic.com</span></p>
            <p className="text-stone-400 mt-1 break-all">OPENAI_BASE_URL=<span className="text-rose-400">https://api.openai.com/v1</span></p>

            <div className="border-t border-stone-800 my-5" />

            <p className="text-stone-500 text-xs mb-4 uppercase tracking-widest">After</p>
            <p className="text-stone-300 break-all">ANTHROPIC_BASE_URL=<span className="text-indigo-400">https://api.conductai.ai/proxy/anthropic</span></p>
            <p className="text-stone-300 mt-1 break-all">OPENAI_BASE_URL=<span className="text-indigo-400">https://api.conductai.ai/proxy/openai/v1</span></p>

            <div className="border-t border-stone-800 my-5" />
            <p className="text-stone-500 text-xs">Or run <span className="text-indigo-300">conduct guard sync</span> to apply automatically.</p>
          </div>

          {/* Capability list */}
          <div className="space-y-6">
            {[
              {
                icon: "🛡️",
                title: "Policies enforced before forwarding",
                desc: "Block secret leaks, restrict models, cap spend — evaluated against your workspace rules before the request ever reaches the provider.",
              },
              {
                icon: "🔀",
                title: "Route through your own gateway",
                desc: "Set Portkey, Helicone, LiteLLM, or Azure OpenAI as upstream. Guard sits in front and applies policies regardless of where traffic ends up.",
              },
              {
                icon: "📋",
                title: "Every call in your audit trail",
                desc: "Developer, tool, model, prompt summary, decision, cost — all in Guard Activity alongside your hook-layer events.",
              },
            ].map((item) => (
              <div key={item.title} className="flex gap-4">
                <span className="text-2xl mt-0.5">{item.icon}</span>
                <div>
                  <p className="font-semibold text-stone-900 mb-1">{item.title}</p>
                  <p className="text-stone-500 text-sm leading-relaxed">{item.desc}</p>
                </div>
              </div>
            ))}

            <div className="pt-2">
              <a href="/guard" className="inline-flex items-center gap-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-semibold px-5 py-2.5 rounded-lg transition-colors">
                Set up Guard Proxy →
              </a>
            </div>
          </div>

        </div>
      </div>
    </section>
  )
}

/* ─── Proxy Comparison ─────────────────────────────────────────────────── */

function ProxyCompareSection() {
  const rows = [
    { cap: "LLM calls reach the model",          direct: true,  byo: true,  guard: true,  guardByo: true  },
    { cap: "Observability / logging",             direct: false, byo: true,  guard: true,  guardByo: true  },
    { cap: "Cost tracking",                       direct: false, byo: "By API key", guard: "By agent", guardByo: "By agent" },
    { cap: "Policy enforcement (block / warn)",   direct: false, byo: false, guard: true,  guardByo: true  },
    { cap: "Blocks the call before it sends",     direct: false, byo: false, guard: true,  guardByo: true  },
    { cap: "Agent identity on every call",        direct: false, byo: false, guard: true,  guardByo: true  },
    { cap: "Audit trail tied to run + workflow",  direct: false, byo: false, guard: true,  guardByo: true  },
    { cap: "Spend budget per agent / workflow",   direct: false, byo: false, guard: true,  guardByo: true  },
    { cap: "Custom routing / caching",            direct: false, byo: true,  guard: true,  guardByo: true  },
  ]

  function Cell({ val }: { val: boolean | string }) {
    if (val === true)  return <span className="text-emerald-500 font-bold text-base">✓</span>
    if (val === false) return <span className="text-stone-300 text-base">—</span>
    return <span className="text-stone-500 text-xs leading-tight">{val}</span>
  }

  const cols = ["", "Direct LLM", "Portkey / Helicone", "Guard Proxy", "Guard + BYO"]

  return (
    <section className="bg-stone-50 px-6 py-20">
      <div className="max-w-5xl mx-auto">
        <p className="text-xs font-semibold uppercase tracking-widest text-indigo-600 mb-3 text-center">Why Guard Proxy</p>
        <h2 className="text-3xl sm:text-4xl font-black text-stone-900 tracking-tight leading-tight mb-4 text-center">
          Observe or enforce — pick one. Unless you use Guard.
        </h2>
        <p className="text-stone-500 text-base leading-relaxed mb-12 text-center max-w-2xl mx-auto">
          Portkey and Helicone sit beside the call and observe. Guard sits in front and can stop it.
          Set an LLM upstream in Proxy Settings to keep Portkey&apos;s routing with Guard&apos;s enforcement on top.
        </p>

        <div className="overflow-x-auto rounded-xl border border-stone-200 bg-white">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-stone-100">
                {cols.map((c, i) => (
                  <th key={c} className={`px-5 py-4 text-left font-semibold ${i === 0 ? "text-stone-400 w-64" : i === 3 ? "text-indigo-600 bg-indigo-50" : i === 4 ? "text-indigo-700 bg-indigo-50" : "text-stone-700"}`}>
                    {c}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, ri) => (
                <tr key={row.cap} className={`border-b border-stone-50 ${ri % 2 === 0 ? "bg-white" : "bg-stone-50/60"}`}>
                  <td className="px-5 py-3.5 text-stone-600 font-medium">{row.cap}</td>
                  <td className="px-5 py-3.5 text-center"><Cell val={row.direct} /></td>
                  <td className="px-5 py-3.5 text-center"><Cell val={row.byo} /></td>
                  <td className="px-5 py-3.5 text-center bg-indigo-50/40"><Cell val={row.guard} /></td>
                  <td className="px-5 py-3.5 text-center bg-indigo-50/40"><Cell val={row.guardByo} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <p className="text-stone-400 text-xs text-center mt-5">
          Custom routing in Guard Proxy: set any LLM upstream (Portkey, LiteLLM, Azure OpenAI) in Settings → Proxy.
        </p>
      </div>
    </section>
  )
}

/* ─── GitHub Enterprise ────────────────────────────────────────────────── */

function GitHubEnterpriseSection() {
  return (
    <section className="border-y border-stone-200 bg-white px-6 py-16">
      <div className="max-w-4xl mx-auto">
        <div className="grid md:grid-cols-2 gap-12 items-center">
          <div>
            <p className="text-xs font-semibold uppercase tracking-widest text-stone-400 mb-4">GitHub Copilot Enterprise</p>
            <h2 className="text-3xl font-black text-stone-900 tracking-tight leading-tight mb-4">
              One API key. Every developer covered.
            </h2>
            <p className="text-stone-500 leading-relaxed mb-6">
              GitHub Copilot for Business supports hosted MCP servers. Add the ConductGuard URL to your org settings once — every developer in your org gets policy enforcement automatically. No CLI install. No per-developer setup.
            </p>
            <div className="space-y-2 text-sm text-stone-600">
              <div className="flex items-center gap-2"><span className="text-emerald-500">✓</span> Admin generates one API key from Settings</div>
              <div className="flex items-center gap-2"><span className="text-emerald-500">✓</span> Paste URL into GitHub org MCP settings</div>
              <div className="flex items-center gap-2"><span className="text-emerald-500">✓</span> All developers get Guard enforcement on next Copilot session</div>
              <div className="flex items-center gap-2"><span className="text-emerald-500">✓</span> Full audit trail in the Conduct dashboard</div>
            </div>
          </div>

          <div className="space-y-4">
            <div className="rounded-xl border border-stone-200 bg-stone-50 p-5">
              <p className="text-xs font-semibold text-stone-400 uppercase tracking-wide mb-3">MCP server URL</p>
              <code className="block text-xs font-mono text-stone-700 break-all leading-relaxed">
                https://api.conductai.ai/guard/mcp
              </code>
            </div>
            <div className="rounded-xl border border-stone-200 bg-stone-50 p-5">
              <p className="text-xs font-semibold text-stone-400 uppercase tracking-wide mb-3">Authorization header</p>
              <code className="block text-xs font-mono text-stone-700">
                Authorization: Bearer cond_live_xxx
              </code>
              <p className="text-xs text-stone-400 mt-2">Generate from conductai.ai → Settings → API Keys</p>
            </div>
            <p className="text-xs text-stone-400 text-center">
              Works with GitHub Copilot for Business, Cursor, Windsurf, and any MCP-compatible AI tool.
            </p>
          </div>
        </div>
      </div>
    </section>
  )
}

/* ─── Phase 1 — Month 1: Visibility ───────────────────────────────────── */

function Phase1Section() {
  const cards = [
    {
      icon: "🔍",
      title: "Shadow AI discovered in seconds",
      body: "conduct guard discover scans your machine and shows coverage instantly — \"Guard covers 9 of 11 agents.\" Every uncovered tool gets step-by-step remediation instructions.",
    },
    {
      icon: "💸",
      title: "Spend by developer, by day, by tool",
      body: "No more waiting for the invoice. See exactly where AI budget is going in real time.",
    },
    {
      icon: "📋",
      title: "Full audit trail from day one",
      body: "Every tool call logged with decision, developer identity, and timestamp. One place, always current.",
    },
    {
      icon: "✅",
      title: "Validate policy before it hits prod",
      body: "conduct guard lint checks every rule locally — unique IDs, valid regexes, correct actions. Ship with confidence, not a prayer.",
    },
  ]

  return (
    <section className="py-24 px-6 bg-white">
      <div className="max-w-5xl mx-auto">
        <div className="mb-14">
          <p className="text-xs font-semibold uppercase tracking-widest text-indigo-500 mb-3">Month 1</p>
          <h2 className="text-3xl sm:text-4xl font-bold text-stone-900 tracking-tight leading-tight mb-4 max-w-2xl">
            You can&apos;t govern what you can&apos;t see. Now you can see everything.
          </h2>
          <p className="text-xl text-stone-500 max-w-2xl leading-relaxed">
            Within 10 minutes of install, you see every AI agent your team is running, what tools it has access to, and who owns it. Guard is your organization&apos;s memory of its AI — not a spreadsheet, not a quarterly review.
          </p>
        </div>
        <div className="grid sm:grid-cols-2 gap-5">
          {cards.map(c => (
            <div key={c.title} className="rounded-2xl border border-stone-200 p-6 hover:border-stone-300 hover:shadow-sm transition-all">
              <span className="text-2xl mb-3 block">{c.icon}</span>
              <h3 className="text-base font-bold text-stone-900 leading-snug mb-2">{c.title}</h3>
              <p className="text-sm text-stone-500 leading-relaxed">{c.body}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

/* ─── Phase 2 — Month 3: Governance ───────────────────────────────────── */

interface Incident {
  badge: string
  badgeStyle: string
  rule: string
  headline: string
  detail: string
}

function Phase2Section() {
  const incidents: Incident[] = [
    {
      badge: "BLOCKED",
      badgeStyle: "bg-red-100 text-red-700",
      rule: "approve-prod-deploy",
      headline: "Force-deploy to production, intercepted",
      detail: "AI attempted vercel deploy --prod --force at 3:11pm on a Friday. Guard blocked it before it executed.",
    },
    {
      badge: "BLOCKED",
      badgeStyle: "bg-red-100 text-red-700",
      rule: "no-secret-in-commit-msg",
      headline: "Secret embedded in git commit, caught",
      detail: "AI tried to commit code with a credential token in the commit message. Fired twice in the same session.",
    },
    {
      badge: "WARNED",
      badgeStyle: "bg-amber-100 text-amber-700",
      rule: "pii-redact",
      headline: "971 PII events in a single day",
      detail: "Jun 19 spiked 30× the 32/day baseline. Without Guard, every one of those calls would have sent raw credentials to an LLM.",
    },
  ]

  return (
    <section className="py-24 px-6 bg-stone-50">
      <div className="max-w-5xl mx-auto">
        <div className="mb-14">
          <p className="text-xs font-semibold uppercase tracking-widest text-indigo-500 mb-3">Month 3</p>
          <h2 className="text-3xl sm:text-4xl font-bold text-stone-900 tracking-tight leading-tight mb-4 max-w-2xl">
            It caught things your team would never have seen.
          </h2>
          <p className="text-xl text-stone-500 max-w-2xl leading-relaxed">
            Policies enforced at the tool layer, not in a doc. At the moment the agent runs, not the morning after.
          </p>
        </div>

        <div className="grid md:grid-cols-3 gap-5 mb-8">
          {incidents.map(inc => (
            <div key={inc.rule} className="rounded-2xl border border-stone-200 bg-white p-6 flex flex-col gap-3 hover:border-stone-300 hover:shadow-sm transition-all">
              <div className="flex items-center gap-2">
                <span className={`inline-block px-2 py-0.5 rounded-full text-[10px] font-bold tracking-wider ${inc.badgeStyle}`}>
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
            <p className="text-sm font-semibold text-stone-900 mb-1">What would&apos;ve happened without Guard?</p>
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

/* ─── Phase 3 — Month 6–12: Intelligence ──────────────────────────────── */

function Phase3Section() {
  return (
    <section className="py-24 px-6 bg-white">
      <div className="max-w-5xl mx-auto">
        <div className="mb-14">
          <p className="text-xs font-semibold uppercase tracking-widest text-indigo-500 mb-3">Month 6–12</p>
          <h2 className="text-3xl sm:text-4xl font-bold text-stone-900 tracking-tight leading-tight mb-4 max-w-3xl">
            Guard learns as it runs. Every session makes the next one more accurate for your team.
          </h2>
          <p className="text-xl text-stone-500 max-w-2xl leading-relaxed">
            Two memory systems work together. One knows your codebase. One knows your team. No other governance tool has either.
          </p>
        </div>

        <div className="grid md:grid-cols-2 gap-5 mb-8">

          {/* LEFT: Contextual Memory — light card */}
          <div className="rounded-[20px] border border-[#f0eef8] bg-[#faf9ff] p-8 flex flex-col gap-5">
            <div className="flex flex-col gap-1">
              <span className="text-2xl">🧠</span>
              <span className="text-[10px] font-bold uppercase tracking-widest text-violet-700 mt-2">Playbook Layer</span>
              <span className="text-xl font-extrabold text-stone-900">Contextual Memory</span>
            </div>
            <p className="text-[15px] text-stone-600 leading-relaxed">
              Per-workflow, per-repo. Every agent template reads what worked before it acts, then writes what it learned when it finishes.
            </p>
            <ul className="flex flex-col gap-3.5">
              <li className="flex items-start gap-2.5">
                <span className="w-[7px] h-[7px] rounded-full bg-violet-700 flex-shrink-0 mt-[5px]" />
                <span className="text-sm">
                  <span className="font-semibold text-stone-900">Knows which files are fragile</span>
                  <span className="text-stone-500">. Run 1 explores. Run 10 goes straight to the right file.</span>
                </span>
              </li>
              <li className="flex items-start gap-2.5">
                <span className="w-[7px] h-[7px] rounded-full bg-violet-700 flex-shrink-0 mt-[5px]" />
                <span className="text-sm">
                  <span className="font-semibold text-stone-900">Avoids repeating past mistakes</span>
                  <span className="text-stone-500">. If a fix caused a regression last time, the agent knows.</span>
                </span>
              </li>
              <li className="flex items-start gap-2.5">
                <span className="w-[7px] h-[7px] rounded-full bg-violet-700 flex-shrink-0 mt-[5px]" />
                <span className="text-sm">
                  <span className="font-semibold text-stone-900">Compounds across every run</span>
                  <span className="text-stone-500">. A workflow that has run 50 times on your repo is more valuable than a fresh install anywhere else.</span>
                </span>
              </li>
            </ul>
            <div className="rounded-xl bg-[#f4f0ff] border border-[#ede9fe] px-5 py-4">
              <p className="text-[11px] font-bold uppercase tracking-wider text-violet-700 mb-1.5">How it works</p>
              <p className="text-[13px] text-stone-600 leading-relaxed">Before every run → reads prior outcomes. After every run → writes what happened.</p>
            </div>
          </div>

          {/* RIGHT: Team Session Memory — dark card */}
          <div
            className="rounded-[20px] p-8 flex flex-col gap-5"
            style={{ background: "linear-gradient(135deg, #0a0815, #1f1048)" }}
          >
            <div className="flex flex-col gap-1">
              <span className="text-2xl">👥</span>
              <span className="text-[10px] font-bold uppercase tracking-widest text-violet-400 mt-2">CLI Layer</span>
              <span className="text-xl font-extrabold text-white">Team Session Memory</span>
            </div>
            <p className="text-[15px] leading-relaxed" style={{ color: "rgba(255,255,255,0.55)" }}>
              Per-developer, across every AI tool. The CLI hook captures sessions passively. Zero extra effort from your team.
            </p>
            <ul className="flex flex-col gap-3.5">
              <li className="flex items-start gap-2.5">
                <span className="w-[7px] h-[7px] rounded-full bg-violet-400 flex-shrink-0 mt-[5px]" />
                <span className="text-sm">
                  <span className="font-semibold text-white">Knows how each developer works</span>
                  <span style={{ color: "rgba(255,255,255,0.45)" }}>. Sarah always requires tests. The security lead flags credential exposure.</span>
                </span>
              </li>
              <li className="flex items-start gap-2.5">
                <span className="w-[7px] h-[7px] rounded-full bg-violet-400 flex-shrink-0 mt-[5px]" />
                <span className="text-sm">
                  <span className="font-semibold text-white">Captured across all AI tools</span>
                  <span style={{ color: "rgba(255,255,255,0.45)" }}>. One CLI hook. Every session adds to the team&apos;s shared context.</span>
                </span>
              </li>
              <li className="flex items-start gap-2.5">
                <span className="w-[7px] h-[7px] rounded-full bg-violet-400 flex-shrink-0 mt-[5px]" />
                <span className="text-sm">
                  <span className="font-semibold text-white">The agent behaves like a team member</span>
                  <span style={{ color: "rgba(255,255,255,0.45)" }}>. Not a contractor who just showed up. An engineer who&apos;s been here for months.</span>
                </span>
              </li>
            </ul>
            <div
              className="rounded-xl px-5 py-4"
              style={{ background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.08)" }}
            >
              <p className="text-[11px] font-bold uppercase tracking-wider text-violet-400 mb-1.5">How it works</p>
              <p className="text-[13px] leading-relaxed" style={{ color: "rgba(255,255,255,0.5)" }}>
                <code className="text-[13px] opacity-70">conduct login</code> installs a hook. Each session is captured silently. Patterns accumulate. Templates draw on this automatically.
              </p>
            </div>
          </div>

        </div>

        {/* Together callout */}
        <div
          className="rounded-[20px] px-10 py-10 text-center"
          style={{ background: "linear-gradient(135deg, #7c3aed, #4c1d95)" }}
        >
          <h3 className="text-[22px] font-extrabold text-white tracking-tight mb-3">
            An agent that knows your codebase and your team.
          </h3>
          <p className="text-[15px] leading-relaxed mb-6 max-w-lg mx-auto" style={{ color: "rgba(255,255,255,0.7)" }}>
            No other automation tool has either. GitHub Actions has zero memory. Copilot has no team context. Conduct compounds both: silently, continuously, from day one.
          </p>
          <CtaLink className="inline-flex items-center rounded-xl bg-white text-violet-700 px-7 py-3.5 text-base font-bold hover:bg-violet-50 transition-colors" />
        </div>

      </div>
    </section>
  )
}

/* ─── MCP ──────────────────────────────────────────────────────────────── */

function MCPSection() {
  const clients = [
    { name: "Claude Desktop", icon: "🖥️" },
    { name: "Claude.ai", icon: "🌐" },
    { name: "Cursor", icon: "⚡" },
    { name: "Windsurf", icon: "🏄" },
    { name: "VS Code Copilot", icon: "💠" },
    { name: "Codex CLI", icon: "⌨️" },
    { name: "Devin", icon: "🤖" },
    { name: "Any MCP agent", icon: "🔌" },
  ]
  return (
    <section className="bg-stone-950 px-6 py-24">
      <div className="max-w-5xl mx-auto">
        <div className="text-center mb-14">
          <p className="text-xs font-semibold uppercase tracking-widest text-indigo-400 mb-3">MCP-native governance</p>
          <h2 className="text-3xl sm:text-4xl font-black text-white tracking-tight leading-tight mb-5">
            If your AI agent speaks MCP,<br />ConductGuard already governs it.
          </h2>
          <p className="text-stone-400 text-lg leading-relaxed max-w-2xl mx-auto">
            No CLI install. No hook. No code changes. Any agent that connects to <code className="text-indigo-300 text-base">conductguard-mcp</code> inherits your team&apos;s policies the moment it starts.
          </p>
        </div>

        {/* Client grid */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-12">
          {clients.map(c => (
            <div key={c.name} className="rounded-xl border border-stone-800 bg-stone-900 px-4 py-4 flex items-center gap-3">
              <span className="text-xl">{c.icon}</span>
              <span className="text-sm font-medium text-stone-300">{c.name}</span>
            </div>
          ))}
        </div>

        {/* Two columns: how it works + what gets enforced */}
        <div className="grid md:grid-cols-2 gap-6 mb-10">
          <div className="rounded-2xl border border-stone-800 bg-stone-900 p-8">
            <p className="text-xs font-bold uppercase tracking-widest text-indigo-400 mb-4">How it works</p>
            <ol className="space-y-4">
              {[
                ["Agent connects", "Any MCP-capable agent adds conductguard-mcp as a server — one URL, one API key."],
                ["Policy syncs", "Your active ConductGuard policy propagates instantly. No redeploy required."],
                ["Every tool call checked", "guard_check fires before the agent acts. Block, warn, or audit — your rules, enforced."],
                ["Audit trail written", "Every decision logged to the same Flight Recorder your security team already uses."],
              ].map(([step, desc], i) => (
                <li key={step} className="flex gap-4">
                  <span className="w-6 h-6 rounded-full bg-indigo-600 text-white text-xs font-bold flex items-center justify-center flex-shrink-0 mt-0.5">{i + 1}</span>
                  <div>
                    <p className="text-sm font-semibold text-white mb-0.5">{step}</p>
                    <p className="text-sm text-stone-400 leading-relaxed">{desc}</p>
                  </div>
                </li>
              ))}
            </ol>
          </div>

          <div className="rounded-2xl border border-stone-800 bg-stone-900 p-8">
            <p className="text-xs font-bold uppercase tracking-widest text-indigo-400 mb-4">What gets enforced</p>
            <ul className="space-y-3">
              {[
                ["Prompt injection", "Malicious instructions in external content intercepted before the model sees them."],
                ["Credential exposure", "API keys and secrets blocked from leaving your network in LLM calls."],
                ["PII in prompts", "Patient data, PII flagged before it reaches the provider."],
                ["Spend limits", "Per-developer token budgets enforced across every connected agent."],
                ["Blast radius tracking", "Every action scored by scope — local / repo / network / destructive."],
                ["Human sovereignty", "Approval gates are first-class workflow blocks, not optional add-ons. Conduct preserves human sovereignty at every step that matters."],
                ["Custody proof", "Every decision cryptographically logged at the execution boundary — not reconstructed after the fact. SOC2 auditors get proof, not promises. Every allowed action produces a Governance Authorization Artifact: replay-verifiable evidence that authorisation was confirmed before execution."],
              ].map(([label, desc]) => (
                <li key={label} className="flex gap-3">
                  <span className="w-1.5 h-1.5 rounded-full bg-indigo-500 flex-shrink-0 mt-[7px]" />
                  <div>
                    <span className="text-sm font-semibold text-white">{label} — </span>
                    <span className="text-sm text-stone-400">{desc}</span>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        </div>

        {/* Connect snippet */}
        <div className="rounded-2xl border border-stone-800 bg-stone-900 px-8 py-6">
          <p className="text-xs font-bold uppercase tracking-widest text-stone-500 mb-3">Add to any MCP client</p>
          <pre className="text-sm font-mono text-indigo-300 leading-relaxed overflow-x-auto">{`{
  "mcpServers": {
    "conductguard": {
      "url": "https://api.conductai.ai/guard/mcp",
      "headers": { "Authorization": "Bearer <your-api-key>" }
    }
  }
}`}</pre>
          <p className="text-xs text-stone-500 mt-3">Works with Claude Desktop, Cursor, Windsurf, VS Code, Codex CLI, and any MCP-compatible agent.</p>
        </div>

        {/* SDK code snippets */}
        <CodeSnippetSection />
      </div>
    </section>
  )
}

function CodeSnippetSection() {
  const [tab, setTab] = useState<"ts" | "py" | "java" | "csharp" | "go">("ts")

  const snippets: Record<typeof tab, { label: string; code: string }> = {
    ts: {
      label: "TypeScript",
      code: `import Anthropic from "@anthropic-ai/sdk";

const client = new Anthropic();

const response = await client.beta.messages.create({
  model: "claude-opus-4-5",
  max_tokens: 1024,
  tools: [{
    type: "mcp",
    server_url: "https://api.conductai.ai/guard/mcp",
    server_name: "ConductGuard",
    authorization_token: process.env.CONDUCT_API_KEY,
  }],
  messages: [{ role: "user", content: "..." }],
});
// Every tool call is now governed by your Guard policy`,
    },
    py: {
      label: "Python",
      code: `import anthropic, os

client = anthropic.Anthropic()

response = client.beta.messages.create(
    model="claude-opus-4-5",
    max_tokens=1024,
    tools=[{
        "type": "mcp",
        "server_url": "https://api.conductai.ai/guard/mcp",
        "server_name": "ConductGuard",
        "authorization_token": os.environ["CONDUCT_API_KEY"],
    }],
    messages=[{"role": "user", "content": "..."}],
)
# Every tool call is now governed by your Guard policy`,
    },
    java: {
      label: "Java",
      code: `import java.net.http.*;
import java.net.URI;

// Connect via HTTP — any MCP-over-SSE client works
var request = HttpRequest.newBuilder()
    .uri(URI.create("https://api.conductai.ai/guard/mcp"))
    .header("Authorization", "Bearer " + System.getenv("CONDUCT_API_KEY"))
    .header("Content-Type", "application/json")
    .POST(HttpRequest.BodyPublishers.ofString(payload))
    .build();

var client = HttpClient.newHttpClient();
var response = client.send(request, HttpResponse.BodyHandlers.ofString());
// guard_check, guard_status, guard_activity tools available`,
    },
    csharp: {
      label: "C#",
      code: `using System.Net.Http.Json;

var client = new HttpClient();
client.DefaultRequestHeaders.Add(
    "Authorization", $"Bearer {Environment.GetEnvironmentVariable("CONDUCT_API_KEY")}");

// Call any Guard MCP tool over HTTP
var response = await client.PostAsJsonAsync(
    "https://api.conductai.ai/guard/mcp",
    new { method = "tools/call", params = new { name = "guard_check", arguments = new { action = "..." } } }
);
// Returns: { "result": "ALLOWED" | "BLOCKED" | "WARNED" }`,
    },
    go: {
      label: "Go",
      code: `package main

import (
  "bytes"
  "encoding/json"
  "net/http"
  "os"
)

client := &http.Client{}
body, _ := json.Marshal(map[string]any{
  "method": "tools/call",
  "params": map[string]any{
    "name":      "guard_check",
    "arguments": map[string]any{"action": "..."},
  },
})
req, _ := http.NewRequest("POST", "https://api.conductai.ai/guard/mcp", bytes.NewReader(body))
req.Header.Set("Authorization", "Bearer "+os.Getenv("CONDUCT_API_KEY"))
req.Header.Set("Content-Type", "application/json")
resp, _ := client.Do(req)
// Returns: { "result": "ALLOWED" | "BLOCKED" | "WARNED" }`,
    },
  }

  const tabs = [
    { id: "ts" as const, label: "TypeScript" },
    { id: "py" as const, label: "Python" },
    { id: "java" as const, label: "Java" },
    { id: "csharp" as const, label: "C#" },
    { id: "go" as const, label: "Go" },
  ]

  return (
    <div className="mt-6 rounded-2xl border border-stone-800 bg-stone-900 overflow-hidden">
      <div className="flex items-center justify-between px-6 pt-5 pb-0">
        <p className="text-xs font-bold uppercase tracking-widest text-stone-500">Connect from any language</p>
        <div className="flex gap-1">
          {tabs.map(t => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors ${
                tab === t.id
                  ? "bg-indigo-600 text-white"
                  : "text-stone-400 hover:text-stone-200 hover:bg-stone-800"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>
      <pre className="px-6 py-5 text-sm font-mono text-indigo-200 leading-relaxed overflow-x-auto whitespace-pre">
        {snippets[tab].code}
      </pre>
      <div className="px-6 pb-4">
        <p className="text-xs text-stone-500">
          Same Guard policy enforced regardless of language. Java and C# use the MCP HTTP/SSE transport directly.
        </p>
      </div>
    </div>
  )
}

/* ─── Agent Identity ───────────────────────────────────────────────────── */

function AgentIdentitySection() {
  const tokenTypes = [
    {
      prefix: "cond_agt_*",
      label: "Session token",
      ttl: "8 hours",
      source: "conduct login",
      use: "Claude Code, Cursor, Windsurf, Codex CLI — any interactive tool.",
      color: "border-indigo-200 bg-indigo-50",
      badge: "bg-indigo-100 text-indigo-700",
    },
    {
      prefix: "cond_api_*",
      label: "API token",
      ttl: "Long-lived",
      source: "Agent Identity page",
      use: "CI/CD pipelines, server agents, integrations — any non-interactive context.",
      color: "border-violet-200 bg-violet-50",
      badge: "bg-violet-100 text-violet-700",
    },
  ]
  return (
    <section className="px-6 py-24 bg-white">
      <div className="max-w-5xl mx-auto">
        <div className="text-center mb-14">
          <p className="text-xs font-semibold uppercase tracking-widest text-indigo-600 mb-3">Agent Identity</p>
          <h2 className="text-3xl sm:text-4xl font-black text-stone-900 tracking-tight leading-tight mb-5">
            Every agent gets an identity.<br />Every call is attributed.
          </h2>
          <p className="text-stone-500 text-lg leading-relaxed max-w-2xl mx-auto">
            Guard issues scoped tokens to every agent. Short-lived for interactive tools, long-lived for CI and integrations. Both enforce the same proxy rules and write to the same audit trail.
          </p>
          <p className="text-stone-500 text-base leading-relaxed max-w-2xl mx-auto mt-3">
            Guard validates authority at the execution boundary — short-lived run tokens mean permissions expire with the action, not the session. Conduct uses short-lived run tokens: every run mints fresh credentials. There are no stale approvals.
          </p>
        </div>

        <div className="grid md:grid-cols-2 gap-6 mb-10">
          {tokenTypes.map(t => (
            <div key={t.prefix} className={`rounded-2xl border ${t.color} p-8`}>
              <div className="flex items-center justify-between mb-4">
                <code className="text-sm font-mono font-bold text-stone-900">{t.prefix}</code>
                <span className={`text-xs font-semibold px-2.5 py-1 rounded-full ${t.badge}`}>{t.label}</span>
              </div>
              <div className="space-y-3 text-sm">
                <div className="flex gap-3">
                  <span className="text-stone-400 w-16 shrink-0">Expires</span>
                  <span className="text-stone-700 font-medium">{t.ttl}</span>
                </div>
                <div className="flex gap-3">
                  <span className="text-stone-400 w-16 shrink-0">Issued by</span>
                  <code className="text-stone-700 text-xs bg-white/60 px-1.5 py-0.5 rounded">{t.source}</code>
                </div>
                <div className="flex gap-3">
                  <span className="text-stone-400 w-16 shrink-0">Use for</span>
                  <span className="text-stone-600 leading-relaxed">{t.use}</span>
                </div>
              </div>
            </div>
          ))}
        </div>

        <div className="grid md:grid-cols-3 gap-4">
          {[
            ["RFC 8693 compliant", "Token exchange follows the same standard as Okta and Entra. Your security team already knows the protocol."],
            ["Auto-refresh", "Session tokens refresh 5 minutes before expiry. No manual re-login during long coding sessions."],
            ["Workspace-scoped", "Tokens are enforced to a single workspace. Cross-workspace reuse is rejected at the proxy."],
          ].map(([title, desc]) => (
            <div key={title} className="rounded-xl border border-stone-200 bg-stone-50 px-5 py-5">
              <p className="text-sm font-bold text-stone-900 mb-2">{title}</p>
              <p className="text-xs text-stone-500 leading-relaxed">{desc}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

/* ─── Enterprise grade ─────────────────────────────────────────────────── */

function EnterpriseGradeSection() {
  const decisions = [
    {
      label: "Fail-closed by default",
      body: "If the Guard API is unreachable, tool calls are blocked — not silently allowed. Every new workspace starts fail-closed. Fail-open is available but you have to choose it.",
      tag: "Incident response",
    },
    {
      label: "30-second policy propagation",
      body: "When you revoke a rule, every developer's machine picks it up within 30 seconds — automatically, with no manual sync. The background drain daemon refreshes policy on every active session.",
      tag: "Policy enforcement",
    },
    {
      label: "SHA-256 hash chain, one-click verification",
      body: "Every audit event is linked to the previous one via a SHA-256 chain. A CISO can open the Governance page, click Verify integrity, and confirm the log has not been altered — no CLI needed.",
      tag: "Audit trail",
    },
    {
      label: "Real-time incident feed",
      body: "The activity feed streams new events within two seconds of each tool call. Click Go Live during an incident and watch blocks appear across your team in real time, without refreshing.",
      tag: "Live monitoring",
    },
    {
      label: "Daemon health visible in guard status",
      body: "The background event daemon self-heals: stale processes are detected, killed, and replaced on the next tool call. `conduct guard status` shows running, stale, or not running — not a silent gap.",
      tag: "Reliability",
    },
    {
      label: "Proxy coverage check in every status call",
      body: "`conduct guard status` shows which AI providers are actually routed through the Guard proxy in the current shell — and flags the ones that are not, with the exact command to fix it.",
      tag: "Coverage visibility",
    },
  ]

  return (
    <section className="bg-stone-950 px-6 py-24 border-t border-stone-900">
      <div className="max-w-5xl mx-auto">
        <div className="text-center mb-14">
          <p className="text-xs font-semibold uppercase tracking-widest text-indigo-400 mb-3">Built for enterprise security</p>
          <h2 className="text-3xl sm:text-4xl font-black text-white tracking-tight leading-tight mb-5">
            Six decisions that separate<br />governance from compliance theater.
          </h2>
          <p className="text-stone-400 text-lg leading-relaxed max-w-2xl mx-auto">
            Every tool claims to govern AI. These are the choices that show we actually thought about what happens when things go wrong.
          </p>
        </div>

        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {decisions.map((d) => (
            <div key={d.label} className="rounded-2xl border border-stone-800 bg-stone-900 p-6 flex flex-col gap-3">
              <span className="text-xs font-bold uppercase tracking-widest text-indigo-400">{d.tag}</span>
              <h3 className="text-base font-bold text-white leading-snug">{d.label}</h3>
              <p className="text-sm text-stone-400 leading-relaxed">{d.body}</p>
            </div>
          ))}
        </div>

        <p className="text-center text-stone-600 text-xs mt-10">
          All six shipped in the same week. None were on a roadmap — they came from asking what a CISO would ask during a board demo.
        </p>
      </div>
    </section>
  )
}

/* ─── Final CTA ────────────────────────────────────────────────────────── */


function GatewayVsGuardSection() {
  return (
    <section className="bg-white border-t border-stone-100 px-6 py-20">
      <div className="max-w-3xl mx-auto">
        <p className="text-xs font-semibold uppercase tracking-widest text-stone-400 mb-4">How ConductGuard is different</p>
        <h2 className="text-3xl font-bold text-stone-900 mb-4 leading-tight">
          A gateway governs what the model costs.<br />Guard governs what the agent does.
        </h2>
        <p className="text-stone-500 mb-10 text-lg">
          Provider gateways sit between your team and the LLM. They cap spend, enforce SSO, and log model requests. That&apos;s the right layer for cost control.
        </p>
        <div className="grid md:grid-cols-2 gap-6 mb-10">
          <div className="border border-stone-200 rounded-xl p-6">
            <p className="text-sm font-semibold text-stone-400 uppercase tracking-widest mb-4">Provider gateway</p>
            <ul className="space-y-3 text-sm text-stone-600">
              {([
                ["yes", "Caps LLM spend per user"],
                ["yes", "SSO sign-in"],
                ["yes", "Model selection controls"],
                ["no",  "Sees tool calls (Bash, Write, Read)"],
                ["no",  "Blocks destructive commands before they run"],
                ["no",  "Detects credential leaks in tool input"],
                ["no",  "One policy across Claude, Codex, ChatGPT, Cursor, Copilot"],
                ["no",  "Custody proof audit log"],
              ] as [string, string][]).map(([state, label]) => (
                <li key={label} className="flex items-start gap-2">
                  <span className={state === "yes" ? "text-green-500 font-bold mt-0.5" : "text-stone-300 font-bold mt-0.5"}>{state === "yes" ? "✓" : "✗"}</span>
                  <span className={state === "no" ? "text-stone-400" : ""}>{label}</span>
                </li>
              ))}
            </ul>
          </div>
          <div className="border border-indigo-200 bg-indigo-50 rounded-xl p-6">
            <p className="text-sm font-semibold text-indigo-500 uppercase tracking-widest mb-4">ConductGuard</p>
            <ul className="space-y-3 text-sm text-stone-700">
              {[
                "Caps LLM spend per user",
                "SSO sign-in",
                "Model selection controls",
                "Sees tool calls (Bash, Write, Read)",
                "Blocks destructive commands before they run",
                "Detects credential leaks in tool input",
                "One policy across Claude, Codex, ChatGPT, Cursor, Copilot",
                "Custody proof audit log",
              ].map((label) => (
                <li key={label} className="flex items-start gap-2">
                  <span className="text-indigo-500 font-bold mt-0.5">✓</span>
                  <span>{label}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
        <p className="text-stone-400 text-sm">
          Use a provider gateway for spend control. Use ConductGuard for everything the model touches after it decides what to do.
        </p>
      </div>
    </section>
  )
}

function FoundationLayerSection() {
  return (
    <section className="bg-stone-50 border-y border-stone-100 py-14 px-6">
      <div className="max-w-5xl mx-auto">
        <p className="text-center text-xs font-semibold uppercase tracking-widest text-stone-400 mb-8">Guard is Layer 2. Start at Layer 0.</p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <a href="/team-os" className="group rounded-2xl border border-stone-200 bg-white p-6 hover:border-stone-400 hover:shadow-md transition-all flex gap-4">
            <div className="text-2xl shrink-0">📄</div>
            <div>
              <div className="flex items-center gap-2 mb-1">
                <p className="font-bold text-stone-900 text-sm">Team OS</p>
                <span className="text-xs bg-emerald-100 text-emerald-700 px-2 py-0.5 rounded-full font-semibold">Free</span>
              </div>
              <p className="text-xs text-stone-500 leading-relaxed">
                CLAUDE.md, REVIEW.md, and standards files — the quality bar Guard enforces, written down so every agent on your team starts from the same place.
              </p>
              <p className="text-xs font-semibold text-stone-600 group-hover:text-stone-900 mt-2 transition-colors">Get the templates →</p>
            </div>
          </a>
          <a href="/sdd" className="group rounded-2xl border border-stone-200 bg-white p-6 hover:border-stone-400 hover:shadow-md transition-all flex gap-4">
            <div className="text-2xl shrink-0">📐</div>
            <div>
              <p className="font-bold text-stone-900 text-sm mb-1">Spec-Driven Development</p>
              <p className="text-xs text-stone-500 leading-relaxed">
                Generate a SPEC.md before agents touch code. Guard enforces spec compliance at runtime — blocking actions that diverge from approved architecture.
              </p>
              <p className="text-xs font-semibold text-stone-600 group-hover:text-stone-900 mt-2 transition-colors">Generate your spec →</p>
            </div>
          </a>
        </div>
      </div>
    </section>
  )
}

function FinalCTASection() {
  return (
    <section className="py-24 px-6 bg-gradient-to-br from-indigo-600 to-violet-600">
      <div className="max-w-3xl mx-auto text-center">
        <h2 className="text-3xl sm:text-4xl font-black text-white tracking-tight leading-tight mb-4">
          Your team is already using AI agents.<br />Guard is how you govern them.
        </h2>
        <p className="text-indigo-200 text-lg leading-relaxed mb-10 max-w-xl mx-auto">
          One platform. Two problems solved.
        </p>
        <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
          <CtaLink className="rounded-xl bg-white text-indigo-600 px-7 py-3.5 text-base font-bold hover:bg-indigo-50 transition-colors w-full sm:w-auto text-center" />
          <a href="https://cal.com/sudhi-seshachala-pks7pd" target="_blank" rel="noopener" className="rounded-xl border border-white/40 text-white px-7 py-3.5 text-base font-semibold hover:bg-white/10 transition-colors w-full sm:w-auto text-center">
            Book a Demo
          </a>
        </div>
        <p className="text-indigo-300 text-xs mt-5">Free tier · No infrastructure changes · Works in minutes</p>
        <p className="text-indigo-300/70 text-xs mt-2">
          Need on-premise or cloud deployment?{" "}
          <a href="/deployment" className="underline hover:text-white transition-colors">See deployment options →</a>
        </p>
      </div>
    </section>
  )
}

