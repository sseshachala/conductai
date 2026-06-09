"use client"

import { useEffect, useRef, useState } from "react"
import { useRouter } from "next/navigation"
import { useAuth } from "@clerk/nextjs"
import Link from "next/link"
import AppShell from "@/components/AppShell"
import NewProjectModal from "@/components/NewProjectModal"
import OnboardingChecklist from "@/components/OnboardingChecklist"

interface Project {
  id: string
  name: string
  agent_count: number
  created_at: string
  workspace_id?: string
  project_type?: string
  security_finding_id?: string
}

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
  const days = Math.floor(hrs / 24)
  if (days === 1) return "yesterday"
  if (days < 30) return `${days}d ago`
  return new Date(ts).toLocaleDateString()
}

const AVATAR_COLORS = [
  "#4f46e5", "#059669", "#d97706", "#dc2626",
  "#7c3aed", "#0284c7", "#be185d", "#15803d",
]
function avatarColor(name: string): string {
  let h = 0
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) & 0xffffffff
  return AVATAR_COLORS[Math.abs(h) % AVATAR_COLORS.length]
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

function PlusIcon({ size = 15 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M12 5v14M5 12h14" />
    </svg>
  )
}

function ShieldIcon() {
  return (
    <svg width={14} height={14} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
    </svg>
  )
}

// ── Auth wrapper ──────────────────────────────────────────────────────────────

export default function ProjectsPage() {
  const clerkEnabled = !!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY
  if (clerkEnabled) return <ProjectsWithAuth />
  return <ProjectsContent getToken={null} />
}

function ProjectsWithAuth() {
  const router = useRouter()
  const { getToken, isLoaded, isSignedIn } = useAuth()
  useEffect(() => {
    if (isLoaded && !isSignedIn) router.replace("/")
  }, [isLoaded, isSignedIn, router])
  if (!isLoaded) return null
  return <ProjectsContent getToken={getToken} />
}

// ── Main content ──────────────────────────────────────────────────────────────

