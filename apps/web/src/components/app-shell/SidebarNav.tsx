"use client"

import { type MouseEvent as ReactMouseEvent } from "react"
import Link from "next/link"
import { Icons } from "./icons"
import { EnableGuardButton, SideNavItem } from "./nav-items"
import type { AppShellState } from "./useAppShellState"

export function SidebarNav({ shell, getToken }: { shell: AppShellState; getToken: (() => Promise<string | null>) | null }) {
  const {
    pathname,
    collapsed,
    pinnedReports,
    activeWorkspace,
    playbookCount,
    projects,
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
    submitCreateProject,
    submitProjectRename,
    activeProjectId,
    canSeeGuard,
    canSeeProjects,
    canCreateProject,
  } = shell
  return (
        <nav style={{ flex: 1, overflowY: "auto", padding: "4px 10px 8px" }}>

          {/* Dashboard — always first */}
          <SideNavItem
            href="/dashboard"
            label="Dashboard"
            icon={<Icons.Spark />}
            active={pathname.startsWith("/dashboard")}
            collapsed={collapsed}
          />

          {/* Lens — platform-wide assistant */}
          <SideNavItem
            href="/lens"
            label="Lens"
            icon={<Icons.Sparkles />}
            active={pathname.startsWith("/lens") && !pathname.startsWith("/lens/report-builder")}
            collapsed={collapsed}
          />

          {/* Reports — #1450 PR 5. Hidden until report builder is built properly.
              Re-enable by removing this false && guard once the surface ships. */}
          {false && (
            <>
              <SideNavItem
                href="/lens/report-builder"
                label="Reports"
                icon={<Icons.Spark />}
                active={pathname.startsWith("/lens/report-builder")}
                collapsed={collapsed}
              />
              {!collapsed && pinnedReports.length > 0 && (
                <div style={{ marginLeft: 28, marginTop: 2, marginBottom: 4, display: "flex", flexDirection: "column", gap: 1 }}>
                  {pinnedReports.map((r) => {
                    const href = `/lens/report-builder?slug=${encodeURIComponent(r.slug)}`
                    const active = false
                    return (
                      <Link
                        key={r.id}
                        href={href}
                        style={{
                          display: "block",
                          padding: "5px 10px",
                          borderRadius: 7,
                          fontSize: 13,
                          fontWeight: active ? 600 : 400,
                          color: active ? "var(--accent-text)" : "var(--text-3)",
                          background: active ? "var(--accent-weak)" : "transparent",
                          textDecoration: "none",
                        }}
                        onMouseEnter={(e: ReactMouseEvent<HTMLElement>) => { if (!active) (e.currentTarget as HTMLAnchorElement).style.background = "var(--surface-2)" }}
                        onMouseLeave={(e: ReactMouseEvent<HTMLElement>) => { if (!active) (e.currentTarget as HTMLAnchorElement).style.background = "transparent" }}
                        title={r.name}
                      >
                        {r.name}
                      </Link>
                    )
                  })}
                </div>
              )}
            </>
          )}

          {/* GOVERN group — Guard */}
          {!canSeeGuard && !collapsed && (
            <EnableGuardButton getToken={getToken} workspaceId={activeWorkspace?.id} />
          )}
          {canSeeGuard && (
            <div>
              {!collapsed && (
                <div style={{ padding: "12px 10px 5px", fontSize: 10, fontWeight: 700, letterSpacing: ".12em", textTransform: "uppercase", color: "var(--text-muted)" }}>
                  Govern
                </div>
              )}
              {collapsed && <div style={{ borderTop: "1px solid var(--border)", margin: "6px 0" }} />}
              <SideNavItem
                href="/governance"
                label="Governance"
                icon={<Icons.Eye />}
                active={pathname.startsWith("/governance")}
                collapsed={collapsed}
              />
              <SideNavItem
                href="/theguard"
                label="Guard"
                icon={<Icons.Shield />}
                active={pathname.startsWith("/theguard") || pathname.startsWith("/logs/guard")}
                collapsed={collapsed}
              />
              {/* Guard sub-nav removed — GuardShell now owns the section rail so both don't render the same six items. */}
              {/* Secure nav item removed entirely (PR #1846 / issue #1840) — code-scan module deleted; Guard Inbox tab lands in PR 2. */}
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
                  badge={projects.filter(p => (p.project_type ?? "user") === "user").length > 0 ? projects.filter(p => (p.project_type ?? "user") === "user").length : undefined}
                />
                {/* Inline project list when not collapsed — user projects only */}
                {!collapsed && canSeeProjects && projects.filter(p => (p.project_type ?? "user") === "user").length > 0 && pathname.startsWith("/projects") && (
                  <div style={{ marginLeft: 28, marginTop: 2, marginBottom: 2, display: "flex", flexDirection: "column", gap: 1 }}>
                    {projects.filter(p => (p.project_type ?? "user") === "user").map(project => {
                      const isActive = activeProjectId === project.id
                      const isRenaming = renamingProjectId === project.id
                      return (
                        <div key={project.id} style={{ display: "flex", alignItems: "center", gap: 6, padding: "4px 8px", borderRadius: 7, background: isActive ? "var(--accent-weak)" : "transparent" }}
                          onMouseEnter={(e: ReactMouseEvent<HTMLElement>) => { if (!isActive) (e.currentTarget as HTMLDivElement).style.background = "var(--surface-2)" }}
                          onMouseLeave={(e: ReactMouseEvent<HTMLElement>) => { if (!isActive) (e.currentTarget as HTMLDivElement).style.background = "transparent" }}
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
                                onMouseEnter={(e: ReactMouseEvent<HTMLElement>) => (e.currentTarget.style.opacity = "1")}
                                onMouseLeave={(e: ReactMouseEvent<HTMLElement>) => (e.currentTarget.style.opacity = "0")}
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
                          onMouseEnter={(e: ReactMouseEvent<HTMLElement>) => { (e.currentTarget as HTMLButtonElement).style.color = "var(--text-2)"; (e.currentTarget as HTMLButtonElement).style.background = "var(--surface-2)" }}
                          onMouseLeave={(e: ReactMouseEvent<HTMLElement>) => { (e.currentTarget as HTMLButtonElement).style.color = "var(--text-muted)"; (e.currentTarget as HTMLButtonElement).style.background = "transparent" }}
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
              href="/workflows"
              label="Workflows"
              icon={<Icons.Flow />}
              active={pathname.startsWith("/workflows")}
              collapsed={collapsed}
            />
            <SideNavItem
              href="/packs"
              label="Registry"
              icon={<Icons.Store />}
              active={pathname.startsWith("/packs")}
              collapsed={collapsed}
              badge={playbookCount}
            />
          </div>

          {/* CONNECT group */}
          <div>
            {!collapsed && (
              <div style={{ padding: "12px 10px 5px", fontSize: 10, fontWeight: 700, letterSpacing: ".12em", textTransform: "uppercase", color: "var(--text-muted)" }}>
                Connect
              </div>
            )}
            {collapsed && <div style={{ borderTop: "1px solid var(--border)", margin: "6px 0" }} />}
            <SideNavItem
              href="/agent-identity"
              label="Agent ID"
              icon={<Icons.Lock />}
              active={pathname.startsWith("/agent-identity")}
              collapsed={collapsed}
            />
            <SideNavItem
              href="/integrations"
              label="MCP Registry"
              icon={<Icons.Plug />}
              active={pathname.startsWith("/integrations")}
              collapsed={collapsed}
            />
            <SideNavItem
              href="/proxy/gateway-profiles"
              label="Gateways"
              icon={<Icons.Plug />}
              active={pathname.startsWith("/proxy")}
              collapsed={collapsed}
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
              href="/logs/guard"
              label="Logs"
              icon={<Icons.Pulse />}
              active={pathname.startsWith("/logs") || pathname.startsWith("/runs")}
              collapsed={collapsed}
            />
            {(pathname.startsWith("/logs") || pathname.startsWith("/runs")) && !collapsed && (
              <div style={{ marginLeft: 28, marginTop: 2, display: "flex", flexDirection: "column", gap: 1 }}>
                {[
                  { label: "Guard", href: "/logs/guard" },
                  { label: "Runs", href: "/logs/runs" },
                  { label: "Observability", href: "/logs/observability" },
                ].map(sub => {
                  const subActive = pathname.startsWith(sub.href)
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
                      onMouseEnter={(e: ReactMouseEvent<HTMLElement>) => { if (!subActive) (e.currentTarget as HTMLAnchorElement).style.background = "var(--surface-2)" }}
                      onMouseLeave={(e: ReactMouseEvent<HTMLElement>) => { if (!subActive) (e.currentTarget as HTMLAnchorElement).style.background = "transparent" }}
                    >
                      {sub.label}
                    </Link>
                  )
                })}
              </div>
            )}
          </div>
        </nav>
  )
}
