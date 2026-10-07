"use client"

import { type MouseEvent as ReactMouseEvent } from "react"
import { Icons } from "./icons"
import type { AppShellState } from "./useAppShellState"

export function WorkspaceSwitcher({ shell }: { shell: AppShellState }) {
  const {
    router,
    collapsed,
    wsOpen,
    setWsOpen,
    wsRef,
    workspaces,
    activeWorkspace,
    setActiveWorkspace,
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
    submitCreateTeam,
    confirmDeleteTeam,
    wsInitials,
    wsOrgLabel,
    wsName,
  } = shell
  return (
        <div style={{ padding: "10px 10px 6px", flexShrink: 0 }} ref={wsRef}>
          {!collapsed ? (
            <div
              onClick={() => setWsOpen(v => !v)}
              style={{
                margin: "0 2px",
                padding: "9px 11px",
                borderRadius: 10,
                border: "1px solid var(--border)",
                background: "var(--surface-2)",
                cursor: "pointer",
                display: "flex",
                alignItems: "center",
                gap: 10,
                position: "relative",
              }}
              onMouseEnter={(e: ReactMouseEvent<HTMLElement>) => (e.currentTarget.style.borderColor = "var(--border-2)")}
              onMouseLeave={(e: ReactMouseEvent<HTMLElement>) => (e.currentTarget.style.borderColor = "var(--border)")}
            >
              <div style={{
                width: 26, height: 26, borderRadius: 7,
                background: "var(--accent)", color: "#fff",
                display: "flex", alignItems: "center", justifyContent: "center",
                fontWeight: 700, fontSize: 12, flexShrink: 0,
              }}>
                {wsInitials}
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", color: "var(--text-muted)", letterSpacing: "0.06em" }}>
                  {wsOrgLabel}
                </div>
                <div style={{ fontSize: 13.5, fontWeight: 600, color: "var(--text)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                  {wsName}
                </div>
              </div>
              <div style={{ color: "var(--text-muted)", flexShrink: 0 }}>
                <Icons.ChevDown />
              </div>
            </div>
          ) : (
            <div
              onClick={() => setWsOpen(v => !v)}
              style={{
                width: 36, height: 36, borderRadius: 7,
                background: "var(--accent)", color: "#fff",
                display: "flex", alignItems: "center", justifyContent: "center",
                fontWeight: 700, fontSize: 12, cursor: "pointer", margin: "0 auto",
              }}
            >
              {wsInitials}
            </div>
          )}

          {/* Workspace dropdown */}
          {wsOpen && !collapsed && (
            <div style={{
              position: "absolute",
              zIndex: 100,
              top: "auto",
              left: 10,
              width: 224,
              background: "var(--surface)",
              border: "1px solid var(--border)",
              borderRadius: 12,
              boxShadow: "var(--shadow-md)",
              padding: "4px 0",
              marginTop: 4,
            }}>
              <p style={{ padding: "6px 12px 4px", fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.1em", color: "var(--text-muted)" }}>
                Workspaces
              </p>
              {workspaces.map(ws => (
                <div key={ws.id}>
                  {deletingTeamId === ws.id ? (
                    <div style={{ padding: "8px 12px", background: "var(--err-bg)", borderTop: "1px solid #fecaca", borderBottom: "1px solid #fecaca" }}>
                      <p style={{ fontSize: 12, color: "var(--err)", marginBottom: 6 }}>Type <strong>{ws.name}</strong> to confirm deletion</p>
                      <div style={{ display: "flex", gap: 6 }}>
                        <input
                          ref={deleteConfirmRef}
                          value={deleteConfirmValue}
                          onChange={e => setDeleteConfirmValue(e.target.value)}
                          onKeyDown={e => {
                            if (e.key === "Enter") confirmDeleteTeam(ws)
                            if (e.key === "Escape") { setDeletingTeamId(null); setDeleteConfirmValue("") }
                          }}
                          placeholder={ws.name}
                          style={{ flex: 1, fontSize: 12, border: "1px solid #fecaca", borderRadius: 6, padding: "4px 8px", outline: "none" }}
                        />
                        <button
                          onClick={() => confirmDeleteTeam(ws)}
                          disabled={deleteConfirmValue !== ws.name}
                          style={{ fontSize: 12, padding: "4px 8px", borderRadius: 6, background: "var(--err)", color: "#fff", border: "none", cursor: "pointer", opacity: deleteConfirmValue !== ws.name ? 0.4 : 1 }}
                        >Delete</button>
                        <button
                          onClick={() => { setDeletingTeamId(null); setDeleteConfirmValue("") }}
                          style={{ fontSize: 12, padding: "4px 8px", borderRadius: 6, background: "transparent", border: "none", cursor: "pointer", color: "var(--text-2)" }}
                        >Cancel</button>
                      </div>
                    </div>
                  ) : (
                    <div style={{ display: "flex", alignItems: "center", padding: "0 12px" }}
                      onMouseEnter={(e: ReactMouseEvent<HTMLElement>) => (e.currentTarget.style.background = "var(--surface-2)")}
                      onMouseLeave={(e: ReactMouseEvent<HTMLElement>) => (e.currentTarget.style.background = "transparent")}
                    >
                      <button
                        onClick={() => { setActiveWorkspace(ws as Parameters<typeof setActiveWorkspace>[0]); setWsOpen(false); router.refresh() }}
                        style={{
                          flex: 1, display: "flex", alignItems: "center", gap: 8,
                          padding: "8px 0", fontSize: 13.5, textAlign: "left",
                          background: "transparent", border: "none", cursor: "pointer",
                          fontWeight: ws.id === activeWorkspace?.id ? 600 : 400,
                          color: ws.id === activeWorkspace?.id ? "var(--text)" : "var(--text-2)",
                        }}
                      >
                        <span style={{
                          width: 20, height: 20, borderRadius: 5,
                          background: "var(--accent-weak-2)", color: "var(--accent-text)",
                          fontSize: 10, fontWeight: 700,
                          display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0,
                        }}>
                          {ws.name[0].toUpperCase()}
                        </span>
                        <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{ws.name}</span>
                        {ws.id === activeWorkspace?.id && <span style={{ color: "var(--accent)", fontSize: 12 }}>✓</span>}
                      </button>
                      <button
                        onClick={() => { setDeletingTeamId(ws.id); setDeleteConfirmValue("") }}
                        style={{ fontSize: 11, padding: "2px 4px", background: "transparent", border: "none", cursor: "pointer", color: "var(--text-muted)", opacity: 0 }}
                        onMouseEnter={(e: ReactMouseEvent<HTMLElement>) => { (e.currentTarget as HTMLButtonElement).style.opacity = "1"; (e.currentTarget as HTMLButtonElement).style.color = "var(--err)" }}
                        onMouseLeave={(e: ReactMouseEvent<HTMLElement>) => { (e.currentTarget as HTMLButtonElement).style.opacity = "0" }}
                        title="Delete workspace"
                        aria-label="Delete workspace"
                      >
                        ✕
                      </button>
                    </div>
                  )}
                </div>
              ))}
              <div style={{ borderTop: "1px solid var(--border)", marginTop: 4, padding: "4px 12px" }}>
                {creatingTeam ? (
                  <input
                    ref={newTeamInputRef}
                    value={newTeamValue}
                    onChange={e => setNewTeamValue(e.target.value)}
                    onBlur={submitCreateTeam}
                    onKeyDown={e => { if (e.key === "Enter") submitCreateTeam(); if (e.key === "Escape") { setCreatingTeam(false); setNewTeamValue("") } }}
                    placeholder="Workspace name"
                    style={{ width: "100%", fontSize: 13, border: "1px solid var(--border)", borderRadius: 8, padding: "6px 10px", outline: "none" }}
                  />
                ) : (
                  <button
                    onClick={() => setCreatingTeam(true)}
                    style={{
                      width: "100%", display: "flex", alignItems: "center", gap: 8,
                      padding: "8px 0", fontSize: 12, background: "transparent", border: "none",
                      cursor: "pointer", color: "var(--text-3)",
                    }}
                  >
                    + New workspace
                  </button>
                )}
              </div>
            </div>
          )}
        </div>
  )
}
