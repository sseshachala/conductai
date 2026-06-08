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

function timeAgo(ts: string): string {
  const diff = Date.now() - new Date(ts).getTime()
  const days = Math.floor(diff / 86400000)
  if (days === 0) return "today"
  if (days === 1) return "yesterday"
  if (days < 30) return `${days}d ago`
  return new Date(ts).toLocaleDateString()
}

// ── Project avatar colours ────────────────────────────────────────────────────

const AVATAR_COLORS = [
  "#4f46e5", "#059669", "#d97706", "#dc2626",
  "#7c3aed", "#0284c7", "#be185d", "#15803d",
]

function avatarColor(name: string): string {
  let h = 0
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) & 0xffffffff
  return AVATAR_COLORS[Math.abs(h) % AVATAR_COLORS.length]
}

// ── Icons ────────────────────────────────────────────────────────────────────

function ArrowRightIcon() {
  return (
    <svg width={17} height={17} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M5 12h14M12 5l7 7-7 7" />
    </svg>
  )
}

function PulseIcon() {
  return (
    <svg width={16} height={16} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
    </svg>
  )
}

function PlusIcon({ size = 15 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M12 5v14M5 12h14" />
    </svg>
  )
}

function DotsIcon() {
  return (
    <svg width={16} height={16} fill="currentColor" viewBox="0 0 20 20" aria-hidden="true">
      <path d="M10 6a2 2 0 1 1 0-4 2 2 0 0 1 0 4zm0 6a2 2 0 1 1 0-4 2 2 0 0 1 0 4zm0 6a2 2 0 1 1 0-4 2 2 0 0 1 0 4z" />
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
  const [loading, setLoading] = useState(true)
  const [showModal, setShowModal] = useState(false)
  const [tab, setTab] = useState<"projects" | "incidents">("projects")

  async function authHeaders(): Promise<Record<string, string>> {
    const h: Record<string, string> = {}
    if (getToken) {
      const token = await getToken()
      if (token) h["Authorization"] = `Bearer ${token}`
    }
    return h
  }

  async function fetchProjects() {
    try {
      const headers = await authHeaders()
      const workspaceId = document.cookie.match(/delegator_project_id=([^;]+)/)?.[1] ?? ""
      if (workspaceId) {
        headers["X-Workspace-Id"] = workspaceId
        const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/workspaces/${workspaceId}/projects`, { headers })
        if (res.ok) { setProjects(await res.json()); return }
      }
      // Fallback: no cookie set yet — show top-level workspaces as projects
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/projects`, { headers })
      if (res.ok) setProjects(await res.json())
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchProjects() }, [])

  function selectProject(id: string, name?: string) {
    router.push(`/workflows?project=${id}`)
  }

  function getWorkspaceId(): string {
    return document.cookie.match(/delegator_project_id=([^;]+)/)?.[1] ?? ""
  }

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

  return (
    <AppShell>
      <div style={{ maxWidth: 1180, margin: "0 auto", padding: "30px 34px 80px" }}>
        <OnboardingChecklist hasProject={projects.length > 0} getToken={getToken} />

        {/* Page header */}
        <div style={{ display: "flex", alignItems: "flex-end", gap: 16, marginBottom: 24 }}>
          <div>
            <h1 style={{ fontSize: 25, fontWeight: 680, letterSpacing: "-.02em", margin: 0, color: "var(--text)" }}>
              Projects
            </h1>
            <p style={{ color: "var(--text-3)", fontSize: 14, marginTop: 5, marginBottom: 0 }}>
              Group agents by team or repo. Each one keeps its own runs, memory, and environments.
            </p>
          </div>
          <div style={{ marginLeft: "auto", display: "flex", gap: 9 }}>
            <Link
              href="/runs"
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 7,
                height: 36,
                padding: "0 15px",
                borderRadius: 9,
                fontSize: 13.5,
                fontWeight: 550,
                border: "1px solid var(--border)",
                color: "var(--text-2)",
                background: "var(--surface)",
                textDecoration: "none",
              }}
            >
              <PulseIcon />
              Recent runs
            </Link>
            <button
              onClick={() => setShowModal(true)}
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 7,
                height: 36,
                padding: "0 15px",
                borderRadius: 9,
                fontSize: 13.5,
                fontWeight: 550,
                border: "1px solid transparent",
                background: "var(--text)",
                color: "#fff",
                cursor: "pointer",
                fontFamily: "inherit",
              }}
            >
              <PlusIcon size={15} />
              New project
            </button>
          </div>
        </div>

        {/* Tabs */}
        {!loading && (
          <div style={{ display: "flex", gap: 6, marginBottom: 20 }}>
            {(["projects", "incidents"] as const).map(t => {
              const count = t === "projects"
                ? projects.filter(p => (p.project_type ?? "user") === "user").length
                : projects.filter(p => p.project_type === "security_incident").length
              const on = tab === t
              return (
                <button
                  key={t}
                  onClick={() => setTab(t)}
                  className="chip"
                  style={{ height: 30, cursor: "pointer", fontWeight: 600, display: "flex", alignItems: "center", gap: 5, background: on ? "var(--accent-weak)" : "var(--surface)", borderColor: on ? "var(--accent-ring)" : "var(--border)", color: on ? "var(--accent-text)" : "var(--text-2)" }}
                >
                  {t === "incidents" && <ShieldIcon />}
                  {t === "projects" ? "Projects" : "Incidents"}
                  <span style={{ opacity: .6 }}>· {count}</span>
                </button>
              )
            })}
          </div>
        )}

        {/* Content */}
        {loading ? (
          <LoadingGrid />
        ) : tab === "projects" ? (
          (() => {
            const userProjects = projects.filter(p => (p.project_type ?? "user") === "user")
            return userProjects.length === 0 ? (
              <EmptyState onNew={() => setShowModal(true)} />
            ) : (
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))", gap: 16 }}>
                {userProjects.map(p => (
                  <ProjectCard
                    key={p.id}
                    project={p}
                    onSelect={() => selectProject(p.id, p.name)}
                    onRename={(name) => renameProject(p.id, name)}
                    onDelete={() => deleteProject(p.id)}
                  />
                ))}
                <NewProjectTile onClick={() => setShowModal(true)} />
              </div>
            )
          })()
        ) : (
          (() => {
            const incidents = projects.filter(p => p.project_type === "security_incident")
            return incidents.length === 0 ? (
              <div style={{ borderRadius: 14, border: "1.5px dashed var(--border-2)", padding: "56px 40px", textAlign: "center" }}>
                <p style={{ fontWeight: 600, color: "var(--text)", marginBottom: 8 }}>No incidents yet</p>
                <p style={{ color: "var(--text-3)", fontSize: 14, maxWidth: 320, margin: "0 auto", lineHeight: 1.6 }}>
                  When Agentic Autopilot triggers a fix, an incident project appears here — one per finding.
                </p>
              </div>
            ) : (
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))", gap: 16 }}>
                {incidents.map(p => (
                  <IncidentCard key={p.id} project={p} onSelect={() => selectProject(p.id, p.name)} />
                ))}
              </div>
            )
          })()
        )}
      </div>

      {showModal && (
        <NewProjectModal
          getToken={getToken}
          onClose={() => setShowModal(false)}
          onCreate={(id) => selectProject(id)}
        />
      )}
    </AppShell>
  )
}

