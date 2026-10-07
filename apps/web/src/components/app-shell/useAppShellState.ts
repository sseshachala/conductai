"use client"

import { useState, useRef, useEffect, useCallback } from "react"
import { usePathname, useRouter } from "next/navigation"
import { LENS_ENTRY_EVENT, lensEntryHref, lensEntryQuestion, type LensEntry } from "@/lib/lens-entry"
import { useWorkspace } from "@/lib/WorkspaceContext"
import { setActiveGuardWorkspace } from "@/lib/guardStorage"
import { type ToastData } from "@/components/ui/Toast"
import { useAuthFetch } from "@/hooks/useAuthFetch"
import { reportLayoutsApi, type ReportLayout } from "@/lib/reportBuilder/api"
import { workspaces as workspacesApi, projects as projectsApi, organizations, runs, guard, workflows } from "@/lib/api"
import { getBreadcrumbs, PALETTE_COMMANDS } from "./nav-data"
import type { NotificationItem, Project, UserRole } from "./types"

// State, effects and handlers for AppShellInnerContent, moved verbatim
// from AppShell.tsx so the render tree can live in section files.
export function useAppShellState({ userId }: { userId: string | null }) {
  const pathname = usePathname()
    const router = useRouter()
  const [desktopCollapsed, setDesktopCollapsed] = useState(false)
  const [isMobile, setIsMobile] = useState(false)
  const [mobileNavOpen, setMobileNavOpen] = useState(false)
  const sidebarRef = useRef<HTMLElement>(null)
  const mainAreaRef = useRef<HTMLDivElement>(null)
  const collapsed = isMobile ? !mobileNavOpen : desktopCollapsed
  function setCollapsed(value: boolean) {
    if (isMobile) setMobileNavOpen(!value)
    else setDesktopCollapsed(value)
  }
  useEffect(() => {
    const media = window.matchMedia("(max-width: 767px)")
    const update = () => { setIsMobile(media.matches); setMobileNavOpen(false) }
    update()
    media.addEventListener("change", update)
    return () => media.removeEventListener("change", update)
  }, [])
  useEffect(() => { setMobileNavOpen(false) }, [pathname])
  useEffect(() => {
    if (!isMobile || !mobileNavOpen) return
    const previous = document.activeElement as HTMLElement | null
    const mainArea = mainAreaRef.current
    mainArea?.setAttribute("inert", "")
    const focusable = () => Array.from(sidebarRef.current?.querySelectorAll<HTMLElement>("a[href], button:not([disabled]), input, select, [tabindex='0']") ?? []).filter(el => el.getClientRects().length > 0)
    focusable()[0]?.focus()
    const keydown = (event: KeyboardEvent) => {
      if (event.key === "Escape") { event.preventDefault(); setMobileNavOpen(false) }
      if (event.key !== "Tab") return
      const elements = focusable()
      const first = elements[0], last = elements[elements.length - 1]
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus() }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus() }
    }
    document.addEventListener("keydown", keydown)
    return () => {
      document.removeEventListener("keydown", keydown)
      mainArea?.removeAttribute("inert")
      requestAnimationFrame(() => {
        if (previous?.isConnected && previous !== document.body) previous.focus()
        else sidebarRef.current?.querySelector<HTMLElement>('[aria-label="Expand sidebar"]')?.focus()
      })
    }
  }, [isMobile, mobileNavOpen])
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

  // Workspace footer group (Integrations / Agent ID / Settings) — collapsed
  // by default; auto-expands when any of its routes is active.
  const workspaceRouteActive = pathname.startsWith("/settings")
  const [workspaceGroupOpen, setWorkspaceGroupOpen] = useState(false)

  // User menu (not used in new design — kept for UserMenu component)
  const [userMenuOpen, setUserMenuOpen] = useState(false)
  const userMenuRef = useRef<HTMLDivElement>(null)

  // Notifications popover
  const [notifOpen, setNotifOpen] = useState(false)
  const notifRef = useRef<HTMLDivElement>(null)
  const [notifications, setNotifications] = useState<NotificationItem[]>([])
  const [pinnedReports, setPinnedReports] = useState<ReportLayout[]>([])
  const [notificationsLoading, setNotificationsLoading] = useState(false)

  // Command palette
  const [paletteOpen, setPaletteOpen] = useState(false)
  const [paletteQuery, setPaletteQuery] = useState("")
  const [paletteActive, setPaletteActive] = useState(0)
  const paletteInputRef = useRef<HTMLInputElement>(null)

  const { workspaces, activeWorkspace, setActiveWorkspace, refresh: refreshWorkspaces } = useWorkspace()

  // Global "Ask Lens" bar + right-side panel (#1214 #B1/#B2/#B5)
  const [askLensQuery, setAskLensQuery] = useState("")
  const [lensPanelOpen, setLensPanelOpen] = useState(false)
  const [lensPanelInitialQuery, setLensPanelInitialQuery] = useState<string | null>(null)
  const [lensPanelEntry, setLensPanelEntry] = useState<LensEntry | null>(null)
  const [lensPanelGeneration, setLensPanelGeneration] = useState(0)

  // Suppress side panel on full-page Lens routes (would render Lens twice).
  const lensPanelSuppressed = pathname?.startsWith("/lens") ?? false

  useEffect(() => {
    if (lensPanelSuppressed) return
    const openEntry = (event: Event) => {
      const entry = (event as CustomEvent<LensEntry>).detail
      try { lensEntryHref(entry) } catch { return }
      if (entry.workspace_id !== activeWorkspace?.id) return
      event.preventDefault()
      setLensPanelEntry(entry)
      setLensPanelInitialQuery(lensEntryQuestion(entry))
      setLensPanelGeneration(n => n + 1)
      setLensPanelOpen(true)
    }
    window.addEventListener(LENS_ENTRY_EVENT, openEntry)
    return () => window.removeEventListener(LENS_ENTRY_EVENT, openEntry)
  }, [lensPanelSuppressed, activeWorkspace?.id])

  useEffect(() => {
    setLensPanelOpen(false)
    setLensPanelEntry(null)
    setLensPanelInitialQuery(null)
  }, [activeWorkspace?.id])

  // Persist open/closed state (#B5). localStorage read is client-only.
  useEffect(() => {
    if (typeof window === "undefined") return
    try { if (window.localStorage.getItem("lens:panelOpen") === "1") setLensPanelOpen(true) } catch { /* ignore */ }
  }, [])
  useEffect(() => {
    if (typeof window === "undefined") return
    try { window.localStorage.setItem("lens:panelOpen", lensPanelOpen ? "1" : "0") } catch { /* ignore */ }
  }, [lensPanelOpen])

  // ⌘. / Ctrl+. toggles Lens panel from anywhere.
  useEffect(() => {
    if (lensPanelSuppressed) return
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === ".") {
        e.preventDefault()
        setLensPanelOpen(v => !v)
      }
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [lensPanelSuppressed])

  // Team rename/create/delete state
  const [creatingTeam, setCreatingTeam] = useState(false)
  const [newTeamValue, setNewTeamValue] = useState("")
  const [deletingTeamId, setDeletingTeamId] = useState<string | null>(null)
  const [deleteConfirmValue, setDeleteConfirmValue] = useState("")
  const newTeamInputRef = useRef<HTMLInputElement>(null)
  const deleteConfirmRef = useRef<HTMLInputElement>(null)

  const { authFetch } = useAuthFetch()

  // Guard install state
  const [guardInstalled, setGuardInstalled] = useState(false)

  // Active runs count (for sidebar badge)
  const [activeRunsCount, setActiveRunsCount] = useState<number | undefined>(undefined)

  // Registry playbook count (for sidebar badge)
  const [playbookCount, setPlaybookCount] = useState<number | undefined>(undefined)

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

  const unreadCount = notifications.filter(n => n.unread).length

  useEffect(() => {
    let cancelled = false
    async function fetchNotifications() {
      if (!activeWorkspace?.id) return
      setNotificationsLoading(true)
      try {
        const data = await workspacesApi.notifications(authFetch, activeWorkspace.id, 8)
        const items = Array.isArray(data?.items) ? data.items : []
        if (!cancelled) setNotifications(items)
      } catch {
        if (!cancelled) setNotifications([])
      } finally {
        if (!cancelled) setNotificationsLoading(false)
      }
    }
    fetchNotifications()
    return () => { cancelled = true }
  }, [activeWorkspace?.id])

  // #1450 PR 5: pinned reports for the left-nav Reports section. Refetches
  // when the workspace changes; the pin/unpin action on the report-builder
  // page updates the row server-side but we do NOT live-invalidate here —
  // navigating between report-builder and other pages triggers a fresh
  // AppShell mount which picks up the change.
  useEffect(() => {
    let cancelled = false
    async function loadPinned() {
      if (!activeWorkspace?.id) { setPinnedReports([]); return }
      try {
        const all = await reportLayoutsApi.list(authFetch, activeWorkspace.id)
        if (cancelled) return
        setPinnedReports(all.filter((r) => r.is_pinned))
      } catch {
        if (cancelled) return
        setPinnedReports([])
      }
    }
    void loadPinned()
    // Live-invalidate when the report-builder toggles a pin. Window event
    // is cheap here because there is at most one AppShell mounted at a
    // time; if the app ever mounts multiple AppShells, hoist pinnedReports
    // into WorkspaceContext instead of listening broadcast-style.
    const onChange = () => { void loadPinned() }
    window.addEventListener("reports:changed", onChange)
    return () => {
      cancelled = true
      window.removeEventListener("reports:changed", onChange)
    }
  }, [activeWorkspace?.id, authFetch])


  // Fetch user role from members API
  useEffect(() => {
    let cancelled = false
    async function fetchRole() {
      if (!activeWorkspace || !userId) return
      try {
        const members: { clerk_user_id: string; role: string }[] = await projectsApi.members.list(authFetch, activeWorkspace.id)
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
        const data = await organizations.list(authFetch)
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

  // Fetch active runs count for sidebar badge
  useEffect(() => {
    let cancelled = false
    async function fetchRunsCount() {
      if (!activeWorkspace?.id) return
      try {
        const data: { status: string }[] = await runs.list(authFetch, { limit: 500, offset: 0 })
        const active = data.filter(r => r.status === "running" || r.status === "paused").length
        if (!cancelled) setActiveRunsCount(active > 0 ? active : undefined)
      } catch {}
    }
    fetchRunsCount()
    return () => { cancelled = true }
  }, [activeWorkspace?.id])

  // Fetch registry playbook count for sidebar badge
  useEffect(() => {
    let cancelled = false
    async function fetchPlaybookCount() {
      try {
        const data: unknown[] = await workflows.playbooks.list(authFetch)
        if (!cancelled) setPlaybookCount(Array.isArray(data) && data.length > 0 ? data.length : undefined)
      } catch {}
    }
    fetchPlaybookCount()
    return () => { cancelled = true }
  }, [])

  // Guard install check
  useEffect(() => {
    let cancelled = false
    async function checkGuardInstall() {
      const wsId = activeWorkspace?.id
      if (!wsId) return
      try {
        const data = await guard.config.installed(authFetch, wsId)
        if (!cancelled) {
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
  }, [activeWorkspace])

  const fetchProjects = useCallback(async () => {
    if (!activeWorkspace) return
    try {
      const data = await workspacesApi.projects.list(authFetch, activeWorkspace.id)
      setProjects(Array.isArray(data) ? data : [])
    } catch {}
  }, [activeWorkspace, authFetch])

  useEffect(() => { fetchProjects() }, [fetchProjects])

  async function submitCreateTeam() {
    const name = newTeamValue.trim()
    setCreatingTeam(false); setNewTeamValue("")
    if (!name) return
    try {
      const res = await projectsApi.create(authFetch, { name })
      if (res.ok) { setWsOpen(false); refreshWorkspaces() }
      else showError("Could not create team — please try again.")
    } catch { showError("Could not create team — check your connection.") }
  }

  async function confirmDeleteTeam(ws: { id: string; name: string }) {
    if (deleteConfirmValue !== ws.name) return
    setDeletingTeamId(null); setDeleteConfirmValue("")
    try {
      const res = await projectsApi.remove(authFetch, ws.id)
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
      const res = await workspacesApi.projects.create(authFetch, activeWorkspace.id, { name })
      if (res.ok) fetchProjects()
      else showError("Could not create project — please try again.")
    } catch { showError("Could not create project — check your connection.") }
  }

  async function submitProjectRename(projectId: string) {
    const name = renameValue.trim()
    setRenamingProjectId(null)
    if (!name || !activeWorkspace) return
    try {
      const res = await workspacesApi.projects.rename(authFetch, activeWorkspace.id, projectId, { name })
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

  return {
    pathname,
    router,
    desktopCollapsed,
    setDesktopCollapsed,
    isMobile,
    setIsMobile,
    mobileNavOpen,
    setMobileNavOpen,
    sidebarRef,
    mainAreaRef,
    collapsed,
    setCollapsed,
    toast,
    setToast,
    showError,
    showSuccess,
    orgName,
    setOrgName,
    userRole,
    setUserRole,
    wsOpen,
    setWsOpen,
    wsRef,
    workspaceRouteActive,
    workspaceGroupOpen,
    setWorkspaceGroupOpen,
    userMenuOpen,
    setUserMenuOpen,
    userMenuRef,
    notifOpen,
    setNotifOpen,
    notifRef,
    notifications,
    setNotifications,
    pinnedReports,
    setPinnedReports,
    notificationsLoading,
    setNotificationsLoading,
    paletteOpen,
    setPaletteOpen,
    paletteQuery,
    setPaletteQuery,
    paletteActive,
    setPaletteActive,
    paletteInputRef,
    workspaces,
    activeWorkspace,
    setActiveWorkspace,
    refreshWorkspaces,
    askLensQuery,
    setAskLensQuery,
    lensPanelOpen,
    setLensPanelOpen,
    lensPanelInitialQuery,
    setLensPanelInitialQuery,
    lensPanelEntry,
    setLensPanelEntry,
    lensPanelGeneration,
    setLensPanelGeneration,
    lensPanelSuppressed,
    creatingTeam,
    setCreatingTeam,
    newTeamValue,
    setNewTeamValue,
    deletingTeamId,
    setDeletingTeamId,
    deleteConfirmValue,
    setDeleteConfirmValue,
    newTeamInputRef,
    deleteConfirmRef,
    authFetch,
    guardInstalled,
    setGuardInstalled,
    activeRunsCount,
    setActiveRunsCount,
    playbookCount,
    setPlaybookCount,
    projects,
    setProjects,
    renamingProjectId,
    setRenamingProjectId,
    renameValue,
    setRenameValue,
    creatingProject,
    setCreatingProject,
    newProjectValue,
    setNewProjectValue,
    renameInputRef,
    newProjectInputRef,
    unreadCount,
    fetchProjects,
    submitCreateTeam,
    confirmDeleteTeam,
    submitCreateProject,
    submitProjectRename,
    activeProjectId,
    canSeeGuard,
    canSeeProjects,
    canCreateProject,
    isOnCanvas,
    filteredCommands,
    groupedCommands,
    breadcrumbs,
    wsInitials,
    wsOrgLabel,
    wsName,
  }
}

export type AppShellState = ReturnType<typeof useAppShellState>
