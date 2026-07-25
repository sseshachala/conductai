"use client"

import { useEffect, useState, useCallback } from "react"
import AppShell from "@/components/AppShell"
import { GuardShell } from "@/components/guard/GuardShell"
import { useWorkspace } from "@/lib/WorkspaceContext"
import { useGuardRole } from "@/hooks/useGuardRole"
import { useAuthFetch } from "@/hooks/useAuthFetch"
import { guard } from "@/lib/api"

interface DiscoveredAgent {
  id: string
  name: string | null
  framework: string | null
  source: string | null
  location: string | null
  risk_score: number | null
  under_guard: boolean
  last_seen_at: string
  proxy_routed: boolean
}

interface Summary {
  total: number
  under_guard: number
  missing: number
  coverage_pct: number
}

interface Scan {
  id: string
  triggered_by: string
  status: "running" | "complete" | "failed"
  agents_found: number | null
  guard_coverage: number | null
  started_at: string
  completed_at: string | null
}


const FRAMEWORK_LABELS: Record<string, string> = {
  "claude-code":    "Claude Code",
  "claude-desktop": "Claude Desktop",
  "codex":          "Codex",
  "codex-desktop":  "Codex Desktop",
  "cursor":         "Cursor",
  "windsurf":       "Windsurf",
  "vscode":         "VS Code / Copilot",
  "langchain":      "LangChain",
  "crewai":         "CrewAI",
  "autogen":        "AutoGen",
  "openai-agents":  "OpenAI Agents",
  "llama-index":    "LlamaIndex",
  "copilot":        "GitHub Copilot",
}

function RiskBadge({ score }: { score: number | null }) {
  if (score == null) return <span className="text-stone-400 text-xs">—</span>
  const color = score >= 70 ? "bg-red-100 text-red-700" : score >= 40 ? "bg-yellow-100 text-yellow-700" : "bg-green-100 text-green-700"
  const label = score >= 70 ? "High" : score >= 40 ? "Medium" : "Low"
  return <span className={`text-xs px-2 py-0.5 rounded font-medium ${color}`}>{label}</span>
}

const CONFIG_SOURCES = new Set(["claude-code", "claude-desktop", "cursor", "codex", "codex-desktop", "windsurf", "vscode", "copilot"])

function remediationFor(a: DiscoveredAgent): { type: "sync" | "proxy" | "env" } {
  if (a.source === "config" || CONFIG_SOURCES.has(a.framework ?? "")) return { type: "sync" }
  if (a.source === "env") return { type: "env" }
  return { type: "proxy" }
}

