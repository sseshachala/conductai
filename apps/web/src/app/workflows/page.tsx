"use client"

import { useEffect, useRef, useState } from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { useAuth } from "@clerk/nextjs"
import AppShell from "@/components/AppShell"

interface Workflow {
  id: string
  name: string
  workspace_id: string
  updated_at: string
  last_run_status: string | null
  last_run_at: string | null
  project_name: string | null
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

function getActiveProject(): { id: string; name: string } | null {
  if (typeof document === "undefined") return null
  const idMatch = document.cookie.match(/(?:^|;\s*)delegator_project_id=([^;]+)/)
  if (!idMatch) return null
  const nameMatch = document.cookie.match(/(?:^|;\s*)delegator_project_name=([^;]+)/)
  return { id: idMatch[1], name: nameMatch ? decodeURIComponent(nameMatch[1]) : "Project" }
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

function statusKey(label: string): string {
  return ({ Running: "run", Awaiting: "wait", Succeeded: "ok", Failed: "err", "Never run": "idle" } as Record<string, string>)[label] ?? "idle"
}

function AgentStatusPill({ s }: { s: string }) {
  const m = ({ ok: ["ok", "Succeeded"], wait: ["warn", "Awaiting approval"], run: ["run", "Running"], err: ["err", "Failed"], idle: ["idle", "Never run"], warn: ["warn", "Degraded"] } as Record<string, [string, string]>)[s] || ["idle", "Never run"]
  return (
    <span className={"sbadge " + m[0]}>
      {(s === "run" || s === "wait") && (
        <span className="dot pulse" style={{ background: m[0] === "warn" ? "var(--warn)" : "var(--info)" }} />
      )}
      {m[1]}
    </span>
  )
}

function MiniSpark({ pct, runs }: { pct: number; runs: number }) {
  if (runs === 0) return <span style={{ fontSize: 12, color: "var(--text-muted)" }}>—</span>
  const c = pct >= 0.9 ? "var(--ok)" : pct >= 0.75 ? "var(--info)" : pct >= 0.5 ? "var(--warn)" : "var(--err)"
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
      <div style={{ width: 64, height: 6, borderRadius: 6, background: "var(--surface-3)", overflow: "hidden" }}>
        <div style={{ width: `${pct * 100}%`, height: "100%", borderRadius: 6, background: c }} />
      </div>
      <span className="mono" style={{ fontSize: 12, color: "var(--text-3)", width: 30, textAlign: "right" }}>{Math.round(pct * 100)}%</span>
    </div>
  )
}

const Toggle = ({ on, onClick }: { on: boolean; onClick: () => void }) => (
  <span
    onClick={(e) => { e.stopPropagation(); onClick() }}
    style={{ width: 36, height: 21, borderRadius: 20, background: on ? "var(--accent)" : "var(--border-2)", position: "relative", cursor: "pointer", flexShrink: 0, transition: "background .15s", display: "inline-block" }}
  >
    <span style={{ position: "absolute", top: 2.5, left: on ? 17.5 : 2.5, width: 16, height: 16, borderRadius: "50%", background: "#fff", transition: "left .15s", boxShadow: "var(--shadow-sm)" }} />
  </span>
)

export default function WorkflowsPage() {
  const clerkEnabled = !!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY
  if (clerkEnabled) return <WorkflowsWithAuth />
  return <WorkflowsContent getToken={null} currentUserId={null} />
}

function WorkflowsWithAuth() {
  const router = useRouter()
  const { getToken, isLoaded, isSignedIn, userId } = useAuth()

  useEffect(() => {
    if (isLoaded && !isSignedIn) router.replace("/")
  }, [isLoaded, isSignedIn, router])

  if (!isLoaded) return null
  return <WorkflowsContent getToken={getToken} currentUserId={userId ?? null} />
}

function WorkflowsContent({ getToken, currentUserId }: { getToken: (() => Promise<string | null>) | null; currentUserId: string | null }) {
  const clerkEnabled = !!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY
  const router = useRouter()
  const [workflows, setWorkflows] = useState<Workflow[]>([])
  const [project, setProject] = useState<{ id: string; name: string } | null>(null)
  const [loading, setLoading] = useState(true)
  const [isAdmin, setIsAdmin] = useState(!clerkEnabled)
  const [q, setQ] = useState("")
  const [status, setStatus] = useState("All")
  const [sort, setSort] = useState("recent")
  const [view, setView] = useState<"list" | "grid">("list")
  const [enabled, setEnabled] = useState<Record<string, boolean>>({})
  const [confirming, setConfirming] = useState<string | null>(null)
  const [confirmValue, setConfirmValue] = useState("")
  const [menuOpen, setMenuOpen] = useState<string | null>(null)
  const [renaming, setRenaming] = useState<string | null>(null)
  const [renameValue, setRenameValue] = useState("")
  const menuRef = useRef<HTMLDivElement>(null)
  const confirmInputRef = useRef<HTMLInputElement>(null)
  const renameInputRef = useRef<HTMLInputElement>(null)
  const [runModal, setRunModal] = useState<{ id: string; name: string } | null>(null)
  const [runParams, setRunParams] = useState("")
  const [runDryRun, setRunDryRun] = useState(false)
  const [runGuard, setRunGuard] = useState(true)
  const [runLoading, setRunLoading] = useState(false)
  const [runError, setRunError] = useState<string | null>(null)

  async function authHeaders(): Promise<Record<string, string>> {
    const h: Record<string, string> = {}
    if (getToken) {
      const token = await getToken()
      if (token) h["Authorization"] = `Bearer ${token}`
    }
    return h
  }

  useEffect(() => {
    const p = getActiveProject()
    setProject(p)
    loadWorkflows(p?.id ?? null)
    if (clerkEnabled && p?.id && currentUserId) loadRole(p.id)
  }, [currentUserId])

  useEffect(() => {
    if (confirming !== null) confirmInputRef.current?.focus()
  }, [confirming])

  useEffect(() => {
    if (renaming !== null) renameInputRef.current?.focus()
  }, [renaming])

  useEffect(() => {
    function handleEsc(e: KeyboardEvent) { if (e.key === "Escape") setRunModal(null) }
    document.addEventListener("keydown", handleEsc)
    return () => document.removeEventListener("keydown", handleEsc)
  }, [])

  async function runWorkflow() {
    if (!runModal) return
    setRunLoading(true)
    setRunError(null)
    const initial_state: Record<string, string> = {}
    for (const line of runParams.split("\n")) {
      const idx = line.indexOf("=")
      if (idx > 0) initial_state[line.slice(0, idx).trim()] = line.slice(idx + 1).trim()
    }
    try {
      const h = await authHeaders()
      h["Content-Type"] = "application/json"
      if (project?.id) h["X-Workspace-ID"] = project.id
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/workflows/${runModal.id}/runs`, {
        method: "POST",
        headers: h,
        body: JSON.stringify({ triggered_by: "manual", dry_run: runDryRun, guard_enabled: runGuard, initial_state }),
      })
      if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail ?? "Failed to start run") }
      setRunModal(null)
      router.push(`/workflows/${runModal.id}/runs`)
    } catch (err) {
      setRunError(err instanceof Error ? err.message : "Failed to start run")
    } finally {
      setRunLoading(false)
    }
  }

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuOpen(null)
    }
    document.addEventListener("mousedown", handleClick)
    return () => document.removeEventListener("mousedown", handleClick)
  }, [])

  async function loadRole(projectId: string) {
    try {
      const h = await authHeaders()
      h["X-Workspace-Id"] = projectId
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/projects/${projectId}/members`, { headers: h })
      if (!res.ok) return
      const members: { clerk_user_id: string; role: string }[] = await res.json()
      setIsAdmin(members.find(m => m.clerk_user_id === currentUserId)?.role === "admin")
    } catch { }
  }

