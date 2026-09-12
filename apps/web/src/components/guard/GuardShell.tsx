"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { usePathname } from "next/navigation"
import { useGuardRole } from "@/hooks/useGuardRole"
import { GUARD_SECTIONS, activeGuardSection, type GuardSectionId } from "@/lib/navigation/guardSections"

const COLLAPSE_KEY = "guard:railCollapsed"
const RAIL_EXPANDED = 200
const RAIL_COLLAPSED = 56

// ─── Helpers ──────────────────────────────────────────────────────────────────

function relativeTime(ts: Date | null | undefined): string {
  if (!ts) return "never"
  const sec = Math.floor((Date.now() - ts.getTime()) / 1000)
  if (sec < 5) return "just now"
  if (sec < 60) return `${sec}s ago`
  const min = Math.floor(sec / 60)
  if (min < 60) return `${min}m ago`
  return `${Math.floor(min / 60)}h ago`
}

function SectionIcon({ id }: { id: GuardSectionId }) {
  const common = { width: 16, height: 16, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 2, strokeLinecap: "round" as const, strokeLinejoin: "round" as const }
  switch (id) {
    case "overview":    return <svg {...common}><path d="M3 3h7v7H3zm11 0h7v7h-7zM3 14h7v7H3zm11 0h7v7h-7z" /></svg>
    case "inbox":       return <svg {...common}><path d="M22 12h-6l-2 3h-4l-2-3H2" /><path d="M5.45 5.11L2 12v6a2 2 0 002 2h16a2 2 0 002-2v-6l-3.45-6.89A2 2 0 0016.76 4H7.24a2 2 0 00-1.79 1.11z" /></svg>
    case "agents":      return <svg {...common}><path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2" /><circle cx="9" cy="7" r="4" /><path d="M23 21v-2a4 4 0 00-3-3.87M16 3.13a4 4 0 010 7.75" /></svg>
    case "controls":    return <svg {...common}><rect x="3" y="11" width="18" height="11" rx="2" /><path d="M7 11V7a5 5 0 0110 0v4" /></svg>
    case "activity":    return <svg {...common}><polyline points="22 12 18 12 15 21 9 3 6 12 2 12" /></svg>
    case "spend":       return <svg {...common}><path d="M12 2v20M17 5H9.5a3.5 3.5 0 000 7h5a3.5 3.5 0 010 7H6" /></svg>
    case "connections": return <svg {...common}><path d="M9 3v4M15 3v4M9 7a3 3 0 000 6h6a3 3 0 000-6M12 13v8" /></svg>
  }
}

function ComplianceIcon() {
  const common = { width: 16, height: 16, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 2, strokeLinecap: "round" as const, strokeLinejoin: "round" as const }
  return <svg {...common}><path d="M9 12l2 2 4-4" /><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" /></svg>
}

function SettingsIcon() {
  const common = { width: 16, height: 16, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 2, strokeLinecap: "round" as const, strokeLinejoin: "round" as const }
  return <svg {...common}><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z" /></svg>
}

function ChevronLeft() {
  return <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="15 18 9 12 15 6" /></svg>
}

function ChevronRight() {
  return <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="9 18 15 12 9 6" /></svg>
}

// ─── Rail item ────────────────────────────────────────────────────────────────

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

// ─── Props ────────────────────────────────────────────────────────────────────

export interface GuardShellProps {
  children: React.ReactNode
  lastFetched?: Date | null
  live?: boolean
  agentCount?: number | null
  proxyCount?: number | null
  advisory?: boolean
}

// ─── Component ────────────────────────────────────────────────────────────────

