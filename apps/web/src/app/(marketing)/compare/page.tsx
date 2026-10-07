import Link from "next/link"

export const metadata = {
  title: "How Conduct compares to AI governance tools | Conduct",
  description:
    "Content guardrails, AI gateways, MCP gateways, and framework callbacks each govern one surface. Conduct enforces one policy across LLM calls, MCP tools, and CLI actions, with per-action approval, spend caps, and a hash-chained audit trail.",
  alternates: { canonical: "https://conductai.ai/compare" },
}

type Cell = "yes" | "partial" | "no"

const COLUMNS = ["Content guardrails", "AI gateways", "MCP gateways", "Framework callbacks", "Conduct"] as const

// ponytail: category-level comparison on purpose. Named-vendor rows need sourced, dated claims.
const ROWS: { capability: string; cells: [Cell, Cell, Cell, Cell, Cell] }[] = [
  { capability: "Inspects prompts and responses", cells: ["yes", "partial", "no", "partial", "yes"] },
  { capability: "Enforces policy on tool and MCP calls", cells: ["no", "no", "yes", "partial", "yes"] },
  { capability: "Enforces policy on local CLI and shell actions", cells: ["no", "no", "no", "no", "yes"] },
  { capability: "One policy across frameworks and vendors", cells: ["no", "partial", "partial", "no", "yes"] },
  { capability: "Human approves a specific action before it runs", cells: ["no", "no", "partial", "partial", "yes"] },
  { capability: "Spend caps that stop the call", cells: ["no", "yes", "no", "no", "yes"] },
  { capability: "Tamper-evident audit trail", cells: ["no", "partial", "partial", "no", "yes"] },
  { capability: "Mapped to compliance frameworks", cells: ["no", "no", "no", "no", "yes"] },
]

const MARK: Record<Cell, { glyph: string; label: string; cls: string }> = {
  yes: { glyph: "●", label: "Yes", cls: "text-emerald-600" },
  partial: { glyph: "◐", label: "Partial", cls: "text-amber-500" },
  no: { glyph: "○", label: "No", cls: "text-stone-300" },
}

const CATEGORIES = [
  {
    name: "Content guardrails",
    covers: "Filter what goes into and comes out of a model: injection, PII, toxicity.",
    gap: "Stop at the response. The tool call, shell command, or deploy the agent makes next is out of view.",
  },
  {
    name: "AI gateways",
    covers: "Route, meter, and rate-limit LLM traffic across providers.",
    gap: "See model requests only. MCP tool calls and actions on a developer's machine never pass through.",
  },
  {
    name: "MCP gateways",
    covers: "Allow or deny tool calls made over MCP.",
    gap: "Cover one transport. Model calls and CLI actions need a second and third policy.",
  },
  {
    name: "Framework callbacks",
    covers: "Hooks inside one agent framework.",
    gap: "Policy lives in each app's code, so five frameworks means five copies of the rules.",
  },
]

export default function ComparePage() {
  return (
    <div className="min-h-screen bg-white">
      <main className="max-w-5xl mx-auto px-6">
        <section className="pt-20 pb-14 text-left max-w-3xl">
          <p className="text-xs font-mono font-bold uppercase tracking-widest text-stone-400 mb-4">Compare</p>
          <h1 className="text-4xl sm:text-5xl font-black tracking-tight text-stone-900 leading-[1.05] mb-6">
            One policy. Every agent.
          </h1>
          <p className="text-lg text-stone-500 leading-relaxed">
            Most AI governance tools cover one surface: the prompt, the gateway, the MCP server, or one framework.
            Conduct enforces a single policy wherever an agent acts, and runs alongside the tools you already use.
          </p>
        </section>

        <section className="mb-16">
          <h2 className="text-2xl font-bold text-stone-900 mb-3">Coverage by approach</h2>
          <p className="text-stone-500 text-sm leading-relaxed mb-6 max-w-2xl">
            Typical coverage for each category. Individual products vary.
          </p>
          <div className="overflow-x-auto border border-stone-200 rounded-2xl">
            <table className="w-full min-w-[640px] text-sm">
              <thead className="bg-stone-50 text-stone-500">
                <tr>
                  <th scope="col" className="text-left font-semibold px-4 py-3">Capability</th>
                  {COLUMNS.map((c) => (
                    <th
                      key={c}
                      scope="col"
                      className={`px-3 py-3 font-semibold text-center ${c === "Conduct" ? "text-stone-900 bg-emerald-50" : ""}`}
                    >
                      {c}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-stone-200">
                {ROWS.map((r) => (
                  <tr key={r.capability}>
                    <th scope="row" className="text-left font-normal text-stone-700 px-4 py-3">{r.capability}</th>
                    {r.cells.map((cell, i) => (
                      <td key={COLUMNS[i]} className={`text-center px-3 py-3 ${i === 4 ? "bg-emerald-50" : ""}`}>
                        <span className={`text-lg ${MARK[cell].cls}`} aria-hidden="true">{MARK[cell].glyph}</span>
                        <span className="sr-only">{MARK[cell].label}</span>
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="text-xs text-stone-400 mt-3">● Yes · ◐ Partial · ○ No</p>
        </section>

        <section className="mb-16">
          <h2 className="text-2xl font-bold text-stone-900 mb-6">Where each approach stops</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {CATEGORIES.map((c) => (
              <div key={c.name} className="rounded-2xl border border-stone-200 p-5">
                <h3 className="font-bold text-stone-900 mb-2">{c.name}</h3>
                <p className="text-sm text-stone-700 leading-relaxed mb-2">{c.covers}</p>
                <p className="text-sm text-stone-500 leading-relaxed">{c.gap}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="mb-16">
          <h2 className="text-2xl font-bold text-stone-900 mb-3">Works with what you run</h2>
          <p className="text-stone-500 text-sm leading-relaxed mb-6 max-w-2xl">
            Conduct is the policy layer underneath, not a replacement. Keep your gateway, guardrails, and frameworks.
          </p>
          <ul className="space-y-3 text-sm text-stone-700">
            <li><strong className="text-stone-900">Guardrails:</strong> NVIDIA NeMo Guardrails via <code>conduct-nemo-guard</code>.</li>
            <li><strong className="text-stone-900">Gateways:</strong> LiteLLM via <code>conduct-litellm-guard</code>, plus bring-your-own Azure, OpenRouter, Portkey, and Helicone.</li>
            <li><strong className="text-stone-900">Agent frameworks:</strong> Claude Agent SDK, OpenAI Agents, LangChain, Google ADK, and CrewAI via <code>conduct-agent-guard</code>.</li>
            <li><strong className="text-stone-900">Coding agents:</strong> Claude Code, Cursor, and Windsurf via CLI hooks and MCP.</li>
          </ul>
        </section>

        <section className="mb-24 rounded-2xl bg-stone-900 text-white p-8">
          <h2 className="text-2xl font-bold mb-3">See one policy across your agents</h2>
          <p className="text-stone-300 text-sm leading-relaxed mb-6 max-w-2xl">
            Connect one agent, set one rule, and watch it apply to model calls, MCP tools, and the CLI.
          </p>
          <div className="flex flex-wrap gap-3">
            <Link href="/sign-up" className="inline-block rounded-xl bg-white text-stone-900 px-6 py-3 text-sm font-semibold hover:bg-stone-200 transition-colors">
              Get started
            </Link>
            <Link href="/what-is-conduct-ai" className="inline-block rounded-xl border border-stone-600 px-6 py-3 text-sm font-semibold hover:bg-stone-800 transition-colors">
              What is Conduct?
            </Link>
          </div>
        </section>
      </main>
    </div>
  )
}
