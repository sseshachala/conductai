"use client"

import { type MouseEvent as ReactMouseEvent } from "react"
import Link from "next/link"
import { Icons } from "./icons"
import { UserChip } from "./UserChip"
import { Search, Sparkles } from "lucide-react"
import type { AppShellState } from "./useAppShellState"

export function Topbar({ shell }: { shell: AppShellState }) {
  const {
    pathname,
    isMobile,
    collapsed,
    userRole,
    notifOpen,
    setNotifOpen,
    notifRef,
    notifications,
    notificationsLoading,
    setPaletteOpen,
    setPaletteQuery,
    setPaletteActive,
    askLensQuery,
    setAskLensQuery,
    setLensPanelOpen,
    setLensPanelInitialQuery,
    setLensPanelEntry,
    setLensPanelGeneration,
    unreadCount,
    breadcrumbs,
  } = shell
  return (
        <header style={{
          flexShrink: 0,
          height: 60,
          background: "color-mix(in srgb, var(--surface) 80%, transparent)",
          backdropFilter: "blur(8px)",
          borderBottom: "1px solid var(--border)",
          display: "flex",
          alignItems: "center",
          padding: isMobile ? "0 8px" : "0 20px",
          gap: isMobile ? 6 : 12,
        }}>
          {/* Breadcrumbs */}
          <div style={{ display: "flex", alignItems: "center", gap: 6, flex: 1, minWidth: 0 }}>
            {(isMobile ? breadcrumbs.slice(-1) : breadcrumbs).map((crumb, i) => (
              <div key={i} style={{ display: "flex", alignItems: "center", gap: 6, minWidth: 0 }}>
                {i > 0 && (
                  <span style={{ color: "var(--text-muted)", display: "flex", alignItems: "center" }}>
                    <Icons.ChevRight />
                  </span>
                )}
                <span style={{
                  fontSize: 14,
                  fontWeight: i === breadcrumbs.length - 1 ? 600 : 400,
                  color: i === breadcrumbs.length - 1 ? "var(--text)" : "var(--text-3)",
                  whiteSpace: "nowrap",
                  overflow: "hidden", textOverflow: "ellipsis",
                }}>
                  {crumb}
                </span>
              </div>
            ))}
          </div>

          {/* Right cluster */}
          <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0 }}>
            {/* Global "Ask Lens" bar (#1333 #5) — hidden while on /lens (Lens has its own composer). */}
            {isMobile && !pathname?.startsWith("/lens") && <>
              <button type="button" className="btn btn-sm" style={{ width: 34, height: 34, padding: 0, display: "grid", placeItems: "center" }} title="Ask Lens" aria-label="Ask Lens" onClick={() => setLensPanelOpen(true)}><Sparkles size={16} /></button>
              <button type="button" className="btn btn-sm" style={{ width: 34, height: 34, padding: 0, display: "grid", placeItems: "center" }} title="Command palette" aria-label="Command palette" onClick={() => { setPaletteOpen(true); setPaletteQuery(""); setPaletteActive(0) }}><Search size={16} /></button>
            </>}
            {!isMobile && !pathname?.startsWith("/lens") && (
              <form
                onSubmit={(e) => {
                  e.preventDefault()
                  const q = askLensQuery.trim()
                  if (!q) return
                  setLensPanelInitialQuery(q)
                  setLensPanelEntry(null)
                  setLensPanelGeneration(n => n + 1)
                  setLensPanelOpen(true)
                  setAskLensQuery("")
                }}
                style={{
                  display: "flex", alignItems: "center", gap: 6,
                  padding: "3px 10px", borderRadius: 8,
                  border: "1px solid var(--border)",
                  background: "var(--surface-2)",
                  width: 280,
                }}
              >
                <Icons.Sparkles />
                <input
                  type="text"
                  value={askLensQuery}
                  onChange={(e) => setAskLensQuery(e.target.value)}
                  placeholder="Ask Lens…"
                  aria-label="Ask Lens"
                  style={{
                    flex: 1, background: "transparent", border: "none",
                    outline: "none", color: "var(--text)", fontSize: 13,
                  }}
                />
                <button
                  type="button"
                  onClick={() => { setPaletteOpen(true); setPaletteQuery(""); setPaletteActive(0) }}
                  title="Command palette"
                  style={{
                    padding: "1px 5px", borderRadius: 4, border: "1px solid var(--border-2)",
                    background: "var(--surface-3)", color: "var(--text-muted)",
                    fontFamily: "inherit", fontSize: 10.5, cursor: "pointer",
                  }}
                >⌘K</button>
              </form>
            )}

            {/* Bell / notifications */}
            <div ref={notifRef} style={{ position: "relative" }}>
              <button
                onClick={() => setNotifOpen(v => !v)}
                aria-label="Notifications"
                style={{
                  position: "relative", width: 34, height: 34, borderRadius: 8,
                  border: "1px solid var(--border)", background: "var(--surface-2)",
                  cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center",
                  color: "var(--text-2)",
                }}
                onMouseEnter={(e: ReactMouseEvent<HTMLElement>) => (e.currentTarget.style.background = "var(--surface-3)")}
                onMouseLeave={(e: ReactMouseEvent<HTMLElement>) => (e.currentTarget.style.background = "var(--surface-2)")}
              >
                <Icons.Bell />
                {unreadCount > 0 && (
                  <span style={{
                    position: "absolute", top: 5, right: 5, width: 7, height: 7,
                    borderRadius: "50%", background: "var(--err)",
                    border: "1.5px solid var(--surface)",
                  }} />
                )}
              </button>

              {/* Notifications popover */}
              {notifOpen && (
                <div style={{
                  position: "absolute", zIndex: 200, top: "calc(100% + 8px)", right: 0,
                  width: isMobile ? "min(360px, calc(100vw - 88px))" : 360, background: "var(--surface)",
                  ...(isMobile ? { position: "fixed" as const, top: 64, left: 72, right: 8 } : {}),
                  border: "1px solid var(--border)", borderRadius: 12,
                  boxShadow: "var(--shadow-lg)",
                  overflow: "hidden",
                }}>
                  <div style={{ padding: "12px 16px 10px", display: "flex", alignItems: "center", justifyContent: "space-between", borderBottom: "1px solid var(--border)" }}>
                    <span style={{ fontSize: 13, fontWeight: 700, color: "var(--text)" }}>Notifications</span>
                    {unreadCount > 0 && (
                      <span style={{
                        fontSize: 10.5, fontWeight: 700, padding: "1px 7px", borderRadius: 20,
                        background: "var(--err-bg)", color: "var(--err)",
                      }}>{unreadCount} unread</span>
                    )}
                  </div>
                  <div style={{ overflowY: "auto", maxHeight: 340 }}>
                    {notificationsLoading ? (
                      <div style={{ padding: "16px", fontSize: 12, color: "var(--text-muted)" }}>Loading activity...</div>
                    ) : notifications.length === 0 ? (
                      <div style={{ padding: "16px", fontSize: 12, color: "var(--text-muted)" }}>No recent activity.</div>
                    ) : notifications.map(n => {
                      const toneColors: Record<string, { bg: string; color: string }> = {
                        warn: { bg: "var(--warn-bg)", color: "var(--warn)" },
                        err: { bg: "var(--err-bg)", color: "var(--err)" },
                        ok: { bg: "var(--ok-bg)", color: "var(--ok)" },
                        info: { bg: "var(--info-bg)", color: "var(--info)" },
                      }
                      const tc = toneColors[n.tone] ?? toneColors.info
                      const isSecurity = n.id.startsWith("sf-")
                      const isGuardBlock = n.id.startsWith("guard-")
                      const toneIcon = isSecurity ? "🛡" : isGuardBlock ? "🚫" : n.tone === "warn" ? "⚠" : n.tone === "err" ? "✕" : n.tone === "ok" ? "✓" : "i"
                      const Wrapper = n.href ? "a" : "div"
                      return (
                        <Wrapper key={n.id} href={n.href} style={{
                          display: "flex", alignItems: "flex-start", gap: 12,
                          padding: "12px 16px",
                          borderBottom: "1px solid var(--border)",
                          background: n.unread ? "var(--surface-2)" : "var(--surface)",
                          textDecoration: "none", cursor: n.href ? "pointer" : "default",
                        }}>
                          <div style={{
                            width: 30, height: 30, borderRadius: 8, flexShrink: 0,
                            background: tc.bg, color: tc.color,
                            display: "flex", alignItems: "center", justifyContent: "center",
                            fontWeight: 700, fontSize: 13,
                          }}>
                            {toneIcon}
                          </div>
                          <div style={{ flex: 1, minWidth: 0 }}>
                            <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
                              <span style={{ fontSize: 13, fontWeight: 700, color: "var(--text)" }}>{n.title}</span>
                              {n.unread && (
                                <span style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--accent)", flexShrink: 0 }} />
                              )}
                            </div>
                            <div style={{ fontSize: 12, color: "var(--text-muted)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                              {n.desc}
                            </div>
                          </div>
                          <span style={{ fontSize: 11, color: "var(--text-muted)", flexShrink: 0 }}>{n.time}</span>
                        </Wrapper>
                      )
                    })}
                  </div>
                  <div style={{ padding: "10px 16px", borderTop: "1px solid var(--border)" }}>
                    <Link
                      href="/runs"
                      onClick={() => setNotifOpen(false)}
                      style={{ fontSize: 12.5, color: "var(--accent-text)", fontWeight: 600, textDecoration: "none" }}
                    >
                      View all activity →
                    </Link>
                  </div>
                </div>
              )}
            </div>

            {/* User avatar / settings / logout */}
            <UserChip collapsed={false} userRole={userRole} topbar />
          </div>
        </header>
  )
}
