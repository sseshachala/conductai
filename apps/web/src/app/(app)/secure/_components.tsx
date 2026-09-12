"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { useEffect, useState } from "react"
import { timeAgo } from "@/lib/runUtils"
import { SECURE_SECTIONS, activeSecureSection, type SecureSectionId } from "@/lib/navigation/secureSections"

const COLLAPSE_KEY = "secure:railCollapsed"
const RAIL_EXPANDED = 200
const RAIL_COLLAPSED = 56

export function SecureLoopIcon({ size = 20 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
    </svg>
  )
}

export type Severity = "critical" | "high" | "medium" | "low" | "info"
export type FindingStatus = "open" | "triaging" | "fixed" | "dismissed"

export interface SecurityFinding {
  id: string
  severity: Severity
  type: string
  file: string | null
  line: number | null
  description: string
  tool: string | null
  repo_full_name: string | null
  reporter_email: string | null
  status: FindingStatus
  created_at: string
  source_run_id?: string | null
}

export const STATUS_TRANSITIONS: Record<FindingStatus, { label: string; next: FindingStatus; tone: string }[]> = {
  open:      [{ label: "Acknowledge", next: "triaging", tone: "warn" }, { label: "Dismiss", next: "dismissed", tone: "err" }],
  triaging:  [{ label: "Mark fixed",  next: "fixed",    tone: "ok"   }, { label: "Dismiss", next: "dismissed", tone: "err" }],
  fixed:     [{ label: "Reopen",      next: "open",     tone: "warn" }],
  dismissed: [{ label: "Reopen",      next: "open",     tone: "warn" }],
}

export const SEVERITY_STYLES: Record<Severity, { bg: string; color: string; label: string }> = {
  critical: { bg: "#fee2e2", color: "#dc2626", label: "Critical" },
  high:     { bg: "#fff7ed", color: "#ea580c", label: "High" },
  medium:   { bg: "#fefce8", color: "#ca8a04", label: "Medium" },
  low:      { bg: "#eff6ff", color: "#2563eb", label: "Low" },
  info:     { bg: "#f5f5f4", color: "#78716c", label: "Info" },
}

export const STATUS_STYLES: Record<FindingStatus, { bg: string; color: string; label: string }> = {
  open:      { bg: "var(--surface-3)", color: "var(--text-3)",     label: "Open" },
  triaging:  { bg: "var(--info-bg)",   color: "var(--info)",       label: "Triaging" },
  fixed:     { bg: "var(--ok-bg)",     color: "var(--ok)",         label: "Fixed" },
  dismissed: { bg: "var(--surface-3)", color: "var(--text-muted)", label: "Dismissed" },
}

function SectionIcon({ id }: { id: SecureSectionId }) {
  const common = { width: 16, height: 16, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 2, strokeLinecap: "round" as const, strokeLinejoin: "round" as const }
  switch (id) {
    case "overview": return <svg {...common}><path d="M3 3h7v7H3zm11 0h7v7h-7zM3 14h7v7H3zm11 0h7v7h-7z" /></svg>
    case "findings": return <svg {...common}><circle cx="11" cy="11" r="8" /><path d="m21 21-4.35-4.35" /></svg>
  }
}

function ChevronLeft() {
  return <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="15 18 9 12 15 6" /></svg>
}

function ChevronRight() {
  return <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="9 18 15 12 9 6" /></svg>
}

function RailItem({
  href, label, icon, active, collapsed,
}: {
  href: string
  label: string
  icon: React.ReactNode
  active: boolean
  collapsed: boolean
}) {
  return (
    <Link
      href={href}
      aria-current={active ? "page" : undefined}
      aria-label={collapsed ? label : undefined}
      title={collapsed ? label : undefined}
      style={{
        display: "flex",
        alignItems: "center",
        gap: 10,
        padding: collapsed ? "8px" : "8px 12px",
        justifyContent: collapsed ? "center" : "flex-start",
        fontSize: 13.5,
        fontWeight: active ? 650 : 500,
        color: active ? "var(--text)" : "var(--text-3)",
        background: active ? "var(--surface-2)" : "transparent",
        borderRadius: 6,
        textDecoration: "none",
        transition: "background .12s, color .12s",
      }}
    >
      <span style={{ display: "flex", flexShrink: 0 }}>{icon}</span>
      {!collapsed && <span>{label}</span>}
    </Link>
  )
}