// ── Loading grid ──────────────────────────────────────────────────────────────

function LoadingGrid() {
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))",
        gap: 16,
      }}
    >
      {[1, 2, 3].map(i => (
        <div
          key={i}
          style={{
            height: 188,
            borderRadius: 14,
            border: "1px solid var(--border)",
            background: "var(--surface)",
            animation: "pulse 1.5s ease-in-out infinite",
          }}
        />
      ))}
    </div>
  )
}

// ── Empty state ───────────────────────────────────────────────────────────────

function EmptyState({ onNew }: { onNew: () => void }) {
  return (
    <div
      style={{
        borderRadius: 14,
        border: "1.5px dashed var(--border-2)",
        padding: "56px 40px",
        textAlign: "center",
      }}
    >
      <p style={{ fontWeight: 600, color: "var(--text)", marginBottom: 8 }}>Create your first project</p>
      <p style={{ color: "var(--text-3)", fontSize: 14, marginBottom: 8, maxWidth: 320, margin: "0 auto 8px", lineHeight: 1.6 }}>
        A project groups your agents, runs, and credentials. Think of it as one repo or one team.
      </p>
      <p style={{ color: "var(--text-3)", fontSize: 14, marginBottom: 32, maxWidth: 320, margin: "0 auto 32px", lineHeight: 1.6 }}>
        Once created, you&apos;ll pick a template and have your first agent running in minutes.
      </p>
      <button
        onClick={onNew}
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: 7,
          height: 36,
          padding: "0 18px",
          borderRadius: 9,
          fontSize: 13.5,
          fontWeight: 550,
          border: "1px solid transparent",
          background: "var(--text)",
          color: "#fff",
          cursor: "pointer",
          fontFamily: "inherit",
        }}
      >
        <PlusIcon size={15} />
        New project
      </button>
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
        borderRadius: 14,
        display: "grid",
        placeItems: "center",
        minHeight: 188,
        cursor: "pointer",
        color: hovered ? "var(--accent-text)" : "var(--text-3)",
        transition: "border-color .15s, color .15s",
      }}
    >
      <div style={{ textAlign: "center" }}>
        <PlusIcon size={22} />
        <div style={{ fontSize: 13.5, fontWeight: 600, marginTop: 6 }}>New project</div>
      </div>
    </div>
  )
}

