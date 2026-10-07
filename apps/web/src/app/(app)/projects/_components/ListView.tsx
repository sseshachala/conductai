"use client"

import { useEffect, useRef, useState, type MouseEvent as ReactMouseEvent } from "react"
import { useRouter } from "next/navigation"
import Link from "next/link"
import AgentStatusPill from "@/components/workflows/AgentStatusPill"
// P2-1: import timeAgo from runUtils to avoid duplication
import { timeAgo } from "@/lib/runUtils"
import { avatarColor, mapStatus, type Project, type Workflow } from "./shared"

// ── List view ─────────────────────────────────────────────────────────────────

export function ListView({
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
  const cancelRenameRef = useRef(false) // P2-3
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

  // P2-3: check cancelledRef before committing rename on blur
  async function submitRename() {
    if (cancelRenameRef.current) { cancelRenameRef.current = false; return }
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
              onClick={(e: ReactMouseEvent<HTMLElement>) => e.stopPropagation()}
              onBlur={submitRename}
              onKeyDown={e => {
                if (e.key === "Enter") submitRename()
                if (e.key === "Escape") { cancelRenameRef.current = true; setNameValue(project.name); setRenaming(false) }
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

        <div style={{ display: "flex", gap: 6, alignItems: "center" }} onClick={(e: ReactMouseEvent<HTMLElement>) => e.stopPropagation()}>
          <Link
            href={`/workflows/new?project_id=${project.id}`}
            className="btn btn-ghost btn-sm"
            style={{ fontSize: 11 }}
            onClick={(e: ReactMouseEvent<HTMLElement>) => e.stopPropagation()}
          >
            + Agent
          </Link>
          <div ref={menuRef} style={{ position: "relative" }}>
            {/* P2-8: aria-haspopup on trigger */}
            <button
              className="btn btn-ghost btn-icon btn-sm"
              aria-label="Project actions"
              aria-haspopup="menu"
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

      {/* Agent rows — only rendered when agents are loaded */}
      {agents.map((w, idx) => (
        <AgentRow
          key={w.id}
          workflow={w}
          isLast={idx === agents.length - 1}
          router={router}
        />
      ))}
    </div>
  )
}

// P1-3: row click → canvas (primary); P1-4: Runs stays as secondary button
function AgentRow({ workflow: w, isLast, router }: { workflow: Workflow; isLast: boolean; router: ReturnType<typeof useRouter> }) {
  const status = mapStatus(w.last_run_status)
  return (
    <div
      style={{ display: "grid", gridTemplateColumns: "2fr 1fr 80px", gap: 14, padding: "11px 18px 11px 58px", borderBottom: isLast ? "none" : "1px solid var(--border)", alignItems: "center", cursor: "pointer", transition: "background .12s" }}
      onClick={() => router.push(`/workflows/${w.id}`)}
      onMouseEnter={(e: ReactMouseEvent<HTMLElement>) => (e.currentTarget as HTMLElement).style.background = "var(--surface-2)"}
      onMouseLeave={(e: ReactMouseEvent<HTMLElement>) => (e.currentTarget as HTMLElement).style.background = ""}
    >
      <div style={{ minWidth: 0 }}>
        <div style={{ fontWeight: 600, fontSize: 13.5, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", color: "var(--text)" }}>{w.name}</div>
        <div className="mono" style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 2 }}>edited {timeAgo(w.updated_at)}</div>
      </div>
      <AgentStatusPill s={status} />
      <div style={{ display: "flex", gap: 4, justifyContent: "flex-end" }} onClick={(e: ReactMouseEvent<HTMLElement>) => e.stopPropagation()}>
        <Link
          href={`/workflows/${w.id}/runs`}
          className="btn btn-ghost btn-sm"
          style={{ fontSize: 11, padding: "3px 9px" }}
          aria-label="View runs"
        >Runs</Link>
        <Link
          href={`/workflows/${w.id}`}
          className="btn btn-ghost btn-icon btn-sm"
          aria-label="Open in canvas"
        >→</Link>
      </div>
    </div>
  )
}