export function SecureShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const activeId = activeSecureSection(pathname ?? "")
  const [collapsed, setCollapsed] = useState(false)

  useEffect(() => {
    if (typeof window === "undefined") return
    try { if (window.localStorage.getItem(COLLAPSE_KEY) === "1") setCollapsed(true) } catch { /* ignore */ }
  }, [])

  useEffect(() => {
    if (typeof window === "undefined") return
    try { window.localStorage.setItem(COLLAPSE_KEY, collapsed ? "1" : "0") } catch { /* ignore */ }
  }, [collapsed])

  const railWidth = collapsed ? RAIL_COLLAPSED : RAIL_EXPANDED

  return (
    <div style={{ display: "grid", gridTemplateColumns: "auto 1fr", minHeight: "100%" }}>
      {/* Truly-left rail — mirrors GuardShell. */}
      <aside style={{
        width: railWidth,
        borderRight: "1px solid var(--border)",
        padding: "12px 8px 16px",
        display: "flex",
        flexDirection: "column",
        gap: 2,
        transition: "width .15s ease",
      }}>
        {/* Collapse toggle at top, right-aligned when expanded, centered when collapsed. */}
        <div style={{ display: "flex", justifyContent: collapsed ? "center" : "flex-end", marginBottom: 8 }}>
          <button
            onClick={() => setCollapsed(c => !c)}
            aria-label={collapsed ? "Expand Secure nav" : "Collapse Secure nav"}
            title={collapsed ? "Expand" : "Collapse"}
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              width: 28,
              height: 28,
              padding: 0,
              border: "none",
              background: "transparent",
              color: "var(--text-3)",
              cursor: "pointer",
              borderRadius: 6,
              transition: "background .12s",
            }}
            onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.background = "var(--surface-2)" }}
            onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.background = "transparent" }}
          >
            {collapsed ? <ChevronRight /> : <ChevronLeft />}
          </button>
        </div>

        <nav aria-label="Secure sections" style={{ display: "flex", flexDirection: "column", gap: 2 }}>
          {SECURE_SECTIONS.map(s => (
            <RailItem
              key={s.id}
              href={s.href}
              label={s.label}
              icon={<SectionIcon id={s.id} />}
              active={s.id === activeId}
              collapsed={collapsed}
            />
          ))}
        </nav>
      </aside>

      {/* Right column: header + content, centered inside. */}
      <div style={{ padding: "28px 24px 48px", minWidth: 0 }}>
        <div style={{ maxWidth: 1080, margin: "0 auto" }}>
          <div style={{ display: "flex", alignItems: "flex-start", marginBottom: 20 }}>
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: 11 }}>
                <span style={{ width: 32, height: 32, borderRadius: 9, background: "#dc2626", color: "#fff", display: "grid", placeItems: "center", flexShrink: 0 }}>
                  <SecureLoopIcon size={16} />
                </span>
                <h1 style={{ fontSize: 22, fontWeight: 700, color: "var(--text)", letterSpacing: "-.02em", margin: 0 }}>
                  Secure
                </h1>
                <span className="sbadge ok" style={{ marginTop: 2 }}>
                  <span className="conduct-pulse-dot" />
                  active
                </span>
              </div>
              <p style={{ fontSize: 13, color: "var(--text-3)", marginTop: 5 }}>
                Security findings from every scan — PR reviews, BugHunter, Guard violations. Triages automatically, triggers fixes.
              </p>
            </div>
          </div>
          {children}
        </div>
      </div>
    </div>
  )
}

export function SeverityPill({ severity }: { severity: Severity }) {
  const s = SEVERITY_STYLES[severity] ?? SEVERITY_STYLES.info
  return (
    <span style={{
      display: "inline-flex", alignItems: "center",
      padding: "2px 9px", borderRadius: 20,
      fontSize: 11, fontWeight: 700,
      background: s.bg, color: s.color, whiteSpace: "nowrap",
    }}>
      {s.label}
    </span>
  )
}

export function StatusBadge({ status }: { status: FindingStatus }) {
  const s = STATUS_STYLES[status] ?? STATUS_STYLES.open
  return (
    <span style={{
      display: "inline-flex", alignItems: "center",
      padding: "2px 9px", borderRadius: 20,
      fontSize: 11, fontWeight: 600,
      background: s.bg, color: s.color, whiteSpace: "nowrap",
    }}>
      {s.label}
    </span>
  )
}

