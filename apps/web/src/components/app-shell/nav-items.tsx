"use client"

import { useState, type MouseEvent as ReactMouseEvent } from "react"
import { apiUrl } from "@/lib/auth/runtime"
import Link from "next/link"
import { invalidate } from "@/lib/api/sharedCache"
import { Icons } from "./icons"

// ── EnableGuardButton ─────────────────────────────────────────────────────────

export function EnableGuardButton({ getToken, workspaceId }: { getToken?: (() => Promise<string | null>) | null; workspaceId?: string }) {
  const [loading, setLoading] = useState(false)

  async function handleEnable() {
    if (!workspaceId) return
    setLoading(true)
    try {
      const h: Record<string, string> = {}
      if (getToken) { const t = await getToken(); if (t) h["Authorization"] = `Bearer ${t}` }
      const res = await fetch(
        `${apiUrl()}/guard/config?workspace_id=${workspaceId}`,
        { headers: h }
      )
      if (res.ok) {
        invalidate(`${apiUrl()}/guard/config`)
        window.dispatchEvent(new CustomEvent("guard-install-changed", { detail: { installed: true } }))
      }
    } catch {}
    setLoading(false)
  }

  return (
    <div style={{ padding: "10px 10px 4px" }}>
      <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: ".12em", textTransform: "uppercase", color: "var(--text-muted)", marginBottom: 6 }}>
        Govern
      </div>
      <button
        onClick={handleEnable}
        disabled={loading}
        style={{
          width: "100%",
          padding: "7px 10px",
          borderRadius: 8,
          border: "1px dashed var(--border)",
          background: "transparent",
          color: "var(--text-3)",
          fontSize: 13,
          cursor: loading ? "wait" : "pointer",
          textAlign: "left",
          display: "flex",
          alignItems: "center",
          gap: 8,
        }}
      >
        <Icons.Shield />
        {loading ? "Enabling…" : "Enable Guard"}
      </button>
    </div>
  )
}

// ── SideNavItem ───────────────────────────────────────────────────────────────

export function SideNavItem({
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
      onMouseEnter={(e: ReactMouseEvent<HTMLAnchorElement>) => { if (!active) { e.currentTarget.style.background = "var(--surface-2)"; e.currentTarget.style.color = "var(--text)" } }}
      onMouseLeave={(e: ReactMouseEvent<HTMLAnchorElement>) => { if (!active) { e.currentTarget.style.background = "transparent"; e.currentTarget.style.color = "var(--text-2)" } }}
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
