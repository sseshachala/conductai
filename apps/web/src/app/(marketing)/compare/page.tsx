import Link from "next/link"

export const metadata = {
  title: "How Conduct compares to AI governance tools | Conduct",
  description:
    "Content guardrails, AI gateways, MCP gateways, and framework callbacks each govern part of the stack. Conduct enforces one policy across LLM calls, MCP tools, and CLI actions, with per-action approval, spend caps, and a hash-chained audit trail.",
  alternates: { canonical: "https://conductai.ai/compare" },
}

type Cell = "yes" | "partial" | "no" | "unknown"

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
  unknown: { glyph: "–", label: "Not documented", cls: "text-stone-300" },
}

// Named tools, from each vendor's public docs as of 2026-10-07. "unknown" = not documented, not "No".
// Re-verify before changing a cell; keep SOURCES in sync.
const VENDORS = ["Conduct", "Lakera Guard", "Zenity", "Lasso", "Prompt Security", "Kong AI Gateway", "Cloudflare AI Gateway"] as const

const VENDOR_ROWS: { capability: string; cells: Cell[] }[] = [
  { capability: "Inspects prompts and responses", cells: ["yes", "yes", "unknown", "yes", "yes", "yes", "yes"] },
  { capability: "Enforces policy on tool and MCP calls", cells: ["yes", "partial", "yes", "yes", "yes", "yes", "partial"] },
  { capability: "Enforces policy on coding-agent CLI actions", cells: ["yes", "unknown", "yes", "yes", "partial", "no", "no"] },
  { capability: "One policy across LLM, MCP, and CLI", cells: ["yes", "partial", "partial", "partial", "partial", "partial", "partial"] },
  { capability: "Human approves a specific action before it runs", cells: ["yes", "no", "unknown", "unknown", "unknown", "no", "no"] },
  { capability: "Spend caps that stop the call", cells: ["yes", "unknown", "unknown", "unknown", "unknown", "yes", "yes"] },
  { capability: "Tamper-evident (hash-chained) audit trail", cells: ["yes", "unknown", "partial", "partial", "partial", "partial", "partial"] },
  { capability: "Mapped to compliance frameworks", cells: ["yes", "partial", "partial", "yes", "unknown", "unknown", "unknown"] },
]

