"use client"

import { useState, useRef, useEffect, useCallback } from "react"
import Link from "next/link"
import { usePathname, useRouter } from "next/navigation"
import { useAuth } from "@clerk/nextjs"
import AuthButton from "@/components/AuthButton"
import { WorkspaceProvider, useWorkspace } from "@/lib/WorkspaceContext"

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

  // Org state
  const [orgs, setOrgs] = useState<Org[]>([])
  const [activeOrg, setActiveOrg] = useState<Org | null>(null)
  const [orgOpen, setOrgOpen] = useState(false)
  const [orgRenaming, setOrgRenaming] = useState(false)
  const [orgNameValue, setOrgNameValue] = useState("")
  const orgRef = useRef<HTMLDivElement>(null)
  const orgInputRef = useRef<HTMLInputElement>(null)

  // Team state
  const [teamOpen, setTeamOpen] = useState(false)
  const teamRef = useRef<HTMLDivElement>(null)
  const { workspaces, activeWorkspace, setActiveWorkspace, refresh: refreshWorkspaces } = useWorkspace()

  // Projects state
  const [projects, setProjects] = useState<Project[]>([])
  const [projectsOpen, setProjectsOpen] = useState(true)
  const [renamingProjectId, setRenamingProjectId] = useState<string | null>(null)
  const [renameValue, setRenameValue] = useState("")
  const renameInputRef = useRef<HTMLInputElement>(null)

  // Close dropdowns on outside click
  useEffect(() => {
    function handle(e: MouseEvent) {
      if (orgRef.current && !orgRef.current.contains(e.target as Node)) setOrgOpen(false)
      if (teamRef.current && !teamRef.current.contains(e.target as Node)) setTeamOpen(false)
    }
    document.addEventListener("mousedown", handle)
    return () => document.removeEventListener("mousedown", handle)
  }, [])

  useEffect(() => { if (orgRenaming) orgInputRef.current?.focus() }, [orgRenaming])
  useEffect(() => { if (renamingProjectId) renameInputRef.current?.focus() }, [renamingProjectId])

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
    const h = await headers()
    h["Content-Type"] = "application/json"
    const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/organizations/${activeOrg.id}`, {
      method: "PATCH", headers: h, body: JSON.stringify({ name: orgNameValue.trim() })
    })
    if (res.ok) { const updated = await res.json(); setActiveOrg(updated); fetchOrgs() }
  }

  async function createTeam() {
    const name = prompt("Team name:")
    if (!name?.trim()) return
    const h = await headers()
    h["Content-Type"] = "application/json"
    await fetch(`${process.env.NEXT_PUBLIC_API_URL}/projects`, {
      method: "POST", headers: h, body: JSON.stringify({ name: name.trim() })
    })
    setTeamOpen(false)
    refreshWorkspaces()
  }

  async function renameTeam() {
    if (!activeWorkspace) return
    const name = prompt("Team name:", activeWorkspace.name)
    if (!name?.trim() || name === activeWorkspace.name) return
    const h = await headers()
    h["Content-Type"] = "application/json"
    await fetch(`${process.env.NEXT_PUBLIC_API_URL}/projects/${activeWorkspace.id}`, {
      method: "PATCH", headers: h, body: JSON.stringify({ name: name.trim() })
    })
    refreshWorkspaces()
  }

  async function createProject() {
    const name = prompt("Project name:")
    if (!name?.trim() || !activeWorkspace) return
    const h = await headers()
    h["Content-Type"] = "application/json"
    await fetch(`${process.env.NEXT_PUBLIC_API_URL}/workspaces/${activeWorkspace.id}/projects`, {
      method: "POST", headers: h, body: JSON.stringify({ name: name.trim() })
    })
    fetchProjects()
  }

  async function submitProjectRename(projectId: string) {
    const name = renameValue.trim()
    setRenamingProjectId(null)
    if (!name || !activeWorkspace) return
    const h = await headers()
    h["Content-Type"] = "application/json"
    await fetch(`${process.env.NEXT_PUBLIC_API_URL}/workspaces/${activeWorkspace.id}/projects/${projectId}`, {
      method: "PATCH", headers: h, body: JSON.stringify({ name })
    })
    fetchProjects()
  }

  const activeProjectId = pathname.match(/\/projects\/([^/]+)/)?.[1]

  return (
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

        {/* Org switcher — GitHub style */}
        <div ref={orgRef} className="relative border-b border-stone-100">
          <div className={`flex items-center gap-1 px-2 py-2 ${collapsed ? "justify-center" : ""}`}>
            <span className="w-5 h-5 rounded-md bg-violet-100 text-violet-700 text-[10px] font-bold flex items-center justify-center shrink-0">
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
                  className="flex-1 text-sm font-semibold text-stone-900 bg-transparent border-b border-violet-400 outline-none"
                />
              ) : (
                <button
                  onClick={() => setOrgOpen(v => !v)}
                  onDoubleClick={() => { setOrgNameValue(activeOrg?.name ?? ""); setOrgRenaming(true) }}
                  className="flex-1 flex items-center gap-1 text-sm font-semibold text-stone-800 hover:text-stone-600 text-left"
                  title="Click to switch · Double-click to rename"
                >
                  <span className="truncate">{activeOrg?.name ?? "Organization"}</span>
                  <span className="text-stone-400 text-[10px] shrink-0">{orgOpen ? "▴" : "▾"}</span>
                </button>
              )
            )}

            {!collapsed && !orgRenaming && (
              <button
                onClick={() => { setOrgNameValue(activeOrg?.name ?? ""); setOrgRenaming(true) }}
                className="shrink-0 p-0.5 text-stone-300 hover:text-stone-600 text-xs opacity-0 group-hover:opacity-100 transition-opacity"
                title="Rename organization"
              >✎</button>
            )}
          </div>

          {orgOpen && orgs.length > 0 && (
            <div className="absolute z-50 left-2 right-2 top-full bg-white border border-stone-200 rounded-xl shadow-lg py-1">
              <p className="px-3 py-1.5 text-[10px] font-semibold text-stone-400 uppercase tracking-wider">Organizations</p>
              {orgs.map(org => (
                <button
                  key={org.id}
                  onClick={() => { setActiveOrg(org); setOrgOpen(false) }}
                  className={`w-full flex items-center gap-2 px-3 py-2 text-sm text-left hover:bg-stone-50 ${org.id === activeOrg?.id ? "font-semibold text-stone-900" : "text-stone-600"}`}
                >
                  <span className="w-5 h-5 rounded-md bg-violet-100 text-violet-700 text-[10px] font-bold flex items-center justify-center shrink-0">
                    {org.name[0].toUpperCase()}
                  </span>
                  <span className="flex-1 truncate">{org.name}</span>
                  {org.id === activeOrg?.id && <span className="text-violet-500">✓</span>}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Team switcher */}
        <div ref={teamRef} className="relative border-b border-stone-100">
          <div className={`flex items-center gap-1 px-2 py-2 group ${collapsed ? "justify-center" : ""}`}>
            <span className="w-5 h-5 rounded-md bg-indigo-100 text-indigo-700 text-[10px] font-bold flex items-center justify-center shrink-0">
              {(activeWorkspace?.name ?? "T")[0].toUpperCase()}
            </span>

            {!collapsed && (
              <button
                onClick={() => setTeamOpen(v => !v)}
                className="flex-1 flex items-center gap-1 text-sm font-medium text-stone-700 hover:text-stone-500 text-left"
                title="Switch team"
              >
                <span className="truncate">{activeWorkspace?.name ?? "Team"}</span>
                <span className="text-stone-400 text-[10px] shrink-0">{teamOpen ? "▴" : "▾"}</span>
              </button>
            )}

            {!collapsed && (
              <button onClick={renameTeam} className="shrink-0 p-0.5 text-stone-300 hover:text-stone-600 text-xs" title="Rename team">✎</button>
            )}
          </div>

          {teamOpen && (
            <div className={`absolute z-50 bg-white border border-stone-200 rounded-xl shadow-lg py-1 ${collapsed ? "left-14 top-0 w-48" : "left-2 right-2 top-full"}`}>
              <p className="px-3 py-1.5 text-[10px] font-semibold text-stone-400 uppercase tracking-wider">Teams</p>
              {workspaces.map(ws => (
                <button
                  key={ws.id}
                  onClick={() => { setActiveWorkspace(ws); setTeamOpen(false); setProjects([]); router.refresh() }}
                  className={`w-full flex items-center gap-2 px-3 py-2 text-sm text-left hover:bg-stone-50 ${ws.id === activeWorkspace?.id ? "font-semibold text-stone-900" : "text-stone-600"}`}
                >
                  <span className="w-5 h-5 rounded-md bg-indigo-100 text-indigo-700 text-[10px] font-bold flex items-center justify-center shrink-0">
                    {ws.name[0].toUpperCase()}
                  </span>
                  <span className="flex-1 truncate">{ws.name}</span>
                  {ws.id === activeWorkspace?.id && <span className="text-indigo-500">✓</span>}
                </button>
              ))}
              <div className="border-t border-stone-100 mt-1 pt-1">
                <button onClick={createTeam} className="w-full flex items-center gap-2 px-3 py-2 text-xs text-stone-500 hover:bg-stone-50 hover:text-stone-800">
                  <span>＋</span> New team
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Nav */}
        <nav className="flex-1 px-2 py-3 overflow-y-auto space-y-0.5">
          <NavItem href="/dashboard" icon="◎" label="Dashboard" collapsed={collapsed} pathname={pathname} />
          <NavItem href="/marketplace" icon="📦" label="Playbooks" collapsed={collapsed} pathname={pathname} />

          {/* Projects */}
          <div className="pt-3">
            {!collapsed && (
              <button
                onClick={() => setProjectsOpen(v => !v)}
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
                          <Link href={`/projects/${project.id}`} className={`flex-1 text-sm truncate ${isActive ? "font-semibold text-stone-900" : "text-stone-600"}`}>
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
                  <button onClick={createProject} className="w-full flex items-center gap-2 px-2 py-1.5 rounded-lg text-xs text-stone-400 hover:text-stone-600 hover:bg-stone-50">
                    <span>＋</span> New project
                  </button>
                )}
              </div>
            )}
          </div>

          <div className="pt-2 border-t border-stone-100 mt-2 space-y-0.5">
            <NavItem href="/runs" icon="▶" label="Runs" collapsed={collapsed} pathname={pathname} />
            <NavItem href="/settings" icon="⚙" label="Settings" collapsed={collapsed} pathname={pathname} />
          </div>
        </nav>

        <div className={`px-2 py-3 border-t border-stone-100 flex ${collapsed ? "justify-center" : ""}`}>
          <AuthButton afterSignOutUrl="/sign-in" dropUp />
        </div>

        <div className={`px-2 pb-1 flex ${collapsed ? "justify-center" : ""}`}>
          <a href="https://github.com/sseshachala/conductai/discussions/new?category=ideas" target="_blank" rel="noopener noreferrer"
            className={`flex items-center gap-1.5 text-xs text-stone-400 hover:text-stone-700 hover:bg-stone-100 rounded-lg px-2 py-1.5 w-full ${collapsed ? "justify-center" : ""}`}>
            <span>💡</span>{!collapsed && <span>Request an idea</span>}
          </a>
        </div>

        <div className={`px-2 pb-3 flex ${collapsed ? "justify-center" : ""}`}>
          <button onClick={() => setCollapsed(v => !v)}
            className={`flex items-center gap-1.5 text-xs text-stone-400 hover:text-stone-700 hover:bg-stone-100 rounded-lg px-2 py-1.5 w-full ${collapsed ? "justify-center" : ""}`}>
            <span>{collapsed ? "›" : "‹"}</span>{!collapsed && <span>Collapse</span>}
          </button>
        </div>
      </aside>

      <main className={`flex-1 min-h-0 ${noPadding ? "overflow-hidden flex flex-col" : "overflow-auto"}`}>{children}</main>
    </div>
  )
}

function NavItem({ href, icon, label, collapsed, pathname }: { href: string; icon: string; label: string; collapsed: boolean; pathname: string }) {
  const active = pathname.startsWith(href)
  return (
    <Link href={href} title={collapsed ? label : undefined}
      className={`flex items-center gap-2.5 px-2 py-2 rounded-lg text-sm font-medium transition-colors ${collapsed ? "justify-center" : ""} ${active ? "bg-stone-100 text-stone-900" : "text-stone-500 hover:text-stone-800 hover:bg-stone-50"}`}>
      <span className="text-base leading-none shrink-0">{icon}</span>
      {!collapsed && label}
    </Link>
  )
}
