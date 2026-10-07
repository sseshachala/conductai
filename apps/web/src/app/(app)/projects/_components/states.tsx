"use client"

import { PlusIcon } from "./shared"

// ── Loading skeleton ──────────────────────────────────────────────────────────

// P1-8: reads view from localStorage before rendering so skeleton matches the chosen layout
export function LoadingSkeleton() {
  const storedView = typeof window !== "undefined" ? localStorage.getItem("projects_view") : null
  const isGrid = storedView === "grid"
  if (isGrid) {
    return (
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))", gap: 14 }}>
        {[1, 2, 3, 4].map(i => (
          <div key={i} style={{ height: 200, borderRadius: 14, border: "1px solid var(--border)", background: "var(--surface)", opacity: 0.5, animation: "pulse 1.5s ease-in-out infinite" }} />
        ))}
      </div>
    )
  }
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {[1, 2, 3].map(i => (
        <div key={i} style={{ height: 140, borderRadius: 12, border: "1px solid var(--border)", background: "var(--surface)", opacity: 0.5, animation: "pulse 1.5s ease-in-out infinite" }} />
      ))}
    </div>
  )
}

// ── Empty states ──────────────────────────────────────────────────────────────

export function EmptyState({ onNew, hasQuery }: { onNew: () => void; hasQuery: boolean }) {
  return (
    <div style={{ padding: "60px 20px", textAlign: "center" }}>
      <p style={{ fontWeight: 650, fontSize: 16, color: "var(--text)", marginBottom: 8 }}>
        {hasQuery ? "No projects match" : "Create your first project"}
      </p>
      <p style={{ fontSize: 13.5, color: "var(--text-3)", marginBottom: 20, maxWidth: 360, margin: "0 auto 20px", lineHeight: 1.6 }}>
        {hasQuery
          ? "Try a different search term."
          : "A project groups your agents, runs, and credentials. Think of it as one repo or one team."}
      </p>
      {!hasQuery && (
        <button onClick={onNew} className="btn btn-primary">
          <PlusIcon size={14} /> New project
        </button>
      )}
    </div>
  )
}

export function AutomationEmpty() {
  return (
    <div style={{ padding: "60px 20px", textAlign: "center" }}>
      <p style={{ fontWeight: 650, fontSize: 16, color: "var(--text)", marginBottom: 8 }}>No automation project yet</p>
      <p style={{ fontSize: 13.5, color: "var(--text-3)", maxWidth: 400, margin: "0 auto", lineHeight: 1.6 }}>
        Install Security Loop from the registry. A Security Automation project will be created automatically — all triage and fix runs live here.
      </p>
    </div>
  )
}
