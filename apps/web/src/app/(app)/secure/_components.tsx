"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { timeAgo } from "@/lib/runUtils"

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

const SECURE_TABS = [
  { href: "/secure",           label: "Overview"  },
  { href: "/secure/policies",  label: "Policies"  },
  { href: "/secure/activity",  label: "Activity"  },
  { href: "/secure/settings",  label: "Settings"  },
]

export function SecureShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  return (
    <div style={{ maxWidth: 1240, margin: "0 auto", padding: "28px 24px 48px" }}>
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
            Security Loop for Claude Code — captures findings from every AI-assisted coding session.
          </p>
        </div>
      </div>
      <div className="guard-tab-nav">
        {SECURE_TABS.map(tab => {
          const isActive = tab.href === "/secure"
            ? pathname === "/secure"
            : pathname?.startsWith(tab.href)
          return (
            <Link key={tab.href} href={tab.href} className={`guard-tab${isActive ? " active" : ""}`}>
              {tab.label}
            </Link>
          )
        })}
      </div>
      {children}
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
            No findings — enable Security Emit in{" "}
            <Link href="/secure/settings" style={{ color: "var(--accent)", textDecoration: "none" }}>Settings</Link>
            {" "}to start capturing.
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
