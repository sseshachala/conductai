"use client"

import { useEffect, useRef, useState } from "react"
import Link from "next/link"
import { useParams, useRouter } from "next/navigation"
import { useAuth } from "@clerk/nextjs"
import AppShell from "@/components/AppShell"
import { formatTrigger, timeAgo as runsTimeAgo, duration } from "@/lib/runUtils"

interface Workflow {
  id: string
  name: string
  project_id: string | null
  updated_at: string
  last_run_status: string | null
  last_run_at: string | null
}

interface Project {
  id: string
  name: string
  workspace_id: string
  agent_count: number
}

interface Run {
  id: string
  workflow_id: string
  workflow_name: string
  status: string
  triggered_by: string | null
  started_at: string | null
  completed_at: string | null
  created_at: string
}

function timeAgo(ts: string): string {
  const diff = Date.now() - new Date(ts).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return "just now"
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}

function mapStatus(s: string | null): string {
  if (!s) return "idle"
  const l = s.toLowerCase()
  if (l === "running") return "run"
  if (l === "waiting" || l === "pending" || l === "awaiting") return "wait"
  if (l === "succeeded" || l === "success") return "ok"
  if (l === "failed" || l === "error") return "err"
  if (l === "warn" || l === "degraded") return "warn"
  return "idle"
}

function AgentStatusPill({ s }: { s: string }) {
  const m = ({
    ok: ["ok", "Succeeded"], wait: ["warn", "Awaiting"], run: ["run", "Running"],
    err: ["err", "Failed"], idle: ["idle", "Never run"], warn: ["warn", "Degraded"],
  } as Record<string, [string, string]>)[s] || ["idle", "Never run"]
  return (
    <span className={"sbadge " + m[0]}>
      {(s === "run" || s === "wait") && (
        <span className="dot pulse" style={{ background: m[0] === "warn" ? "var(--warn)" : "var(--info)" }} />
      )}
      {m[1]}
    </span>
  )
}

function RunStatusBadge({ status }: { status: string }) {
  const m = mapStatus(status)
  return <AgentStatusPill s={m} />
}

export default function ProjectPage() {
  const clerkEnabled = !!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY
  if (clerkEnabled) return <ProjectWithAuth />
  return <ProjectContent getToken={null} currentUserId={null} />
}

function ProjectWithAuth() {
  const router = useRouter()
  const { getToken, isLoaded, isSignedIn, userId } = useAuth()
  useEffect(() => {
    if (isLoaded && !isSignedIn) router.replace("/")
  }, [isLoaded, isSignedIn, router])
  if (!isLoaded) return null
  return <ProjectContent getToken={getToken} currentUserId={userId ?? null} />
}