export function GuardShell({
  children,
  lastFetched,
  live = true,
  agentCount,
  proxyCount,
  advisory = false,
}: GuardShellProps) {
  const pathname = usePathname()
  const [, setTick] = useState(0)
  const activeId = activeGuardSection(pathname ?? "")
  const { role } = useGuardRole()

  const [collapsed, setCollapsed] = useState(false)

  // Hydrate collapse state from localStorage on mount.
  useEffect(() => {
    if (typeof window === "undefined") return
    try { if (window.localStorage.getItem(COLLAPSE_KEY) === "1") setCollapsed(true) } catch { /* ignore */ }
  }, [])

  useEffect(() => {
    if (typeof window === "undefined") return
    try { window.localStorage.setItem(COLLAPSE_KEY, collapsed ? "1" : "0") } catch { /* ignore */ }
  }, [collapsed])

  // Re-render every 10s so the "last updated" timestamp stays fresh.
  useEffect(() => {
    const t = setInterval(() => setTick(n => n + 1), 10_000)
    return () => clearInterval(t)
  }, [])

  const showCompliance = role === "admin" || role === "security"
  const showSettings   = role === "admin"
  const hasAdminItems  = showCompliance || showSettings

  const isComplianceActive = pathname?.startsWith("/theguard/compliance") ?? false
  const isSettingsActive   = pathname?.startsWith("/theguard/settings") ?? false

  const railWidth = collapsed ? RAIL_COLLAPSED : RAIL_EXPANDED

  return (
    <div style={{ display: "grid", gridTemplateColumns: "auto 1fr", minHeight: "100%" }}>
      {/* Truly-left rail: flush against content-area edge, extends full height. */}
      <aside style={{
        width: railWidth,
        borderRight: "1px solid var(--border)",
        padding: "12px 8px 16px",
        display: "flex",
        flexDirection: "column",
        gap: 2,
        transition: "width .15s ease",
      }}>
        {/* Collapse toggle — top of rail, right-aligned when expanded, centered when collapsed. */}
        <div style={{ display: "flex", justifyContent: collapsed ? "center" : "flex-end", marginBottom: 8 }}>
          <button
            onClick={() => setCollapsed(c => !c)}
            aria-label={collapsed ? "Expand Guard nav" : "Collapse Guard nav"}
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

        <nav aria-label="Guard sections" style={{ display: "flex", flexDirection: "column", gap: 2 }}>
          {GUARD_SECTIONS.map(s => (
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

        {/* Admin cluster — bottom of rail, role-gated. */}
        {hasAdminItems && (
          <>
            <div style={{ margin: "12px 8px 6px", borderTop: "1px solid var(--border)" }} />
            <nav aria-label="Guard admin" style={{ display: "flex", flexDirection: "column", gap: 2 }}>
              {showCompliance && (
                <RailItem
                  href="/theguard/compliance"
                  label="Compliance"
                  icon={<ComplianceIcon />}
                  active={isComplianceActive}
                  collapsed={collapsed}
                />
              )}
              {showSettings && (
                <RailItem
                  href="/theguard/settings"
                  label="Settings"
                  icon={<SettingsIcon />}
                  active={isSettingsActive}
                  collapsed={collapsed}
                />
              )}
            </nav>
          </>
        )}

      </aside>

      {/* Right column: header + content, centered inside. */}
      <div style={{ padding: "28px 24px 48px", minWidth: 0 }}>
        <div style={{ maxWidth: 1080, margin: "0 auto" }}>
          <div style={{ display: "flex", alignItems: "flex-start", marginBottom: 20 }}>
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: 11 }}>
                <h1 style={{ fontSize: 22, fontWeight: 700, color: "var(--text)", letterSpacing: "-.02em", margin: 0 }}>
                  Guard
                </h1>
                {live ? (
                  <span className="sbadge ok" style={{ marginTop: 2 }}>
                    <span className="conduct-pulse-dot" />
                    live
                  </span>
                ) : (
                  <span className="sbadge" style={{ marginTop: 2, background: "var(--surface-3)", color: "var(--text-muted)", border: "1px solid var(--border)" }}>
                    offline
                  </span>
                )}
                {advisory && (
                  <span style={{ marginTop: 2, fontSize: 11, fontWeight: 700, padding: "2px 9px", borderRadius: 20, background: "var(--warn-bg)", color: "var(--warn)", border: "1px solid var(--warn-bd)", letterSpacing: ".04em" }}>
                    ADVISORY
                  </span>
                )}
                {(agentCount != null || proxyCount != null) && (
                  <span style={{
                    marginTop: 2,
                    fontSize: 11.5,
                    fontWeight: 600,
                    padding: "2px 8px",
                    borderRadius: 6,
                    background: "var(--surface-2)",
                    color: "var(--text-2)",
                    border: "1px solid var(--border)",
                  }}>
                    {agentCount ?? 0} agent · {proxyCount ?? 0} proxy
                  </span>
                )}
              </div>
              <p style={{ fontSize: 13, color: "var(--text-3)", marginTop: 5 }}>
                MDM for AI coding tools — when a hard cap is hit, every tool call across Claude Code, Codex, and Cursor is blocked immediately and your security team is notified on Slack.
              </p>
            </div>
            <div style={{ marginLeft: "auto", fontSize: 12, color: "var(--text-muted)", paddingTop: 4 }}>
              {lastFetched != null ? <>last updated: {relativeTime(lastFetched)}</> : null}
            </div>
          </div>

          {children}
        </div>
      </div>
    </div>
  )
}