// ── Incident card ─────────────────────────────────────────────────────────────

function IncidentCard({ project, onSelect }: { project: Project; onSelect: () => void }) {
  const [hovered, setHovered] = useState(false)
  return (
    <div
      onClick={onSelect}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        borderRadius: 14,
        border: "1px solid #fecaca",
        background: hovered ? "#fff5f5" : "#fef2f2",
        overflow: "hidden",
        cursor: "pointer",
        boxShadow: hovered ? "var(--shadow-md)" : "none",
        transition: "background .15s, box-shadow .15s",
        padding: "18px 20px",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10 }}>
        <div style={{ width: 36, height: 36, borderRadius: 10, background: "#dc2626", color: "#fff", display: "grid", placeItems: "center", flexShrink: 0 }}>
          <ShieldIcon />
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontWeight: 650, fontSize: 14, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", color: "#991b1b" }}>
            {project.name}
          </div>
          <div style={{ fontSize: 11, color: "#b91c1c", marginTop: 2 }}>
            {timeAgo(project.created_at)}
          </div>
        </div>
        <span style={{ fontSize: 9.5, fontWeight: 700, letterSpacing: ".04em", padding: "2px 8px", borderRadius: 20, background: "rgba(220,38,38,.12)", color: "#dc2626", border: "1px solid rgba(220,38,38,.25)", flexShrink: 0 }}>
          INCIDENT
        </span>
      </div>
      <div style={{ fontSize: 12, color: "#b91c1c", display: "flex", alignItems: "center", gap: 6 }}>
        <svg width={12} height={12} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>
        {project.security_finding_id ? `Finding ${project.security_finding_id.slice(0, 8)}` : "Security finding"}
      </div>
      <div style={{ marginTop: 12, paddingTop: 12, borderTop: "1px solid #fecaca", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <span style={{ fontSize: 12, color: "#b91c1c" }}>{project.agent_count} agent{project.agent_count !== 1 ? "s" : ""}</span>
        <span style={{ fontSize: 12, color: "#dc2626", fontWeight: 600 }}>View incident →</span>
      </div>
    </div>
  )
}

// ── Project card ──────────────────────────────────────────────────────────────

interface ProjectCardProps {
  project: Project
  onSelect: () => void
  onRename: (name: string) => Promise<void>
  onDelete: () => Promise<void>
}