function ProjectContent({ getToken, currentUserId }: {
  getToken: (() => Promise<string | null>) | null
  currentUserId: string | null
}) {
  const { id: projectId } = useParams<{ id: string }>()
  const router = useRouter()
  const clerkEnabled = !!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY
  const [project, setProject] = useState<Project | null>(null)
  const [workflows, setWorkflows] = useState<Workflow[]>([])
  const [loading, setLoading] = useState(true)
  const [isAdmin, setIsAdmin] = useState(!clerkEnabled)
  const [activeTab, setActiveTab] = useState<"Agents" | "Runs">("Agents")
  const [runs, setRuns] = useState<Run[]>([])
  const [runsLoading, setRunsLoading] = useState(false)
  const [runsError, setRunsError] = useState<string | null>(null)
  const [q, setQ] = useState("")
  const [sort, setSort] = useState("recent")
  const [statusFilter, setStatusFilter] = useState("All")
  const [view, setView] = useState<"list" | "grid">(() =>
    typeof window !== "undefined" ? (localStorage.getItem("agents_view") as "list" | "grid") ?? "list" : "list"
  )
  const [menuOpen, setMenuOpen] = useState<string | null>(null)
  const [renaming, setRenaming] = useState<string | null>(null)
  const [renameValue, setRenameValue] = useState("")
  const [confirming, setConfirming] = useState<string | null>(null)
  const [confirmValue, setConfirmValue] = useState("")
  const menuRef = useRef<HTMLDivElement>(null)
  const renameInputRef = useRef<HTMLInputElement>(null)
  const confirmInputRef = useRef<HTMLInputElement>(null)

  async function authHeaders(): Promise<Record<string, string>> {
    const h: Record<string, string> = {}
    if (getToken) {
      const token = await getToken()
      if (token) h["Authorization"] = `Bearer ${token}`
    }
    const wsId = project?.workspace_id || document.cookie.match(/(?:^|;\s*)delegator_project_id=([^;]+)/)?.[1]
    if (wsId) h["X-Workspace-ID"] = wsId
    return h
  }

  useEffect(() => {
    if (!projectId) return
    loadProject()
    loadWorkflows()
  }, [projectId, currentUserId])

  useEffect(() => { if (renaming) renameInputRef.current?.focus() }, [renaming])
  useEffect(() => { if (confirming) confirmInputRef.current?.focus() }, [confirming])
  useEffect(() => {
    function h(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuOpen(null)
    }
    document.addEventListener("mousedown", h)
    return () => document.removeEventListener("mousedown", h)
  }, [])

  async function loadProject() {
    try {
      const h = await authHeaders()
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/projects/${projectId}`, { headers: h })
      if (!res.ok) return
      const found: Project = await res.json()
      setProject(found)
      if (clerkEnabled && currentUserId) {
        const mRes = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/projects/${found.workspace_id}/members`, { headers: h })
        if (mRes.ok) {
          const members: { clerk_user_id: string; role: string }[] = await mRes.json()
          setIsAdmin(members.find(m => m.clerk_user_id === currentUserId)?.role === "admin")
        }
      }
    } catch {}
  }

  async function loadWorkflows() {
    try {
      const h = await authHeaders()
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/workflows?project_id=${projectId}`, { headers: h })
      if (res.ok) setWorkflows(await res.json())
    } finally {
      setLoading(false)
    }
  }

  async function loadRuns() {
    setRunsLoading(true)
    setRunsError(null)
    try {
      const h = await authHeaders()
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/runs?project_id=${projectId}&limit=100`, { headers: h })
      if (res.ok) {
        setRuns(await res.json())
      } else {
        setRuns([])
        setRunsError(res.status === 403 ? "You do not have access to runs for this project." : `Failed to load runs (${res.status}).`)
      }
    } catch {
      setRunsError("Network error while loading runs.")
    } finally {
      setRunsLoading(false)
    }
  }

  function handleTabChange(tab: "Agents" | "Runs") {
    setActiveTab(tab)
    if (tab === "Runs" && runs.length === 0) loadRuns()
  }

  async function renameAgent(id: string, name: string) {
    const h = await authHeaders()
    h["Content-Type"] = "application/json"
    const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/workflows/${id}`, {
      method: "PUT", headers: h, body: JSON.stringify({ name }),
    })
    if (res.ok) {
      const updated = await res.json()
      setWorkflows(prev => prev.map(w => w.id === id ? { ...w, name: updated.name } : w))
    }
  }

  async function deleteAgent(id: string) {
    const h = await authHeaders()
    await fetch(`${process.env.NEXT_PUBLIC_API_URL}/workflows/${id}`, { method: "DELETE", headers: h })
    setWorkflows(prev => prev.filter(w => w.id !== id))
    setConfirming(null)
    setConfirmValue("")
  }

  const filtered = workflows.filter(w => {
    if (!w.name.toLowerCase().includes(q.toLowerCase())) return false
    if (statusFilter !== "All" && mapStatus(w.last_run_status) !== STATUS_KEY[statusFilter]) return false
    return true
  })

  const STATUS_FILTERS = ["All", "Running", "Awaiting", "Succeeded", "Failed", "Never run"]
  const STATUS_KEY: Record<string, string> = { Running: "run", Awaiting: "wait", Succeeded: "ok", Failed: "err", "Never run": "idle" }

  const rows = [...filtered].sort((a, b) => {
    if (sort === "name") return a.name.localeCompare(b.name)
    if (sort === "status") return mapStatus(a.last_run_status).localeCompare(mapStatus(b.last_run_status))
    return new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()
  })

  const AGENT_GRID = "2fr 1.4fr 1fr 64px"
  const AGENT_HEADERS = ["Agent", "Last run", "Success 30d", ""]

  return (
    <AppShell>
      <div style={{ maxWidth: 1200, margin: "0 auto", padding: "30px 34px 80px" }}>

        {/* Breadcrumb */}
        <nav style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: "var(--text-3)", marginBottom: 12 }}>
          <Link href="/projects" style={{ color: "var(--text-3)", textDecoration: "none" }}
            onMouseEnter={e => (e.currentTarget.style.color = "var(--text-2)")}
            onMouseLeave={e => (e.currentTarget.style.color = "var(--text-3)")}
          >Projects</Link>
          <span>/</span>
          <span style={{ color: "var(--text-2)", fontWeight: 500 }}>{project?.name ?? "…"}</span>
        </nav>

        {/* Page header */}
        <div className="page-head" style={{ display: "flex", alignItems: "flex-end" }}>
          <div>
            <h1 className="page-title">{project?.name ?? "Loading…"}</h1>
            <p className="page-sub">{workflows.length} agent{workflows.length !== 1 ? "s" : ""} in this project</p>
          </div>
          <div style={{ marginLeft: "auto", display: "flex", gap: 9 }}>
            <Link href={`/workflows/new?project_id=${projectId}`} className="btn btn-primary" style={{ textDecoration: "none" }}>
              + New agent
            </Link>
          </div>
        </div>

        {/* Tab chips */}
        <div style={{ display: "flex", gap: 7, marginBottom: 16, flexWrap: "wrap" }}>
          {(["Agents", "Runs"] as const).map(tab => {
            const on = activeTab === tab
            return (
              <button
                key={tab}
                onClick={() => handleTabChange(tab)}
                className="chip"
                style={{ height: 30, cursor: "pointer", fontWeight: 600, background: on ? "var(--accent-weak)" : "var(--surface)", borderColor: on ? "var(--accent-ring)" : "var(--border)", color: on ? "var(--accent-text)" : "var(--text-2)" }}
              >
                {tab}
                <span style={{ opacity: .6, marginLeft: 1 }}>· {tab === "Agents" ? workflows.length : runs.length}</span>
              </button>
            )
          })}
        </div>

        {/* ── Agents tab ── */}
        {activeTab === "Agents" && (
          <>
            {/* Toolbar */}
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 14, flexWrap: "wrap" }}>
              <div style={{ position: "relative", flex: 1, minWidth: 220, maxWidth: 340 }}>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" style={{ position: "absolute", left: 11, top: 10, color: "var(--text-muted)" }}>
                  <path d="M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16zm4.15-2.85 3.7 3.7" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                </svg>
                <input
                  value={q}
                  onChange={e => setQ(e.target.value)}
                  placeholder="Search agents…"
                  style={{ width: "100%", height: 36, padding: "0 12px 0 33px", borderRadius: 9, border: "1px solid var(--border)", background: "var(--surface)", color: "var(--text)", fontSize: 13.5, outline: "none" }}
                />
              </div>
              <select
                value={sort}
                onChange={e => setSort(e.target.value)}
                className="btn btn-ghost"
                style={{ height: 36, fontWeight: 600 }}
              >
                <option value="recent">Sort: Recently edited</option>
                <option value="status">Sort: Status</option>
                <option value="name">Sort: Name</option>
              </select>
              <div style={{ marginLeft: "auto", display: "flex", background: "var(--surface-3)", borderRadius: 8, padding: 3 }}>
                {(["list", "grid"] as const).map(v => (
                  <button
                    key={v}
                    onClick={() => { setView(v); localStorage.setItem("agents_view", v) }}
                    style={{ border: "none", background: view === v ? "var(--surface)" : "transparent", borderRadius: 6, padding: "5px 9px", cursor: "pointer", color: view === v ? "var(--text)" : "var(--text-3)", boxShadow: view === v ? "var(--shadow-sm)" : "none" }}
                  >
                    {v === "list" ? (
                      <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><rect x="0" y="1" width="14" height="2" rx="1" fill="currentColor" /><rect x="0" y="6" width="14" height="2" rx="1" fill="currentColor" /><rect x="0" y="11" width="14" height="2" rx="1" fill="currentColor" /></svg>
                    ) : (
                      <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><rect x="0" y="0" width="6" height="6" rx="1" fill="currentColor" /><rect x="8" y="0" width="6" height="6" rx="1" fill="currentColor" /><rect x="0" y="8" width="6" height="6" rx="1" fill="currentColor" /><rect x="8" y="8" width="6" height="6" rx="1" fill="currentColor" /></svg>
                    )}
                  </button>
                ))}
              </div>
            </div>

            {/* Status chips */}
            <div style={{ display: "flex", gap: 7, marginBottom: 16, flexWrap: "wrap" }}>
              {STATUS_FILTERS.map(s => {
                const n = s === "All" ? workflows.length : workflows.filter(w => mapStatus(w.last_run_status) === STATUS_KEY[s]).length
                const on = statusFilter === s
                return (
                  <button
                    key={s}
                    onClick={() => setStatusFilter(s)}
                    className="chip"
                    style={{ height: 30, cursor: "pointer", fontWeight: 600, background: on ? "var(--accent-weak)" : "var(--surface)", borderColor: on ? "var(--accent-ring)" : "var(--border)", color: on ? "var(--accent-text)" : "var(--text-2)" }}
                  >
                    {s}<span style={{ opacity: .6, marginLeft: 1 }}>· {n}</span>
                  </button>
                )
              })}
            </div>

            {loading ? (
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {[1, 2, 3].map(i => <div key={i} style={{ height: 60, borderRadius: 10, border: "1px solid var(--border)", background: "var(--surface)", opacity: 0.5 }} />)}
              </div>
            ) : workflows.length === 0 ? (
              <div style={{ padding: "60px 20px", textAlign: "center" }}>
                <p style={{ fontWeight: 650, fontSize: 16, color: "var(--text)", marginBottom: 8 }}>No agents in this project</p>
                <p style={{ fontSize: 13.5, color: "var(--text-3)", marginBottom: 20 }}>Create a new agent or start from an agent template.</p>
                <div style={{ display: "flex", gap: 10, justifyContent: "center" }}>
                  <Link href={`/workflows/new?project_id=${projectId}`} className="btn btn-primary" style={{ textDecoration: "none" }}>+ New agent</Link>
                  <Link href="/marketplace" className="btn btn-ghost" style={{ textDecoration: "none" }}>Agent templates</Link>
                </div>
              </div>
            ) : view === "list" ? (
              <div className="card" style={{ overflow: "hidden" }}>
                <div style={{ display: "grid", gridTemplateColumns: AGENT_GRID, gap: 14, padding: "10px 18px", borderBottom: "1px solid var(--border)", background: "var(--surface-2)" }}>
                  {AGENT_HEADERS.map((h, i) => (
                    <div key={i} className="eyebrow" style={{ fontSize: 9.5 }}>{h}</div>
                  ))}
                </div>
                {rows.length === 0 && (
                  <div style={{ padding: 40, textAlign: "center", color: "var(--text-muted)", fontSize: 13 }}>No agents match.</div>
                )}
                {rows.map(w => {
                  if (confirming === w.id) {
                    return (
                      <div key={w.id} style={{ padding: "12px 18px", borderBottom: "1px solid var(--border)", background: "var(--err-weak, #fff5f5)" }}>
                        <p style={{ fontSize: 13, color: "var(--err)", marginBottom: 8 }}>
                          Type <strong>{w.name}</strong> to permanently delete this agent.
                        </p>
                        <div style={{ display: "flex", gap: 8 }}>
                          <input
                            ref={confirmInputRef}
                            value={confirmValue}
                            onChange={e => setConfirmValue(e.target.value)}
                            onKeyDown={e => {
                              if (e.key === "Enter" && confirmValue === w.name) deleteAgent(w.id)
                              if (e.key === "Escape") { setConfirming(null); setConfirmValue("") }
                            }}
                            placeholder={w.name}
                            style={{ flex: 1, fontSize: 13, border: "1px solid var(--err, #fca5a5)", borderRadius: 7, padding: "5px 10px", outline: "none", background: "var(--surface)" }}
                          />
                          <button onClick={() => deleteAgent(w.id)} disabled={confirmValue !== w.name} className="btn btn-sm" style={{ background: "var(--err)", color: "#fff", opacity: confirmValue !== w.name ? 0.4 : 1 }}>Delete</button>
                          <button onClick={() => { setConfirming(null); setConfirmValue("") }} className="btn btn-ghost btn-sm">Cancel</button>
                        </div>
                      </div>
                    )
                  }
                  return (
                    <div
                      key={w.id}
                      style={{ display: "grid", gridTemplateColumns: AGENT_GRID, gap: 14, padding: "13px 18px", borderBottom: "1px solid var(--border)", alignItems: "center", cursor: "pointer", transition: "background .12s" }}
                      onClick={() => router.push(`/workflows/${w.id}`)}
                      onMouseEnter={e => (e.currentTarget as HTMLElement).style.background = "var(--surface-2)"}
                      onMouseLeave={e => (e.currentTarget as HTMLElement).style.background = ""}
                    >
                      <div style={{ minWidth: 0 }}>
                        {renaming === w.id ? (
                          <input
                            ref={renameInputRef}
                            value={renameValue}
                            onChange={e => setRenameValue(e.target.value)}
                            onClick={e => e.stopPropagation()}
                            onBlur={() => {
                              const name = renameValue.trim()
                              if (name && name !== w.name) renameAgent(w.id, name)
                              setRenaming(null); setRenameValue("")
                            }}
                            onKeyDown={e => {
                              e.stopPropagation()
                              if (e.key === "Enter") { const name = renameValue.trim(); if (name && name !== w.name) renameAgent(w.id, name); setRenaming(null); setRenameValue("") }
                              if (e.key === "Escape") { setRenaming(null); setRenameValue("") }
                            }}
                            style={{ fontWeight: 650, fontSize: 14, background: "transparent", border: "none", borderBottom: "1px solid var(--accent)", outline: "none", width: "100%" }}
                          />
                        ) : (
                          <div style={{ fontWeight: 650, fontSize: 14, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{w.name}</div>
                        )}
                        <div className="mono" style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 3 }}>edited {timeAgo(w.updated_at)}</div>
                      </div>
                      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <AgentStatusPill s={mapStatus(w.last_run_status)} />
                        <span style={{ fontSize: 11.5, color: "var(--text-muted)" }}>{w.last_run_at ? timeAgo(w.last_run_at) : ""}</span>
                      </div>
                      <span style={{ fontSize: 12, color: "var(--text-muted)" }}>—</span>
                      <div style={{ display: "flex", gap: 4, justifyContent: "flex-end" }} ref={menuRef}>
                        <button
                          className="btn btn-ghost btn-sm"
                          style={{ fontSize: 11, padding: "3px 9px" }}
                          title="View runs"
                          onClick={e => { e.stopPropagation(); router.push(`/workflows/${w.id}/runs`) }}
                        >Runs</button>
                        <button
                          className="btn btn-ghost btn-icon btn-sm"
                          title="Open canvas"
                          onClick={e => { e.stopPropagation(); router.push(`/workflows/${w.id}`) }}
                        >→</button>
                        {isAdmin && (
                          <div style={{ position: "relative" }}>
                            <button
                              className="btn btn-ghost btn-icon btn-sm"
                              title="More"
                              onClick={e => { e.stopPropagation(); setMenuOpen(menuOpen === w.id ? null : w.id) }}
                            >⋯</button>
                            {menuOpen === w.id && (
                              <div
                                onMouseDown={e => e.stopPropagation()}
                                style={{ position: "absolute", right: 0, top: "100%", marginTop: 4, zIndex: 20, minWidth: 130, background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 10, boxShadow: "var(--shadow-md)", padding: "4px 0" }}
                              >
                                <button onClick={e => { e.stopPropagation(); setMenuOpen(null); setRenaming(w.id); setRenameValue(w.name) }} style={{ width: "100%", textAlign: "left", padding: "7px 14px", fontSize: 13, color: "var(--text)", background: "none", border: "none", cursor: "pointer" }} onMouseEnter={e => (e.currentTarget as HTMLElement).style.background = "var(--surface-2)"} onMouseLeave={e => (e.currentTarget as HTMLElement).style.background = "none"}>Rename</button>
                                <button onMouseDown={e => { e.stopPropagation(); setMenuOpen(null); setConfirming(w.id); setConfirmValue("") }} style={{ width: "100%", textAlign: "left", padding: "7px 14px", fontSize: 13, color: "var(--err)", background: "none", border: "none", cursor: "pointer" }} onMouseEnter={e => (e.currentTarget as HTMLElement).style.background = "var(--surface-2)"} onMouseLeave={e => (e.currentTarget as HTMLElement).style.background = "none"}>Delete</button>
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    </div>
                  )
                })}
              </div>
            ) : (
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))", gap: 14 }}>
                {rows.map(w => (
                  <div
                    key={w.id}
                    onClick={() => router.push(`/workflows/${w.id}`)}
                    className="card"
                    style={{ padding: "16px 18px", cursor: "pointer" }}
                    onMouseEnter={e => { (e.currentTarget as HTMLElement).style.boxShadow = "var(--shadow-md)"; (e.currentTarget as HTMLElement).style.borderColor = "var(--border-2)" }}
                    onMouseLeave={e => { (e.currentTarget as HTMLElement).style.boxShadow = ""; (e.currentTarget as HTMLElement).style.borderColor = "var(--border)" }}
                  >
                    <div style={{ marginBottom: 12 }}>
                      <div style={{ fontWeight: 650, fontSize: 15, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{w.name}</div>
                      <div className="mono" style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 2 }}>edited {timeAgo(w.updated_at)}</div>
                    </div>
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", paddingTop: 12, borderTop: "1px solid var(--border)" }}>
                      <AgentStatusPill s={mapStatus(w.last_run_status)} />
                      <span style={{ fontSize: 12, color: "var(--text-muted)" }}>{w.last_run_at ? timeAgo(w.last_run_at) : "—"}</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </>
        )}

        {/* ── Runs tab ── */}
        {activeTab === "Runs" && (
          runsLoading ? (
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {[1, 2, 3].map(i => <div key={i} style={{ height: 56, borderRadius: 10, border: "1px solid var(--border)", background: "var(--surface)", opacity: 0.5 }} />)}
            </div>
          ) : runsError ? (
            <div style={{ border: "1px solid var(--err-bd, #fecaca)", borderRadius: 12, padding: 24, background: "var(--err-bg, #fff5f5)" }}>
              <p style={{ color: "var(--err)", fontSize: 13.5, marginBottom: 10 }}>{runsError}</p>
              <button onClick={loadRuns} className="btn btn-ghost btn-sm" style={{ color: "var(--err)", borderColor: "var(--err-bd, #fecaca)" }}>Retry</button>
            </div>
          ) : runs.length === 0 ? (
            <div style={{ padding: "60px 20px", textAlign: "center" }}>
              <p style={{ fontWeight: 650, fontSize: 16, color: "var(--text)", marginBottom: 8 }}>No runs yet</p>
              <p style={{ fontSize: 13.5, color: "var(--text-3)" }}>Trigger a run from any agent in this project.</p>
            </div>
          ) : (
            <div className="card" style={{ overflow: "hidden" }}>
              <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr 1.2fr 0.7fr 0.7fr", gap: 14, padding: "10px 18px", borderBottom: "1px solid var(--border)", background: "var(--surface-2)" }}>
                {["Agent", "Trigger", "Status", "Duration", "When"].map((h, i) => (
                  <div key={i} className="eyebrow" style={{ fontSize: 9.5 }}>{h}</div>
                ))}
              </div>
              {runs.map((run, idx) => (
                <div
                  key={run.id}
                  style={{ display: "grid", gridTemplateColumns: "2fr 1fr 1.2fr 0.7fr 0.7fr", gap: 14, padding: "13px 18px", borderBottom: idx < runs.length - 1 ? "1px solid var(--border)" : "none", alignItems: "center", cursor: "pointer", transition: "background .12s" }}
                  onClick={() => router.push(`/workflows/${run.workflow_id}/runs/${run.id}`)}
                  onMouseEnter={e => (e.currentTarget as HTMLElement).style.background = "var(--surface-2)"}
                  onMouseLeave={e => (e.currentTarget as HTMLElement).style.background = ""}
                >
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontWeight: 650, fontSize: 14, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{run.workflow_name}</div>
                    <div className="mono" style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 3 }}>{runsTimeAgo(run.created_at)}</div>
                  </div>
                  <div className="mono" style={{ fontSize: 12, color: "var(--text-3)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{formatTrigger(run.triggered_by)}</div>
                  <RunStatusBadge status={run.status} />
                  <div className="mono" style={{ fontSize: 12, color: "var(--text-3)" }}>{duration(run.started_at, run.completed_at)}</div>
                  <div style={{ fontSize: 12, color: "var(--text-muted)" }}>{runsTimeAgo(run.started_at ?? run.created_at)}</div>
                </div>
              ))}
            </div>
          )
        )}
      </div>
    </AppShell>
  )
}
