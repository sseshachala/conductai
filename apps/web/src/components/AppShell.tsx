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

// ── SVG Icon helpers ──────────────────────────────────────────────────────────

function Icon({ d, children, size = 16, strokeWidth = 1.5, className = "" }: {
  d?: string
  children?: React.ReactNode
  size?: number
  strokeWidth?: number
  className?: string
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      {d ? <path d={d} /> : children}
    </svg>
  )
}

const Icons = {
  Shield: () => <Icon><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" /></Icon>,
  Grid: () => <Icon><path d="M3 3h7v7H3zm11 0h7v7h-7zM3 14h7v7H3zm11 0h7v7h-7z" /></Icon>,
  Board: () => <Icon><path d="M3 3h5v18H3zm7 0h5v11h-5zm7 0h5v14h-5z" /></Icon>,
  Flow: () => (
    <Icon>
      <circle cx="5" cy="12" r="2" />
      <circle cx="19" cy="5" r="2" />
      <circle cx="19" cy="19" r="2" />
      <path d="M7 12h3l2-7h2M7 12h3l2 7h2" />
    </Icon>
  ),
  Store: () => (
    <Icon>
      <path d="M3 9l1-6h16l1 6" />
      <path d="M3 9h18v12a1 1 0 01-1 1H4a1 1 0 01-1-1V9z" />
      <path d="M9 9v12M15 9v12" />
    </Icon>
  ),
  Pulse: () => <Icon><polyline points="22 12 18 12 15 21 9 3 6 12 2 12" /></Icon>,
  Gear: () => (
    <Icon>
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z" />
    </Icon>
  ),
  Bell: () => <Icon><path d="M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9M13.73 21a2 2 0 01-3.46 0" /></Icon>,
  Search: () => <Icon><circle cx="11" cy="11" r="8" /><path d="m21 21-4.35-4.35" /></Icon>,
  ChevRight: () => <Icon><polyline points="9 18 15 12 9 6" /></Icon>,
  ChevDown: () => <Icon><polyline points="6 9 12 15 18 9" /></Icon>,
  Plus: () => <Icon><path d="M12 5v14M5 12h14" /></Icon>,
  Play: () => <Icon><polygon points="5 3 19 12 5 21 5 3" /></Icon>,
  Arrow: () => <Icon><path d="M5 12h14M12 5l7 7-7 7" /></Icon>,
}

// ── Breadcrumb logic ──────────────────────────────────────────────────────────

function getBreadcrumbs(pathname: string, projects: Project[]): string[] {
  if (pathname.startsWith('/guard/spend')) return ['Guard', 'Spend']
  if (pathname.startsWith('/guard/policies')) return ['Guard', 'Policies']
  if (pathname.startsWith('/guard/activity')) return ['Guard', 'Activity']
  if (pathname.startsWith('/guard/settings')) return ['Guard', 'Settings']
  if (pathname.startsWith('/guard')) return ['Guard', 'Overview']
  if (pathname.startsWith('/settings')) return ['Settings']
  if (pathname.startsWith('/marketplace')) return ['Marketplace']
  if (pathname.startsWith('/runs')) return ['Runs']
  if (pathname.startsWith('/workflows/new')) return ['Canvas', 'New agent']
  if (pathname.startsWith('/workflows/')) return ['Canvas']
  if (pathname.startsWith('/tasks')) return ['Tasks']
  const projectMatch = pathname.match(/\/projects\/([^/]+)/)
  if (projectMatch) {
    const project = projects.find(p => p.id === projectMatch[1])
    const name = project?.name ?? 'Project'
    if (pathname.includes('/runs')) return ['Projects', name, 'Runs']
    return ['Projects', name]
  }
  if (pathname.startsWith('/projects')) return ['Projects']
  return ['Conduct']
}

// ── Static notification data ──────────────────────────────────────────────────

const NOTIFICATIONS = [
  { id: 1, title: "Awaiting your approval", tone: "warn" as const, desc: "Autopilot + Approval · PROJ-482", time: "now", unread: true },
  { id: 2, title: "Policy block", tone: "err" as const, desc: "sam@ blocked by no-rm in claude-code", time: "6m", unread: true },
  { id: 3, title: "Run failed", tone: "err" as const, desc: "Autopilot Full · 3 retries exhausted", time: "1h", unread: true },
  { id: 4, title: "Budget at 78%", tone: "warn" as const, desc: "maya@ near personal $75 cap", time: "2h", unread: false },
  { id: 5, title: "Review posted", tone: "ok" as const, desc: "PR Reviewer · conductai/web #1291", time: "6m", unread: false },
  { id: 6, title: "PR opened", tone: "ok" as const, desc: "Dependency Updater · #1280", time: "3h", unread: false },
]

const UNREAD_COUNT = NOTIFICATIONS.filter(n => n.unread).length

// ── Command palette commands ──────────────────────────────────────────────────

