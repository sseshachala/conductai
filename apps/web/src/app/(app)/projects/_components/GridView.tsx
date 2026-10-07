"use client"

import { useEffect, useRef, useState, type MouseEvent as ReactMouseEvent } from "react"
import { useRouter } from "next/navigation"
import Link from "next/link"
import AgentStatusPill from "@/components/workflows/AgentStatusPill"
import { timeAgo } from "@/lib/runUtils"
import { avatarColor, mapStatus, PlusIcon, type Project, type Workflow } from "./shared"

// ── Grid view ─────────────────────────────────────────────────────────────────

export function GridView({
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
  const cancelRenameRef = useRef(false) // P2-3
  const color = avatarColor(project.name)

  useEffect(() => { if (renaming) renameRef.current?.focus() }, [renaming])
  useEffect(() => {
    function h(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuOpen(false)
    }
    document.addEventListener("mousedown", h)
    return () => document.removeEventListener("mousedown", h)
  }, [])

  // P2-3: check cancelledRef before committing rename on blur
  async function submitRename() {
    if (cancelRenameRef.current) { cancelRenameRef.current = false; return }
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
              onClick={(e: ReactMouseEvent<HTMLElement>) => e.stopPropagation()}
              onBlur={submitRename}
              onKeyDown={e => {
                if (e.key === "Enter") submitRename()
                if (e.key === "Escape") { cancelRenameRef.current = true; setNameValue(project.name); setRenaming(false) }
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
        {/* P2-8: aria-haspopup + role="menu" on dropdown */}
        <div ref={menuRef} style={{ position: "relative", flexShrink: 0 }} onClick={(e: ReactMouseEvent<HTMLElement>) => e.stopPropagation()}>
          <button
            className="btn btn-ghost btn-icon btn-sm"
            aria-label="Project actions"
            aria-haspopup="menu"
            style={{ opacity: hovered || menuOpen ? 1 : 0, transition: "opacity .15s" }}
            onClick={() => setMenuOpen(v => !v)}
          >⋯</button>
          {menuOpen && (
            <div role="menu" style={{ position: "absolute", right: 0, top: "calc(100% + 4px)", zIndex: 20, minWidth: 130, background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 10, boxShadow: "var(--shadow-md)", padding: "4px 0" }}>
              <button
                role="menuitem"
                onClick={() => { setMenuOpen(false); setRenaming(true) }}
                style={{ width: "100%", textAlign: "left", padding: "7px 14px", fontSize: 13, color: "var(--text)", background: "none", border: "none", cursor: "pointer" }}
                onMouseEnter={(e: ReactMouseEvent<HTMLElement>) => (e.currentTarget as HTMLElement).style.background = "var(--surface-2)"}
                onMouseLeave={(e: ReactMouseEvent<HTMLElement>) => (e.currentTarget as HTMLElement).style.background = "none"}
              >Rename</button>
              <button
                role="menuitem"
                onClick={() => { setMenuOpen(false); setConfirmDelete(true) }}
                style={{ width: "100%", textAlign: "left", padding: "7px 14px", fontSize: 13, color: "var(--err)", background: "none", border: "none", cursor: "pointer" }}
                onMouseEnter={(e: ReactMouseEvent<HTMLElement>) => (e.currentTarget as HTMLElement).style.background = "var(--surface-2)"}
                onMouseLeave={(e: ReactMouseEvent<HTMLElement>) => (e.currentTarget as HTMLElement).style.background = "none"}
              >Delete</button>
            </div>
          )}
        </div>
      </div>

      {/* Agent list */}
      <div style={{ borderTop: "1px solid var(--border)" }}>
        {agents.length === 0 ? (
          <div style={{ padding: "12px 18px", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <span style={{ fontSize: 12, color: "var(--text-muted)" }}>No workflows yet</span>
            <Link href={`/workflows/new?project_id=${project.id}`} className="btn btn-ghost btn-sm" style={{ fontSize: 11 }} onClick={(e: ReactMouseEvent<HTMLElement>) => e.stopPropagation()}>
              + New workflow
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
                  onClick={(e: ReactMouseEvent<HTMLElement>) => { e.stopPropagation(); router.push(`/workflows/${w.id}`) }} // P1-3: go to canvas
                  onMouseEnter={(e: ReactMouseEvent<HTMLElement>) => (e.currentTarget as HTMLElement).style.background = "var(--surface-2)"}
                  onMouseLeave={(e: ReactMouseEvent<HTMLElement>) => (e.currentTarget as HTMLElement).style.background = ""}
                >
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 13, fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", color: "var(--text)" }}>{w.name}</div>
                  </div>
                  <AgentStatusPill s={status} />
                  <Link
                    href={`/workflows/${w.id}`}
                    className="btn btn-ghost btn-icon btn-sm"
                    style={{ opacity: 0.6, fontSize: 12 }}
                    onClick={(e: ReactMouseEvent<HTMLElement>) => e.stopPropagation()}
                    title="Open canvas"
                  >→</Link>
                </div>
              )
            })}
            {agents.length > 4 && (
              <div
                style={{ padding: "9px 18px", fontSize: 12, color: "var(--text-muted)", cursor: "pointer", textAlign: "center", transition: "background .1s" }}
                onClick={() => router.push(`/projects/${project.id}`)}
                onMouseEnter={(e: ReactMouseEvent<HTMLElement>) => (e.currentTarget as HTMLElement).style.background = "var(--surface-2)"}
                onMouseLeave={(e: ReactMouseEvent<HTMLElement>) => (e.currentTarget as HTMLElement).style.background = ""}
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