function ProjectCard({ project, onSelect, onRename, onDelete }: ProjectCardProps) {
  const [menuOpen, setMenuOpen] = useState(false)
  const [renaming, setRenaming] = useState(false)
  const [nameValue, setNameValue] = useState(project.name)
  const [confirmValue, setConfirmValue] = useState<string | null>(null)
  const [hovered, setHovered] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const confirmInputRef = useRef<HTMLInputElement>(null)
  const menuRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (renaming) inputRef.current?.focus()
  }, [renaming])

  useEffect(() => {
    if (confirmValue !== null) confirmInputRef.current?.focus()
  }, [confirmValue])

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuOpen(false)
    }
    document.addEventListener("mousedown", handleClick)
    return () => document.removeEventListener("mousedown", handleClick)
  }, [])

  async function submitRename() {
    const name = nameValue.trim()
    if (name && name !== project.name) await onRename(name)
    else setNameValue(project.name)
    setRenaming(false)
  }

  // Delete confirmation state
  if (confirmValue !== null) {
    return (
      <div
        style={{
          borderRadius: 14,
          border: "1px solid #fecaca",
          background: "#fef2f2",
          padding: "16px 20px",
        }}
      >
        <p style={{ fontSize: 13, color: "#b91c1c", marginBottom: 10 }}>
          Type <strong>{project.name}</strong> to permanently delete this project and all its data.
        </p>
        <div style={{ display: "flex", gap: 8 }}>
          <input
            ref={confirmInputRef}
            value={confirmValue}
            onChange={e => setConfirmValue(e.target.value)}
            onKeyDown={e => {
              if (e.key === "Enter" && confirmValue === project.name) onDelete()
              if (e.key === "Escape") setConfirmValue(null)
            }}
            placeholder={project.name}
            style={{
              flex: 1,
              fontSize: 13,
              border: "1px solid #fecaca",
              borderRadius: 8,
              padding: "6px 10px",
              outline: "none",
              fontFamily: "inherit",
            }}
          />
          <button
            onClick={() => onDelete()}
            disabled={confirmValue !== project.name}
            style={{
              fontSize: 12,
              fontWeight: 600,
              color: "#fff",
              background: "#dc2626",
              border: "none",
              padding: "6px 12px",
              borderRadius: 8,
              cursor: "pointer",
              opacity: confirmValue !== project.name ? 0.4 : 1,
              fontFamily: "inherit",
            }}
          >
            Delete
          </button>
          <button
            onClick={() => setConfirmValue(null)}
            style={{
              fontSize: 12,
              fontWeight: 600,
              color: "var(--text-2)",
              background: "var(--surface)",
              border: "1px solid var(--border)",
              padding: "6px 12px",
              borderRadius: 8,
              cursor: "pointer",
              fontFamily: "inherit",
            }}
          >
            Cancel
          </button>
        </div>
      </div>
    )
  }

  const color = avatarColor(project.name)

  return (
    <div
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        borderRadius: 14,
        border: "1px solid var(--border)",
        background: "var(--surface)",
        overflow: "hidden",
        cursor: "pointer",
        boxShadow: hovered ? "var(--shadow-md)" : "none",
        transition: "border-color .15s, box-shadow .15s",
      }}
    >
      {/* Top section */}
      <div
        style={{ padding: "18px 20px 16px" }}
        onClick={renaming ? undefined : onSelect}
      >
        {/* Header row: avatar + name + repo + 3-dot menu */}
        <div style={{ display: "flex", alignItems: "center", gap: 11, marginBottom: 12 }}>
          <div
            style={{
              width: 36,
              height: 36,
              borderRadius: 10,
              background: color,
              color: "#fff",
              display: "grid",
              placeItems: "center",
              fontWeight: 700,
              fontSize: 14,
              flexShrink: 0,
            }}
          >
            {project.name[0].toUpperCase()}
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            {renaming ? (
              <input
                ref={inputRef}
                value={nameValue}
                onChange={e => setNameValue(e.target.value)}
                onBlur={submitRename}
                onKeyDown={e => {
                  if (e.key === "Enter") submitRename()
                  if (e.key === "Escape") { setNameValue(project.name); setRenaming(false) }
                }}
                onClick={e => e.stopPropagation()}
                style={{
                  fontSize: 16,
                  fontWeight: 650,
                  color: "var(--text)",
                  background: "transparent",
                  border: "none",
                  borderBottom: "1px solid var(--accent-ring)",
                  outline: "none",
                  width: "100%",
                  fontFamily: "inherit",
                }}
              />
            ) : (
              <div style={{ fontWeight: 650, fontSize: 16, color: "var(--text)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {project.name}
              </div>
            )}
          </div>

          {/* 3-dot menu */}
          <div
            ref={menuRef}
            style={{ position: "relative", flexShrink: 0 }}
            onClick={e => e.stopPropagation()}
          >
            <button
              onClick={() => setMenuOpen(v => !v)}
              style={{
                width: 28,
                height: 28,
                borderRadius: 7,
                border: "none",
                background: "transparent",
                cursor: "pointer",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: "var(--text-muted)",
                opacity: hovered || menuOpen ? 1 : 0,
                transition: "opacity .15s, background .15s",
              }}
              onMouseEnter={e => (e.currentTarget.style.background = "var(--surface-3)")}
              onMouseLeave={e => (e.currentTarget.style.background = "transparent")}
              aria-label="Project actions"
            >
              <DotsIcon />
            </button>
            {menuOpen && (
              <div
                style={{
                  position: "absolute",
                  right: 0,
                  top: "calc(100% + 4px)",
                  zIndex: 20,
                  width: 144,
                  background: "var(--surface)",
                  borderRadius: 12,
                  border: "1px solid var(--border)",
                  boxShadow: "var(--shadow-md)",
                  padding: "4px 0",
                }}
              >
                <button
                  onClick={() => { setMenuOpen(false); setRenaming(true) }}
                  style={{
                    width: "100%",
                    textAlign: "left",
                    padding: "8px 14px",
                    fontSize: 13,
                    color: "var(--text-2)",
                    background: "transparent",
                    border: "none",
                    cursor: "pointer",
                    fontFamily: "inherit",
                  }}
                  onMouseEnter={e => (e.currentTarget.style.background = "var(--surface-2)")}
                  onMouseLeave={e => (e.currentTarget.style.background = "transparent")}
                >
                  Rename
                </button>
                <button
                  onClick={() => { setMenuOpen(false); setConfirmValue("") }}
                  style={{
                    width: "100%",
                    textAlign: "left",
                    padding: "8px 14px",
                    fontSize: 13,
                    color: "var(--err)",
                    background: "transparent",
                    border: "none",
                    cursor: "pointer",
                    fontFamily: "inherit",
                  }}
                  onMouseEnter={e => (e.currentTarget.style.background = "var(--err-bg)")}
                  onMouseLeave={e => (e.currentTarget.style.background = "transparent")}
                >
                  Delete
                </button>
              </div>
            )}
          </div>
        </div>

        {/* Description */}
        <p
          style={{
            fontSize: 13,
            color: "var(--text-3)",
            margin: "0 0 4px",
            lineHeight: 1.5,
          }}
          onClick={onSelect}
        >
          {project.name}
        </p>
      </div>

      {/* Footer row */}
      <div
        style={{
          display: "flex",
          borderTop: "1px solid var(--border)",
          background: "var(--surface-2)",
        }}
        onClick={onSelect}
      >
        <div style={{ flex: 1, padding: "11px 20px" }}>
          <div style={{ fontSize: 17, fontWeight: 650, color: "var(--text)" }}>{project.agent_count ?? 0}</div>
          <div style={{ fontSize: 11, color: "var(--text-muted)" }}>agents</div>
        </div>
        <div style={{ flex: 1, padding: "11px 20px", borderLeft: "1px solid var(--border)" }}>
          <div style={{ fontSize: 17, fontWeight: 650, color: "var(--text)" }}>{timeAgo(project.created_at)}</div>
          <div style={{ fontSize: 11, color: "var(--text-muted)" }}>created</div>
        </div>
        <div
          style={{
            display: "grid",
            placeItems: "center",
            padding: "0 18px",
            borderLeft: "1px solid var(--border)",
            color: "var(--text-muted)",
          }}
        >
          <ArrowRightIcon />
        </div>
      </div>
    </div>
  )
}