function RemediationModal({ agent, onClose }: { agent: DiscoveredAgent; onClose: () => void }) {
  const label = FRAMEWORK_LABELS[agent.framework ?? ""] ?? agent.name ?? agent.framework ?? "this agent"
  const { type } = remediationFor(agent)
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={onClose}>
      <div className="bg-white rounded-xl shadow-xl p-6 max-w-lg w-full mx-4 space-y-4" onClick={e => e.stopPropagation()}>
        <div className="flex items-start justify-between">
          <div>
            <p className="font-semibold text-stone-900">Bring {label} under Guard</p>
            <p className="text-xs text-stone-400 mt-0.5">{agent.framework} · {agent.source}</p>
          </div>
          <button onClick={onClose} className="text-stone-400 hover:text-stone-600 text-lg leading-none">×</button>
        </div>

        {type === "sync" && (
          <div className="space-y-3">
            <p className="text-sm text-stone-600">
              This tool is governed by the Guard hook. Run sync to (re)install the hook and download the latest policies.
            </p>
            <code className="block bg-stone-100 text-stone-800 text-xs px-4 py-3 rounded-lg">
              conduct guard sync
            </code>
            <p className="text-xs text-stone-400">After sync, run <code className="bg-stone-100 px-1 rounded">conduct guard discover</code> to verify coverage.</p>
          </div>
        )}

        {type === "proxy" && (
          <div className="space-y-3">
            <p className="text-sm text-stone-600">
              Route this agent&apos;s LLM calls through the Guard proxy. Set these env vars before running your agent:
            </p>
            <code className="block bg-stone-100 text-stone-800 text-xs px-4 py-3 rounded-lg whitespace-pre">
{`export OPENAI_BASE_URL=https://api.conductai.ai/proxy/openai
export ANTHROPIC_BASE_URL=https://api.conductai.ai/proxy/anthropic`}
            </code>
            <p className="text-xs text-stone-400">Or set <code className="bg-stone-100 px-1 rounded">CONDUCT_LLM_PROXY</code> if your framework reads a single proxy URL.</p>
          </div>
        )}

        {type === "env" && (
          <div className="space-y-3">
            <p className="text-sm text-stone-600">
              A raw LLM API key was found in <code className="bg-stone-100 px-1 rounded text-xs">{agent.location ?? ".env"}</code>.
              Replace it with the Guard proxy so calls are governed:
            </p>
            <code className="block bg-stone-100 text-stone-800 text-xs px-4 py-3 rounded-lg whitespace-pre">
{`# Remove the raw key and use the Guard proxy instead
OPENAI_BASE_URL=https://api.conductai.ai/proxy/openai
ANTHROPIC_BASE_URL=https://api.conductai.ai/proxy/anthropic`}
            </code>
            <p className="text-xs text-stone-400">Your team&apos;s credentials stay in the Guard vault — no key needed in the .env file.</p>
          </div>
        )}

        <div className="pt-2 flex justify-end">
          <button onClick={onClose} className="text-sm px-4 py-2 rounded-lg bg-stone-100 text-stone-700 hover:bg-stone-200 transition-colors">Done</button>
        </div>
      </div>
    </div>
  )
}

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const m = Math.floor(diff / 60000)
  if (m < 2)  return "just now"
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ago`
  return `${Math.floor(h / 24)}d ago`
}

function isStale(lastSeen: string): boolean {
  return Date.now() - new Date(lastSeen).getTime() > 24 * 60 * 60 * 1000
}

function RoutingBadge({ routed, framework }: { routed: boolean; framework: string | null }) {
  if (framework === "codex-desktop")
    return <span className="text-xs px-2 py-0.5 rounded font-medium bg-yellow-100 text-yellow-700">Partial</span>
  if (routed)
    return <span className="text-xs px-2 py-0.5 rounded font-medium bg-green-100 text-green-700">Proxied</span>
  return <span className="text-xs px-2 py-0.5 rounded font-medium bg-red-100 text-red-700">Not Proxied</span>
}

function GuardBadge({ under, lastSeen }: { under: boolean; lastSeen: string }) {
  if (!under) return <span className="text-xs px-2 py-0.5 rounded font-medium bg-red-100 text-red-700">Missing from Guard</span>
  if (isStale(lastSeen)) return <span className="text-xs px-2 py-0.5 rounded font-medium bg-yellow-100 text-yellow-700" title="Hook hasn't fired in 24h — agent may be uninstalled">Stale</span>
  return <span className="text-xs px-2 py-0.5 rounded font-medium bg-green-100 text-green-700">Under Guard</span>
}

export default function DiscoveryPage() {
  const { authFetch } = useAuthFetch()
  const { activeWorkspace } = useWorkspace()
  const { permissions, loading: roleLoading } = useGuardRole()
  const canRegister = !roleLoading && permissions.canEditPolicies
  const workspaceId = activeWorkspace?.id ?? null
  const [summary, setSummary] = useState<Summary | null>(null)
  const [agents, setAgents]   = useState<DiscoveredAgent[]>([])
  const [scans, setScans]     = useState<Scan[]>([])
  const [loading, setLoading] = useState(true)
  const [registering, setRegistering] = useState<string | null>(null)
  const [modalAgent, setModalAgent] = useState<DiscoveredAgent | null>(null)
  const [agentLimit, setAgentLimit] = useState(10)
  const [scanLimit, setScanLimit]   = useState(10)

  const load = useCallback(async () => {
    const [sumData, agentData, scanData] = await Promise.allSettled([
      guard.discover.summary(authFetch),
      guard.discover.agents(authFetch),
      guard.discover.scans(authFetch),
    ])

    if (sumData.status === "fulfilled")   setSummary(sumData.value)
    if (agentData.status === "fulfilled") setAgents(agentData.value)
    if (scanData.status === "fulfilled")  setScans(scanData.value)
    setLoading(false)
  }, [authFetch])

  useEffect(() => { load() }, [load])

  async function register(agentId: string) {
    setRegistering(agentId)
    await guard.discover.register(authFetch, agentId)
    await load()
    setRegistering(null)
  }

  const coveragePct = summary?.coverage_pct ?? 0
  const barColor    = coveragePct >= 70 ? "bg-green-500" : coveragePct >= 40 ? "bg-yellow-500" : "bg-red-500"

  return (
    <AppShell><GuardShell>
      {modalAgent && <RemediationModal agent={modalAgent} onClose={() => setModalAgent(null)} />}
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
            <div className="card" style={{ overflow: "hidden" }}>
              <div style={{ display: "grid", gridTemplateColumns: "1.6fr 0.7fr 1.6fr 0.7fr 0.9fr 0.9fr 1fr", gap: 12, padding: "10px 18px", borderBottom: "1px solid var(--border)", background: "var(--surface-2)" }}>
                {["Agent", "Source", "Location", "Risk", "Status", "Last seen", ""].map((h, i) => (
                  <div key={i} className="eyebrow" style={{ fontSize: 9.5 }}>{h}</div>
                ))}
              </div>
              {agents.slice(0, agentLimit).map((a, i) => (
                <div key={a.id} style={{ display: "grid", gridTemplateColumns: "1.6fr 0.7fr 1.6fr 0.7fr 0.9fr 0.9fr 1fr", gap: 12, padding: "11px 18px", alignItems: "center", borderBottom: i < Math.min(agents.length, agentLimit) - 1 ? "1px solid var(--border)" : "none" }}>
                  <div>
                    <p className="text-sm font-medium text-stone-800">{FRAMEWORK_LABELS[a.framework ?? ""] ?? a.name ?? a.framework ?? "Unknown"}</p>
                    <p className="text-xs text-stone-400">{a.framework}</p>
                  </div>
                  <div className="text-sm text-stone-500 capitalize">{a.source ?? "—"}</div>
                  <div className="text-xs font-mono text-stone-400 truncate">{a.location ?? "—"}</div>
                  <div><RiskBadge score={a.risk_score} /></div>
                  <div className="flex flex-col gap-1">
                    <GuardBadge under={a.under_guard} lastSeen={a.last_seen_at} />
                    {a.source === "ai-tool" && <RoutingBadge routed={a.proxy_routed} framework={a.framework} />}
                  </div>
                  <div className="text-xs text-stone-400" title={new Date(a.last_seen_at).toLocaleString()}>
                    {relativeTime(a.last_seen_at)}
                  </div>
                  <div className="text-right">
                    {!a.under_guard && (() => {
                      const { type } = remediationFor(a)
                      if (type === "sync") return (
                        <span className="text-xs text-stone-400 italic">Run <code className="bg-stone-100 px-1 rounded">conduct guard sync</code></span>
                      )
                      return (
                        <button onClick={() => setModalAgent(a)} disabled={!canRegister} className="text-xs px-3 py-1.5 rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 transition-colors disabled:opacity-40 disabled:cursor-not-allowed">
                          Bring under Guard
                        </button>
                      )
                    })()}
                  </div>
                </div>
              ))}
            </div>

            <div className="flex items-center justify-between">
              <p className="text-xs text-stone-400">
                Auto-refreshes every 15 min via <code className="bg-stone-100 px-1 rounded">conduct guard watch</code>. Yellow = hook silent &gt;24h.
              </p>
              {agents.length > agentLimit && (
                <button
                  onClick={() => setAgentLimit(n => n + 10)}
                  className="text-xs text-indigo-600 hover:text-indigo-700 font-medium"
                >
                  Load more ({agents.length - agentLimit} remaining)
                </button>
              )}
            </div>

            {/* Scan history */}
            {scans.length > 0 && (
              <div className="card" style={{ overflow: "hidden" }}>
                <div style={{ padding: "10px 18px", borderBottom: "1px solid var(--border)", background: "var(--surface-2)" }}>
                  <p className="eyebrow">Scan History</p>
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "1.4fr 1.2fr 0.8fr 0.8fr 0.8fr", gap: 12, padding: "10px 18px", borderBottom: "1px solid var(--border)", background: "var(--surface-2)" }}>
                  {["When", "Triggered by", "Agents found", "Under Guard", "Status"].map((h, i) => (
                    <div key={i} className="eyebrow" style={{ fontSize: 9.5 }}>{h}</div>
                  ))}
                </div>
                {scans.slice(0, scanLimit).map((s, i) => (
                  <div key={s.id} style={{ display: "grid", gridTemplateColumns: "1.4fr 1.2fr 0.8fr 0.8fr 0.8fr", gap: 12, padding: "11px 18px", alignItems: "center", borderBottom: i < Math.min(scans.length, scanLimit) - 1 ? "1px solid var(--border)" : "none" }}>
                    <div className="text-xs text-stone-500">{new Date(s.started_at).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })}</div>
                    <div className="text-xs font-mono text-stone-600">{s.triggered_by}</div>
                    <div className="text-sm text-stone-700">{s.agents_found ?? "—"}</div>
                    <div className="text-sm text-stone-700">{s.guard_coverage ?? "—"}</div>
                    <div>
                      <span className={`text-xs px-2 py-0.5 rounded font-medium ${
                        s.status === "complete" ? "bg-green-100 text-green-700" :
                        s.status === "failed"   ? "bg-red-100 text-red-700" :
                                                  "bg-yellow-100 text-yellow-700"
                      }`}>{s.status}</span>
                    </div>
                  </div>
                ))}
                {scans.length > scanLimit && (
                  <div style={{ padding: "10px 18px", borderTop: "1px solid var(--border)" }}>
                    <button onClick={() => setScanLimit(n => n + 10)} className="text-xs text-indigo-600 hover:text-indigo-700 font-medium">
                      Load more ({scans.length - scanLimit} remaining)
                    </button>
                  </div>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </GuardShell></AppShell>
  )
}