const PALETTE_COMMANDS = [
  { group: "BUILD", label: "Projects", href: "/projects", icon: "Grid" as const },
  { group: "BUILD", label: "Tasks", href: "/tasks", icon: "Board" as const },
  { group: "BUILD", label: "Canvas", href: "/workflows/new", icon: "Flow" as const },
  { group: "BUILD", label: "Marketplace", href: "/marketplace", icon: "Store" as const },
  { group: "OBSERVE", label: "Runs", href: "/runs", icon: "Pulse" as const },
  { group: "GOVERN", label: "Guard · Overview", href: "/guard", icon: "Shield" as const },
  { group: "GOVERN", label: "Guard · Spend", href: "/guard/spend", icon: "Shield" as const },
  { group: "GOVERN", label: "Guard · Policies", href: "/guard/policies", icon: "Shield" as const },
  { group: "GOVERN", label: "Guard · Activity", href: "/guard/activity", icon: "Shield" as const },
  { group: "WORKSPACE", label: "Settings · Environments", href: "/settings", icon: "Gear" as const },
]

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

  // Org name
  const [orgName, setOrgName] = useState<string | null>(null)

  // Role state
  const [userRole, setUserRole] = useState<UserRole>(null)

  // Workspace switcher (sidebar)
  const [wsOpen, setWsOpen] = useState(false)
  const wsRef = useRef<HTMLDivElement>(null)

  // User menu (not used in new design — kept for UserMenu component)
  const [userMenuOpen, setUserMenuOpen] = useState(false)
  const userMenuRef = useRef<HTMLDivElement>(null)

  // Notifications popover
  const [notifOpen, setNotifOpen] = useState(false)
  const notifRef = useRef<HTMLDivElement>(null)

  // Command palette
  const [paletteOpen, setPaletteOpen] = useState(false)
  const [paletteQuery, setPaletteQuery] = useState("")
  const [paletteActive, setPaletteActive] = useState(0)
  const paletteInputRef = useRef<HTMLInputElement>(null)

  // Team rename/create/delete state
  const [creatingTeam, setCreatingTeam] = useState(false)
  const [newTeamValue, setNewTeamValue] = useState("")
  const [deletingTeamId, setDeletingTeamId] = useState<string | null>(null)
  const [deleteConfirmValue, setDeleteConfirmValue] = useState("")
  const newTeamInputRef = useRef<HTMLInputElement>(null)
  const deleteConfirmRef = useRef<HTMLInputElement>(null)

  const { workspaces, activeWorkspace, setActiveWorkspace, refresh: refreshWorkspaces } = useWorkspace()

  // Guard install state
  const [guardInstalled, setGuardInstalled] = useState(false)

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
      if (notifRef.current && !notifRef.current.contains(e.target as Node)) setNotifOpen(false)
    }
    document.addEventListener("mousedown", handle)
    return () => document.removeEventListener("mousedown", handle)
  }, [])

  // Command palette keyboard shortcut
  useEffect(() => {
    function handle(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault()
        setPaletteOpen(v => !v)
        setPaletteQuery("")
        setPaletteActive(0)
      }
      if (e.key === "Escape") setPaletteOpen(false)
    }
    document.addEventListener("keydown", handle)
    return () => document.removeEventListener("keydown", handle)
  }, [])

  useEffect(() => { if (paletteOpen) paletteInputRef.current?.focus() }, [paletteOpen])
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
        if (!cancelled) setUserRole(myRole ?? "admin")
      } catch {
        if (!cancelled) setUserRole("admin")
      }
    }
    fetchRole()
    return () => { cancelled = true }
  }, [activeWorkspace?.id, userId])

  // Fetch org name
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
      } catch {}
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
      } catch {}
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
  const canSeeGuard = guardInstalled
  const canSeeProjects = userRole === "admin" || userRole === "developer" || userRole === "viewer"
  const canCreateProject = userRole === "admin" || userRole === "developer"

  const isOnCanvas = pathname.startsWith("/workflows")

  // Palette filtered commands
  const filteredCommands = paletteQuery
    ? PALETTE_COMMANDS.filter(c => c.label.toLowerCase().includes(paletteQuery.toLowerCase()))
    : PALETTE_COMMANDS

  const groupedCommands = filteredCommands.reduce<Record<string, typeof PALETTE_COMMANDS>>((acc, cmd) => {
    if (!acc[cmd.group]) acc[cmd.group] = []
    acc[cmd.group].push(cmd)
    return acc
  }, {})

  const breadcrumbs = getBreadcrumbs(pathname, projects)

  // Workspace display values
  const wsInitials = (orgName ?? activeWorkspace?.name ?? "O").slice(0, 2).toUpperCase()
  const wsOrgLabel = (orgName ?? "Organisation").toUpperCase()
  const wsName = activeWorkspace?.name ?? "Workspace"

  return (
    <PreferencesProvider workspaceId={activeWorkspace?.id ?? ""} getToken={getToken}>
    <div style={{ display: "flex", height: "100vh", background: "var(--bg)" }}>

      {/* ── Sidebar ─────────────────────────────────────────────────────── */}
      <aside style={{
        width: collapsed ? 64 : 244,
        flexShrink: 0,
        background: "var(--surface)",
        borderRight: "1px solid var(--border)",
        display: "flex",
        flexDirection: "column",
        transition: "width 200ms ease",
        overflow: "hidden",
      }}>

        {/* Brand header */}
        <div style={{
          display: "flex",
          alignItems: "center",
          justifyContent: collapsed ? "center" : "space-between",
          padding: collapsed ? "14px 0" : "14px 14px 14px 16px",
          borderBottom: "1px solid var(--border)",
          flexShrink: 0,
        }}>
          {!collapsed && (
            <Link href="/projects" style={{ display: "flex", alignItems: "center", gap: 8, textDecoration: "none" }}>
              <div style={{
                width: 28, height: 28, borderRadius: 8,
                background: "var(--accent)",
                display: "flex", alignItems: "center", justifyContent: "center",
              }}>
                <Icons.Flow />
              </div>
              <span style={{ fontSize: 14, fontWeight: 700, color: "var(--text)", letterSpacing: "-0.01em" }}>Conduct</span>
            </Link>
          )}
          {collapsed && (
            <div style={{
              width: 28, height: 28, borderRadius: 8,
              background: "var(--accent)", color: "#fff",
              display: "flex", alignItems: "center", justifyContent: "center",
            }}>
              <Icons.Flow />
            </div>
          )}
          {!collapsed && (
            <button
              onClick={() => setCollapsed(true)}
              aria-label="Collapse sidebar"
              style={{
                padding: "4px 6px", borderRadius: 6, border: "none",
                background: "transparent", cursor: "pointer",
                color: "var(--text-muted)", fontSize: 14, lineHeight: 1,
              }}
            >
              ‹
            </button>
          )}
        </div>

        {/* Workspace selector */}
        <div style={{ padding: "10px 10px 6px", flexShrink: 0 }} ref={wsRef}>
          {!collapsed ? (
            <div
              onClick={() => setWsOpen(v => !v)}
              style={{
                margin: "0 2px",
                padding: "9px 11px",
                borderRadius: 10,
                border: "1px solid var(--border)",
                background: "var(--surface-2)",
                cursor: "pointer",
                display: "flex",
                alignItems: "center",
                gap: 10,
                position: "relative",
              }}
              onMouseEnter={e => (e.currentTarget.style.borderColor = "var(--border-2)")}
              onMouseLeave={e => (e.currentTarget.style.borderColor = "var(--border)")}
            >
              <div style={{
                width: 26, height: 26, borderRadius: 7,
                background: "var(--accent)", color: "#fff",
                display: "flex", alignItems: "center", justifyContent: "center",
                fontWeight: 700, fontSize: 12, flexShrink: 0,
              }}>
                {wsInitials}
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", color: "var(--text-muted)", letterSpacing: "0.06em" }}>
                  {wsOrgLabel}
                </div>
                <div style={{ fontSize: 13.5, fontWeight: 600, color: "var(--text)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                  {wsName}
                </div>
              </div>
              <div style={{ color: "var(--text-muted)", flexShrink: 0 }}>
                <Icons.ChevDown />
              </div>
            </div>
          ) : (
            <div
              onClick={() => setWsOpen(v => !v)}
              style={{
                width: 36, height: 36, borderRadius: 7,
                background: "var(--accent)", color: "#fff",
                display: "flex", alignItems: "center", justifyContent: "center",
                fontWeight: 700, fontSize: 12, cursor: "pointer", margin: "0 auto",
              }}
            >
              {wsInitials}
            </div>
          )}

          {/* Workspace dropdown */}
          {wsOpen && !collapsed && (
            <div style={{
              position: "absolute",
              zIndex: 100,
              top: "auto",
              left: 10,
              width: 224,
              background: "var(--surface)",
              border: "1px solid var(--border)",
              borderRadius: 12,
              boxShadow: "var(--shadow-md)",
              padding: "4px 0",
              marginTop: 4,
            }}>
              <p style={{ padding: "6px 12px 4px", fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.1em", color: "var(--text-muted)" }}>
                Workspaces
              </p>
              {workspaces.map(ws => (
                <div key={ws.id}>
                  {deletingTeamId === ws.id ? (
                    <div style={{ padding: "8px 12px", background: "var(--err-bg)", borderTop: "1px solid #fecaca", borderBottom: "1px solid #fecaca" }}>
                      <p style={{ fontSize: 12, color: "var(--err)", marginBottom: 6 }}>Type <strong>{ws.name}</strong> to confirm deletion</p>
                      <div style={{ display: "flex", gap: 6 }}>
                        <input
                          ref={deleteConfirmRef}
                          value={deleteConfirmValue}
                          onChange={e => setDeleteConfirmValue(e.target.value)}
                          onKeyDown={e => {
                            if (e.key === "Enter") confirmDeleteTeam(ws)
                            if (e.key === "Escape") { setDeletingTeamId(null); setDeleteConfirmValue("") }
                          }}
                          placeholder={ws.name}
                          style={{ flex: 1, fontSize: 12, border: "1px solid #fecaca", borderRadius: 6, padding: "4px 8px", outline: "none" }}
                        />
                        <button
                          onClick={() => confirmDeleteTeam(ws)}
                          disabled={deleteConfirmValue !== ws.name}
                          style={{ fontSize: 12, padding: "4px 8px", borderRadius: 6, background: "var(--err)", color: "#fff", border: "none", cursor: "pointer", opacity: deleteConfirmValue !== ws.name ? 0.4 : 1 }}
                        >Delete</button>
                        <button
                          onClick={() => { setDeletingTeamId(null); setDeleteConfirmValue("") }}
                          style={{ fontSize: 12, padding: "4px 8px", borderRadius: 6, background: "transparent", border: "none", cursor: "pointer", color: "var(--text-2)" }}
                        >Cancel</button>
                      </div>
                    </div>
                  ) : (
                    <div style={{ display: "flex", alignItems: "center", padding: "0 12px" }}
                      onMouseEnter={e => (e.currentTarget.style.background = "var(--surface-2)")}
                      onMouseLeave={e => (e.currentTarget.style.background = "transparent")}
                    >
                      <button
                        onClick={() => { setActiveWorkspace(ws as Parameters<typeof setActiveWorkspace>[0]); setWsOpen(false); router.refresh() }}
                        style={{
                          flex: 1, display: "flex", alignItems: "center", gap: 8,
                          padding: "8px 0", fontSize: 13.5, textAlign: "left",
                          background: "transparent", border: "none", cursor: "pointer",
                          fontWeight: ws.id === activeWorkspace?.id ? 600 : 400,
                          color: ws.id === activeWorkspace?.id ? "var(--text)" : "var(--text-2)",
                        }}
                      >
                        <span style={{
                          width: 20, height: 20, borderRadius: 5,
                          background: "var(--accent-weak-2)", color: "var(--accent-text)",
                          fontSize: 10, fontWeight: 700,
                          display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0,
                        }}>
                          {ws.name[0].toUpperCase()}
                        </span>
                        <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{ws.name}</span>
                        {ws.id === activeWorkspace?.id && <span style={{ color: "var(--accent)", fontSize: 12 }}>✓</span>}
                      </button>
                      <button
                        onClick={() => { setDeletingTeamId(ws.id); setDeleteConfirmValue("") }}
                        style={{ fontSize: 11, padding: "2px 4px", background: "transparent", border: "none", cursor: "pointer", color: "var(--text-muted)", opacity: 0 }}
                        onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.opacity = "1"; (e.currentTarget as HTMLButtonElement).style.color = "var(--err)" }}
                        onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.opacity = "0" }}
                        title="Delete workspace"
                        aria-label="Delete workspace"
                      >
                        ✕
                      </button>
                    </div>
                  )}
                </div>
              ))}
              <div style={{ borderTop: "1px solid var(--border)", marginTop: 4, padding: "4px 12px" }}>
                {creatingTeam ? (
                  <input
                    ref={newTeamInputRef}
                    value={newTeamValue}
                    onChange={e => setNewTeamValue(e.target.value)}
                    onBlur={submitCreateTeam}
                    onKeyDown={e => { if (e.key === "Enter") submitCreateTeam(); if (e.key === "Escape") { setCreatingTeam(false); setNewTeamValue("") } }}
                    placeholder="Workspace name"
                    style={{ width: "100%", fontSize: 13, border: "1px solid var(--border)", borderRadius: 8, padding: "6px 10px", outline: "none" }}
                  />
                ) : (
                  <button
                    onClick={() => setCreatingTeam(true)}
                    style={{
                      width: "100%", display: "flex", alignItems: "center", gap: 8,
                      padding: "8px 0", fontSize: 12, background: "transparent", border: "none",
                      cursor: "pointer", color: "var(--text-3)",
                    }}
                  >
                    + New workspace
                  </button>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Nav scroll area */}
        <nav style={{ flex: 1, overflowY: "auto", padding: "4px 10px 8px" }}>

          {/* GOVERN group — Guard */}
          {canSeeGuard && (
            <div>
              {!collapsed && (
                <div style={{ padding: "12px 10px 5px", fontSize: 10, fontWeight: 700, letterSpacing: ".12em", textTransform: "uppercase", color: "var(--text-muted)" }}>
                  Govern
                </div>
              )}
              {collapsed && <div style={{ borderTop: "1px solid var(--border)", margin: "6px 0" }} />}
              <SideNavItem
                href="/guard"
                label="Guard"
                icon={<Icons.Shield />}
                active={pathname.startsWith("/guard")}
                collapsed={collapsed}
              />
              {/* Guard sub-nav — auto-expand when on any /guard route */}
              {pathname.startsWith("/guard") && !collapsed && (
                <div style={{ marginLeft: 28, marginTop: 2, display: "flex", flexDirection: "column", gap: 1 }}>
                  {[
                    { label: "Overview", href: "/guard" },
                    { label: "Spend", href: "/guard/spend" },
                    { label: "Policies", href: "/guard/policies" },
                    { label: "Activity", href: "/guard/activity" },
                    { label: "Settings", href: "/guard/settings" },
                  ].map(sub => {
                    const subActive = sub.href === "/guard" ? pathname === "/guard" : pathname.startsWith(sub.href)
                    return (
                      <Link
                        key={sub.href}
                        href={sub.href}
                        style={{
                          display: "block",
                          padding: "5px 10px",
                          borderRadius: 7,
                          fontSize: 13,
                          fontWeight: subActive ? 600 : 400,
                          color: subActive ? "var(--accent-text)" : "var(--text-3)",
                          background: subActive ? "var(--accent-weak)" : "transparent",
                          textDecoration: "none",
                        }}
                        onMouseEnter={e => { if (!subActive) (e.currentTarget as HTMLAnchorElement).style.background = "var(--surface-2)" }}
                        onMouseLeave={e => { if (!subActive) (e.currentTarget as HTMLAnchorElement).style.background = "transparent" }}
                      >
                        {sub.label}
                      </Link>
                    )
                  })}
                </div>
              )}
            </div>
          )}

          {/* BUILD group */}
          <div>
            {!collapsed && (
              <div style={{ padding: "12px 10px 5px", fontSize: 10, fontWeight: 700, letterSpacing: ".12em", textTransform: "uppercase", color: "var(--text-muted)" }}>
                Build
              </div>
            )}
            {collapsed && canSeeGuard && <div style={{ borderTop: "1px solid var(--border)", margin: "6px 0" }} />}

            {canSeeProjects && (
              <div>
                <SideNavItem
                  href="/projects"
                  label="Projects"
                  icon={<Icons.Grid />}
                  active={pathname.startsWith("/projects")}
                  collapsed={collapsed}
                  badge={projects.length > 0 ? projects.length : undefined}
                />
                {/* Inline project list when not collapsed */}
                {!collapsed && canSeeProjects && projects.length > 0 && pathname.startsWith("/projects") && (
                  <div style={{ marginLeft: 28, marginTop: 2, marginBottom: 2, display: "flex", flexDirection: "column", gap: 1 }}>
                    {projects.map(project => {
                      const isActive = activeProjectId === project.id
                      const isRenaming = renamingProjectId === project.id
                      return (
                        <div key={project.id} style={{ display: "flex", alignItems: "center", gap: 6, padding: "4px 8px", borderRadius: 7, background: isActive ? "var(--accent-weak)" : "transparent" }}
                          onMouseEnter={e => { if (!isActive) (e.currentTarget as HTMLDivElement).style.background = "var(--surface-2)" }}
                          onMouseLeave={e => { if (!isActive) (e.currentTarget as HTMLDivElement).style.background = "transparent" }}
                        >
                          <span style={{
                            width: 16, height: 16, borderRadius: 4,
                            background: "var(--surface-3)", color: "var(--text-3)",
                            fontSize: 9, fontWeight: 700, flexShrink: 0,
                            display: "flex", alignItems: "center", justifyContent: "center",
                          }}>
                            {project.name[0].toUpperCase()}
                          </span>
                          {isRenaming ? (
                            <input
                              ref={renameInputRef}
                              value={renameValue}
                              onChange={e => setRenameValue(e.target.value)}
                              onBlur={() => submitProjectRename(project.id)}
                              onKeyDown={e => { if (e.key === "Enter") submitProjectRename(project.id); if (e.key === "Escape") setRenamingProjectId(null) }}
                              style={{ flex: 1, fontSize: 12.5, background: "transparent", border: "none", borderBottom: "1px solid var(--accent)", outline: "none" }}
                            />
                          ) : (
                            <>
                              <Link
                                href={`/projects/${project.id}`}
                                style={{
                                  flex: 1, fontSize: 12.5,
                                  fontWeight: isActive ? 600 : 400,
                                  color: isActive ? "var(--accent-text)" : "var(--text-2)",
                                  textDecoration: "none", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                                }}
                              >
                                {project.name}
                              </Link>
                              <button
                                onClick={() => { setRenamingProjectId(project.id); setRenameValue(project.name) }}
                                style={{ fontSize: 11, background: "transparent", border: "none", cursor: "pointer", color: "var(--text-muted)", opacity: 0, padding: "0 2px" }}
                                onMouseEnter={e => (e.currentTarget.style.opacity = "1")}
                                onMouseLeave={e => (e.currentTarget.style.opacity = "0")}
                                title="Rename"
                              >✎</button>
                            </>
                          )}
                        </div>
                      )
                    })}
                    {canCreateProject && (
                      creatingProject ? (
                        <div style={{ padding: "4px 8px" }}>
                          <input
                            ref={newProjectInputRef}
                            value={newProjectValue}
                            onChange={e => setNewProjectValue(e.target.value)}
                            onBlur={submitCreateProject}
                            onKeyDown={e => { if (e.key === "Enter") submitCreateProject(); if (e.key === "Escape") { setCreatingProject(false); setNewProjectValue("") } }}
                            placeholder="Project name"
                            style={{ width: "100%", fontSize: 12.5, border: "1px solid var(--border)", borderRadius: 6, padding: "4px 8px", outline: "none" }}
                          />
                        </div>
                      ) : (
                        <button
                          onClick={() => setCreatingProject(true)}
                          style={{
                            display: "flex", alignItems: "center", gap: 6,
                            padding: "4px 8px", borderRadius: 7, fontSize: 12.5,
                            background: "transparent", border: "none", cursor: "pointer",
                            color: "var(--text-muted)", width: "100%",
                          }}
                          onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.color = "var(--text-2)"; (e.currentTarget as HTMLButtonElement).style.background = "var(--surface-2)" }}
                          onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.color = "var(--text-muted)"; (e.currentTarget as HTMLButtonElement).style.background = "transparent" }}
                        >
                          + New project
                        </button>
                      )
                    )}
                  </div>
                )}
              </div>
            )}

            <SideNavItem
              href="/tasks"
              label="Tasks"
              icon={<Icons.Board />}
              active={pathname.startsWith("/tasks")}
              collapsed={collapsed}
              badge={9}
            />
            <SideNavItem
              href="/workflows/new"
              label="Canvas"
              icon={<Icons.Flow />}
              active={pathname.startsWith("/workflows")}
              collapsed={collapsed}
            />
            <SideNavItem
              href="/marketplace"
              label="Marketplace"
              icon={<Icons.Store />}
              active={pathname.startsWith("/marketplace")}
              collapsed={collapsed}
              badge={18}
            />
          </div>

          {/* OBSERVE group */}
          <div>
            {!collapsed && (
              <div style={{ padding: "12px 10px 5px", fontSize: 10, fontWeight: 700, letterSpacing: ".12em", textTransform: "uppercase", color: "var(--text-muted)" }}>
                Observe
              </div>
            )}
            {collapsed && <div style={{ borderTop: "1px solid var(--border)", margin: "6px 0" }} />}
            <SideNavItem
              href="/runs"
              label="Runs"
              icon={<Icons.Pulse />}
              active={pathname.startsWith("/runs")}
              collapsed={collapsed}
              badge={3}
            />
          </div>
        </nav>

        {/* Sidebar footer */}
        <div style={{ borderTop: "1px solid var(--border)", padding: "8px 10px", flexShrink: 0 }}>
          {/* Collapse toggle (only shows when expanded — collapsed gets expand button in the topbar area) */}
          {collapsed && (
            <button
              onClick={() => setCollapsed(false)}
              aria-label="Expand sidebar"
              style={{
                display: "flex", alignItems: "center", justifyContent: "center",
                width: "100%", padding: "6px 0",
                background: "transparent", border: "none", cursor: "pointer",
                color: "var(--text-muted)", fontSize: 16, marginBottom: 4,
              }}
            >
              ›
            </button>
          )}
          <SideNavItem
            href="/settings"
            label="Settings"
            icon={<Icons.Gear />}
            active={pathname.startsWith("/settings")}
            collapsed={collapsed}
          />
          {/* User chip */}
          <UserChip collapsed={collapsed} userRole={userRole} />
        </div>
      </aside>

      {/* ── Main area ───────────────────────────────────────────────────── */}
      <div style={{ flex: 1, minHeight: 0, display: "flex", flexDirection: "column" }}>

        {/* Topbar */}
        <header style={{
          flexShrink: 0,
          height: 60,
          background: "color-mix(in srgb, var(--surface) 80%, transparent)",
          backdropFilter: "blur(8px)",
          borderBottom: "1px solid var(--border)",
          display: "flex",
          alignItems: "center",
          padding: "0 20px",
          gap: 12,
        }}>
          {/* Breadcrumbs */}
          <div style={{ display: "flex", alignItems: "center", gap: 6, flex: 1, minWidth: 0 }}>
            {breadcrumbs.map((crumb, i) => (
              <div key={i} style={{ display: "flex", alignItems: "center", gap: 6 }}>
                {i > 0 && (
                  <span style={{ color: "var(--text-muted)", display: "flex", alignItems: "center" }}>
                    <Icons.ChevRight />
                  </span>
                )}
                <span style={{
                  fontSize: 14,
                  fontWeight: i === breadcrumbs.length - 1 ? 600 : 400,
                  color: i === breadcrumbs.length - 1 ? "var(--text)" : "var(--text-3)",
                  whiteSpace: "nowrap",
                }}>
                  {crumb}
                </span>
              </div>
            ))}
          </div>

          {/* Right cluster */}
          <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0 }}>
            {/* Search / command palette trigger */}
            <button
              onClick={() => { setPaletteOpen(true); setPaletteQuery(""); setPaletteActive(0) }}
              style={{
                display: "flex", alignItems: "center", gap: 6,
                padding: "5px 10px", borderRadius: 8,
                border: "1px solid var(--border)",
                background: "var(--surface-2)",
                cursor: "pointer", fontSize: 13,
                color: "var(--text-3)",
              }}
              onMouseEnter={e => (e.currentTarget.style.borderColor = "var(--border-2)")}
              onMouseLeave={e => (e.currentTarget.style.borderColor = "var(--border)")}
            >
              <Icons.Search />
              <span>Search</span>
              <kbd style={{
                fontSize: 10.5, padding: "1px 5px", borderRadius: 4,
                background: "var(--surface-3)", border: "1px solid var(--border-2)",
                color: "var(--text-muted)", fontFamily: "inherit",
              }}>⌘K</kbd>
            </button>

            {/* Bell / notifications */}
            <div ref={notifRef} style={{ position: "relative" }}>
              <button
                onClick={() => setNotifOpen(v => !v)}
                aria-label="Notifications"
                style={{
                  position: "relative", width: 34, height: 34, borderRadius: 8,
                  border: "1px solid var(--border)", background: "var(--surface-2)",
                  cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center",
                  color: "var(--text-2)",
                }}
                onMouseEnter={e => (e.currentTarget.style.background = "var(--surface-3)")}
                onMouseLeave={e => (e.currentTarget.style.background = "var(--surface-2)")}
              >
                <Icons.Bell />
                {UNREAD_COUNT > 0 && (
                  <span style={{
                    position: "absolute", top: 5, right: 5, width: 7, height: 7,
                    borderRadius: "50%", background: "var(--err)",
                    border: "1.5px solid var(--surface)",
                  }} />
                )}
              </button>

              {/* Notifications popover */}
              {notifOpen && (
                <div style={{
                  position: "absolute", zIndex: 200, top: "calc(100% + 8px)", right: 0,
                  width: 360, background: "var(--surface)",
                  border: "1px solid var(--border)", borderRadius: 12,
                  boxShadow: "var(--shadow-lg)",
                  overflow: "hidden",
                }}>
                  <div style={{ padding: "12px 16px 10px", display: "flex", alignItems: "center", justifyContent: "space-between", borderBottom: "1px solid var(--border)" }}>
                    <span style={{ fontSize: 13, fontWeight: 700, color: "var(--text)" }}>Notifications</span>
                    {UNREAD_COUNT > 0 && (
                      <span style={{
                        fontSize: 10.5, fontWeight: 700, padding: "1px 7px", borderRadius: 20,
                        background: "var(--err-bg)", color: "var(--err)",
                      }}>{UNREAD_COUNT} unread</span>
                    )}
                  </div>
                  <div style={{ overflowY: "auto", maxHeight: 340 }}>
                    {NOTIFICATIONS.map(n => {
                      const toneColors: Record<string, { bg: string; color: string }> = {
                        warn: { bg: "var(--warn-bg)", color: "var(--warn)" },
                        err: { bg: "var(--err-bg)", color: "var(--err)" },
                        ok: { bg: "var(--ok-bg)", color: "var(--ok)" },
                        info: { bg: "var(--info-bg)", color: "var(--info)" },
                      }
                      const tc = toneColors[n.tone] ?? toneColors.info
                      const toneIcon = n.tone === "warn" ? "⚠" : n.tone === "err" ? "✕" : n.tone === "ok" ? "✓" : "i"
                      return (
                        <div key={n.id} style={{
                          display: "flex", alignItems: "flex-start", gap: 12,
                          padding: "12px 16px",
                          borderBottom: "1px solid var(--border)",
                          background: n.unread ? "var(--surface-2)" : "var(--surface)",
                        }}>
                          <div style={{
                            width: 30, height: 30, borderRadius: 8, flexShrink: 0,
                            background: tc.bg, color: tc.color,
                            display: "flex", alignItems: "center", justifyContent: "center",
                            fontWeight: 700, fontSize: 13,
                          }}>
                            {toneIcon}
                          </div>
                          <div style={{ flex: 1, minWidth: 0 }}>
                            <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
                              <span style={{ fontSize: 13, fontWeight: 700, color: "var(--text)" }}>{n.title}</span>
                              {n.unread && (
                                <span style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--accent)", flexShrink: 0 }} />
                              )}
                            </div>
                            <div style={{ fontSize: 12, color: "var(--text-muted)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                              {n.desc}
                            </div>
                          </div>
                          <span style={{ fontSize: 11, color: "var(--text-muted)", flexShrink: 0 }}>{n.time}</span>
                        </div>
                      )
                    })}
                  </div>
                  <div style={{ padding: "10px 16px", borderTop: "1px solid var(--border)" }}>
                    <Link
                      href="/runs"
                      onClick={() => setNotifOpen(false)}
                      style={{ fontSize: 12.5, color: "var(--accent-text)", fontWeight: 600, textDecoration: "none" }}
                    >
                      View all activity →
                    </Link>
                  </div>
                </div>
              )}
            </div>

            {/* Context action button */}
            {isOnCanvas ? (
              <div style={{ display: "flex", gap: 6 }}>
                <button style={{
                  padding: "6px 14px", borderRadius: 8, fontSize: 13, fontWeight: 600,
                  border: "1px solid var(--border)", background: "var(--surface-2)",
                  cursor: "pointer", color: "var(--text-2)",
                }}>
                  Dry run
                </button>
                <button style={{
                  padding: "6px 14px", borderRadius: 8, fontSize: 13, fontWeight: 600,
                  border: "none", background: "var(--accent)", color: "#fff",
                  cursor: "pointer", display: "flex", alignItems: "center", gap: 6,
                }}>
                  <Icons.Play />
                  Run
                </button>
              </div>
            ) : (
              <Link
                href="/workflows/new"
                style={{
                  display: "flex", alignItems: "center", gap: 6,
                  padding: "6px 14px", borderRadius: 8, fontSize: 13, fontWeight: 600,
                  background: "var(--accent)", color: "#fff",
                  textDecoration: "none",
                }}
              >
                <Icons.Plus />
                New agent
              </Link>
            )}
          </div>
        </header>

        {/* Page content */}
        <main style={{ flex: 1, minHeight: 0, overflow: noPadding ? "hidden" : "auto", display: noPadding ? "flex" : "block", flexDirection: noPadding ? "column" : undefined }}>
          <ErrorBoundary>{children}</ErrorBoundary>
        </main>
      </div>
    </div>

    {/* Command Palette */}
    {paletteOpen && (
      <div
        style={{
          position: "fixed", inset: 0, zIndex: 1000,
          background: "rgba(28,25,23,0.4)",
          backdropFilter: "blur(4px)",
          display: "flex", alignItems: "flex-start", justifyContent: "center",
          paddingTop: "15vh",
        }}
        onClick={e => { if (e.target === e.currentTarget) setPaletteOpen(false) }}
      >
        <div style={{
          width: 560, maxHeight: "60vh",
          background: "var(--surface)",
          borderRadius: 14,
          border: "1px solid var(--border)",
          boxShadow: "var(--shadow-lg)",
          overflow: "hidden",
          display: "flex", flexDirection: "column",
        }}>
          {/* Search input */}
          <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "12px 16px", borderBottom: "1px solid var(--border)" }}>
            <Icons.Search />
            <input
              ref={paletteInputRef}
              value={paletteQuery}
              onChange={e => { setPaletteQuery(e.target.value); setPaletteActive(0) }}
              onKeyDown={e => {
                if (e.key === "ArrowDown") { e.preventDefault(); setPaletteActive(v => Math.min(v + 1, filteredCommands.length - 1)) }
                if (e.key === "ArrowUp") { e.preventDefault(); setPaletteActive(v => Math.max(v - 1, 0)) }
                if (e.key === "Enter" && filteredCommands[paletteActive]) {
                  router.push(filteredCommands[paletteActive].href)
                  setPaletteOpen(false)
                }
                if (e.key === "Escape") setPaletteOpen(false)
              }}
              placeholder="Jump to a screen..."
              style={{
                flex: 1, fontSize: 14, background: "transparent", border: "none", outline: "none",
                color: "var(--text)",
              }}
            />
            <kbd style={{
              fontSize: 10.5, padding: "2px 7px", borderRadius: 5,
              background: "var(--surface-3)", border: "1px solid var(--border-2)",
              color: "var(--text-muted)", fontFamily: "inherit",
            }}>esc</kbd>
          </div>

          {/* Results */}
          <div style={{ overflowY: "auto", flex: 1 }}>
            {Object.entries(groupedCommands).map(([group, cmds]) => (
              <div key={group}>
                <div style={{ padding: "8px 16px 4px", fontSize: 10, fontWeight: 700, letterSpacing: ".12em", textTransform: "uppercase", color: "var(--text-muted)" }}>
                  {group}
                </div>
                {cmds.map(cmd => {
                  const flatIdx = filteredCommands.findIndex(c => c.href === cmd.href && c.label === cmd.label)
                  const isActive = flatIdx === paletteActive
                  const IconComp = Icons[cmd.icon]
                  return (
                    <button
                      key={cmd.href + cmd.label}
                      onMouseEnter={() => setPaletteActive(flatIdx)}
                      onClick={() => { router.push(cmd.href); setPaletteOpen(false) }}
                      style={{
                        display: "flex", alignItems: "center", gap: 10, width: "100%",
                        padding: "8px 16px", fontSize: 13.5, fontWeight: 500,
                        background: isActive ? "var(--accent-weak)" : "transparent",
                        color: isActive ? "var(--accent-text)" : "var(--text-2)",
                        border: "none", cursor: "pointer", textAlign: "left",
                      }}
                    >
                      <span style={{ color: isActive ? "var(--accent-text)" : "var(--text-muted)" }}>
                        <IconComp />
                      </span>
                      {cmd.label}
                    </button>
                  )
                })}
              </div>
            ))}
            {filteredCommands.length === 0 && (
              <div style={{ padding: "24px 16px", textAlign: "center", fontSize: 13, color: "var(--text-muted)" }}>
                No results found
              </div>
            )}
          </div>
        </div>
      </div>
    )}

    {toast && <Toast message={toast.message} type={toast.type} onDismiss={() => setToast(null)} />}
    </PreferencesProvider>
  )
}

