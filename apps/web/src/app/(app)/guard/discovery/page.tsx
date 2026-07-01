"use client"

import { useEffect, useState, useCallback } from "react"
import { useAuth } from "@clerk/nextjs"
import { GuardShell } from "@/components/guard/GuardShell"
import { useWorkspace } from "@/lib/WorkspaceContext"

interface DiscoveredAgent {
  id: string
  name: string | null
  framework: string | null
  source: string | null
  location: string | null
  risk_score: number | null
  under_guard: boolean
  last_seen_at: string
}

interface Summary {
  total: number
  under_guard: number
  missing: number
  coverage_pct: number
}

const API = process.env.NEXT_PUBLIC_API_URL ?? "https://api.conductai.ai"

const FRAMEWORK_LABELS: Record<string, string> = {
  "claude-code": "Claude Code",
  "codex":       "Codex",
  "cursor":      "Cursor",
  "windsurf":    "Windsurf",
  "vscode":      "VS Code / Copilot",
  "langchain":   "LangChain",
  "crewai":      "CrewAI",
  "autogen":     "AutoGen",
  "openai-agents": "OpenAI Agents",
  "llama-index": "LlamaIndex",
  "copilot":     "GitHub Copilot",
}

function RiskBadge({ score }: { score: number | null }) {
  if (score == null) return <span className="text-stone-400 text-xs">—</span>
  const color = score >= 70 ? "bg-red-100 text-red-700" : score >= 40 ? "bg-yellow-100 text-yellow-700" : "bg-green-100 text-green-700"
  const label = score >= 70 ? "High" : score >= 40 ? "Medium" : "Low"
  return <span className={`text-xs px-2 py-0.5 rounded font-medium ${color}`}>{label}</span>
}

function GuardBadge({ under }: { under: boolean }) {
  return under
    ? <span className="text-xs px-2 py-0.5 rounded font-medium bg-green-100 text-green-700">Under Guard</span>
    : <span className="text-xs px-2 py-0.5 rounded font-medium bg-red-100 text-red-700">Missing from Guard</span>
}

