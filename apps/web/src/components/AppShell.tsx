"use client"

import { useState, useRef, useEffect, useCallback } from "react"
import Link from "next/link"
import { usePathname, useRouter } from "next/navigation"
import { useAuth, useUser, useClerk } from "@clerk/nextjs"
import { WorkspaceProvider, useWorkspace } from "@/lib/WorkspaceContext"
import { setActiveGuardWorkspace } from "@/lib/guardStorage"
import { PreferencesProvider } from "@/lib/PreferencesContext"
import Toast, { type ToastData } from "@/components/ui/Toast"
import ErrorBoundary from "@/components/ui/ErrorBoundary"

interface Project { id: string; name: string; agent_count: number }

type UserRole = "admin" | "security" | "developer" | "viewer" | null

const GUARD_SECTION_KEY = "conduct_guard_section_open"
const PROJECTS_SECTION_KEY = "conduct_projects_section_open"

export default function AppShell({ children, noPadding }: { children: React.ReactNode; noPadding?: boolean }) {
  const clerkEnabled = !!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY
  return (
    <WorkspaceProvider clerkEnabled={clerkEnabled}>
      <AppShellInner noPadding={noPadding}>{children}</AppShellInner>
    </WorkspaceProvider>
  )
}

function AppShellInner({ children, noPadding }: { children: React.ReactNode; noPadding?: boolean }) {
  const pathname = usePathname()
  const router = useRouter()
  const { getToken, userId } = useAuth()
  const [collapsed, setCollapsed] = useState(false)
  const [toast, setToast] = useState<ToastData | null>(null)
  function showError(message: string) { setToast({ message, type: "error" }) }
  function showSuccess(message: string) { setToast({ message, type: "success" }) }

  // Org name (read-only label in header)
  const [orgName, setOrgName] = useState<string | null>(null)

  // Role state
  const [userRole, setUserRole] = useState<UserRole>(null)

  // Workspace switcher (top-right)
  const [wsOpen, setWsOpen] = useState(false)
  const wsRef = useRef<HTMLDivElement>(null)

  // User menu (top-right)
  const [userMenuOpen, setUserMenuOpen] = useState(false)
  const userMenuRef = useRef<HTMLDivElement>(null)

  // Team (workspace) rename state — kept in sidebar for collapsed mode context
  const [creatingTeam, setCreatingTeam] = useState(false)
  const [newTeamValue, setNewTeamValue] = useState("")
  const [deletingTeamId, setDeletingTeamId] = useState<string | null>(null)
  const [deleteConfirmValue, setDeleteConfirmValue] = useState("")
  const newTeamInputRef = useRef<HTMLInputElement>(null)
  const deleteConfirmRef = useRef<HTMLInputElement>(null)

  const { workspaces, activeWorkspace, setActiveWorkspace, refresh: refreshWorkspaces } = useWorkspace()

  // Guard install state
  const [guardInstalled, setGuardInstalled] = useState(false)

  // Collapsible section states — persisted to localStorage
  const [guardSectionOpen, setGuardSectionOpen] = useState(() => {
    if (typeof window === "undefined") return true
    const stored = localStorage.getItem(GUARD_SECTION_KEY)
    return stored === null ? true : stored === "1"
  })
  const [projectsSectionOpen, setProjectsSectionOpen] = useState(() => {
    if (typeof window === "undefined") return true
    const stored = localStorage.getItem(PROJECTS_SECTION_KEY)
    return stored === null ? true : stored === "1"
  })

  function toggleGuardSection() {
    setGuardSectionOpen(v => {
      const next = !v
      localStorage.setItem(GUARD_SECTION_KEY, next ? "1" : "0")
      return next
    })
  }

  function toggleProjectsSection() {
    setProjectsSectionOpen(v => {
      const next = !v
      localStorage.setItem(PROJECTS_SECTION_KEY, next ? "1" : "0")
      return next
    })
  }

  // Projects state
  const [projects, setProjects] = useState<Project[]>([])
  const [renamingProjectId, setRenamingProjectId] = useState<string | null>(null)
  const [renameValue, setRenameValue] = useState("")
  const [creatingProject, setCreatingProject] = useState(false)
  const [newProjectValue, setNewProjectValue] = useState("")
  const renameInputRef = useRef<HTMLInputElement>(null)
  const newProjectInputRef = useRef<HTMLInputElement>(null)

  // Close dropdowns on outside click
  useEffect(() => {
    function handle(e: MouseEvent) {
      if (wsRef.current && !wsRef.current.contains(e.target as Node)) setWsOpen(false)
      if (userMenuRef.current && !userMenuRef.current.contains(e.target as Node)) setUserMenuOpen(false)
    }
    document.addEventListener("mousedown", handle)
    return () => document.removeEventListener("mousedown", handle)
  }, [])

  useEffect(() => { if (creatingTeam) newTeamInputRef.current?.focus() }, [creatingTeam])
  useEffect(() => { if (deletingTeamId) deleteConfirmRef.current?.focus() }, [deletingTeamId])
  useEffect(() => { if (renamingProjectId) renameInputRef.current?.focus() }, [renamingProjectId])
  useEffect(() => { if (creatingProject) newProjectInputRef.current?.focus() }, [creatingProject])

  async function authHeaders(wsId?: string): Promise<Record<string, string>> {
    const h: Record<string, string> = {}
    if (getToken) { const t = await getToken(); if (t) h["Authorization"] = `Bearer ${t}` }
    const id = wsId ?? activeWorkspace?.id
    if (id) h["X-Workspace-ID"] = id
    return h
  }

  // Fetch user role from members API
  useEffect(() => {
    let cancelled = false
    async function fetchRole() {
      if (!activeWorkspace || !userId) return
      try {
        const h = await authHeaders()
        const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/projects/${activeWorkspace.id}/members`, { headers: h })
        if (!res.ok || cancelled) return
        const members: { clerk_user_id: string; role: string }[] = await res.json()
        const myRole = members.find(m => m.clerk_user_id === userId)?.role as UserRole ?? null
        if (!cancelled) setUserRole(myRole ?? "admin") // default to admin if not found (sole owner)
      } catch {
        if (!cancelled) setUserRole("admin")
      }
    }
    fetchRole()
    return () => { cancelled = true }
  }, [activeWorkspace?.id, userId])

  // Fetch org name for header label
  useEffect(() => {
    let cancelled = false
    async function fetchOrgName() {
      try {
        const h = await authHeaders()
        const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/organizations`, { headers: h })
        if (!res.ok || cancelled) return
        const data = await res.json()
        const name = Array.isArray(data) && data.length > 0 ? data[0].name : null
        if (!cancelled) setOrgName(name)
      } catch {
        // Non-fatal: show nothing
      }
    }
    fetchOrgName()
    function onOrgNameChange(e: Event) {
      const { name } = (e as CustomEvent<{ name: string }>).detail
      setOrgName(name)
    }
    window.addEventListener("conduct:org-name-changed", onOrgNameChange)
    return () => {
      cancelled = true
      window.removeEventListener("conduct:org-name-changed", onOrgNameChange)
    }
  }, [activeWorkspace?.id])

  // Guard install check
  useEffect(() => {
    let cancelled = false
    async function checkGuardInstall() {
      const wsId = activeWorkspace?.id
      if (!wsId) return
      try {
        const h: Record<string, string> = {}
        if (getToken) { const t = await getToken(); if (t) h["Authorization"] = `Bearer ${t}` }
        const res = await fetch(
          `${process.env.NEXT_PUBLIC_API_URL}/guard/config/installed?workspace_id=${wsId}`,
          { headers: h }
        )
        if (!cancelled && res.ok) {
          const data = await res.json()
          setGuardInstalled(!!data.installed)
          if (data.installed && wsId) setActiveGuardWorkspace(wsId)
        }
      } catch {
        // Non-fatal: default to hidden
      }
    }
    checkGuardInstall()

    function onGuardChange(e: Event) {
      const detail = (e as CustomEvent<{ installed: boolean }>).detail
      setGuardInstalled(detail.installed)
    }
    window.addEventListener("guard-install-changed", onGuardChange)
    return () => {
      cancelled = true
      window.removeEventListener("guard-install-changed", onGuardChange)
    }
  }, [getToken, activeWorkspace])

  const fetchProjects = useCallback(async () => {
    if (!activeWorkspace) return
    try {
      const h = await authHeaders()
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/workspaces/${activeWorkspace.id}/projects`, { headers: h })
      if (!res.ok) return
      const data = await res.json()
      setProjects(Array.isArray(data) ? data : [])
    } catch {}
  }, [activeWorkspace])

  useEffect(() => { fetchProjects() }, [fetchProjects])

  async function submitCreateTeam() {
    const name = newTeamValue.trim()
    setCreatingTeam(false); setNewTeamValue("")
    if (!name) return
    try {
      const h = await authHeaders()
      h["Content-Type"] = "application/json"
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/projects`, {
        method: "POST", headers: h, body: JSON.stringify({ name })
      })
      if (res.ok) { setWsOpen(false); refreshWorkspaces() }
      else showError("Could not create team — please try again.")
    } catch { showError("Could not create team — check your connection.") }
  }

  async function confirmDeleteTeam(ws: { id: string; name: string }) {
    if (deleteConfirmValue !== ws.name) return
    setDeletingTeamId(null); setDeleteConfirmValue("")
    try {
      const h = await authHeaders()
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/projects/${ws.id}`, { method: "DELETE", headers: h })
      if (res.ok) {
        const next = workspaces.find(w => w.id !== ws.id)
        if (activeWorkspace?.id === ws.id && next) setActiveWorkspace(next)
        refreshWorkspaces()
      } else showError("Could not delete team — please try again.")
    } catch { showError("Could not delete team — check your connection.") }
  }

  async function submitCreateProject() {
    const name = newProjectValue.trim()
    setCreatingProject(false); setNewProjectValue("")
    if (!name || !activeWorkspace) return
    try {
      const h = await authHeaders()
      h["Content-Type"] = "application/json"
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/workspaces/${activeWorkspace.id}/projects`, {
        method: "POST", headers: h, body: JSON.stringify({ name })
      })
      if (res.ok) fetchProjects()
      else showError("Could not create project — please try again.")
    } catch { showError("Could not create project — check your connection.") }
  }

  async function submitProjectRename(projectId: string) {
    const name = renameValue.trim()
    setRenamingProjectId(null)
    if (!name || !activeWorkspace) return
    try {
      const h = await authHeaders()
      h["Content-Type"] = "application/json"
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/workspaces/${activeWorkspace.id}/projects/${projectId}`, {
        method: "PATCH", headers: h, body: JSON.stringify({ name })
      })
      if (res.ok) fetchProjects()
      else showError("Could not rename project — please try again.")
    } catch { showError("Could not rename project — check your connection.") }
  }

  const activeProjectId = pathname.match(/\/projects\/([^/]+)/)?.[1]

  // Role-based visibility
  const canSeeGuard = guardInstalled
  const canSeeProjects = userRole === "admin" || userRole === "developer" || userRole === "viewer"
  const canCreateProject = userRole === "admin" || userRole === "developer"

  return (
    <PreferencesProvider workspaceId={activeWorkspace?.id ?? ""} getToken={getToken}>
    <div className="flex h-screen bg-stone-50">
      {/* Left sidebar */}
      <aside className={`relative shrink-0 bg-white border-r border-stone-200 flex flex-col transition-all duration-200 ${collapsed ? "w-14" : "w-52"}`}>

        {/* Logo */}
        <div className={`px-3 py-3 border-b border-stone-100 flex items-center ${collapsed ? "justify-center" : ""}`}>
          <Link href="/dashboard">
            {collapsed
              ? <img src="/icon.png" alt="Conduct AI" className="w-7 h-7" />
              : <img src="/logo.png" alt="Conduct AI" className="h-9 w-auto" />}
          </Link>
        </div>

        {/* Nav */}
        <nav className="flex-1 px-2 py-3 overflow-y-auto space-y-0.5">
          {/* Top-level nav items */}
          <NavItem href="/dashboard" icon="◎" label="Dashboard" collapsed={collapsed} pathname={pathname} />
          <NavItem href="/marketplace" icon="📦" label="Playbooks" collapsed={collapsed} pathname={pathname} />
          <NavItem href="/runs" icon="▶" label="Runs" collapsed={collapsed} pathname={pathname} />
          <NavItem href="/observability" icon="◉" label="Observability" collapsed={collapsed} pathname={pathname} />

          {/* Guard section — all roles see Guard when it is installed */}
          {canSeeGuard && (
            <div className="pt-3">
              {!collapsed && (
                <button
                  onClick={toggleGuardSection}
                  className="w-full flex items-center justify-between px-2 mb-1 text-[10px] font-semibold text-stone-400 uppercase tracking-wider hover:text-stone-600"
                >
                  <span>Guard</span>
                  <span>{guardSectionOpen ? "▾" : "›"}</span>
                </button>
              )}
              {collapsed && (
                <div className="px-2 mb-1">
                  <span className="block text-[9px] font-semibold text-stone-400 uppercase tracking-wider text-center">GD</span>
                </div>
              )}
              {(guardSectionOpen || collapsed) && (
                <div className="space-y-0.5">
                  <NavItem href="/guard" icon="🛡" label="Activity" collapsed={collapsed} pathname={pathname} exact />
                  <NavItem href="/guard/policies" icon="◈" label="Policies" collapsed={collapsed} pathname={pathname} />
                  <NavItem href="/guard/spend" icon="◆" label="Spend" collapsed={collapsed} pathname={pathname} />
                  <NavItem href="/guard/activity" icon="📋" label="Activity log" collapsed={collapsed} pathname={pathname} />
                  <NavItem href="/guard/settings" icon="⚙" label="Settings" collapsed={collapsed} pathname={pathname} />
                </div>
              )}
            </div>
          )}

          {/* Projects section */}
          {canSeeProjects && (
            <div className="pt-3">
              {!collapsed && (
                <button
                  onClick={toggleProjectsSection}
                  className="w-full flex items-center justify-between px-2 mb-1 text-[10px] font-semibold text-stone-400 uppercase tracking-wider hover:text-stone-600"
                >
                  <span>Projects</span>
                  <span>{projectsSectionOpen ? "▾" : "›"}</span>
                </button>
              )}
              {collapsed && (
                <div className="px-2 mb-1">
                  <span className="block text-[9px] font-semibold text-stone-400 uppercase tracking-wider text-center">PJ</span>
                </div>
              )}
              {(projectsSectionOpen || collapsed) && (
                <div className="space-y-0.5">
                  {projects.map(project => {
                    const isActive = activeProjectId === project.id
                    const isRenaming = renamingProjectId === project.id
                    return (
                      <div key={project.id} className={`group flex items-center gap-1.5 px-2 py-1.5 rounded-lg transition-colors ${isActive ? "bg-stone-100" : "hover:bg-stone-50"}`}>
                        <span className="w-4 h-4 rounded bg-stone-200 text-stone-500 text-[9px] font-bold flex items-center justify-center shrink-0">
                          {project.name[0].toUpperCase()}
                        </span>
                        {isRenaming ? (
                          <input
                            ref={renameInputRef}
                            value={renameValue}
                            onChange={e => setRenameValue(e.target.value)}
                            onBlur={() => submitProjectRename(project.id)}
                            onKeyDown={e => { if (e.key === "Enter") submitProjectRename(project.id); if (e.key === "Escape") setRenamingProjectId(null) }}
                            className="flex-1 text-sm bg-transparent border-b border-indigo-400 outline-none"
                          />
                        ) : (
                          <>
                            <Link
                              href={`/projects/${project.id}`}
                              title={project.name}
                              className={`flex-1 text-sm truncate ${isActive ? "font-semibold text-stone-900" : "text-stone-600"}`}
                            >
                              {project.name}
                            </Link>
                            {!collapsed && (
                              <>
                                <button
                                  onClick={() => { setRenamingProjectId(project.id); setRenameValue(project.name) }}
                                  className="text-stone-300 hover:text-stone-600 text-xs opacity-0 group-hover:opacity-100 transition-opacity"
                                  title="Rename"
                                >✎</button>
                                <span className="text-[10px] text-stone-400 shrink-0">{project.agent_count}</span>
                              </>
                            )}
                          </>
                        )}
                      </div>
                    )
                  })}

                  {/* Per-project sub-nav when a project is active */}
                  {activeProjectId && !collapsed && (
                    <div className="ml-4 mt-0.5 space-y-0.5 border-l border-stone-100 pl-2">
                      <NavItem href={`/projects/${activeProjectId}`} icon="" label="Agents" collapsed={false} pathname={pathname} exact />
                      <NavItem href={`/projects/${activeProjectId}/playbooks`} icon="" label="Playbooks" collapsed={false} pathname={pathname} />
                      <NavItem href={`/projects/${activeProjectId}/runs`} icon="" label="Runs" collapsed={false} pathname={pathname} />
                    </div>
                  )}

                  {!collapsed && canCreateProject && (
                    creatingProject ? (
                      <div className="px-2 py-1">
                        <input
                          ref={newProjectInputRef}
                          value={newProjectValue}
                          onChange={e => setNewProjectValue(e.target.value)}
                          onBlur={submitCreateProject}
                          onKeyDown={e => { if (e.key === "Enter") submitCreateProject(); if (e.key === "Escape") { setCreatingProject(false); setNewProjectValue("") } }}
                          placeholder="Project name"
                          className="w-full text-sm border border-stone-200 rounded-lg px-2 py-1.5 outline-none focus:ring-2 focus:ring-indigo-200"
                        />
                      </div>
                    ) : (
                      <button
                        onClick={() => setCreatingProject(true)}
                        className="w-full flex items-center gap-2 px-2 py-1.5 rounded-lg text-xs text-stone-400 hover:text-stone-600 hover:bg-stone-50"
                      >
                        <span>＋</span> New project
                      </button>
                    )
                  )}
                </div>
              )}
            </div>
          )}

          {/* Bottom util items */}
          <div className="pt-2 border-t border-stone-100 mt-2 space-y-0.5">
            <NavItem href="/eval" icon="◈" label="Quality" collapsed={collapsed} pathname={pathname} />
            <NavItem href="/benchmark" icon="▲" label="Benchmark" collapsed={collapsed} pathname={pathname} />
            <NavItem href="/audit" icon="📋" label="Audit Log" collapsed={collapsed} pathname={pathname} />
            <NavItem href="/settings" icon="⚙" label="Global Settings" collapsed={collapsed} pathname={pathname} />
          </div>
        </nav>

        {/* Collapse toggle + idea link */}
        <div className="border-t border-stone-100 px-2 py-2 space-y-0.5">
          <a
            href="https://github.com/sseshachala/conductai/discussions/new?category=ideas"
            target="_blank"
            rel="noopener noreferrer"
            className={`flex items-center gap-1.5 text-xs text-stone-400 hover:text-stone-700 hover:bg-stone-100 rounded-lg px-2 py-1.5 w-full ${collapsed ? "justify-center" : ""}`}
          >
            <span aria-hidden="true">💡</span>{!collapsed && <span>Request an idea</span>}
          </a>
          <button
            onClick={() => setCollapsed(v => !v)}
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            className={`flex items-center gap-1.5 text-xs text-stone-400 hover:text-stone-700 hover:bg-stone-100 rounded-lg px-2 py-1.5 w-full ${collapsed ? "justify-center" : ""}`}
          >
            <span aria-hidden="true">{collapsed ? "›" : "‹"}</span>{!collapsed && <span aria-hidden="true">Collapse</span>}
          </button>
        </div>
      </aside>

      {/* Main area: topbar + content */}
      <div className="flex-1 min-h-0 flex flex-col">
        {/* Top bar */}
        <header className="shrink-0 h-11 bg-white border-b border-stone-200 flex items-center justify-end px-4 gap-3">
          {/* Org name label */}
          {orgName && <span className="text-xs text-stone-400 font-medium">{orgName}</span>}

          {/* Workspace switcher */}
          <WorkspaceSwitcher
            wsRef={wsRef}
            wsOpen={wsOpen}
            setWsOpen={setWsOpen}
            workspaces={workspaces}
            activeWorkspace={activeWorkspace}
            setActiveWorkspace={(ws) => { setActiveWorkspace(ws); setWsOpen(false); router.refresh() }}
            creatingTeam={creatingTeam}
            setCreatingTeam={setCreatingTeam}
            newTeamValue={newTeamValue}
            setNewTeamValue={setNewTeamValue}
            newTeamInputRef={newTeamInputRef}
            submitCreateTeam={submitCreateTeam}
            deletingTeamId={deletingTeamId}
            setDeletingTeamId={setDeletingTeamId}
            deleteConfirmValue={deleteConfirmValue}
            setDeleteConfirmValue={setDeleteConfirmValue}
            deleteConfirmRef={deleteConfirmRef}
            confirmDeleteTeam={confirmDeleteTeam}
          />

          {/* User avatar + menu */}
          <UserMenu
            userMenuRef={userMenuRef}
            userMenuOpen={userMenuOpen}
            setUserMenuOpen={setUserMenuOpen}
          />
        </header>

        {/* Page content */}
        <main className={`flex-1 min-h-0 ${noPadding ? "overflow-hidden flex flex-col" : "overflow-auto"}`}>
          <ErrorBoundary>{children}</ErrorBoundary>
        </main>
      </div>
    </div>
    {toast && <Toast message={toast.message} type={toast.type} onDismiss={() => setToast(null)} />}
    </PreferencesProvider>
  )
}

// ── Workspace Switcher (top-right) ────────────────────────────────────────────

interface WorkspaceSwitcherProps {
  wsRef: React.RefObject<HTMLDivElement>
  wsOpen: boolean
  setWsOpen: (v: boolean | ((v: boolean) => boolean)) => void
  workspaces: { id: string; name: string }[]
  activeWorkspace: { id: string; name: string } | null
  setActiveWorkspace: (ws: { id: string; name: string; owner_id: string; is_approved: boolean; workflow_count: number }) => void
  creatingTeam: boolean
  setCreatingTeam: (v: boolean) => void
  newTeamValue: string
  setNewTeamValue: (v: string) => void
  newTeamInputRef: React.RefObject<HTMLInputElement>
  submitCreateTeam: () => void
  deletingTeamId: string | null
  setDeletingTeamId: (id: string | null) => void
  deleteConfirmValue: string
  setDeleteConfirmValue: (v: string) => void
  deleteConfirmRef: React.RefObject<HTMLInputElement>
  confirmDeleteTeam: (ws: { id: string; name: string }) => void
}

function WorkspaceSwitcher({
  wsRef, wsOpen, setWsOpen,
  workspaces, activeWorkspace, setActiveWorkspace,
  creatingTeam, setCreatingTeam, newTeamValue, setNewTeamValue, newTeamInputRef, submitCreateTeam,
  deletingTeamId, setDeletingTeamId, deleteConfirmValue, setDeleteConfirmValue, deleteConfirmRef, confirmDeleteTeam,
}: WorkspaceSwitcherProps) {
  return (
    <div ref={wsRef} className="relative">
      <button
        onClick={() => setWsOpen(v => !v)}
        className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-sm font-medium text-stone-600 hover:text-stone-900 hover:bg-stone-100 transition-colors"
      >
        <span className="w-5 h-5 rounded-md bg-indigo-100 text-indigo-700 text-[10px] font-bold flex items-center justify-center shrink-0">
          {(activeWorkspace?.name ?? "T")[0].toUpperCase()}
        </span>
        <span className="max-w-[140px] truncate" title={activeWorkspace?.name}>
          {activeWorkspace?.name ?? "Select workspace"}
        </span>
        <span className="text-stone-400 text-[10px]">{wsOpen ? "▴" : "▾"}</span>
      </button>

      {wsOpen && (
        <div className="absolute z-50 top-full right-0 mt-1 w-56 bg-white border border-stone-200 rounded-xl shadow-lg py-1">
          <p className="px-3 py-1.5 text-[10px] font-semibold text-stone-400 uppercase tracking-wider">Workspaces</p>
          {workspaces.map(ws => (
            <div key={ws.id}>
              {deletingTeamId === ws.id ? (
                <div className="px-3 py-2 bg-red-50 border-y border-red-100">
                  <p className="text-xs text-red-700 mb-1.5">Type <strong>{ws.name}</strong> to confirm deletion</p>
                  <div className="flex gap-1.5">
                    <input
                      ref={deleteConfirmRef}
                      value={deleteConfirmValue}
                      onChange={e => setDeleteConfirmValue(e.target.value)}
                      onKeyDown={e => {
                        if (e.key === "Enter") confirmDeleteTeam(ws)
                        if (e.key === "Escape") { setDeletingTeamId(null); setDeleteConfirmValue("") }
                      }}
                      placeholder={ws.name}
                      className="flex-1 text-xs border border-red-200 rounded px-2 py-1 outline-none focus:ring-1 focus:ring-red-400"
                    />
                    <button
                      onClick={() => confirmDeleteTeam(ws)}
                      disabled={deleteConfirmValue !== ws.name}
                      className="text-xs px-2 py-1 rounded bg-red-600 text-white disabled:opacity-40 hover:bg-red-700"
                    >Delete</button>
                    <button
                      onClick={() => { setDeletingTeamId(null); setDeleteConfirmValue("") }}
                      className="text-xs px-2 py-1 rounded text-stone-500 hover:bg-stone-100"
                    >Cancel</button>
                  </div>
                </div>
              ) : (
                <div className="group flex items-center gap-1 px-3 hover:bg-stone-50">
                  <button
                    onClick={() => setActiveWorkspace(ws as Parameters<typeof setActiveWorkspace>[0])}
                    className={`flex-1 flex items-center gap-2 py-2 text-sm text-left ${ws.id === activeWorkspace?.id ? "font-semibold text-stone-900" : "text-stone-600"}`}
                  >
                    <span className="w-5 h-5 rounded-md bg-indigo-100 text-indigo-700 text-[10px] font-bold flex items-center justify-center shrink-0">
                      {ws.name[0].toUpperCase()}
                    </span>
                    <span className="flex-1 truncate" title={ws.name}>{ws.name}</span>
                    {ws.id === activeWorkspace?.id && <span className="text-indigo-500 text-xs">✓</span>}
                  </button>
                  <button
                    onClick={() => { setDeletingTeamId(ws.id); setDeleteConfirmValue("") }}
                    className="opacity-0 group-hover:opacity-100 text-stone-300 hover:text-red-500 transition-all text-xs px-1"
                    title="Delete workspace"
                    aria-label="Delete workspace"
                  ><span aria-hidden="true">🗑</span></button>
                </div>
              )}
            </div>
          ))}
          <div className="border-t border-stone-100 mt-1 pt-1 px-3">
            {creatingTeam ? (
              <input
                ref={newTeamInputRef}
                value={newTeamValue}
                onChange={e => setNewTeamValue(e.target.value)}
                onBlur={submitCreateTeam}
                onKeyDown={e => { if (e.key === "Enter") submitCreateTeam(); if (e.key === "Escape") { setCreatingTeam(false); setNewTeamValue("") } }}
                placeholder="Workspace name"
                className="w-full text-sm border border-stone-200 rounded-lg px-2 py-1.5 outline-none focus:ring-2 focus:ring-indigo-200"
              />
            ) : (
              <button
                onClick={() => setCreatingTeam(true)}
                className="w-full flex items-center gap-2 py-2 text-xs text-stone-500 hover:text-stone-800"
              >
                <span>＋</span> New workspace
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

// ── User Menu (top-right) ─────────────────────────────────────────────────────

function UserMenu({
  userMenuRef,
  userMenuOpen,
  setUserMenuOpen,
}: {
  userMenuRef: React.RefObject<HTMLDivElement>
  userMenuOpen: boolean
  setUserMenuOpen: (v: boolean | ((v: boolean) => boolean)) => void
}) {
  const clerkEnabled = !!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY
  if (!clerkEnabled) return null
  return <UserMenuInner userMenuRef={userMenuRef} userMenuOpen={userMenuOpen} setUserMenuOpen={setUserMenuOpen} />
}

function UserMenuInner({
  userMenuRef,
  userMenuOpen,
  setUserMenuOpen,
}: {
  userMenuRef: React.RefObject<HTMLDivElement>
  userMenuOpen: boolean
  setUserMenuOpen: (v: boolean | ((v: boolean) => boolean)) => void
}) {
  const { user } = useUser()
  const { signOut } = useClerk()
  const router = useRouter()

  const email = user?.primaryEmailAddress?.emailAddress ?? ""
  const firstName = user?.firstName ?? ""
  const lastName = user?.lastName ?? ""
  const initials = firstName && lastName
    ? `${firstName[0]}${lastName[0]}`.toUpperCase()
    : email
    ? email[0].toUpperCase()
    : "?"

  // Use Clerk avatar if available, else initials
  const avatarUrl = user?.imageUrl

  return (
    <div ref={userMenuRef} className="relative">
      <button
        onClick={() => setUserMenuOpen(v => !v)}
        title={email}
        className="w-7 h-7 rounded-full overflow-hidden bg-violet-600 text-white text-[11px] font-bold flex items-center justify-center hover:ring-2 hover:ring-violet-300 transition-all"
      >
        {avatarUrl
          ? <img src={avatarUrl} alt={initials} className="w-full h-full object-cover" />
          : initials}
      </button>

      {userMenuOpen && (
        <div className="absolute z-50 top-full right-0 mt-1 w-52 bg-white border border-stone-200 rounded-xl shadow-lg py-1">
          {email && (
            <>
              <div className="px-3 py-2">
                {(firstName || lastName) && (
                  <p className="text-sm font-medium text-stone-800 truncate">{[firstName, lastName].filter(Boolean).join(" ")}</p>
                )}
                <p className="text-[11px] text-stone-500 truncate">{email}</p>
              </div>
              <div className="border-t border-stone-100 my-1" />
            </>
          )}
          <Link
            href="/settings"
            onClick={() => setUserMenuOpen(false)}
            className="block px-3 py-2 text-sm text-stone-600 hover:bg-stone-50 hover:text-stone-900 transition-colors"
          >
            Settings
          </Link>
          <div className="border-t border-stone-100 my-1" />
          <button
            onClick={() => { setUserMenuOpen(false); signOut(() => router.push("/sign-in")) }}
            className="w-full text-left px-3 py-2 text-sm text-stone-600 hover:bg-stone-50 hover:text-stone-900 transition-colors"
          >
            Sign out
          </button>
        </div>
      )}
    </div>
  )
}

// ── NavItem ───────────────────────────────────────────────────────────────────

function NavItem({
  href, icon, label, collapsed, pathname, exact,
}: {
  href: string
  icon: string
  label: string
  collapsed: boolean
  pathname: string
  exact?: boolean
}) {
  const active = exact ? pathname === href : pathname.startsWith(href)
  return (
    <Link
      href={href}
      aria-label={collapsed ? label : undefined}
      title={collapsed ? label : undefined}
      className={`flex items-center gap-2.5 px-2 py-2 rounded-lg text-sm font-medium transition-colors ${collapsed ? "justify-center" : ""} ${active ? "bg-stone-100 text-stone-900" : "text-stone-500 hover:text-stone-800 hover:bg-stone-50"}`}
    >
      {icon && <span aria-hidden="true" className="text-base leading-none shrink-0">{icon}</span>}
      {!collapsed && label}
    </Link>
  )
}
