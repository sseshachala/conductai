"use client"

import { useEffect, useRef, useState } from "react"
import Link from "next/link"
import { useParams, useRouter } from "next/navigation"
import { useAuth } from "@clerk/nextjs"
import AppShell from "@/components/AppShell"
import { statusStyle, formatTrigger, timeAgo as runsTimeAgo, duration } from "@/lib/runUtils"

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
  const clerkEnabled = !!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY
  const [project, setProject] = useState<Project | null>(null)
  const [workflows, setWorkflows] = useState<Workflow[]>([])
  const [loading, setLoading] = useState(true)
  const [isAdmin, setIsAdmin] = useState(!clerkEnabled)
  const [activeTab, setActiveTab] = useState<"Agents" | "Runs">("Agents")
  const [runs, setRuns] = useState<Run[]>([])
  const [runsLoading, setRunsLoading] = useState(false)
  const [runsError, setRunsError] = useState<string | null>(null)

  async function authHeaders(): Promise<Record<string, string>> {
    const h: Record<string, string> = {}
    if (getToken) {
      const token = await getToken()
      if (token) h["Authorization"] = `Bearer ${token}`
    }
    // Prefer the project's workspace ID so cross-workspace project pages load correctly.
    const wsId = project?.workspace_id || document.cookie.match(/(?:^|;\s*)delegator_project_id=([^;]+)/)?.[1]
    if (wsId) h["X-Workspace-ID"] = wsId
    return h
  }

  useEffect(() => {
    if (!projectId) return
    loadProject()
    loadWorkflows()
  }, [projectId, currentUserId])

  async function loadProject() {
    try {
      const h = await authHeaders()
      // Fetch project directly — workspace is derived server-side from the project ID.
      // This works correctly regardless of which workspace the cookie currently points to.
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/projects/${projectId}`,
        { headers: h }
      )
      if (!res.ok) return
      const found: Project = await res.json()
      setProject(found)

      if (clerkEnabled && currentUserId) {
        const mRes = await fetch(
          `${process.env.NEXT_PUBLIC_API_URL}/projects/${found.workspace_id}/members`,
          { headers: h }
        )
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
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/workflows?project_id=${projectId}`,
        { headers: h }
      )
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
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/runs?project_id=${projectId}&limit=100`,
        { headers: h }
      )
      if (res.ok) {
        setRuns(await res.json())
      } else {
        setRuns([])
        if (res.status === 403) {
          setRunsError("You do not have access to runs for this project in the selected workspace.")
        } else if (res.status === 404) {
          setRunsError("Runs endpoint not found.")
        } else {
          setRunsError(`Failed to load runs (${res.status}).`)
        }
      }
    } catch {
      setRuns([])
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
  }

  return (
    <AppShell>
      <div style={{ maxWidth: 840, margin: "0 auto", padding: "32px 24px" }}>
        {/* Breadcrumb */}
        <nav style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: "var(--text-3)", marginBottom: 16 }}>
          <Link href="/projects" style={{ color: "var(--text-3)", textDecoration: "none" }}>Projects</Link>
          <span>/</span>
          <span style={{ color: "var(--text-2)", fontWeight: 500 }}>{project?.name ?? "…"}</span>
        </nav>

        {/* Header */}
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 24 }}>
          <div>
            <h1 className="page-title" style={{ fontSize: 22, marginBottom: 4 }}>{project?.name ?? "Loading..."}</h1>
            <p style={{ fontSize: 12.5, color: "var(--text-muted)" }}>{workflows.length} agent{workflows.length !== 1 ? "s" : ""}</p>
          </div>
          <Link
            href={`/workflows/new?project_id=${projectId}`}
            className="btn btn-primary btn-sm"
            style={{ textDecoration: "none", display: "inline-flex", alignItems: "center", gap: 6 }}
          >
            + New agent
          </Link>
        </div>

        {/* Tabs */}
        <div style={{ display: "flex", gap: 4, borderBottom: "1px solid var(--border)", marginBottom: 24 }}>
          {(["Agents", "Runs"] as const).map(tab => (
            <button
              key={tab}
              onClick={() => handleTabChange(tab)}
              style={{
                background: "none",
                border: "none",
                padding: "9px 14px",
                fontSize: 13.5,
                fontWeight: activeTab === tab ? 600 : 500,
                cursor: "pointer",
                marginBottom: -1,
                color: activeTab === tab ? "var(--text)" : "var(--text-3)",
                borderBottom: `2px solid ${activeTab === tab ? "var(--accent)" : "transparent"}`,
              }}
            >
              {tab}
            </button>
          ))}
        </div>

        {/* Runs tab */}
        {activeTab === "Runs" && (
          runsLoading ? (
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {[1,2,3].map(i => <div key={i} style={{ height: 56, borderRadius: 12, border: "1px solid var(--border)", background: "var(--surface-2)", opacity: 0.6 }} />)}
            </div>
          ) : runsError ? (
            <div style={{ border: "1px solid var(--err-bd, #fecaca)", borderRadius: 14, padding: "24px", background: "var(--err-bg, #fff5f5)" }}>
              <p style={{ color: "var(--err, #dc2626)", fontSize: 13.5, marginBottom: 10 }}>{runsError}</p>
              <button
                onClick={loadRuns}
                className="btn btn-ghost btn-sm"
                style={{ color: "var(--err, #dc2626)", borderColor: "var(--err-bd, #fecaca)" }}
              >
                Retry
              </button>
            </div>
          ) : runs.length === 0 ? (
            <div style={{ border: "1.5px dashed var(--border)", borderRadius: 14, padding: "48px 32px", textAlign: "center" }}>
              <p style={{ color: "var(--text-muted)", fontSize: 13.5 }}>No runs yet for this project.</p>
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {runs.map(run => {
                const sKey = run.status === "running" ? "run" : run.status === "succeeded" ? "ok" : run.status === "failed" ? "err" : run.status === "paused" ? "warn" : "idle"
                return (
                  <Link
                    key={run.id}
                    href={`/workflows/${run.workflow_id}/runs/${run.id}`}
                    className="card"
                    style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "12px 18px", textDecoration: "none", color: "inherit", gap: 12 }}
                  >
                    <div style={{ minWidth: 0, flex: 1 }}>
                      <p style={{ fontSize: 13.5, fontWeight: 600, color: "var(--text)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{run.workflow_name}</p>
                      <p style={{ fontSize: 11.5, color: "var(--text-muted)", marginTop: 2 }}>{formatTrigger(run.triggered_by)}</p>
                    </div>
                    <div style={{ display: "flex", alignItems: "center", gap: 10, flexShrink: 0 }}>
                      <span className={`sbadge ${sKey}`}>{run.status}</span>
                      <span style={{ fontSize: 11.5, color: "var(--text-muted)" }}>{runsTimeAgo(run.created_at)}</span>
                      {(run.started_at || run.completed_at) && (
                        <span style={{ fontSize: 11.5, color: "var(--text-3)" }}>{duration(run.started_at, run.completed_at)}</span>
                      )}
                    </div>
                  </Link>
                )
              })}
            </div>
          )
        )}

        {/* Agents list */}
        {activeTab === "Agents" && (loading ? (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {[1, 2, 3].map(i => (
              <div key={i} style={{ height: 72, borderRadius: 12, border: "1px solid var(--border)", background: "var(--surface-2)", opacity: 0.6 }} />
            ))}
          </div>
        ) : workflows.length === 0 ? (
          <div style={{ border: "1.5px dashed var(--border)", borderRadius: 14, padding: "48px 32px", textAlign: "center" }}>
            <p style={{ fontSize: 14, fontWeight: 600, color: "var(--text)", marginBottom: 8 }}>No agents in this project</p>
            <p style={{ fontSize: 13, color: "var(--text-muted)", marginBottom: 24 }}>Create your first agent or install a playbook.</p>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 10 }}>
              <Link href={`/workflows/new?project_id=${projectId}`} className="btn btn-primary btn-sm" style={{ textDecoration: "none" }}>
                Create agent →
              </Link>
              <Link href="/marketplace" className="btn btn-ghost btn-sm" style={{ textDecoration: "none" }}>
                Browse playbooks
              </Link>
            </div>
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {workflows.map(w => (
              <AgentCard
                key={w.id}
                workflow={w}
                isAdmin={isAdmin}
                onRename={name => renameAgent(w.id, name)}
                onDelete={() => deleteAgent(w.id)}
              />
            ))}
          </div>
        ))}
      </div>
    </AppShell>
  )
}

function AgentCard({ workflow, isAdmin, onRename, onDelete }: {
  workflow: Workflow
  isAdmin: boolean
  onRename: (name: string) => Promise<void>
  onDelete: () => Promise<void>
}) {
  const [menuOpen, setMenuOpen] = useState(false)
  const [renaming, setRenaming] = useState(false)
  const [nameValue, setNameValue] = useState(workflow.name)
  const [confirmValue, setConfirmValue] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const confirmInputRef = useRef<HTMLInputElement>(null)
  const menuRef = useRef<HTMLDivElement>(null)

  useEffect(() => { if (renaming) inputRef.current?.focus() }, [renaming])

  useEffect(() => { if (confirmValue !== null) confirmInputRef.current?.focus() }, [confirmValue])

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuOpen(false)
    }
    document.addEventListener("mousedown", handleClick)
    return () => document.removeEventListener("mousedown", handleClick)
  }, [])

  async function submitRename() {
    const name = nameValue.trim()
    if (name && name !== workflow.name) await onRename(name)
    else setNameValue(workflow.name)
    setRenaming(false)
  }

  const status = workflow.last_run_status ? statusStyle(workflow.last_run_status) : null

  if (confirmValue !== null) {
    return (
      <div className="card" style={{ padding: "14px 16px", borderColor: "var(--err-bd)", background: "var(--err-bg)" }}>
        <p style={{ fontSize: 12.5, color: "var(--err)", marginBottom: 10 }}>
          Type <strong>{workflow.name}</strong> to permanently delete this agent and all its data.
        </p>
        <div style={{ display: "flex", gap: 8 }}>
          <input
            ref={confirmInputRef}
            value={confirmValue}
            onChange={e => setConfirmValue(e.target.value)}
            onKeyDown={e => {
              if (e.key === "Enter" && confirmValue === workflow.name) onDelete()
              if (e.key === "Escape") setConfirmValue(null)
            }}
            placeholder={workflow.name}
            style={{ flex: 1, fontSize: 12.5, border: "1px solid var(--err-bd)", borderRadius: 8, padding: "6px 10px", outline: "none", background: "var(--surface)" }}
          />
          <button onClick={() => onDelete()} disabled={confirmValue !== workflow.name} className="btn btn-sm" style={{ background: "var(--err)", color: "#fff", border: "none", opacity: confirmValue !== workflow.name ? 0.4 : 1 }}>Delete</button>
          <button onClick={() => setConfirmValue(null)} className="btn btn-ghost btn-sm">Cancel</button>
        </div>
      </div>
    )
  }

  return (
    <div className="card" style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "14px 18px", gap: 12 }}>
      <Link href={renaming ? "#" : `/workflows/${workflow.id}/runs`} style={{ flex: 1, minWidth: 0, textDecoration: "none", color: "inherit" }} onClick={renaming ? e => e.preventDefault() : undefined}>
        {renaming ? (
          <input
            ref={inputRef}
            value={nameValue}
            onChange={e => setNameValue(e.target.value)}
            onBlur={submitRename}
            onKeyDown={e => { if (e.key === "Enter") submitRename(); if (e.key === "Escape") { setNameValue(workflow.name); setRenaming(false) } }}
            onClick={e => e.preventDefault()}
            style={{ fontSize: 13.5, fontWeight: 600, color: "var(--text)", background: "transparent", borderBottom: "1px solid var(--accent)", outline: "none", width: "100%" }}
          />
        ) : (
          <p style={{ fontSize: 13.5, fontWeight: 600, color: "var(--text)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{workflow.name}</p>
        )}
        <p style={{ fontSize: 11.5, color: "var(--text-muted)", marginTop: 3 }}>edited {timeAgo(workflow.updated_at)}</p>
      </Link>

      <div style={{ display: "flex", alignItems: "center", gap: 10, flexShrink: 0 }}>
        {status ? (() => {
          const sKey = workflow.last_run_status === "running" ? "run" : workflow.last_run_status === "succeeded" ? "ok" : workflow.last_run_status === "failed" ? "err" : workflow.last_run_status === "paused" ? "warn" : "idle"
          return <span className={`sbadge ${sKey}`}>{status.label}</span>
        })() : (
          <span style={{ fontSize: 11.5, color: "var(--text-muted)", fontStyle: "italic" }}>never run</span>
        )}
        {workflow.last_run_at && <span style={{ fontSize: 11.5, color: "var(--text-muted)" }}>{timeAgo(workflow.last_run_at)}</span>}

        {isAdmin && (
          <div style={{ position: "relative" }} ref={menuRef}>
            <button
              onClick={e => { e.preventDefault(); setMenuOpen(v => !v) }}
              className="btn btn-ghost btn-icon btn-sm"
              style={{ color: "var(--text-3)" }}
            >
              <svg width="14" height="14" fill="currentColor" viewBox="0 0 20 20">
                <path d="M10 6a2 2 0 1 1 0-4 2 2 0 0 1 0 4zm0 6a2 2 0 1 1 0-4 2 2 0 0 1 0 4zm0 6a2 2 0 1 1 0-4 2 2 0 0 1 0 4z" />
              </svg>
            </button>
            {menuOpen && (
              <div style={{ position: "absolute", right: 0, top: "calc(100% + 4px)", zIndex: 20, width: 140, background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 12, boxShadow: "var(--shadow-lg)", overflow: "hidden" }}>
                <button onClick={() => { setMenuOpen(false); setRenaming(true) }} style={{ width: "100%", textAlign: "left", padding: "10px 14px", fontSize: 13, color: "var(--text)", background: "none", border: "none", cursor: "pointer" }}>Rename</button>
                <button onClick={() => { setMenuOpen(false); setConfirmValue("") }} style={{ width: "100%", textAlign: "left", padding: "10px 14px", fontSize: 13, color: "var(--err)", background: "none", border: "none", cursor: "pointer" }}>Delete</button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