function ProjectsContent({ getToken }: { getToken: (() => Promise<string | null>) | null }) {
  const router = useRouter()
  const [projects, setProjects] = useState<Project[]>([])
  const [workflows, setWorkflows] = useState<Workflow[]>([])
  const [loading, setLoading] = useState(true)
  const [showModal, setShowModal] = useState(false)
  const [tab, setTab] = useState<"projects" | "automation">("projects")
  const [q, setQ] = useState("")
  const [view, setView] = useState<"list" | "grid">(() => {
    if (typeof window !== "undefined") return (localStorage.getItem("projects_view") as "list" | "grid") ?? "list"
    return "list"
  })

  async function authHeaders(): Promise<Record<string, string>> {
    const h: Record<string, string> = {}
    if (getToken) {
      const token = await getToken()
      if (token) h["Authorization"] = `Bearer ${token}`
    }
    return h
  }

  function getWorkspaceId(): string {
    return document.cookie.match(/delegator_project_id=([^;]+)/)?.[1] ?? ""
  }

  async function fetchAll() {
    const wsId = getWorkspaceId()
    const headers = await authHeaders()
    if (wsId) headers["X-Workspace-Id"] = wsId

    // Load projects first so the page renders immediately
    const projRes = await (wsId
      ? fetch(`${process.env.NEXT_PUBLIC_API_URL}/workspaces/${wsId}/projects`, { headers })
      : fetch(`${process.env.NEXT_PUBLIC_API_URL}/projects`, { headers }))
    if (projRes.ok) setProjects(await projRes.json())
    setLoading(false)

    // Load workflows in the background — agents populate without blocking the page
    const wfRes = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/workflows`, {
      headers: { ...headers, ...(wsId ? { "X-Workspace-ID": wsId } : {}) },
    })
    if (wfRes.ok) setWorkflows(await wfRes.json())
  }

  useEffect(() => { fetchAll() }, [])

  async function renameProject(id: string, name: string) {
    const h = await authHeaders()
    h["Content-Type"] = "application/json"
    const wsId = getWorkspaceId()
    if (wsId) h["X-Workspace-Id"] = wsId
    const url = wsId
      ? `${process.env.NEXT_PUBLIC_API_URL}/workspaces/${wsId}/projects/${id}`
      : `${process.env.NEXT_PUBLIC_API_URL}/projects/${id}`
    const res = await fetch(url, { method: "PATCH", headers: h, body: JSON.stringify({ name }) })
    if (res.ok) {
      const updated = await res.json()
      setProjects(prev => prev.map(p => p.id === id ? { ...p, name: updated.name } : p))
    }
  }

  async function deleteProject(id: string) {
    const h = await authHeaders()
    const wsId = getWorkspaceId()
    if (wsId) h["X-Workspace-Id"] = wsId
    const url = wsId
      ? `${process.env.NEXT_PUBLIC_API_URL}/workspaces/${wsId}/projects/${id}`
      : `${process.env.NEXT_PUBLIC_API_URL}/projects/${id}`
    await fetch(url, { method: "DELETE", headers: h })
    setProjects(prev => prev.filter(p => p.id !== id))
  }

  function workflowsForProject(project: Project): Workflow[] {
    return workflows.filter(w => w.project_name === project.name)
  }

  const userProjects = projects.filter(p => (p.project_type ?? "user") === "user")
  const automationProjects = projects.filter(p => p.project_type === "security_automation")

  const filteredProjects = (tab === "projects" ? userProjects : automationProjects)
    .filter(p => p.name.toLowerCase().includes(q.toLowerCase()))

  return (
    <AppShell>
      <div style={{ maxWidth: 1200, margin: "0 auto", padding: "30px 34px 80px" }}>
        <OnboardingChecklist hasProject={projects.length > 0} getToken={getToken} />

        {/* Page header */}
        <div className="page-head" style={{ display: "flex", alignItems: "flex-end" }}>
          <div>
            <h1 className="page-title">Projects</h1>
            <p className="page-sub">Group agents by team or repo. Each project keeps its own runs, memory, and environments.</p>
          </div>
          <div style={{ marginLeft: "auto", display: "flex", gap: 9 }}>
            <button
              onClick={() => setShowModal(true)}
              className="btn btn-primary"
            >
              <PlusIcon size={14} /> New project
            </button>
          </div>
        </div>

        {/* Toolbar: search + view toggle */}
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 14, flexWrap: "wrap" }}>
          <div style={{ position: "relative", flex: 1, minWidth: 220, maxWidth: 340 }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" style={{ position: "absolute", left: 11, top: 10, color: "var(--text-muted)" }}>
              <path d="M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16zm4.15-2.85 3.7 3.7" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
            </svg>
            <input
              value={q}
              onChange={e => setQ(e.target.value)}
              placeholder="Search projects…"
              style={{ width: "100%", height: 36, padding: "0 12px 0 33px", borderRadius: 9, border: "1px solid var(--border)", background: "var(--surface)", color: "var(--text)", fontSize: 13.5, outline: "none" }}
            />
          </div>
          <div style={{ marginLeft: "auto", display: "flex", background: "var(--surface-3)", borderRadius: 8, padding: 3 }}>
            {(["list", "grid"] as const).map(v => (
              <button
                key={v}
                onClick={() => { setView(v); localStorage.setItem("projects_view", v) }}
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

        {/* Tab chips */}
        {!loading && (
          <div style={{ display: "flex", gap: 7, marginBottom: 16, flexWrap: "wrap" }}>
            {(["projects", "automation"] as const).map(t => {
              const count = t === "projects" ? userProjects.length : automationProjects.length
              const on = tab === t
              return (
                <button
                  key={t}
                  onClick={() => setTab(t)}
                  className="chip"
                  style={{ height: 30, cursor: "pointer", fontWeight: 600, display: "flex", alignItems: "center", gap: 5, background: on ? "var(--accent-weak)" : "var(--surface)", borderColor: on ? "var(--accent-ring)" : "var(--border)", color: on ? "var(--accent-text)" : "var(--text-2)" }}
                >
                  {t === "automation" && <ShieldIcon />}
                  {t === "projects" ? "Projects" : "Automation"}
                  <span style={{ opacity: .6 }}>· {count}</span>
                </button>
              )
            })}
          </div>
        )}

        {/* Content */}
        {loading ? (
          <LoadingSkeleton />
        ) : filteredProjects.length === 0 ? (
          tab === "automation" ? (
            <AutomationEmpty />
          ) : (
            <EmptyState onNew={() => setShowModal(true)} hasQuery={q.length > 0} />
          )
        ) : view === "list" ? (
          <ListView
            projects={filteredProjects}
            workflowsFor={workflowsForProject}
            onRename={renameProject}
            onDelete={deleteProject}
            router={router}
          />
        ) : (
          <GridView
            projects={filteredProjects}
            workflowsFor={workflowsForProject}
            onRename={renameProject}
            onDelete={deleteProject}
            onNew={() => setShowModal(true)}
            router={router}
          />
        )}
      </div>

      {showModal && (
        <NewProjectModal
          getToken={getToken}
          onClose={() => setShowModal(false)}
          onCreate={(id) => router.push(`/workflows?project=${id}`)}
        />
      )}
    </AppShell>
  )
}

// ── List view ─────────────────────────────────────────────────────────────────

function ListView({
  projects, workflowsFor, onRename, onDelete, router,
}: {
  projects: Project[]
  workflowsFor: (p: Project) => Workflow[]
  onRename: (id: string, name: string) => Promise<void>
  onDelete: (id: string) => Promise<void>
  router: ReturnType<typeof useRouter>
}) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      {projects.map(p => (
        <ProjectListSection
          key={p.id}
          project={p}
          agents={workflowsFor(p)}
          onRename={name => onRename(p.id, name)}
          onDelete={() => onDelete(p.id)}
          router={router}
        />
      ))}
    </div>
  )
}

function ProjectListSection({
  project, agents, onRename, onDelete, router,
}: {
  project: Project
  agents: Workflow[]
  onRename: (name: string) => Promise<void>
  onDelete: () => Promise<void>
  router: ReturnType<typeof useRouter>
}) {
  const [menuOpen, setMenuOpen] = useState(false)
  const [renaming, setRenaming] = useState(false)
  const [nameValue, setNameValue] = useState(project.name)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [confirmValue, setConfirmValue] = useState("")
  const menuRef = useRef<HTMLDivElement>(null)
  const renameRef = useRef<HTMLInputElement>(null)
  const confirmRef = useRef<HTMLInputElement>(null)
  const color = avatarColor(project.name)

  useEffect(() => { if (renaming) renameRef.current?.focus() }, [renaming])
  useEffect(() => { if (confirmDelete) confirmRef.current?.focus() }, [confirmDelete])
  useEffect(() => {
    function h(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuOpen(false)
    }
    document.addEventListener("mousedown", h)
    return () => document.removeEventListener("mousedown", h)
  }, [])

  async function submitRename() {
    const name = nameValue.trim()
    if (name && name !== project.name) await onRename(name)
    else setNameValue(project.name)
    setRenaming(false)
  }

  return (
    <div className="card" style={{ overflow: "hidden" }}>
      {/* Project header row */}
      <div
        style={{ display: "flex", alignItems: "center", gap: 12, padding: "13px 18px", borderBottom: agents.length > 0 ? "1px solid var(--border)" : undefined, cursor: "pointer", background: "var(--surface-2)" }}
        onClick={() => !renaming && router.push(`/projects/${project.id}`)}
      >
        <div style={{ width: 32, height: 32, borderRadius: 9, background: color, color: "#fff", display: "grid", placeItems: "center", fontWeight: 700, fontSize: 13, flexShrink: 0 }}>
          {project.name[0].toUpperCase()}
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          {renaming ? (
            <input
              ref={renameRef}
              value={nameValue}
              onChange={e => setNameValue(e.target.value)}
              onClick={e => e.stopPropagation()}
              onBlur={submitRename}
              onKeyDown={e => {
                if (e.key === "Enter") submitRename()
                if (e.key === "Escape") { setNameValue(project.name); setRenaming(false) }
              }}
              style={{ fontWeight: 650, fontSize: 14, background: "transparent", border: "none", borderBottom: "1px solid var(--accent-ring)", outline: "none", width: "100%", fontFamily: "inherit" }}
            />
          ) : (
            <div style={{ fontWeight: 650, fontSize: 14, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", color: "var(--text)" }}>
              {project.name}
            </div>
          )}
          <div className="mono" style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 2 }}>
            {agents.length} agent{agents.length !== 1 ? "s" : ""} · created {timeAgo(project.created_at)}
          </div>
        </div>

        <div style={{ display: "flex", gap: 6, alignItems: "center" }} onClick={e => e.stopPropagation()}>
          <Link
            href={`/workflows/new?project=${project.id}`}
            className="btn btn-ghost btn-sm"
            style={{ fontSize: 11 }}
            onClick={e => e.stopPropagation()}
          >
            + Agent
          </Link>
          <div ref={menuRef} style={{ position: "relative" }}>
            <button
              className="btn btn-ghost btn-icon btn-sm"
              onClick={() => setMenuOpen(v => !v)}
              title="Project actions"
            >⋯</button>
            {menuOpen && (
              <div style={{ position: "absolute", right: 0, top: "calc(100% + 4px)", zIndex: 20, minWidth: 130, background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 10, boxShadow: "var(--shadow-md)", padding: "4px 0" }}>
                <button
                  onClick={() => { setMenuOpen(false); setRenaming(true) }}
                  style={{ width: "100%", textAlign: "left", padding: "7px 14px", fontSize: 13, color: "var(--text)", background: "none", border: "none", cursor: "pointer" }}
                  onMouseEnter={e => (e.currentTarget as HTMLElement).style.background = "var(--surface-2)"}
                  onMouseLeave={e => (e.currentTarget as HTMLElement).style.background = "none"}
                >Rename</button>
                <button
                  onClick={() => { setMenuOpen(false); setConfirmDelete(true) }}
                  style={{ width: "100%", textAlign: "left", padding: "7px 14px", fontSize: 13, color: "var(--err)", background: "none", border: "none", cursor: "pointer" }}
                  onMouseEnter={e => (e.currentTarget as HTMLElement).style.background = "var(--surface-2)"}
                  onMouseLeave={e => (e.currentTarget as HTMLElement).style.background = "none"}
                >Delete</button>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Delete confirmation */}
      {confirmDelete && (
        <div style={{ padding: "12px 18px", borderBottom: "1px solid var(--border)", background: "var(--err-weak, #fff5f5)" }}>
          <p style={{ fontSize: 13, color: "var(--err)", marginBottom: 8 }}>
            Type <strong>{project.name}</strong> to permanently delete this project and all its data.
          </p>
          <div style={{ display: "flex", gap: 8 }}>
            <input
              ref={confirmRef}
              value={confirmValue}
              onChange={e => setConfirmValue(e.target.value)}
              onKeyDown={e => {
                if (e.key === "Enter" && confirmValue === project.name) onDelete()
                if (e.key === "Escape") { setConfirmDelete(false); setConfirmValue("") }
              }}
              placeholder={project.name}
              style={{ flex: 1, fontSize: 13, border: "1px solid var(--err, #fca5a5)", borderRadius: 7, padding: "5px 10px", outline: "none", background: "var(--surface)" }}
            />
            <button
              onClick={() => onDelete()}
              disabled={confirmValue !== project.name}
              className="btn btn-sm"
              style={{ background: "var(--err)", color: "#fff", opacity: confirmValue !== project.name ? 0.4 : 1 }}
            >Delete</button>
            <button
              onClick={() => { setConfirmDelete(false); setConfirmValue("") }}
              className="btn btn-ghost btn-sm"
            >Cancel</button>
          </div>
        </div>
      )}

      {/* Agent rows */}
      {agents.length === 0 ? (
        <div style={{ padding: "14px 18px", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <span style={{ fontSize: 13, color: "var(--text-muted)" }}>No agents yet</span>
          <Link href={`/workflows/new?project=${project.id}`} className="btn btn-ghost btn-sm" style={{ fontSize: 11 }}>
            + New agent
          </Link>
        </div>
      ) : (
        <>
          {/* Column headers */}
          <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr 1fr 80px", gap: 14, padding: "7px 18px 7px 58px", background: "var(--surface-2)", borderBottom: "1px solid var(--border)" }}>
            {["Agent", "Status", "Last run", ""].map((h, i) => (
              <div key={i} className="eyebrow" style={{ fontSize: 9.5 }}>{h}</div>
            ))}
          </div>
          {agents.map((w, idx) => (
            <AgentRow
              key={w.id}
              workflow={w}
              isLast={idx === agents.length - 1}
              router={router}
            />
          ))}
        </>
      )}
    </div>
  )
}

function AgentRow({ workflow: w, isLast, router }: { workflow: Workflow; isLast: boolean; router: ReturnType<typeof useRouter> }) {
  const status = mapStatus(w.last_run_status)
  return (
    <div
      style={{ display: "grid", gridTemplateColumns: "2fr 1fr 1fr 80px", gap: 14, padding: "11px 18px 11px 58px", borderBottom: isLast ? "none" : "1px solid var(--border)", alignItems: "center", cursor: "pointer", transition: "background .12s" }}
      onClick={() => router.push(`/workflows/${w.id}/runs`)}
      onMouseEnter={e => (e.currentTarget as HTMLElement).style.background = "var(--surface-2)"}
      onMouseLeave={e => (e.currentTarget as HTMLElement).style.background = ""}
    >
      <div style={{ minWidth: 0 }}>
        <div style={{ fontWeight: 600, fontSize: 13.5, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", color: "var(--text)" }}>{w.name}</div>
        <div className="mono" style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 2 }}>edited {timeAgo(w.updated_at)}</div>
      </div>
      <AgentStatusPill s={status} />
      <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
        {w.last_run_at ? timeAgo(w.last_run_at) : "—"}
      </div>
      <div style={{ display: "flex", gap: 4, justifyContent: "flex-end" }} onClick={e => e.stopPropagation()}>
        <Link
          href={`/workflows/${w.id}/runs`}
          className="btn btn-ghost btn-sm"
          style={{ fontSize: 11, padding: "3px 9px" }}
          title="View runs"
        >Runs</Link>
        <Link
          href={`/workflows/${w.id}`}
          className="btn btn-ghost btn-icon btn-sm"
          title="Open canvas"
        >→</Link>
      </div>
    </div>
  )
}

// ── Grid view ─────────────────────────────────────────────────────────────────

function GridView({
  projects, workflowsFor, onRename, onDelete, onNew, router,
}: {
  projects: Project[]
  workflowsFor: (p: Project) => Workflow[]
  onRename: (id: string, name: string) => Promise<void>
  onDelete: (id: string) => Promise<void>
  onNew: () => void
  router: ReturnType<typeof useRouter>
}) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))", gap: 14 }}>
      {projects.map(p => (
        <ProjectGridCard
          key={p.id}
          project={p}
          agents={workflowsFor(p)}
          onRename={name => onRename(p.id, name)}
          onDelete={() => onDelete(p.id)}
          router={router}
        />
      ))}
      <NewProjectTile onClick={onNew} />
    </div>
  )
}

function ProjectGridCard({
  project, agents, onRename, onDelete, router,
}: {
  project: Project
  agents: Workflow[]
  onRename: (name: string) => Promise<void>
  onDelete: () => Promise<void>
  router: ReturnType<typeof useRouter>
}) {
  const [menuOpen, setMenuOpen] = useState(false)
  const [renaming, setRenaming] = useState(false)
  const [nameValue, setNameValue] = useState(project.name)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [confirmValue, setConfirmValue] = useState("")
  const [hovered, setHovered] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)
  const renameRef = useRef<HTMLInputElement>(null)
  const color = avatarColor(project.name)

  useEffect(() => { if (renaming) renameRef.current?.focus() }, [renaming])
  useEffect(() => {
    function h(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuOpen(false)
    }
    document.addEventListener("mousedown", h)
    return () => document.removeEventListener("mousedown", h)
  }, [])

  async function submitRename() {
    const name = nameValue.trim()
    if (name && name !== project.name) await onRename(name)
    else setNameValue(project.name)
    setRenaming(false)
  }

  if (confirmDelete) {
    return (
      <div className="card" style={{ padding: "16px 18px", border: "1px solid #fecaca", background: "#fef2f2" }}>
        <p style={{ fontSize: 13, color: "var(--err)", marginBottom: 10 }}>
          Type <strong>{project.name}</strong> to delete this project.
        </p>
        <div style={{ display: "flex", gap: 8 }}>
          <input
            autoFocus
            value={confirmValue}
            onChange={e => setConfirmValue(e.target.value)}
            onKeyDown={e => {
              if (e.key === "Enter" && confirmValue === project.name) onDelete()
              if (e.key === "Escape") { setConfirmDelete(false); setConfirmValue("") }
            }}
            placeholder={project.name}
            style={{ flex: 1, fontSize: 13, border: "1px solid #fecaca", borderRadius: 8, padding: "6px 10px", outline: "none", fontFamily: "inherit" }}
          />
          <button
            onClick={() => onDelete()}
            disabled={confirmValue !== project.name}
            className="btn btn-sm"
            style={{ background: "var(--err)", color: "#fff", opacity: confirmValue !== project.name ? 0.4 : 1 }}
          >Delete</button>
          <button onClick={() => { setConfirmDelete(false); setConfirmValue("") }} className="btn btn-ghost btn-sm">Cancel</button>
        </div>
      </div>
    )
  }

  return (
    <div
      className="card"
      style={{ overflow: "hidden", cursor: "pointer", boxShadow: hovered ? "var(--shadow-md)" : undefined, transition: "box-shadow .15s, border-color .15s", borderColor: hovered ? "var(--border-2)" : undefined }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      {/* Card header */}
      <div
        style={{ padding: "16px 18px 14px", display: "flex", alignItems: "center", gap: 10 }}
        onClick={() => !renaming && router.push(`/projects/${project.id}`)}
      >
        <div style={{ width: 36, height: 36, borderRadius: 10, background: color, color: "#fff", display: "grid", placeItems: "center", fontWeight: 700, fontSize: 14, flexShrink: 0 }}>
          {project.name[0].toUpperCase()}
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          {renaming ? (
            <input
              ref={renameRef}
              value={nameValue}
              onChange={e => setNameValue(e.target.value)}
              onClick={e => e.stopPropagation()}
              onBlur={submitRename}
              onKeyDown={e => {
                if (e.key === "Enter") submitRename()
                if (e.key === "Escape") { setNameValue(project.name); setRenaming(false) }
              }}
              style={{ fontWeight: 650, fontSize: 15, background: "transparent", border: "none", borderBottom: "1px solid var(--accent-ring)", outline: "none", width: "100%", fontFamily: "inherit" }}
            />
          ) : (
            <div style={{ fontWeight: 650, fontSize: 15, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", color: "var(--text)" }}>
              {project.name}
            </div>
          )}
          <div className="mono" style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 2 }}>
            created {timeAgo(project.created_at)}
          </div>
        </div>
        <div ref={menuRef} style={{ position: "relative", flexShrink: 0 }} onClick={e => e.stopPropagation()}>
          <button
            className="btn btn-ghost btn-icon btn-sm"
            style={{ opacity: hovered || menuOpen ? 1 : 0, transition: "opacity .15s" }}
            onClick={() => setMenuOpen(v => !v)}
            title="Project actions"
          >⋯</button>
          {menuOpen && (
            <div style={{ position: "absolute", right: 0, top: "calc(100% + 4px)", zIndex: 20, minWidth: 130, background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 10, boxShadow: "var(--shadow-md)", padding: "4px 0" }}>
              <button
                onClick={() => { setMenuOpen(false); setRenaming(true) }}
                style={{ width: "100%", textAlign: "left", padding: "7px 14px", fontSize: 13, color: "var(--text)", background: "none", border: "none", cursor: "pointer" }}
                onMouseEnter={e => (e.currentTarget as HTMLElement).style.background = "var(--surface-2)"}
                onMouseLeave={e => (e.currentTarget as HTMLElement).style.background = "none"}
              >Rename</button>
              <button
                onClick={() => { setMenuOpen(false); setConfirmDelete(true) }}
                style={{ width: "100%", textAlign: "left", padding: "7px 14px", fontSize: 13, color: "var(--err)", background: "none", border: "none", cursor: "pointer" }}
                onMouseEnter={e => (e.currentTarget as HTMLElement).style.background = "var(--surface-2)"}
                onMouseLeave={e => (e.currentTarget as HTMLElement).style.background = "none"}
              >Delete</button>
            </div>
          )}
        </div>
      </div>

      {/* Agent list */}
      <div style={{ borderTop: "1px solid var(--border)" }}>
        {agents.length === 0 ? (
          <div style={{ padding: "12px 18px", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <span style={{ fontSize: 12, color: "var(--text-muted)" }}>No agents yet</span>
            <Link href={`/workflows/new?project=${project.id}`} className="btn btn-ghost btn-sm" style={{ fontSize: 11 }} onClick={e => e.stopPropagation()}>
              + New agent
            </Link>
          </div>
        ) : (
          <>
            {agents.slice(0, 4).map((w, idx) => {
              const status = mapStatus(w.last_run_status)
              return (
                <div
                  key={w.id}
                  style={{ display: "flex", alignItems: "center", gap: 10, padding: "9px 18px", borderBottom: idx < Math.min(agents.length, 4) - 1 ? "1px solid var(--border)" : "none", cursor: "pointer", transition: "background .1s" }}
                  onClick={e => { e.stopPropagation(); router.push(`/workflows/${w.id}/runs`) }}
                  onMouseEnter={e => (e.currentTarget as HTMLElement).style.background = "var(--surface-2)"}
                  onMouseLeave={e => (e.currentTarget as HTMLElement).style.background = ""}
                >
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 13, fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", color: "var(--text)" }}>{w.name}</div>
                  </div>
                  <AgentStatusPill s={status} />
                  <Link
                    href={`/workflows/${w.id}`}
                    className="btn btn-ghost btn-icon btn-sm"
                    style={{ opacity: 0.6, fontSize: 12 }}
                    onClick={e => e.stopPropagation()}
                    title="Open canvas"
                  >→</Link>
                </div>
              )
            })}
            {agents.length > 4 && (
              <div
                style={{ padding: "9px 18px", fontSize: 12, color: "var(--text-muted)", cursor: "pointer", textAlign: "center", transition: "background .1s" }}
                onClick={() => router.push(`/projects/${project.id}`)}
                onMouseEnter={e => (e.currentTarget as HTMLElement).style.background = "var(--surface-2)"}
                onMouseLeave={e => (e.currentTarget as HTMLElement).style.background = ""}
              >
                +{agents.length - 4} more agents →
              </div>
            )}
          </>
        )}
      </div>

      {/* Card footer */}
      <div style={{ display: "flex", borderTop: "1px solid var(--border)", background: "var(--surface-2)" }}>
        <div style={{ flex: 1, padding: "10px 18px" }}>
          <div style={{ fontSize: 16, fontWeight: 650, color: "var(--text)" }}>{agents.length}</div>
          <div style={{ fontSize: 11, color: "var(--text-muted)" }}>agents</div>
        </div>
        <div
          style={{ display: "grid", placeItems: "center", padding: "0 18px", borderLeft: "1px solid var(--border)", color: "var(--text-muted)", cursor: "pointer" }}
          onClick={() => router.push(`/projects/${project.id}`)}
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round"><path d="M5 12h14M12 5l7 7-7 7" /></svg>
        </div>
      </div>
    </div>
  )
}

// ── New project dashed tile ───────────────────────────────────────────────────

function NewProjectTile({ onClick }: { onClick: () => void }) {
  const [hovered, setHovered] = useState(false)
  return (
    <div
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        border: `1.5px dashed ${hovered ? "var(--accent-ring)" : "var(--border-2)"}`,
        borderRadius: 14, display: "grid", placeItems: "center", minHeight: 160, cursor: "pointer",
        color: hovered ? "var(--accent-text)" : "var(--text-3)", transition: "border-color .15s, color .15s",
      }}
    >
      <div style={{ textAlign: "center" }}>
        <PlusIcon size={22} />
        <div style={{ fontSize: 13.5, fontWeight: 600, marginTop: 6 }}>New project</div>
      </div>
    </div>
  )
}

// ── Loading skeleton ──────────────────────────────────────────────────────────

function LoadingSkeleton() {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {[1, 2, 3].map(i => (
        <div key={i} style={{ height: 140, borderRadius: 12, border: "1px solid var(--border)", background: "var(--surface)", opacity: 0.5, animation: "pulse 1.5s ease-in-out infinite" }} />
      ))}
    </div>
  )
}

// ── Empty states ──────────────────────────────────────────────────────────────

function EmptyState({ onNew, hasQuery }: { onNew: () => void; hasQuery: boolean }) {
  return (
    <div style={{ padding: "60px 20px", textAlign: "center" }}>
      <p style={{ fontWeight: 650, fontSize: 16, color: "var(--text)", marginBottom: 8 }}>
        {hasQuery ? "No projects match" : "Create your first project"}
      </p>
      <p style={{ fontSize: 13.5, color: "var(--text-3)", marginBottom: 20, maxWidth: 360, margin: "0 auto 20px", lineHeight: 1.6 }}>
        {hasQuery
          ? "Try a different search term."
          : "A project groups your agents, runs, and credentials. Think of it as one repo or one team."}
      </p>
      {!hasQuery && (
        <button onClick={onNew} className="btn btn-primary">
          <PlusIcon size={14} /> New project
        </button>
      )}
    </div>
  )
}

function AutomationEmpty() {
  return (
    <div style={{ padding: "60px 20px", textAlign: "center" }}>
      <p style={{ fontWeight: 650, fontSize: 16, color: "var(--text)", marginBottom: 8 }}>No automation project yet</p>
      <p style={{ fontSize: 13.5, color: "var(--text-3)", maxWidth: 400, margin: "0 auto", lineHeight: 1.6 }}>
        Install Security Loop from the marketplace. A Security Automation project will be created automatically — all triage and fix runs live here.
      </p>
    </div>
  )
}