  async function loadWorkflows(pid: string | null) {
    try {
      const headers = await authHeaders()
      if (pid) headers["X-Workspace-ID"] = pid
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/workflows`, { headers })
      if (res.ok) {
        const data: Workflow[] = await res.json()
        setWorkflows(data)
        const init: Record<string, boolean> = {}
        data.forEach(w => { init[w.id] = true })
        setEnabled(init)
      }
    } finally {
      setLoading(false)
    }
  }

  async function renameAgent(id: string, name: string) {
    const h = await authHeaders()
    h["Content-Type"] = "application/json"
    const wf = workflows.find(w => w.id === id)
    const wsId = project?.id ?? wf?.workspace_id
    if (wsId) h["X-Workspace-ID"] = wsId
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
    const wf = workflows.find(w => w.id === id)
    const wsId = project?.id ?? wf?.workspace_id
    const qParam = wsId ? `?workspace_id=${wsId}` : ""
    const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/workflows/${id}${qParam}`, { method: "DELETE", headers: h })
    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      alert(body.detail ?? `Delete failed (${res.status})`)
      return
    }
    setWorkflows(prev => prev.filter(w => w.id !== id))
    setConfirming(null)
    setConfirmValue("")
  }

  const filtered = workflows.filter(w => {
    const matchQ = w.name.toLowerCase().includes(q.toLowerCase())
    const matchStatus = status === "All" || mapStatus(w.last_run_status) === statusKey(status)
    return matchQ && matchStatus
  })

  const rows = [...filtered].sort((a, b) => {
    if (sort === "name") return a.name.localeCompare(b.name)
    if (sort === "status") return mapStatus(a.last_run_status).localeCompare(mapStatus(b.last_run_status))
    return new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()
  })

  return (
    <AppShell>
      <div style={{ maxWidth: 1200, margin: "0 auto", padding: "30px 34px 80px" }}>

        <div className="page-head" style={{ display: "flex", alignItems: "flex-end" }}>
          <div>
            <h1 className="page-title">Agents</h1>
            <p className="page-sub">Every workflow in this workspace — status, triggers, and 30-day reliability at a glance.</p>
          </div>
          <div style={{ marginLeft: "auto", display: "flex", gap: 9 }}>
            <Link href="/workflows/new" className="btn btn-primary"><span>+</span> New agent</Link>
          </div>
        </div>

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
                onClick={() => setView(v)}
                style={{ border: "none", background: view === v ? "var(--surface)" : "transparent", borderRadius: 6, padding: "5px 9px", cursor: "pointer", color: view === v ? "var(--text)" : "var(--text-3)", boxShadow: view === v ? "var(--shadow-sm)" : "none" }}
              >
                {v === "list" ? (
                  <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                    <rect x="0" y="1" width="14" height="2" rx="1" fill="currentColor" />
                    <rect x="0" y="6" width="14" height="2" rx="1" fill="currentColor" />
                    <rect x="0" y="11" width="14" height="2" rx="1" fill="currentColor" />
                  </svg>
                ) : (
                  <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                    <rect x="0" y="0" width="6" height="6" rx="1" fill="currentColor" />
                    <rect x="8" y="0" width="6" height="6" rx="1" fill="currentColor" />
                    <rect x="0" y="8" width="6" height="6" rx="1" fill="currentColor" />
                    <rect x="8" y="8" width="6" height="6" rx="1" fill="currentColor" />
                  </svg>
                )}
              </button>
            ))}
          </div>
        </div>

        <div style={{ display: "flex", gap: 7, marginBottom: 16, flexWrap: "wrap" }}>
          {["All", "Running", "Awaiting", "Succeeded", "Failed", "Never run"].map(s => {
            const n = s === "All" ? workflows.length : workflows.filter(w => mapStatus(w.last_run_status) === statusKey(s)).length
            const on = status === s
            return (
              <button
                key={s}
                onClick={() => setStatus(s)}
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
            {[1, 2, 3].map(i => (
              <div key={i} style={{ height: 60, borderRadius: 10, border: "1px solid var(--border)", background: "var(--surface)", opacity: 0.5 }} />
            ))}
          </div>
        ) : !loading && workflows.length === 0 ? (
          <div style={{ padding: "60px 20px", textAlign: "center" }}>
            <p style={{ fontWeight: 650, fontSize: 16, color: "var(--text)", marginBottom: 8 }}>No agents yet</p>
            <p style={{ fontSize: 13.5, color: "var(--text-3)", marginBottom: 20 }}>Pick a playbook template to create your first agent.</p>
            <Link href="/workflows/new" className="btn btn-primary">+ New agent</Link>
          </div>
        ) : (
          <>
            {view === "list" && (
              <div className="card" style={{ overflow: "hidden" }}>
                <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr 1.2fr 1.1fr 64px", gap: 14, padding: "10px 18px", borderBottom: "1px solid var(--border)", background: "var(--surface-2)" }}>
                  {["Agent", "Project", "Last run", "Success 30d", ""].map((h, i) => (
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
                        <p style={{ fontSize: 13, color: "var(--err, #dc2626)", marginBottom: 8 }}>
                          Type <strong>{w.name}</strong> to permanently delete this agent and all its data.
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
                          <button
                            onClick={() => deleteAgent(w.id)}
                            disabled={confirmValue !== w.name}
                            className="btn btn-sm"
                            style={{ background: "var(--err, #dc2626)", color: "#fff", opacity: confirmValue !== w.name ? 0.4 : 1, cursor: confirmValue !== w.name ? "not-allowed" : "pointer" }}
                          >Delete</button>
                          <button
                            onClick={() => { setConfirming(null); setConfirmValue("") }}
                            className="btn btn-ghost btn-sm"
                          >Cancel</button>
                        </div>
                      </div>
                    )
                  }
                  return (
                    <div
                      key={w.id}
                      style={{ display: "grid", gridTemplateColumns: "2fr 1fr 1.2fr 1.1fr 64px", gap: 14, padding: "13px 18px", borderBottom: "1px solid var(--border)", alignItems: "center", cursor: "pointer", transition: "background .12s" }}
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
                              setRenaming(null)
                              setRenameValue("")
                            }}
                            onKeyDown={e => {
                              e.stopPropagation()
                              if (e.key === "Enter") {
                                const name = renameValue.trim()
                                if (name && name !== w.name) renameAgent(w.id, name)
                                setRenaming(null)
                                setRenameValue("")
                              }
                              if (e.key === "Escape") { setRenaming(null); setRenameValue("") }
                            }}
                            style={{ fontWeight: 650, fontSize: 14, background: "transparent", border: "none", borderBottom: "1px solid var(--accent)", outline: "none", width: "100%" }}
                          />
                        ) : (
                          <div style={{ fontWeight: 650, fontSize: 14, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{w.name}</div>
                        )}
                        <div className="mono" style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 3 }}>edited {timeAgo(w.updated_at)}</div>
                      </div>
                      <div style={{ fontSize: 12, color: "var(--text-3)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                        {w.project_name ?? <span style={{ color: "var(--text-muted)" }}>—</span>}
                      </div>
                      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <AgentStatusPill s={mapStatus(w.last_run_status)} />
                        <span style={{ fontSize: 11.5, color: "var(--text-muted)" }}>{w.last_run_at ? timeAgo(w.last_run_at) : ""}</span>
                      </div>
                      <MiniSpark pct={0} runs={0} />
                      <div style={{ display: "flex", gap: 4, justifyContent: "flex-end", position: "relative" }}>
                        <button
                          className="btn btn-ghost btn-sm"
                          title="Trigger a manual run of this agent"
                          style={{ fontSize: 11, padding: "3px 9px" }}
                          onClick={e => { e.stopPropagation(); setRunParams(""); setRunDryRun(false); setRunGuard(true); setRunError(null); setRunModal({ id: w.id, name: w.name }) }}
                        >Run</button>
                        <button
                          className="btn btn-ghost btn-icon btn-sm"
                          title="Open"
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
                                <button
                                  onClick={e => { e.stopPropagation(); setMenuOpen(null); setRenaming(w.id); setRenameValue(w.name) }}
                                  style={{ width: "100%", textAlign: "left", padding: "7px 14px", fontSize: 13, color: "var(--text)", background: "none", border: "none", cursor: "pointer" }}
                                  onMouseEnter={e => (e.currentTarget as HTMLElement).style.background = "var(--surface-2)"}
                                  onMouseLeave={e => (e.currentTarget as HTMLElement).style.background = "none"}
                                >Rename</button>
                                <button
                                  onMouseDown={e => { e.stopPropagation(); setMenuOpen(null); setConfirming(w.id); setConfirmValue("") }}
                                  style={{ width: "100%", textAlign: "left", padding: "7px 14px", fontSize: 13, color: "var(--err, #dc2626)", background: "none", border: "none", cursor: "pointer" }}
                                  onMouseEnter={e => (e.currentTarget as HTMLElement).style.background = "var(--surface-2)"}
                                  onMouseLeave={e => (e.currentTarget as HTMLElement).style.background = "none"}
                                >Delete</button>
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    </div>
                  )
                })}
              </div>
            )}

            {view === "grid" && (
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))", gap: 14 }}>
                {rows.map(w => (
                  <div
                    key={w.id}
                    onClick={() => router.push(`/workflows/${w.id}`)}
                    className="card"
                    style={{ padding: "16px 18px", cursor: "pointer", opacity: enabled[w.id] ? 1 : .65 }}
                    onMouseEnter={e => { (e.currentTarget as HTMLElement).style.boxShadow = "var(--shadow-md)"; (e.currentTarget as HTMLElement).style.borderColor = "var(--border-2)" }}
                    onMouseLeave={e => { (e.currentTarget as HTMLElement).style.boxShadow = ""; (e.currentTarget as HTMLElement).style.borderColor = "var(--border)" }}
                  >
                    <div style={{ display: "flex", alignItems: "flex-start", gap: 10, marginBottom: 12 }}>
                      <div style={{ minWidth: 0, flex: 1 }}>
                        <div style={{ fontWeight: 650, fontSize: 15, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{w.name}</div>
                        <div className="mono" style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 2 }}>edited {timeAgo(w.updated_at)}</div>
                      </div>
                      <Toggle on={!!enabled[w.id]} onClick={() => setEnabled(s => ({ ...s, [w.id]: !s[w.id] }))} />
                    </div>
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", paddingTop: 12, borderTop: "1px solid var(--border)" }}>
                      <AgentStatusPill s={mapStatus(w.last_run_status)} />
                      <MiniSpark pct={0} runs={0} />
                    </div>
                  </div>
                ))}
              </div>
            )}
          </>
        )}

      </div>

      {/* Run modal */}
      {runModal && (
        <div
          style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.45)", zIndex: 1000, display: "flex", alignItems: "center", justifyContent: "center" }}
          onClick={() => setRunModal(null)}
        >
          <div
            style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 12, boxShadow: "var(--shadow-lg)", padding: 24, width: 440, maxWidth: "90vw" }}
            onClick={e => e.stopPropagation()}
          >
            <div style={{ fontWeight: 650, fontSize: 15, marginBottom: 16 }}>Run — {runModal.name}</div>

            <div style={{ marginBottom: 14 }}>
              <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 6 }}>Parameters (optional)</div>
              <textarea
                rows={4}
                value={runParams}
                onChange={e => setRunParams(e.target.value)}
                placeholder={"MODEL=claude-sonnet-4-6\nBRANCH=main"}
                style={{ width: "100%", fontSize: 12.5, fontFamily: "var(--font-mono, monospace)", border: "1px solid var(--border)", borderRadius: 8, padding: "8px 12px", background: "var(--surface-2)", color: "var(--text)", resize: "vertical", boxSizing: "border-box" }}
              />
              <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 4 }}>One KEY=VALUE per line</div>
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 20 }}>
              <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, cursor: "pointer" }}>
                <input type="checkbox" checked={runGuard} onChange={e => setRunGuard(e.target.checked)} />
                Enable Guard
              </label>
              <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, cursor: "pointer" }}>
                <input type="checkbox" checked={runDryRun} onChange={e => setRunDryRun(e.target.checked)} />
                Dry run (simulate without executing)
              </label>
            </div>

            {runError && <div style={{ fontSize: 12, color: "var(--err)", marginBottom: 12 }}>{runError}</div>}

            <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
              <button className="btn btn-ghost" onClick={() => setRunModal(null)}>Cancel</button>
              <button className="btn btn-primary" onClick={runWorkflow} disabled={runLoading}>
                {runLoading ? "Starting…" : "Run now"}
              </button>
            </div>
          </div>
        </div>
      )}
    </AppShell>
  )
}
