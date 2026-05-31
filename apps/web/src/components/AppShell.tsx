"use client"

import { useState, useRef, useEffect, useCallback } from "react"
import Link from "next/link"
import { usePathname, useRouter } from "next/navigation"
import { useAuth } from "@clerk/nextjs"
import AuthButton from "@/components/AuthButton"
import { WorkspaceProvider, useWorkspace } from "@/lib/WorkspaceContext"
import { PreferencesProvider } from "@/lib/PreferencesContext"
import Toast, { type ToastData } from "@/components/ui/Toast"
import ErrorBoundary from "@/components/ui/ErrorBoundary"

interface Project { id: string; name: string; agent_count: number }
interface Org { id: string; name: string; slug: string }

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
  const { getToken } = useAuth()
  const [collapsed, setCollapsed] = useState(false)
  const [toast, setToast] = useState<ToastData | null>(null)
  function showError(message: string) { setToast({ message, type: "error" }) }
  function showSuccess(message: string) { setToast({ message, type: "success" }) }

  // Org state (lives at bottom)
  const [orgs, setOrgs] = useState<Org[]>([])
  const [activeOrg, setActiveOrg] = useState<Org | null>(null)
  const [orgOpen, setOrgOpen] = useState(false)
  const [orgRenaming, setOrgRenaming] = useState(false)
  const [orgNameValue, setOrgNameValue] = useState("")
  const [creatingOrg, setCreatingOrg] = useState(false)
  const [newOrgValue, setNewOrgValue] = useState("")
  const orgRef = useRef<HTMLDivElement>(null)
  const orgInputRef = useRef<HTMLInputElement>(null)
  const newOrgInputRef = useRef<HTMLInputElement>(null)

  // Team state
  const [teamOpen, setTeamOpen] = useState(false)
  const [teamRenaming, setTeamRenaming] = useState(false)
  const [teamNameValue, setTeamNameValue] = useState("")
  const [creatingTeam, setCreatingTeam] = useState(false)
  const [newTeamValue, setNewTeamValue] = useState("")
  const [deletingTeamId, setDeletingTeamId] = useState<string | null>(null)
  const [deleteConfirmValue, setDeleteConfirmValue] = useState("")
  const teamRef = useRef<HTMLDivElement>(null)
  const teamInputRef = useRef<HTMLInputElement>(null)
  const newTeamInputRef = useRef<HTMLInputElement>(null)
  const deleteConfirmRef = useRef<HTMLInputElement>(null)
  const { workspaces, activeWorkspace, setActiveWorkspace, refresh: refreshWorkspaces } = useWorkspace()

  // Guard install state — re-checked whenever the active workspace changes
  const [guardInstalled, setGuardInstalled] = useState(false)

  useEffect(() => {
    let cancelled = false
    async function checkGuardInstall() {
      const wsId = activeWorkspace?.id
      if (!wsId) return
      try {
        const h: Record<string, string> = {}
        if (getToken) { const t = await getToken(); if (t) h["Authorization"] = `Bearer ${t}` }
        const res = await fetch(
          `${process.env.NEXT_PUBLIC_API_URL}/guard/teams/installed?workspace_id=${wsId}`,
          { headers: h }
        )
        if (!cancelled && res.ok) {
          const data = await res.json()
          setGuardInstalled(!!data.installed)
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

  // Projects state
  const [projects, setProjects] = useState<Project[]>([])
  const [projectsOpen, setProjectsOpen] = useState(true)
  const [renamingProjectId, setRenamingProjectId] = useState<string | null>(null)
  const [renameValue, setRenameValue] = useState("")
  const [creatingProject, setCreatingProject] = useState(false)
  const [newProjectValue, setNewProjectValue] = useState("")
  const renameInputRef = useRef<HTMLInputElement>(null)
  const newProjectInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    function handle(e: MouseEvent) {
      if (orgRef.current && !orgRef.current.contains(e.target as Node)) {
        setOrgOpen(false); setOrgRenaming(false); setCreatingOrg(false)
      }
      if (teamRef.current && !teamRef.current.contains(e.target as Node)) {
        setTeamOpen(false); setTeamRenaming(false); setCreatingTeam(false)
        setDeletingTeamId(null); setDeleteConfirmValue("")
      }
    }
    document.addEventListener("mousedown", handle)
    return () => document.removeEventListener("mousedown", handle)
  }, [])

  useEffect(() => { if (orgRenaming) orgInputRef.current?.focus() }, [orgRenaming])
  useEffect(() => { if (creatingOrg) newOrgInputRef.current?.focus() }, [creatingOrg])
  useEffect(() => { if (teamRenaming) teamInputRef.current?.focus() }, [teamRenaming])
  useEffect(() => { if (creatingTeam) newTeamInputRef.current?.focus() }, [creatingTeam])
  useEffect(() => { if (deletingTeamId) deleteConfirmRef.current?.focus() }, [deletingTeamId])
  useEffect(() => { if (renamingProjectId) renameInputRef.current?.focus() }, [renamingProjectId])
  useEffect(() => { if (creatingProject) newProjectInputRef.current?.focus() }, [creatingProject])

  async function headers(wsId?: string): Promise<Record<string, string>> {
    const h: Record<string, string> = {}
    if (getToken) { const t = await getToken(); if (t) h["Authorization"] = `Bearer ${t}` }
    const id = wsId ?? activeWorkspace?.id
    if (id) h["X-Workspace-ID"] = id
    return h
  }

  const fetchOrgs = useCallback(async () => {
    try {
      const h = await headers()
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/organizations`, { headers: h })
      if (!res.ok) return
      const data: Org[] = await res.json()
      setOrgs(data)
      if (data.length > 0) setActiveOrg(prev => prev ?? data[0])
    } catch {}
  }, [activeWorkspace])

  const fetchProjects = useCallback(async () => {
    if (!activeWorkspace) return
    try {
      const h = await headers()
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/workspaces/${activeWorkspace.id}/projects`, { headers: h })
      if (!res.ok) return
      const data = await res.json()
      setProjects(Array.isArray(data) ? data : [])
    } catch {}
  }, [activeWorkspace])

  useEffect(() => { fetchOrgs() }, [fetchOrgs])
  useEffect(() => { fetchProjects() }, [fetchProjects])

  async function saveOrgRename() {
    setOrgRenaming(false)
    if (!orgNameValue.trim() || !activeOrg || orgNameValue === activeOrg.name) return
    try {
      const h = await headers()
      h["Content-Type"] = "application/json"
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/organizations/${activeOrg.id}`, {
        method: "PATCH", headers: h, body: JSON.stringify({ name: orgNameValue.trim() })
      })
      if (res.ok) { const updated = await res.json(); setActiveOrg(updated); fetchOrgs() }
      else showError("Could not rename organisation — please try again.")
    } catch { showError("Could not rename organisation — check your connection.") }
  }

  async function submitCreateOrg() {
    const name = newOrgValue.trim()
    setCreatingOrg(false); setNewOrgValue("")
    if (!name) return
    try {
      const h = await headers()
      h["Content-Type"] = "application/json"
      const slug = name.toLowerCase().replace(/\s+/g, "-") + "-" + Math.random().toString(36).slice(2, 6)
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/organizations`, {
        method: "POST", headers: h, body: JSON.stringify({ name, slug })
      })
      if (res.ok) { const org = await res.json(); setActiveOrg(org); fetchOrgs() }
      else showError("Could not create organisation — please try again.")
    } catch { showError("Could not create organisation — check your connection.") }
    setOrgOpen(false)
  }

  async function saveTeamRename() {
    setTeamRenaming(false)
    if (!teamNameValue.trim() || !activeWorkspace || teamNameValue === activeWorkspace.name) return
    try {
      const h = await headers()
      h["Content-Type"] = "application/json"
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/projects/${activeWorkspace.id}`, {
        method: "PATCH", headers: h, body: JSON.stringify({ name: teamNameValue.trim() })
      })
      if (res.ok) refreshWorkspaces()
      else showError("Could not rename team — please try again.")
    } catch { showError("Could not rename team — check your connection.") }
  }

  async function submitCreateTeam() {
    const name = newTeamValue.trim()
    setCreatingTeam(false); setNewTeamValue("")
    if (!name) return
    try {
      const h = await headers()
      h["Content-Type"] = "application/json"
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/projects`, {
        method: "POST", headers: h, body: JSON.stringify({ name })
      })
      if (res.ok) { setTeamOpen(false); refreshWorkspaces() }
      else showError("Could not create team — please try again.")
    } catch { showError("Could not create team — check your connection.") }
  }

  async function confirmDeleteTeam(ws: { id: string; name: string }) {
    if (deleteConfirmValue !== ws.name) return
    setDeletingTeamId(null); setDeleteConfirmValue("")
    try {
      const h = await headers()
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
      const h = await headers()
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
      const h = await headers()
      h["Content-Type"] = "application/json"
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/workspaces/${activeWorkspace.id}/projects/${projectId}`, {
        method: "PATCH", headers: h, body: JSON.stringify({ name })
      })
      if (res.ok) fetchProjects()
      else showError("Could not rename project — please try again.")
    } catch { showError("Could not rename project — check your connection.") }
  }

  const activeProjectId = pathname.match(/\/projects\/([^/]+)/)?.[1]

  return (
    <PreferencesProvider workspaceId={activeWorkspace?.id ?? ""} getToken={getToken}>
    <div className="flex h-screen bg-stone-50">
      <aside className={`relative shrink-0 bg-white border-r border-stone-200 flex flex-col transition-all duration-200 ${collapsed ? "w-14" : "w-52"}`}>

        {/* Logo */}
        <div className={`px-3 py-3 border-b border-stone-100 flex items-center ${collapsed ? "justify-center" : ""}`}>
          <Link href="/dashboard">
            {collapsed
              ? <img src="/icon.png" alt="Conduct AI" className="w-7 h-7" />
              : <img src="/logo.png" alt="Conduct AI" className="h-9 w-auto" />}
          </Link>
        </div>

        {/* Team switcher */}
        <div ref={teamRef} className="relative border-b border-stone-100">
          <div className={`flex items-center gap-1 px-2 py-2 group ${collapsed ? "justify-center" : ""}`}>
            <span className="w-5 h-5 rounded-md bg-indigo-100 text-indigo-700 text-[10px] font-bold flex items-center justify-center shrink-0">
              {(activeWorkspace?.name ?? "T")[0].toUpperCase()}
            </span>
            {!collapsed && (
              teamRenaming ? (
                <input
                  ref={teamInputRef}
                  value={teamNameValue}
                  onChange={e => setTeamNameValue(e.target.value)}
                  onBlur={saveTeamRename}
                  onKeyDown={e => { if (e.key === "Enter") saveTeamRename(); if (e.key === "Escape") setTeamRenaming(false) }}
                  className="flex-1 text-sm font-medium text-stone-900 bg-transparent border-b border-indigo-400 outline-none"
                />
              ) : (
                <button
                  onClick={() => setTeamOpen(v => !v)}
                  className="flex-1 flex items-center gap-1 text-sm font-medium text-stone-700 hover:text-stone-500 text-left"
                >
                  <span className="truncate" title={activeWorkspace?.name}>{activeWorkspace?.name ?? "Team"}</span>
                  <span className="text-stone-400 text-[10px] shrink-0">{teamOpen ? "▴" : "▾"}</span>
                </button>
              )
            )}
            {!collapsed && !teamRenaming && (
              <button
                onClick={() => { setTeamNameValue(activeWorkspace?.name ?? ""); setTeamRenaming(true) }}
                className="shrink-0 p-0.5 text-stone-300 hover:text-stone-600 text-xs opacity-0 group-hover:opacity-100 transition-opacity"
                title="Rename team"
              >✎</button>
            )}
          </div>

          {teamOpen && (
            <div className={`absolute z-50 bg-white border border-stone-200 rounded-xl shadow-lg py-1 ${collapsed ? "left-14 top-0 w-48" : "left-2 right-2 top-full"}`}>
              <p className="px-3 py-1.5 text-[10px] font-semibold text-stone-400 uppercase tracking-wider">Teams</p>
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
                        onClick={() => { setActiveWorkspace(ws); setTeamOpen(false); setProjects([]); router.refresh() }}
                        className={`flex-1 flex items-center gap-2 py-2 text-sm text-left ${ws.id === activeWorkspace?.id ? "font-semibold text-stone-900" : "text-stone-600"}`}
                      >
                        <span className="w-5 h-5 rounded-md bg-indigo-100 text-indigo-700 text-[10px] font-bold flex items-center justify-center shrink-0">
                          {ws.name[0].toUpperCase()}
                        </span>
                        <span className="flex-1 truncate" title={ws.name}>{ws.name}</span>
                        {ws.id === activeWorkspace?.id && <span className="text-indigo-500">✓</span>}
                      </button>
                      <button
                        onClick={() => { setDeletingTeamId(ws.id); setDeleteConfirmValue("") }}
                        className="opacity-0 group-hover:opacity-100 text-stone-300 hover:text-red-500 transition-all text-xs px-1"
                        title="Delete team"
                        aria-label="Delete team"
                      ><span aria-hidden="true">🗑</span></button>
                    </div>
                  )}
                </div>
              ))}
              <div className="border-t border-stone-100 mt-1 pt-1 px-3">
                {creatingTeam ? (
                  <input ref={newTeamInputRef} value={newTeamValue}
                    onChange={e => setNewTeamValue(e.target.value)}
                    onBlur={submitCreateTeam}
                    onKeyDown={e => { if (e.key === "Enter") submitCreateTeam(); if (e.key === "Escape") { setCreatingTeam(false); setNewTeamValue("") } }}
                    placeholder="Team name"
                    className="w-full text-sm border border-stone-200 rounded-lg px-2 py-1.5 outline-none focus:ring-2 focus:ring-indigo-200"
                  />
                ) : (
                  <button onClick={() => setCreatingTeam(true)}
                    className="w-full flex items-center gap-2 py-2 text-xs text-stone-500 hover:text-stone-800"
                  >
                    <span>＋</span> New team
                  </button>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Nav */}
        <nav className="flex-1 px-2 py-3 overflow-y-auto space-y-0.5">
          <NavItem href="/dashboard" icon="◎" label="Dashboard" collapsed={collapsed} pathname={pathname} />
          <NavItem href="/marketplace" icon="📦" label="Playbooks" collapsed={collapsed} pathname={pathname} />
          <NavItem href="/eval" icon="◈" label="Quality" collapsed={collapsed} pathname={pathname} />
          <NavItem href="/benchmark" icon="▲" label="Benchmark" collapsed={collapsed} pathname={pathname} />

          <div className="pt-3">
            {!collapsed && (
              <button onClick={() => setProjectsOpen(v => !v)}
                className="w-full flex items-center justify-between px-2 mb-1 text-[10px] font-semibold text-stone-400 uppercase tracking-wider hover:text-stone-600"
              >
                <span>Projects</span>
                <span>{projectsOpen ? "▾" : "›"}</span>
              </button>
            )}
            {(projectsOpen || collapsed) && (
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
                        <input ref={renameInputRef} value={renameValue}
                          onChange={e => setRenameValue(e.target.value)}
                          onBlur={() => submitProjectRename(project.id)}
                          onKeyDown={e => { if (e.key === "Enter") submitProjectRename(project.id); if (e.key === "Escape") setRenamingProjectId(null) }}
                          className="flex-1 text-sm bg-transparent border-b border-indigo-400 outline-none"
                        />
                      ) : (
                        <>
                          <Link href={`/projects/${project.id}`} title={project.name} className={`flex-1 text-sm truncate ${isActive ? "font-semibold text-stone-900" : "text-stone-600"}`}>
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
                {!collapsed && (
                  creatingProject ? (
                    <div className="px-2 py-1">
                      <input ref={newProjectInputRef} value={newProjectValue}
                        onChange={e => setNewProjectValue(e.target.value)}
                        onBlur={submitCreateProject}
                        onKeyDown={e => { if (e.key === "Enter") submitCreateProject(); if (e.key === "Escape") { setCreatingProject(false); setNewProjectValue("") } }}
                        placeholder="Project name"
                        className="w-full text-sm border border-stone-200 rounded-lg px-2 py-1.5 outline-none focus:ring-2 focus:ring-indigo-200"
                      />
                    </div>
                  ) : (
                    <button onClick={() => setCreatingProject(true)}
                      className="w-full flex items-center gap-2 px-2 py-1.5 rounded-lg text-xs text-stone-400 hover:text-stone-600 hover:bg-stone-50"
                    >
                      <span>＋</span> New project
                    </button>
                  )
                )}
              </div>
            )}
          </div>

          <div className="pt-2 border-t border-stone-100 mt-2 space-y-0.5">
            <NavItem href="/runs" icon="▶" label="Runs" collapsed={collapsed} pathname={pathname} />
            <NavItem href="/observability" icon="◉" label="Observability" collapsed={collapsed} pathname={pathname} />
            {guardInstalled && (
              <NavItem href="/guard" icon="🛡" label="Guard" collapsed={collapsed} pathname={pathname} />
            )}
            <NavItem href="/audit" icon="📋" label="Audit Log" collapsed={collapsed} pathname={pathname} />
            <NavItem href="/settings" icon="⚙" label="Settings" collapsed={collapsed} pathname={pathname} />
          </div>
        </nav>

        {/* Bottom: Org switcher + user */}
        <div className="border-t border-stone-100">
          {/* Org row */}
          <div ref={orgRef} className="relative">
            <div className={`flex items-center gap-1.5 px-2 py-2 group ${collapsed ? "justify-center" : ""}`}>
              <span className="w-6 h-6 rounded-md bg-violet-100 text-violet-700 text-[10px] font-bold flex items-center justify-center shrink-0">
                {(activeOrg?.name ?? "O")[0].toUpperCase()}
              </span>
              {!collapsed && (
                orgRenaming ? (
                  <input
                    ref={orgInputRef}
                    value={orgNameValue}
                    onChange={e => setOrgNameValue(e.target.value)}
                    onBlur={saveOrgRename}
                    onKeyDown={e => { if (e.key === "Enter") saveOrgRename(); if (e.key === "Escape") setOrgRenaming(false) }}
                    className="flex-1 text-sm font-medium text-stone-900 bg-transparent border-b border-violet-400 outline-none"
                  />
                ) : (
                  <button
                    onClick={() => setOrgOpen(v => !v)}
                    className="flex-1 flex items-center gap-1 text-sm font-medium text-stone-700 hover:text-stone-500 text-left truncate"
                  >
                    <span className="truncate" title={activeOrg?.name}>{activeOrg?.name ?? "Organisation"}</span>
                    <span className="text-stone-400 text-[10px] shrink-0">{orgOpen ? "▴" : "▾"}</span>
                  </button>
                )
              )}
              {!collapsed && !orgRenaming && (
                <button
                  onClick={() => { setOrgNameValue(activeOrg?.name ?? ""); setOrgRenaming(true) }}
                  className="shrink-0 p-0.5 text-stone-300 hover:text-stone-600 text-xs opacity-0 group-hover:opacity-100 transition-opacity"
                  title="Rename org"
                >✎</button>
              )}
            </div>

            {orgOpen && (
              <div className="absolute z-50 bottom-full left-2 right-2 mb-1 bg-white border border-stone-200 rounded-xl shadow-lg py-1">
                <p className="px-3 py-1.5 text-[10px] font-semibold text-stone-400 uppercase tracking-wider">Organizations</p>
                {orgs.map(org => (
                  <button key={org.id}
                    onClick={() => { setActiveOrg(org); setOrgOpen(false) }}
                    className={`w-full flex items-center gap-2 px-3 py-2 text-sm text-left hover:bg-stone-50 ${org.id === activeOrg?.id ? "font-semibold text-stone-900" : "text-stone-600"}`}
                  >
                    <span className="w-5 h-5 rounded-md bg-violet-100 text-violet-700 text-[10px] font-bold flex items-center justify-center shrink-0">
                      {org.name[0].toUpperCase()}
                    </span>
                    <span className="flex-1 truncate" title={org.name}>{org.name}</span>
                    {org.id === activeOrg?.id && <span className="text-violet-500">✓</span>}
                  </button>
                ))}
                <div className="border-t border-stone-100 mt-1 pt-1 px-3">
                  {creatingOrg ? (
                    <input ref={newOrgInputRef} value={newOrgValue}
                      onChange={e => setNewOrgValue(e.target.value)}
                      onBlur={submitCreateOrg}
                      onKeyDown={e => { if (e.key === "Enter") submitCreateOrg(); if (e.key === "Escape") { setCreatingOrg(false); setNewOrgValue("") } }}
                      placeholder="Organization name"
                      className="w-full text-sm border border-stone-200 rounded-lg px-2 py-1.5 outline-none focus:ring-2 focus:ring-violet-200"
                    />
                  ) : (
                    <button onClick={() => setCreatingOrg(true)}
                      className="w-full flex items-center gap-2 py-2 text-xs text-stone-500 hover:text-stone-800"
                    >
                      <span>＋</span> New organization
                    </button>
                  )}
                </div>
              </div>
            )}
          </div>

          {/* User / sign out */}
          <div className={`px-2 pb-3 flex ${collapsed ? "justify-center" : ""}`}>
            <AuthButton afterSignOutUrl="/sign-in" dropUp />
          </div>
        </div>

        {/* Collapse toggle + idea link */}
        <div className="border-t border-stone-100 px-2 py-2 space-y-0.5">
          <a href="https://github.com/sseshachala/conductai/discussions/new?category=ideas" target="_blank" rel="noopener noreferrer"
            className={`flex items-center gap-1.5 text-xs text-stone-400 hover:text-stone-700 hover:bg-stone-100 rounded-lg px-2 py-1.5 w-full ${collapsed ? "justify-center" : ""}`}>
            <span aria-hidden="true">💡</span>{!collapsed && <span>Request an idea</span>}
          </a>
          <button onClick={() => setCollapsed(v => !v)}
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            className={`flex items-center gap-1.5 text-xs text-stone-400 hover:text-stone-700 hover:bg-stone-100 rounded-lg px-2 py-1.5 w-full ${collapsed ? "justify-center" : ""}`}>
            <span aria-hidden="true">{collapsed ? "›" : "‹"}</span>{!collapsed && <span aria-hidden="true">Collapse</span>}
          </button>
        </div>
      </aside>

      <main className={`flex-1 min-h-0 ${noPadding ? "overflow-hidden flex flex-col" : "overflow-auto"}`}>
        <ErrorBoundary>{children}</ErrorBoundary>
      </main>
    </div>
    {toast && <Toast message={toast.message} type={toast.type} onDismiss={() => setToast(null)} />}
    </PreferencesProvider>
  )
}

function NavItem({ href, icon, label, collapsed, pathname }: { href: string; icon: string; label: string; collapsed: boolean; pathname: string }) {
  const active = pathname.startsWith(href)
  return (
    <Link
      href={href}
      aria-label={collapsed ? label : undefined}
      title={collapsed ? label : undefined}
      className={`flex items-center gap-2.5 px-2 py-2 rounded-lg text-sm font-medium transition-colors ${collapsed ? "justify-center" : ""} ${active ? "bg-stone-100 text-stone-900" : "text-stone-500 hover:text-stone-800 hover:bg-stone-50"}`}
    >
      <span aria-hidden="true" className="text-base leading-none shrink-0">{icon}</span>
      {!collapsed && label}
    </Link>
  )
}