const SOURCES: { vendor: string; note: string; urls: string[] }[] = [
  { vendor: "Lakera Guard", note: "Part of Check Point. Docs list human approval gates as the customer's responsibility.", urls: ["https://docs.lakera.ai/docs/agent-security/framework-mapping"] },
  { vendor: "Zenity", note: "Native hooks for coding agents and an MCP gateway. Audit logs; immutability not documented.", urls: ["https://zenity.io/use-cases/agent-type/device-based", "https://zenity.io/use-cases/business-needs/ai-agents-compliance"] },
  { vendor: "Lasso", note: "Claude Code lifecycle hooks and an MCP gateway. Maps to NIST AI RMF, EU AI Act, ISO 42001, OWASP.", urls: ["https://lasso.security/use-cases/ai-coding-assistants", "https://lasso.security/use-cases/mcp-security"] },
  { vendor: "Prompt Security", note: "Part of SentinelOne. Coding-assistant coverage is for data leakage. Searchable audit log.", urls: ["https://www.sentinelone.com/platform/securing-ai-prompt/"] },
  { vendor: "Kong AI Gateway", note: "Prompt guards, MCP tool ACLs, and spend limits via AI rate limiting. Network gateway only.", urls: ["https://developer.konghq.com/ai-gateway/", "https://developer.konghq.com/mcp/use-access-controls-for-mcp-tools/"] },
  { vendor: "Cloudflare AI Gateway", note: "Guardrails, DLP, spend limits that return 429. MCP portals allowlist tools.", urls: ["https://developers.cloudflare.com/ai-gateway/features/", "https://developers.cloudflare.com/ai-gateway/features/spend-limits/", "https://developers.cloudflare.com/cloudflare-one/access-controls/ai-controls/mcp-portals/"] },
]

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
        {/* Hero: dark full-width band, matches /guard */}
        <section className="-mx-6 sm:-mx-10 lg:-mx-20 px-6 sm:px-10 lg:px-20 py-20 sm:py-24 bg-stone-950 mb-16">
          <p className="text-xs font-mono font-bold uppercase tracking-widest text-indigo-400 mb-4">Compare</p>
          <h1 className="text-4xl sm:text-5xl lg:text-6xl font-black tracking-tight text-white leading-[1.05] mb-6 max-w-3xl">
            One policy. Every agent.
          </h1>
          <p className="text-lg text-stone-400 leading-relaxed max-w-2xl">
            Many AI governance tools cover one or two surfaces: the prompt, the gateway, the MCP server, or one framework.
            Conduct enforces a single policy wherever an agent acts, and runs alongside the tools you already use.
          </p>
        </section>

        <section className="mb-20">
          <h2 className="text-2xl font-bold text-stone-900 mb-3">Coverage by approach</h2>
          <p className="text-stone-500 text-sm leading-relaxed mb-8 max-w-2xl">
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

        <section className="mb-20">
          <h2 className="text-2xl font-bold text-stone-900 mb-3">Named tools</h2>
          <p className="text-stone-500 text-sm leading-relaxed mb-8 max-w-2xl">
            From each vendor&apos;s public documentation as of October 2026. A dash means we found no documentation
            either way, not that the feature is missing. Spot an error? Email{" "}
            <a href="mailto:hello@conductai.ai" className="underline">hello@conductai.ai</a> and we&apos;ll correct it.
          </p>
          <div className="overflow-x-auto border border-stone-200 rounded-2xl">
            <table className="w-full min-w-[820px] text-sm">
              <thead className="bg-stone-50 text-stone-500">
                <tr>
                  <th scope="col" className="text-left font-semibold px-4 py-3">Capability</th>
                  {VENDORS.map((v, i) => (
                    <th key={v} scope="col" className={`px-3 py-3 font-semibold text-center ${i === 0 ? "text-stone-900 bg-emerald-50" : ""}`}>
                      {v}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-stone-200">
                {VENDOR_ROWS.map((r) => (
                  <tr key={r.capability}>
                    <th scope="row" className="text-left font-normal text-stone-700 px-4 py-3">{r.capability}</th>
                    {r.cells.map((cell, i) => (
                      <td key={VENDORS[i]} className={`text-center px-3 py-3 ${i === 0 ? "bg-emerald-50" : ""}`}>
                        <span className={`text-lg ${MARK[cell].cls}`} aria-hidden="true">{MARK[cell].glyph}</span>
                        <span className="sr-only">{MARK[cell].label}</span>
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="text-xs text-stone-400 mt-3">● Yes · ◐ Partial · ○ No · – Not documented</p>
          <details className="mt-6 text-sm text-stone-600">
            <summary className="cursor-pointer font-semibold text-stone-800">Sources</summary>
            <ul className="mt-3 space-y-3">
              {SOURCES.map((s) => (
                <li key={s.vendor}>
                  <strong className="text-stone-900">{s.vendor}:</strong> {s.note}{" "}
                  {s.urls.map((u, i) => (
                    <a key={u} href={u} rel="noopener noreferrer" target="_blank" className="underline break-all">
                      [{i + 1}]
                    </a>
                  ))}
                </li>
              ))}
            </ul>
          </details>
        </section>

        <section className="mb-20">
          <h2 className="text-2xl font-bold text-stone-900 mb-3">Where each approach stops</h2>
          <p className="text-stone-500 text-sm leading-relaxed mb-8 max-w-2xl">
            What each category is built for, and what it can&apos;t see.
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {CATEGORIES.map((c) => (
              <div key={c.name} className="border border-stone-200 rounded-xl bg-white p-5 shadow-sm">
                <p className="font-semibold text-stone-900 mb-2 text-[15px]">{c.name}</p>
                <p className="text-sm text-stone-700 leading-relaxed mb-2">{c.covers}</p>
                <p className="text-sm text-stone-500 leading-relaxed">{c.gap}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="mb-20">
          <h2 className="text-2xl font-bold text-stone-900 mb-3">Works with what you run</h2>
          <p className="text-stone-500 text-sm leading-relaxed mb-8 max-w-2xl">
            Conduct is the policy layer underneath, not a replacement. Keep your gateway, guardrails, and frameworks.
          </p>
          <ul className="space-y-3 text-sm text-stone-700">
            <li><strong className="text-stone-900">Guardrails:</strong> NVIDIA NeMo Guardrails via <code>conduct-nemo-guard</code>.</li>
            <li><strong className="text-stone-900">Gateways:</strong> LiteLLM via <code>conduct-litellm-guard</code>, plus bring-your-own Azure, OpenRouter, Portkey, and Helicone.</li>
            <li><strong className="text-stone-900">Agent frameworks:</strong> Claude Agent SDK, OpenAI Agents, LangChain, Google ADK, and CrewAI via <code>conduct-agent-guard</code>.</li>
            <li><strong className="text-stone-900">Coding agents:</strong> Claude Code, Codex, GitHub Copilot CLI, Cursor, and Windsurf via CLI hooks and MCP.</li>
          </ul>
        </section>

        {/* CTA: indigo full-width band, matches /guard */}
        <section className="-mx-6 sm:-mx-10 lg:-mx-20 px-6 sm:px-10 lg:px-20 py-16 sm:py-24 bg-indigo-600 mb-0 text-center">
          <h2 className="text-2xl sm:text-3xl font-bold text-white tracking-tight mb-6 max-w-2xl mx-auto">
            See one policy across your agents.
          </h2>
          <div className="flex flex-wrap justify-center gap-3">
            <Link
              href="/sign-up"
              className="inline-block rounded-xl bg-white text-indigo-700 px-6 py-3 text-sm font-semibold hover:bg-indigo-50 transition-colors"
            >
              Get started
            </Link>
            <Link
              href="/book-demo"
              className="inline-block rounded-xl border border-indigo-300 bg-transparent text-white px-6 py-3 text-sm font-semibold hover:bg-indigo-700 transition-colors"
            >
              Book a Demo
            </Link>
          </div>
        </section>
      </main>
    </div>
  )
}
