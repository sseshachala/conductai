"use client"

import { useState } from "react"
import { type BlockNodeData } from "./BlockNode"
import { type Node } from "@xyflow/react"

interface BlockEstimate {
  block_id: string
  label: string
  type: string
  mode: string
  integration: string | null
  input_tokens: number
  output_tokens: number
  cost_usd: number
  note: string
}

interface Estimate {
  block_count: number
  blocks: BlockEstimate[]
  total_input_tokens: number
  total_output_tokens: number
  total_tokens: number
  per_run_cost_usd: number
  issues_count: number
  total_cost_usd: number
  integrations_used: string[]
  model: string
  pricing_note: string
  based_on_actuals: boolean
}

const MODE_BADGE: Record<string, string> = {
  agentic: "bg-purple-100 text-purple-700",
  brain:   "bg-purple-100 text-purple-700",
  tool:    "bg-green-100 text-green-700",
  trigger: "bg-blue-100 text-blue-700",
  output:  "bg-rose-100 text-rose-700",
  logic:   "bg-gray-100 text-gray-600",
  approval:"bg-orange-100 text-orange-700",
  cleanup: "bg-yellow-100 text-yellow-700",
  memory:  "bg-amber-100 text-amber-700",
}

function fmt(n: number) {
  return n.toLocaleString()
}

function fmtCost(n: number) {
  if (n === 0) return "—"
  if (n < 0.001) return `< $0.001`
  return `$${n.toFixed(4)}`
}

function getWorkspaceHeader(): Record<string, string> {
  if (typeof document === "undefined") return {}
  const m = document.cookie.match(/(?:^|;\s*)delegator_project_id=([^;]+)/)
  return m ? { "X-Workspace-Id": m[1] } : {}
}

interface Props {
  workflowId: string
  nodes?: Node[]
  getToken?: (() => Promise<string | null>) | null
}