export function FindingsTable({
  findings,
  loading,
  onStatusChange,
  updating = {},
}: {
  findings: SecurityFinding[]
  loading: boolean
  onStatusChange?: (id: string, next: FindingStatus) => void
  updating?: Record<string, boolean>
}) {
  const withActions = !!onStatusChange
  const cols = withActions
    ? "100px 110px 1.2fr 1.6fr 90px 100px 70px 110px 140px"
    : "100px 120px 1.4fr 2fr 90px 110px 80px 100px"
  const headers = withActions
    ? ["Severity", "Type", "File", "Description", "Tool", "Reporter", "Age", "Status", "Actions"]
    : ["Severity", "Type", "File", "Description", "Tool", "Repo", "Age", "Status"]

  return (
    <div className="card" style={{ overflow: "hidden", marginBottom: 26 }}>
      <div style={{ display: "grid", gridTemplateColumns: cols, gap: 12, padding: "10px 20px", borderBottom: "1px solid var(--border)", background: "var(--surface-2)" }}>
        {headers.map(h => <div key={h} className="eyebrow" style={{ fontSize: 10 }}>{h}</div>)}
      </div>
      {loading ? (
        <div style={{ padding: 20, fontSize: 13, color: "var(--text-muted)" }}>Loading…</div>
      ) : findings.length === 0 ? (
        <div style={{ padding: "48px 20px", textAlign: "center" }}>
          <div style={{ fontSize: 13, color: "var(--text-muted)", marginBottom: 6 }}>
            No findings yet. Install the Security Scanner playbook or run BugHunter to start capturing.
          </div>
        </div>
      ) : findings.map((f, i, arr) => {
        const filePart = f.file ? (f.line != null ? `${f.file}:${f.line}` : f.file) : "—"
        const reporter = f.reporter_email ? f.reporter_email.split("@")[0] : (f.repo_full_name || "—")
        const busy = !!updating[f.id]
        const transitions = STATUS_TRANSITIONS[f.status] ?? []
        return (
          <div
            key={f.id}
            style={{ display: "grid", gridTemplateColumns: cols, gap: 12, padding: "12px 20px", borderBottom: i < arr.length - 1 ? "1px solid var(--border)" : "none", alignItems: "center", opacity: busy ? 0.6 : 1 }}
            onMouseEnter={e => (e.currentTarget.style.background = "var(--surface-2)")}
            onMouseLeave={e => (e.currentTarget.style.background = "")}
          >
            <SeverityPill severity={f.severity} />
            <div style={{ fontSize: 12.5, color: "var(--text-2)", fontWeight: 500 }}>{f.type || "—"}</div>
            <div className="mono" style={{ fontSize: 11.5, color: "var(--text-3)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={filePart !== "—" ? filePart : undefined}>{filePart}</div>
            <div style={{ fontSize: 12.5, color: "var(--text-2)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={f.description}>{f.description.length > 72 ? f.description.slice(0, 69) + "…" : f.description}</div>
            <div style={{ fontSize: 12, color: "var(--text-3)" }}>{f.tool || "—"}</div>
            <div className="mono" title={f.reporter_email ?? undefined} style={{ fontSize: 11.5, color: "var(--text-muted)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{reporter}</div>
            <div style={{ fontSize: 12, color: "var(--text-3)" }}>{timeAgo(f.created_at)}</div>
            <StatusBadge status={f.status} />
            {withActions && (
              <div style={{ display: "flex", gap: 5, flexWrap: "wrap" }}>
                {transitions.map(t => (
                  <button
                    key={t.next}
                    disabled={busy}
                    onClick={() => onStatusChange!(f.id, t.next)}
                    style={{
                      fontSize: 10.5, fontWeight: 600, padding: "3px 8px", borderRadius: 6, cursor: busy ? "wait" : "pointer",
                      border: `1px solid ${t.tone === "ok" ? "var(--ok-bd)" : t.tone === "warn" ? "var(--warn-bd)" : "var(--err-bd)"}`,
                      background: t.tone === "ok" ? "var(--ok-bg)" : t.tone === "warn" ? "var(--warn-bg)" : "var(--err-bg)",
                      color: t.tone === "ok" ? "var(--ok)" : t.tone === "warn" ? "var(--warn)" : "var(--err)",
                    }}
                  >
                    {t.label}
                  </button>
                ))}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
