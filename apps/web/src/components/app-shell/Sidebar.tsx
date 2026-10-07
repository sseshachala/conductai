"use client"

import Link from "next/link"
import { Icons } from "./icons"
import { SideNavItem } from "./nav-items"
import { PanelLeftClose, PanelLeftOpen } from "lucide-react"
import { WorkspaceSwitcher } from "./WorkspaceSwitcher"
import { SidebarNav } from "./SidebarNav"
import type { AppShellState } from "./useAppShellState"

export function Sidebar({ shell, getToken }: { shell: AppShellState; getToken: (() => Promise<string | null>) | null }) {
  const {
    pathname,
    isMobile,
    mobileNavOpen,
    setMobileNavOpen,
    sidebarRef,
    collapsed,
    setCollapsed,
    workspaceRouteActive,
    workspaceGroupOpen,
    setWorkspaceGroupOpen,
  } = shell
  return (
      <aside ref={sidebarRef} onClickCapture={e => { if (isMobile && (e.target as Element).closest("a[href]")) setMobileNavOpen(false) }} role={isMobile && mobileNavOpen ? "dialog" : undefined} aria-modal={isMobile && mobileNavOpen ? true : undefined} aria-label="Main navigation" style={{
        position: isMobile && mobileNavOpen ? "fixed" : undefined,
        inset: isMobile && mobileNavOpen ? "0 auto 0 0" : undefined,
        zIndex: isMobile && mobileNavOpen ? 300 : undefined,
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
              title="Collapse sidebar"
              style={{
                padding: "4px 6px", borderRadius: 6, border: "none",
                background: "transparent", cursor: "pointer",
                color: "var(--text-muted)", fontSize: 14, lineHeight: 1,
              }}
            >
              <PanelLeftClose size={16} />
            </button>
          )}
        </div>

        {/* Workspace selector */}
        <WorkspaceSwitcher shell={shell} />

        {/* Nav scroll area */}
        <SidebarNav shell={shell} getToken={getToken} />

        {/* Sidebar footer */}
        <div style={{ borderTop: "1px solid var(--border)", padding: "8px 10px", flexShrink: 0 }}>
          {/* Collapse toggle (only shows when expanded — collapsed gets expand button in the topbar area) */}
          {collapsed && (
            <button
              onClick={() => setCollapsed(false)}
              aria-label="Expand sidebar"
              title="Expand sidebar"
              style={{
                display: "flex", alignItems: "center", justifyContent: "center",
                width: "100%", padding: "6px 0",
                background: "transparent", border: "none", cursor: "pointer",
                color: "var(--text-muted)", fontSize: 16, marginBottom: 4,
              }}
            >
              <PanelLeftOpen size={16} />
            </button>
          )}
          {/* Workspace group — collapsible header. In the icon-only rail
              (collapsed sidebar) items always render; in the expanded rail
              they render only when the group is open or a workspace route
              is active. */}
          {!collapsed && (
            <button
              type="button"
              onClick={() => setWorkspaceGroupOpen(v => !v)}
              aria-expanded={workspaceGroupOpen || workspaceRouteActive}
              style={{
                display: "flex", alignItems: "center", justifyContent: "space-between",
                width: "100%", padding: "8px 10px", marginBottom: 2,
                background: "transparent", border: "none", cursor: "pointer",
                fontSize: 10, fontWeight: 700, letterSpacing: ".12em",
                textTransform: "uppercase", color: "var(--text-muted)",
              }}
            >
              <span>Workspace</span>
              <span aria-hidden style={{ fontSize: 11, transition: "transform .15s", transform: (workspaceGroupOpen || workspaceRouteActive) ? "rotate(90deg)" : "rotate(0deg)" }}>›</span>
            </button>
          )}
          {(collapsed || workspaceGroupOpen || workspaceRouteActive) && (
            <>
              <SideNavItem
                href="/settings"
                label="Settings"
                icon={<Icons.Gear />}
                active={pathname.startsWith("/settings")}
                collapsed={collapsed}
              />
            </>
          )}
        </div>
      </aside>
  )
}
