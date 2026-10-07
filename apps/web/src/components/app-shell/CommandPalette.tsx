"use client"

import { type MouseEvent as ReactMouseEvent } from "react"
import { Icons } from "./icons"
import type { AppShellState } from "./useAppShellState"

export function CommandPalette({ shell }: { shell: AppShellState }) {
  const {
    router,
    setPaletteOpen,
    paletteQuery,
    setPaletteQuery,
    paletteActive,
    setPaletteActive,
    paletteInputRef,
    filteredCommands,
    groupedCommands,
  } = shell
  return (
      <div
        style={{
          position: "fixed", inset: 0, zIndex: 1000,
          background: "rgba(28,25,23,0.4)",
          backdropFilter: "blur(4px)",
          display: "flex", alignItems: "flex-start", justifyContent: "center",
          paddingTop: "15vh",
        }}
        onClick={(e: ReactMouseEvent<HTMLElement>) => { if (e.target === e.currentTarget) setPaletteOpen(false) }}
      >
        <div style={{
          width: 560, maxWidth: "calc(100vw - 24px)", maxHeight: "60vh",
          background: "var(--surface)",
          borderRadius: 14,
          border: "1px solid var(--border)",
          boxShadow: "var(--shadow-lg)",
          overflow: "hidden",
          display: "flex", flexDirection: "column",
        }}>
          {/* Search input */}
          <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "12px 16px", borderBottom: "1px solid var(--border)" }}>
            <Icons.Search />
            <input
              ref={paletteInputRef}
              value={paletteQuery}
              onChange={e => { setPaletteQuery(e.target.value); setPaletteActive(0) }}
              onKeyDown={e => {
                if (e.key === "ArrowDown") { e.preventDefault(); setPaletteActive(v => Math.min(v + 1, filteredCommands.length - 1)) }
                if (e.key === "ArrowUp") { e.preventDefault(); setPaletteActive(v => Math.max(v - 1, 0)) }
                if (e.key === "Enter" && filteredCommands[paletteActive]) {
                  router.push(filteredCommands[paletteActive].href)
                  setPaletteOpen(false)
                }
                if (e.key === "Escape") setPaletteOpen(false)
              }}
              placeholder="Jump to a screen..."
              style={{
                flex: 1, fontSize: 14, background: "transparent", border: "none", outline: "none",
                color: "var(--text)",
              }}
            />
            <kbd style={{
              fontSize: 10.5, padding: "2px 7px", borderRadius: 5,
              background: "var(--surface-3)", border: "1px solid var(--border-2)",
              color: "var(--text-muted)", fontFamily: "inherit",
            }}>esc</kbd>
          </div>

          {/* Results */}
          <div style={{ overflowY: "auto", flex: 1 }}>
            {Object.entries(groupedCommands).map(([group, cmds]) => (
              <div key={group}>
                <div style={{ padding: "8px 16px 4px", fontSize: 10, fontWeight: 700, letterSpacing: ".12em", textTransform: "uppercase", color: "var(--text-muted)" }}>
                  {group}
                </div>
                {cmds.map(cmd => {
                  const flatIdx = filteredCommands.findIndex(c => c.href === cmd.href && c.label === cmd.label)
                  const isActive = flatIdx === paletteActive
                  const IconComp = Icons[cmd.icon]
                  return (
                    <button
                      key={cmd.href + cmd.label}
                      onMouseEnter={() => setPaletteActive(flatIdx)}
                      onClick={() => { router.push(cmd.href); setPaletteOpen(false) }}
                      style={{
                        display: "flex", alignItems: "center", gap: 10, width: "100%",
                        padding: "8px 16px", fontSize: 13.5, fontWeight: 500,
                        background: isActive ? "var(--accent-weak)" : "transparent",
                        color: isActive ? "var(--accent-text)" : "var(--text-2)",
                        border: "none", cursor: "pointer", textAlign: "left",
                      }}
                    >
                      <span style={{ color: isActive ? "var(--accent-text)" : "var(--text-muted)" }}>
                        <IconComp />
                      </span>
                      {cmd.label}
                    </button>
                  )
                })}
              </div>
            ))}
            {filteredCommands.length === 0 && (
              <div style={{ padding: "24px 16px", textAlign: "center", fontSize: 13, color: "var(--text-muted)" }}>
                No results found
              </div>
            )}
          </div>
        </div>
      </div>
  )
}