// ── SideNavItem ───────────────────────────────────────────────────────────────

function SideNavItem({
  href, label, icon, active, collapsed, badge,
}: {
  href: string
  label: string
  icon: React.ReactNode
  active: boolean
  collapsed: boolean
  badge?: number
}) {
  return (
    <Link
      href={href}
      aria-label={collapsed ? label : undefined}
      title={collapsed ? label : undefined}
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: collapsed ? "center" : "flex-start",
        gap: 8,
        padding: "8px 10px",
        borderRadius: 9,
        fontSize: 13.5,
        fontWeight: active ? 600 : 400,
        color: active ? "var(--accent-text)" : "var(--text-2)",
        background: active ? "var(--accent-weak)" : "transparent",
        textDecoration: "none",
        marginBottom: 1,
        transition: "background 120ms, color 120ms",
      }}
      onMouseEnter={e => { if (!active) { (e.currentTarget as HTMLAnchorElement).style.background = "var(--surface-2)"; (e.currentTarget as HTMLAnchorElement).style.color = "var(--text)" } }}
      onMouseLeave={e => { if (!active) { (e.currentTarget as HTMLAnchorElement).style.background = "transparent"; (e.currentTarget as HTMLAnchorElement).style.color = "var(--text-2)" } }}
    >
      <span style={{ flexShrink: 0, display: "flex", alignItems: "center", color: "inherit" }}>{icon}</span>
      {!collapsed && (
        <>
          <span style={{ flex: 1 }}>{label}</span>
          {badge !== undefined && (
            <span style={{
              fontSize: 10.5, fontWeight: 700, padding: "1px 7px", borderRadius: 20,
              background: active ? "var(--accent-weak-2)" : "var(--surface-3)",
              color: active ? "var(--accent-text)" : "var(--text-3)",
            }}>
              {badge}
            </span>
          )}
        </>
      )}
    </Link>
  )
}

