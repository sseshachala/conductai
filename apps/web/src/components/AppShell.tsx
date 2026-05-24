"use client"

import { useState, useRef, useEffect, useCallback } from "react"
import Link from "next/link"
import { usePathname, useRouter } from "next/navigation"
import { useAuth } from "@clerk/nextjs"
import AuthButton from "@/components/AuthButton"
import { WorkspaceProvider, useWorkspace } from "@/lib/WorkspaceContext"

interface Project {
  id: string
  name: string
  agent_count: number
}

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
  const [switcherOpen, setSwitcherOpen] = useState(false)
  const [projects, setProjects] = useState<Project[]>([])
  const [projectsOpen, setProjectsOpen] = useState(true)
  const switcherRef = useRef<HTMLDivElement>(null)
  const { workspaces, activeWorkspace, setActiveWorkspace } = useWorkspace()

  // Close switcher on outside click
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (switcherRef.current && !switcherRef.current.contains(e.target as Node)) {
        setSwitcherOpen(false)
      }
    }
    document.addEventListener("mousedown", handleClick)
    return () => document.removeEventListener("mousedown", handleClick)
  }, [])

  // Fetch projects for active workspace
  const fetchProjects = useCallback(async () => {
    if (!activeWorkspace) return
    try {
      const headers: Record<string, string> = { "X-Workspace-ID": activeWorkspace.id }
      if (getToken) {
        const token = await getToken()
        if (token) headers["Authorization"] = `Bearer ${token}`
      }
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/workspaces/${activeWorkspace.id}/projects`,
        { headers }
      )
      if (!res.ok) return
      const data = await res.json()
      setProjects(Array.isArray(data) ? data : [])
    } catch {}
  }, [activeWorkspace, getToken])

  useEffect(() => { fetchProjects() }, [fetchProjects])

  function handleSwitch(ws: typeof workspaces[0]) {
    setActiveWorkspace(ws)
    setSwitcherOpen(false)
    setProjects([])
    router.refresh()
  }

  const activeProjectId = pathname.match(/\/projects\/([^/]+)/)?.[1]

  return (
    <div className="flex h-screen bg-stone-50">
      <aside className={`relative shrink-0 bg-white border-r border-stone-200 flex flex-col transition-all duration-200 ${collapsed ? "w-14" : "w-52"}`}>

        {/* Logo */}
        <div className={`px-3 py-4 border-b border-stone-100 flex items-center ${collapsed ? "justify-center" : "gap-2"}`}>
          <Link href="/dashboard" className="flex items-center min-w-0">
            {collapsed
              ? <img src="/icon.png" alt="Conduct AI" className="w-7 h-7 shrink-0" />
              : <img src="/logo.png" alt="Conduct AI" className="h-10 w-auto shrink-0" />
            }
          </Link>
        </div>

        {/* Team / Workspace switcher */}
        {workspaces.length > 0 && (
          <div ref={switcherRef} className="relative px-2 py-2 border-b border-stone-100">
            {!collapsed && (
              <p className="px-2 mb-1 text-[10px] font-semibold text-stone-400 uppercase tracking-wider">Team</p>
            )}
            <button
              onClick={() => setSwitcherOpen(v => !v)}
              title={collapsed ? (activeWorkspace?.name ?? "Team") : undefined}
              className={`w-full flex items-center gap-2 px-2 py-1.5 rounded-lg text-xs font-medium text-stone-700 hover:bg-stone-50 transition-colors ${collapsed ? "justify-center" : ""}`}
            >
              <span className="w-5 h-5 rounded bg-indigo-100 text-indigo-700 text-[10px] font-bold flex items-center justify-center shrink-0">
                {(activeWorkspace?.name ?? "T")[0].toUpperCase()}
              </span>
              {!collapsed && (
                <>
                  <span className="flex-1 truncate text-left">{activeWorkspace?.name ?? "Select team"}</span>
                  <span className="text-stone-400 text-[10px]">{switcherOpen ? "▴" : "▾"}</span>
                </>
              )}
            </button>

            {switcherOpen && (
              <div className={`absolute z-50 bg-white border border-stone-200 rounded-xl shadow-lg py-1 ${collapsed ? "left-14 top-0 w-48" : "left-2 right-2 top-full mt-1"}`}>
                <p className="px-3 py-1.5 text-[10px] font-semibold text-stone-400 uppercase tracking-wider">Switch team</p>
                {workspaces.map(ws => (
                  <button
                    key={ws.id}
                    onClick={() => handleSwitch(ws)}
                    className={`w-full flex items-center gap-2.5 px-3 py-2 text-sm text-left hover:bg-stone-50 transition-colors ${ws.id === activeWorkspace?.id ? "text-stone-900 font-medium" : "text-stone-600"}`}
                  >
                    <span className="w-5 h-5 rounded bg-indigo-100 text-indigo-700 text-[10px] font-bold flex items-center justify-center shrink-0">
                      {ws.name[0].toUpperCase()}
                    </span>
                    <span className="flex-1 truncate">{ws.name}</span>
                    {ws.id === activeWorkspace?.id && <span className="text-indigo-500 text-xs">✓</span>}
                  </button>
                ))}
                <div className="border-t border-stone-100 mt-1 pt-1">
                  <Link
                    href="/projects"
                    onClick={() => setSwitcherOpen(false)}
                    className="flex items-center gap-2 px-3 py-2 text-xs text-stone-500 hover:bg-stone-50 hover:text-stone-800 transition-colors"
                  >
                    <span>＋</span> New team
                  </Link>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Nav */}
        <nav className="flex-1 px-2 py-3 overflow-y-auto space-y-0.5">

          {/* Dashboard */}
          <NavItem href="/dashboard" icon="◎" label="Dashboard" collapsed={collapsed} pathname={pathname} />

          {/* Playbooks */}
          <NavItem href="/marketplace" icon="📦" label="Playbooks" collapsed={collapsed} pathname={pathname} />

          {/* Projects section */}
          <div className="pt-3">
            {!collapsed && (
              <button
                onClick={() => setProjectsOpen(v => !v)}
                className="w-full flex items-center justify-between px-2 mb-1 text-[10px] font-semibold text-stone-400 uppercase tracking-wider hover:text-stone-600 transition-colors"
              >
                <span>Projects</span>
                <span>{projectsOpen ? "▾" : "›"}</span>
              </button>
            )}

            {(projectsOpen || collapsed) && (
              <div className="space-y-0.5">
                {projects.map(project => {
                  const active = activeProjectId === project.id
                  return (
                    <Link
                      key={project.id}
                      href={`/projects/${project.id}`}
                      title={collapsed ? project.name : undefined}
                      className={`flex items-center gap-2 px-2 py-2 rounded-lg text-sm font-medium transition-colors ${collapsed ? "justify-center" : ""} ${
                        active ? "bg-stone-100 text-stone-900" : "text-stone-500 hover:text-stone-800 hover:bg-stone-50"
                      }`}
                    >
                      <span className="w-5 h-5 rounded bg-stone-100 text-stone-600 text-[10px] font-bold flex items-center justify-center shrink-0">
                        {project.name[0].toUpperCase()}
                      </span>
                      {!collapsed && (
                        <>
                          <span className="flex-1 truncate">{project.name}</span>
                          <span className="text-[10px] text-stone-400">{project.agent_count}</span>
                        </>
                      )}
                    </Link>
                  )
                })}

                {!collapsed && (
                  <button
                    onClick={async () => {
                      const name = prompt("Project name:")
                      if (!name?.trim() || !activeWorkspace) return
                      const headers: Record<string, string> = {
                        "Content-Type": "application/json",
                        "X-Workspace-ID": activeWorkspace.id,
                      }
                      if (getToken) {
                        const token = await getToken()
                        if (token) headers["Authorization"] = `Bearer ${token}`
                      }
                      await fetch(
                        `${process.env.NEXT_PUBLIC_API_URL}/workspaces/${activeWorkspace.id}/projects`,
                        { method: "POST", headers, body: JSON.stringify({ name: name.trim() }) }
                      )
                      fetchProjects()
                    }}
                    className="w-full flex items-center gap-2 px-2 py-1.5 rounded-lg text-xs text-stone-400 hover:text-stone-600 hover:bg-stone-50 transition-colors"
                  >
                    <span>＋</span> New project
                  </button>
                )}
              </div>
            )}
          </div>

          {/* Workspace-level items */}
          <div className="pt-2 border-t border-stone-100 mt-2 space-y-0.5">
            <NavItem href="/runs" icon="▶" label="Runs" collapsed={collapsed} pathname={pathname} />
            <NavItem href="/settings" icon="⚙" label="Settings" collapsed={collapsed} pathname={pathname} />
          </div>
        </nav>

        {/* User */}
        <div className={`px-2 py-3 border-t border-stone-100 flex ${collapsed ? "justify-center" : ""}`}>
          <AuthButton afterSignOutUrl="/sign-in" dropUp />
        </div>

        {/* Ideas link */}
        <div className={`px-2 pb-1 flex ${collapsed ? "justify-center" : ""}`}>
          <a
            href="https://github.com/sseshachala/conductai/discussions/new?category=ideas"
            target="_blank"
            rel="noopener noreferrer"
            className={`flex items-center gap-1.5 text-xs text-stone-400 hover:text-stone-700 hover:bg-stone-100 rounded-lg px-2 py-1.5 transition-colors w-full ${collapsed ? "justify-center" : ""}`}
            title="Request an integration or flow"
          >
            <span className="text-base leading-none">💡</span>
            {!collapsed && <span>Request an idea</span>}
          </a>
        </div>

        {/* Collapse toggle */}
        <div className={`px-2 pb-3 flex ${collapsed ? "justify-center" : ""}`}>
          <button
            onClick={() => setCollapsed(v => !v)}
            className={`flex items-center gap-1.5 text-xs text-stone-400 hover:text-stone-700 hover:bg-stone-100 rounded-lg px-2 py-1.5 transition-colors w-full ${collapsed ? "justify-center" : ""}`}
            title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          >
            <span className="text-base leading-none">{collapsed ? "›" : "‹"}</span>
            {!collapsed && <span>Collapse</span>}
          </button>
        </div>
      </aside>

      <main className={`flex-1 min-h-0 ${noPadding ? "overflow-hidden flex flex-col" : "overflow-auto"}`}>{children}</main>
    </div>
  )
}

function NavItem({ href, icon, label, collapsed, pathname }: {
  href: string; icon: string; label: string; collapsed: boolean; pathname: string
}) {
  const active = pathname.startsWith(href)
  return (
    <Link
      href={href}
      title={collapsed ? label : undefined}
      className={`flex items-center gap-2.5 px-2 py-2 rounded-lg text-sm font-medium transition-colors ${collapsed ? "justify-center" : ""} ${
        active ? "bg-stone-100 text-stone-900" : "text-stone-500 hover:text-stone-800 hover:bg-stone-50"
      }`}
    >
      <span className="text-base leading-none shrink-0">{icon}</span>
      {!collapsed && label}
    </Link>
  )
}
