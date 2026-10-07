"use client"

import { authEnabled } from "@/lib/auth/runtime"


import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import { useAuth } from "@/lib/auth/client"
import { useAuthFetch } from "@/hooks/useAuthFetch"
import { API } from "@/lib/api"
import AppShell from "@/components/AppShell"
import NewProjectModal from "@/components/NewProjectModal"
import OnboardingChecklist from "@/components/OnboardingChecklist"
import { useWorkspace } from "@/lib/WorkspaceContext"
import { PlusIcon, ShieldIcon, type Project, type Workflow } from "./_components/shared"
import { ListView } from "./_components/ListView"
import { GridView } from "./_components/GridView"
import { LoadingSkeleton, EmptyState, AutomationEmpty } from "./_components/states"
// ── Auth wrapper ──────────────────────────────────────────────────────────────

export default function ProjectsPage() {
  const clerkEnabled = authEnabled()
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
  const { activeWorkspace } = useWorkspace()
  const [projects, setProjects] = useState<Project[]>([])
  const [workflows, setWorkflows] = useState<Workflow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null) // P0-1
  const [showModal, setShowModal] = useState(false)
  const [tab, setTab] = useState<"projects" | "automation">("projects")
  const [q, setQ] = useState("")
  const [view, setView] = useState<"list" | "grid">(() => {
    if (typeof window !== "undefined") return (localStorage.getItem("projects_view") as "list" | "grid") ?? "list"
    return "list"
  })

  const { authFetch } = useAuthFetch()

  // P0-1: add error handling and setError on non-ok responses
  async function fetchAll() {
    setError(null)
    try {
      const wsId = activeWorkspace?.id ?? ""

      // Load projects first so the page renders immediately
      const projRes = await (wsId
        ? authFetch(`${API}/workspaces/${wsId}/projects`)
        : authFetch(`${API}/projects`))
      if (!projRes.ok) {
        setError(projRes.status === 403 ? "You don't have access to this workspace." : `Failed to load projects (${projRes.status}).`)
        setLoading(false)
        return
      }
      setProjects(await projRes.json())
      setLoading(false)

      // Load workflows in the background — agents populate without blocking the page
      const wfRes = await authFetch(`${API}/workflows`)
      if (wfRes.ok) setWorkflows(await wfRes.json())
    } catch {
      setError("Network error — please check your connection.")
      setLoading(false)
    }
  }

  useEffect(() => { fetchAll() }, [])

  async function renameProject(id: string, name: string) {
    const wsId = activeWorkspace?.id ?? ""
    const url = wsId
      ? `${API}/workspaces/${wsId}/projects/${id}`
      : `${API}/projects/${id}`
    const res = await authFetch(url, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name }) })
    if (res.ok) {
      const updated = await res.json()
      setProjects(prev => prev.map(p => p.id === id ? { ...p, name: updated.name } : p))
    }
  }

  async function deleteProject(id: string) {
    const wsId = activeWorkspace?.id ?? ""
    const url = wsId
      ? `${API}/workspaces/${wsId}/projects/${id}`
      : `${API}/projects/${id}`
    await authFetch(url, { method: "DELETE" })
    setProjects(prev => prev.filter(p => p.id !== id))
  }

  function workflowsForProject(project: Project): Workflow[] {
    return workflows.filter(w => w.project_id === project.id)
  }

  const userProjects = projects.filter(p => (p.project_type ?? "user") === "user")
  const automationProjects = projects.filter(p => p.project_type === "security_automation")

  const filteredProjects = (tab === "projects" ? userProjects : automationProjects)
    .filter(p => p.name.toLowerCase().includes(q.toLowerCase()))

  return (
    <AppShell>
      <div style={{ maxWidth: 1200, margin: "0 auto", padding: "30px 34px 80px" }}>
        {/* P0-1: error card */}
        {error && (
          <div style={{ border: "1px solid var(--err-bd, #fecaca)", borderRadius: 12, padding: 24, background: "var(--err-bg, #fff5f5)", marginBottom: 24 }}>
            <p style={{ color: "var(--err)", fontSize: 13.5, marginBottom: 10 }}>{error}</p>
            <button onClick={fetchAll} className="btn btn-ghost btn-sm" style={{ color: "var(--err)", borderColor: "var(--err-bd, #fecaca)" }}>Retry</button>
          </div>
        )}
        {/* P2-5: pass onNewProject so checklist CTA opens modal in-page */}
        <OnboardingChecklist hasProject={projects.length > 0} getToken={getToken} onNewProject={() => setShowModal(true)} />

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
              aria-label="Search projects"
              style={{ width: "100%", height: 36, padding: "0 12px 0 33px", borderRadius: 9, border: "1px solid var(--border)", background: "var(--surface)", color: "var(--text)", fontSize: 13.5, outline: "none" }}
            />
          </div>
          <div style={{ marginLeft: "auto", display: "flex", background: "var(--surface-3)", borderRadius: 8, padding: 3 }}>
            {(["list", "grid"] as const).map(v => (
              <button
                key={v}
                aria-label={v === "list" ? "List view" : "Grid view"}
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

        {/* Tab chips — P1-9: always rendered, no layout jump; counts shown only when loaded */}
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
                {!loading && <span style={{ opacity: .6 }}>· {count}</span>}
              </button>
            )
          })}
        </div>

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

      {/* P1-11: after creation stay on /projects and refresh; don't navigate away */}
      {showModal && (
        <NewProjectModal
          getToken={getToken}
          onClose={() => setShowModal(false)}
          onCreate={() => { setShowModal(false); fetchAll() }}
        />
      )}
    </AppShell>
  )
}