// ── UserChip ──────────────────────────────────────────────────────────────────

function UserChip({ collapsed, userRole }: { collapsed: boolean; userRole: UserRole }) {
  const clerkEnabled = !!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY
  if (!clerkEnabled) return null
  return <UserChipInner collapsed={collapsed} userRole={userRole} />
}

function UserChipInner({ collapsed, userRole }: { collapsed: boolean; userRole: UserRole }) {
  const { user } = useUser()
  const { signOut } = useClerk()
  const router = useRouter()
  const [menuOpen, setMenuOpen] = useState(false)
  const chipRef = useRef<HTMLDivElement>(null)

  const email = user?.primaryEmailAddress?.emailAddress ?? ""
  const firstName = user?.firstName ?? ""
  const lastName = user?.lastName ?? ""
  const initials = firstName && lastName
    ? `${firstName[0]}${lastName[0]}`.toUpperCase()
    : email ? email[0].toUpperCase() : "?"
  const fullName = [firstName, lastName].filter(Boolean).join(" ") || email || "User"
  const roleLabel = userRole ?? "member"
  const avatarUrl = user?.imageUrl

  useEffect(() => {
    function handle(e: MouseEvent) {
      if (chipRef.current && !chipRef.current.contains(e.target as Node)) setMenuOpen(false)
    }
    document.addEventListener("mousedown", handle)
    return () => document.removeEventListener("mousedown", handle)
  }, [])

  return (
    <div ref={chipRef} style={{ position: "relative" }}>
      <button
        onClick={() => setMenuOpen(v => !v)}
        style={{
          display: "flex",
          alignItems: "center",
          gap: collapsed ? 0 : 10,
          padding: "7px 8px",
          borderRadius: 9,
          background: "transparent",
          border: "none",
          cursor: "pointer",
          width: "100%",
          textAlign: "left",
        }}
        onMouseEnter={e => (e.currentTarget.style.background = "var(--surface-2)")}
        onMouseLeave={e => (e.currentTarget.style.background = "transparent")}
      >
        <div style={{
          width: 28, height: 28, borderRadius: "50%",
          background: "var(--accent)", color: "#fff",
          fontSize: 11, fontWeight: 700, flexShrink: 0,
          display: "flex", alignItems: "center", justifyContent: "center",
          overflow: "hidden",
        }}>
          {avatarUrl
            ? <img src={avatarUrl} alt={initials} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
            : initials}
        </div>
        {!collapsed && (
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {fullName}
            </div>
            <div style={{ fontSize: 11, color: "var(--text-muted)" }}>{roleLabel}</div>
          </div>
        )}
      </button>

      {menuOpen && (
        <div style={{
          position: "absolute", bottom: "calc(100% + 4px)", left: 0,
          width: 200, background: "var(--surface)",
          border: "1px solid var(--border)", borderRadius: 10,
          boxShadow: "var(--shadow-md)", padding: "4px 0", zIndex: 100,
        }}>
          {email && (
            <>
              <div style={{ padding: "8px 12px" }}>
                <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text)", overflow: "hidden", textOverflow: "ellipsis" }}>{fullName}</div>
                <div style={{ fontSize: 11, color: "var(--text-muted)", overflow: "hidden", textOverflow: "ellipsis" }}>{email}</div>
              </div>
              <div style={{ borderTop: "1px solid var(--border)", margin: "2px 0" }} />
            </>
          )}
          <Link
            href="/settings"
            onClick={() => setMenuOpen(false)}
            style={{ display: "block", padding: "8px 12px", fontSize: 13, color: "var(--text-2)", textDecoration: "none" }}
            onMouseEnter={e => { (e.currentTarget as HTMLAnchorElement).style.background = "var(--surface-2)"; (e.currentTarget as HTMLAnchorElement).style.color = "var(--text)" }}
            onMouseLeave={e => { (e.currentTarget as HTMLAnchorElement).style.background = "transparent"; (e.currentTarget as HTMLAnchorElement).style.color = "var(--text-2)" }}
          >
            Settings
          </Link>
          <div style={{ borderTop: "1px solid var(--border)", margin: "2px 0" }} />
          <button
            onClick={() => { setMenuOpen(false); signOut(() => router.push("/sign-in")) }}
            style={{
              width: "100%", textAlign: "left", padding: "8px 12px", fontSize: 13,
              color: "var(--text-2)", background: "transparent", border: "none", cursor: "pointer",
            }}
            onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.background = "var(--surface-2)"; (e.currentTarget as HTMLButtonElement).style.color = "var(--text)" }}
            onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.background = "transparent"; (e.currentTarget as HTMLButtonElement).style.color = "var(--text-2)" }}
          >
            Sign out
          </button>
        </div>
      )}
    </div>
  )
}