export default function DiscoveryPage() {
  const { getToken } = useAuth()
  const { activeWorkspace } = useWorkspace()
  const workspaceId = activeWorkspace?.id ?? null
  const [summary, setSummary] = useState<Summary | null>(null)
  const [agents, setAgents]   = useState<DiscoveredAgent[]>([])
  const [loading, setLoading] = useState(true)
  const [registering, setRegistering] = useState<string | null>(null)

  const load = useCallback(async () => {
    const token = await getToken()
    const hdrs  = { Authorization: `Bearer ${token}`, "x-workspace-id": workspaceId ?? "" }

    const [sumRes, agentRes] = await Promise.all([
      fetch(`${API}/guard/discover/summary`, { headers: hdrs }),
      fetch(`${API}/guard/discover/agents`,  { headers: hdrs }),
    ])

    if (sumRes.ok)   setSummary(await sumRes.json())
    if (agentRes.ok) setAgents(await agentRes.json())
    setLoading(false)
  }, [getToken, workspaceId])

  useEffect(() => { load() }, [load])

  async function register(agentId: string) {
    setRegistering(agentId)
    const token = await getToken()
    await fetch(`${API}/guard/discover/agents/${agentId}/register`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}`, "x-workspace-id": workspaceId ?? "" },
    })
    await load()
    setRegistering(null)
  }

  const coveragePct = summary?.coverage_pct ?? 0
  const barColor    = coveragePct >= 70 ? "bg-green-500" : coveragePct >= 40 ? "bg-yellow-500" : "bg-red-500"

  return (
    <GuardShell>
      <div className="max-w-5xl mx-auto px-6 py-8 space-y-8">

        {/* Header */}
        <div>
          <h1 className="text-2xl font-semibold text-stone-900">Shadow AI Discovery</h1>
          <p className="text-sm text-stone-500 mt-1">
            Agent Inventory — all AI agents found in your org, and how many Guard governs.
          </p>
        </div>

        {loading ? (
          <p className="text-sm text-stone-400">Loading...</p>
        ) : summary && summary.total === 0 ? (
          /* Empty state */
          <div className="border border-dashed border-stone-300 rounded-xl p-12 text-center space-y-3">
            <p className="text-stone-500 font-medium">No agents discovered yet</p>
            <p className="text-sm text-stone-400">Run a scan from your machine to populate this view.</p>
            <code className="block mt-4 text-xs bg-stone-100 text-stone-700 px-4 py-2 rounded-lg inline-block">
              conduct guard discover
            </code>
          </div>
        ) : (
          <>
            {/* Coverage meter */}
            {summary && (
              <div className="bg-white border border-stone-200 rounded-xl p-6 space-y-4">
                <div className="flex items-end justify-between">
                  <div>
                    <p className="text-3xl font-bold text-stone-900">{coveragePct}%</p>
                    <p className="text-sm text-stone-500 mt-0.5">Guard coverage</p>
                  </div>
                  <div className="flex gap-6 text-right">
                    <div>
                      <p className="text-xl font-semibold text-stone-900">{summary.total}</p>
                      <p className="text-xs text-stone-500">total agents</p>
                    </div>
                    <div>
                      <p className="text-xl font-semibold text-green-700">{summary.under_guard}</p>
                      <p className="text-xs text-stone-500">under Guard</p>
                    </div>
                    <div>
                      <p className="text-xl font-semibold text-red-600">{summary.missing}</p>
                      <p className="text-xs text-stone-500">missing from Guard</p>
                    </div>
                  </div>
                </div>
                <div className="w-full bg-stone-100 rounded-full h-2">
                  <div className={`h-2 rounded-full transition-all ${barColor}`} style={{ width: `${coveragePct}%` }} />
                </div>
              </div>
            )}

            {/* Agent table */}
            <div className="bg-white border border-stone-200 rounded-xl overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-stone-50 border-b border-stone-200">
                  <tr>
                    <th className="text-left px-4 py-3 text-xs font-medium text-stone-500 uppercase tracking-wide">Agent</th>
                    <th className="text-left px-4 py-3 text-xs font-medium text-stone-500 uppercase tracking-wide">Source</th>
                    <th className="text-left px-4 py-3 text-xs font-medium text-stone-500 uppercase tracking-wide">Location</th>
                    <th className="text-left px-4 py-3 text-xs font-medium text-stone-500 uppercase tracking-wide">Risk</th>
                    <th className="text-left px-4 py-3 text-xs font-medium text-stone-500 uppercase tracking-wide">Status</th>
                    <th className="px-4 py-3" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-stone-100">
                  {agents.map(a => (
                    <tr key={a.id} className="hover:bg-stone-50 transition-colors">
                      <td className="px-4 py-3">
                        <p className="font-medium text-stone-800">{FRAMEWORK_LABELS[a.framework ?? ""] ?? a.name ?? a.framework ?? "Unknown"}</p>
                        <p className="text-xs text-stone-400">{a.framework}</p>
                      </td>
                      <td className="px-4 py-3 text-stone-500 capitalize">{a.source ?? "—"}</td>
                      <td className="px-4 py-3 text-stone-400 text-xs font-mono truncate max-w-48">{a.location ?? "—"}</td>
                      <td className="px-4 py-3"><RiskBadge score={a.risk_score} /></td>
                      <td className="px-4 py-3"><GuardBadge under={a.under_guard} /></td>
                      <td className="px-4 py-3 text-right">
                        {!a.under_guard && (
                          <button
                            onClick={() => register(a.id)}
                            disabled={registering === a.id}
                            className="text-xs px-3 py-1.5 rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-50 transition-colors"
                          >
                            {registering === a.id ? "Registering..." : "Bring under Guard"}
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <p className="text-xs text-stone-400">
              Run <code className="bg-stone-100 px-1 rounded">conduct guard discover</code> again to refresh.
              GitHub scan coming in v2.
            </p>
          </>
        )}
      </div>
    </GuardShell>
  )
}