export default function CostEstimate({ workflowId, nodes, getToken }: Props) {
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [estimate, setEstimate] = useState<Estimate | null>(null)
  const [error, setError] = useState("")

  async function load() {
    setLoading(true)
    setError("")
    try {
      const headers: Record<string, string> = { ...getWorkspaceHeader() }
      if (getToken) {
        const token = await getToken()
        if (token) headers["Authorization"] = `Bearer ${token}`
      }

      // Find trigger block — read repo_allowlist + label to count matching issues
      let issuesCount = 1
      const triggerNode = (nodes ?? []).find(n => {
        const d = n.data as BlockNodeData
        const cfg = (d.config as Record<string, unknown>) ?? {}
        return d.type === "trigger" && (
          cfg.event_type === "github_issue_labeled" || cfg.event_type === "github_issue"
        )
      })
      if (triggerNode) {
        const cfg = (triggerNode.data as BlockNodeData).config as Record<string, unknown>
        const repoAllowlist = (cfg.repo_allowlist as string) || ""
        const label = (cfg.label as string) || ""
        const repos = repoAllowlist.split(",").map(s => s.trim()).filter(Boolean)
        if (repos.length > 0 && label) {
          let total = 0
          await Promise.all(repos.map(async (repo) => {
            try {
              const r = await fetch(
                `${process.env.NEXT_PUBLIC_API_URL}/credentials/github/issues?repo=${encodeURIComponent(repo)}&label=${encodeURIComponent(label)}`,
                { headers }
              )
              if (r.ok) {
                const issues = await r.json()
                total += Array.isArray(issues) ? issues.length : 0
              }
            } catch { /* skip */ }
          }))
          issuesCount = Math.max(1, total)
        }
      }

      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/workflows/${workflowId}/estimate?issues=${issuesCount}`,
        { headers }
      )
      if (!res.ok) throw new Error("Failed to estimate")
      setEstimate(await res.json())
      setOpen(true)
    } catch {
      setError("Could not load estimate")
    } finally {
      setLoading(false)
    }
  }

  return (
    <>
      <button
        onClick={load}
        disabled={loading}
        className="text-xs text-stone-500 hover:text-stone-800 disabled:opacity-50 transition-colors"
      >
        {loading ? "Estimating…" : "Estimate cost"}
      </button>
      {error && <span className="text-xs text-red-400">{error}</span>}

      {/* Modal overlay */}
      {open && estimate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div className="absolute inset-0 bg-black/40" onClick={() => setOpen(false)} />
          <div className="relative bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[85vh] flex flex-col mx-4">

            {/* Header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-stone-200">
              <div>
                <h2 className="text-base font-semibold text-stone-900">Cost estimate</h2>
                <p className="text-xs text-stone-400 mt-0.5">{estimate.model} · {estimate.pricing_note}</p>
              </div>
              <button onClick={() => setOpen(false)} className="text-stone-400 hover:text-stone-600 text-xl leading-none">×</button>
            </div>

            {/* Summary bar */}
            <div className="grid grid-cols-4 gap-px bg-stone-100 border-b border-stone-200">
              <div className="bg-white px-5 py-3">
                <p className="text-xs text-stone-400">
                  {estimate.issues_count > 1 ? `Total (${estimate.issues_count} issues)` : "Est. total cost"}
                </p>
                <p className="text-xl font-semibold text-stone-900 mt-0.5">
                  {estimate.total_cost_usd === 0 ? "Free" : `$${estimate.total_cost_usd.toFixed(4)}`}
                </p>
                {estimate.issues_count > 1 && (
                  <p className="text-xs text-stone-400 mt-0.5">${estimate.per_run_cost_usd.toFixed(4)} × {estimate.issues_count}</p>
                )}
              </div>
              <div className="bg-white px-5 py-3">
                <p className="text-xs text-stone-400">Tokens / run</p>
                <p className="text-xl font-semibold text-stone-900 mt-0.5">{fmt(estimate.total_tokens)}</p>
                <p className="text-xs text-stone-400">{fmt(estimate.total_input_tokens)} in · {fmt(estimate.total_output_tokens)} out</p>
              </div>
              <div className="bg-white px-5 py-3">
                <p className="text-xs text-stone-400">Integrations</p>
                <p className="text-sm font-medium text-stone-700 mt-1">
                  {estimate.integrations_used.length === 0 ? "None" : estimate.integrations_used.join(", ")}
                </p>
              </div>
              <div className="bg-white px-5 py-3">
                <p className="text-xs text-stone-400">Data source</p>
                <p className="text-sm font-medium mt-1">
                  {estimate.based_on_actuals
                    ? <span className="text-emerald-600">✓ historical actuals</span>
                    : <span className="text-amber-500">⚠ static estimate</span>}
                </p>
              </div>
            </div>

            {/* Block breakdown */}
            <div className="overflow-y-auto flex-1">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs text-stone-400 border-b border-stone-100">
                    <th className="px-5 py-2.5 font-medium">Block</th>
                    <th className="px-3 py-2.5 font-medium">Type</th>
                    <th className="px-3 py-2.5 font-medium text-right">Input</th>
                    <th className="px-3 py-2.5 font-medium text-right">Output</th>
                    <th className="px-5 py-2.5 font-medium text-right">Cost</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-stone-50">
                  {estimate.blocks.map((b) => (
                    <tr key={b.block_id} className="hover:bg-stone-50">
                      <td className="px-5 py-2.5">
                        <span className="font-medium text-stone-800">{b.label}</span>
                        {b.note && <span className="ml-2 text-xs text-stone-400">{b.note}</span>}
                        {b.integration && (
                          <span className="ml-2 text-xs text-stone-400">via {b.integration}</span>
                        )}
                      </td>
                      <td className="px-3 py-2.5">
                        <span className={`text-[10px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded ${MODE_BADGE[b.mode] ?? "bg-stone-100 text-stone-500"}`}>
                          {b.mode}
                        </span>
                      </td>
                      <td className="px-3 py-2.5 text-right text-stone-500 font-mono text-xs">
                        {b.input_tokens > 0 ? fmt(b.input_tokens) : "—"}
                      </td>
                      <td className="px-3 py-2.5 text-right text-stone-500 font-mono text-xs">
                        {b.output_tokens > 0 ? fmt(b.output_tokens) : "—"}
                      </td>
                      <td className="px-5 py-2.5 text-right font-medium text-stone-700">
                        {fmtCost(b.cost_usd)}
                      </td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr className="border-t-2 border-stone-200 bg-stone-50">
                    <td className="px-5 py-3 font-semibold text-stone-900" colSpan={2}>Total</td>
                    <td className="px-3 py-3 text-right font-mono text-xs text-stone-600">{fmt(estimate.total_input_tokens)}</td>
                    <td className="px-3 py-3 text-right font-mono text-xs text-stone-600">{fmt(estimate.total_output_tokens)}</td>
                    <td className="px-5 py-3 text-right font-semibold text-stone-900">
                      {estimate.total_cost_usd === 0 ? "Free" : `$${estimate.total_cost_usd.toFixed(4)}`}
                    </td>
                  </tr>
                </tfoot>
              </table>
            </div>

            <div className="px-6 py-3 border-t border-stone-100 text-xs text-stone-400">
              {estimate.based_on_actuals
                ? "Based on averaged actual token usage from previous runs of this workflow."
                : "No run history yet — using static estimates. Accuracy improves after first run."}
              {" "}Pricing: {estimate.pricing_note}.
            </div>
          </div>
        </div>
      )}
    </>
  )
}
