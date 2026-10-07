"use client"

import { type MouseEvent as ReactMouseEvent } from "react"
import { CATEGORY_LABELS, CAT_BLOCK, FRIENDLY_NAMES, GRADE_STYLES, type Playbook } from "./catalog"

export function PlaybookCard({
  playbook,
  installing,
  installCount,
  grade,
  onInstall,
  onViewYaml,
}: {
  playbook: Playbook
  installing: boolean
  installCount: number
  grade?: string
  onInstall: (slug: string) => void
  onViewYaml: (slug: string) => void
}) {
  const blockType = CAT_BLOCK[playbook.category] ?? "brain"
  const displayName = FRIENDLY_NAMES[playbook.slug] ?? playbook.name
  const catLabel = CATEGORY_LABELS[playbook.category] ?? playbook.category
  const blockCount = playbook.block_count ?? playbook.tags?.length ?? 0
  const installCountDisplay = playbook.install_count ?? installCount

  return (
    <div
      className="card"
      style={{
        padding: "16px 18px",
        display: "flex",
        flexDirection: "column",
        transition: "border-color .14s, box-shadow .14s",
        position: "relative",
      }}
      onMouseEnter={(e: ReactMouseEvent<HTMLElement>) => {
        (e.currentTarget as HTMLDivElement).style.boxShadow = "var(--shadow-md)"
        ;(e.currentTarget as HTMLDivElement).style.borderColor = "var(--border-2)"
      }}
      onMouseLeave={(e: ReactMouseEvent<HTMLElement>) => {
        (e.currentTarget as HTMLDivElement).style.boxShadow = ""
        ;(e.currentTarget as HTMLDivElement).style.borderColor = "var(--border)"
      }}
    >
      {/* Grade badge, top right */}
      {grade && (
        <span
          className={`text-[10px] px-1.5 py-0.5 rounded font-semibold tabular-nums ${GRADE_STYLES[grade] ?? "bg-stone-100 text-stone-500"}`}
          title={`Quality grade: ${grade}`}
          style={{ position: "absolute", top: 14, right: 14 }}
        >
          {grade}
        </span>
      )}

      {/* Category chip + popular badge */}
      <div style={{ display: "flex", alignItems: "center", gap: 9, marginBottom: 10 }}>
        <span
          style={{
            display: "inline-flex",
            alignItems: "center",
            height: 21,
            padding: "0 9px",
            borderRadius: 20,
            fontSize: 9.5,
            fontWeight: 700,
            letterSpacing: ".05em",
            textTransform: "uppercase",
            background: `var(--blk-${blockType}-bg)`,
            color: `var(--blk-${blockType}-tx)`,
            border: `1px solid var(--blk-${blockType}-bd)`,
          }}
        >
          {catLabel}
        </span>
        {playbook.featured && (
          <span style={{ fontSize: 9.5, fontWeight: 800, color: "var(--accent-text)", letterSpacing: ".05em" }}>
            ★ POPULAR
          </span>
        )}
      </div>

      {/* Name */}
      <div style={{ fontWeight: 650, fontSize: 15, marginBottom: 5, letterSpacing: "-.01em", color: "var(--text)", paddingRight: grade ? 32 : 0 }}>
        {displayName}
      </div>

      {/* Description */}
      <p style={{ fontSize: 12.5, color: "var(--text-3)", lineHeight: 1.45, margin: "0 0 14px", flex: 1 }}>
        {playbook.description}
      </p>

      {/* Meta row: trigger · blocks · installs */}
      <div style={{ display: "flex", alignItems: "center", gap: 14, fontSize: 11.5, color: "var(--text-muted)", marginBottom: 13 }}>
        {playbook.trigger && (
          <span style={{ display: "flex", alignItems: "center", gap: 5, minWidth: 0, overflow: "hidden" }}>
            <svg width={13} height={13} viewBox="0 0 13 13" fill="none" style={{ flexShrink: 0 }}>
              <path d="M7 1L3 7.5h4L5.5 12 10 5.5H6.5L7 1z" fill="currentColor" />
            </svg>
            <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontFamily: "ui-monospace, monospace", fontSize: 11 }}>
              {playbook.trigger}
            </span>
          </span>
        )}
        {blockCount > 0 && (
          <span style={{ display: "flex", alignItems: "center", gap: 4, flexShrink: 0 }}>
            <svg width={13} height={13} viewBox="0 0 13 13" fill="none">
              <rect x="1" y="1" width="4.5" height="4.5" rx="1" stroke="currentColor" strokeWidth="1.3" />
              <rect x="7.5" y="1" width="4.5" height="4.5" rx="1" stroke="currentColor" strokeWidth="1.3" />
              <rect x="1" y="7.5" width="4.5" height="4.5" rx="1" stroke="currentColor" strokeWidth="1.3" />
              <rect x="7.5" y="7.5" width="4.5" height="4.5" rx="1" stroke="currentColor" strokeWidth="1.3" />
            </svg>
            {blockCount} blocks
          </span>
        )}
        {installCountDisplay > 0 && (
          <span style={{ marginLeft: "auto", whiteSpace: "nowrap", flexShrink: 0 }}>
            {installCountDisplay} installs
          </span>
        )}
      </div>

      {/* Action buttons */}
      <div style={{ display: "flex", gap: 8 }}>
        <button
          onClick={() => onInstall(playbook.slug)}
          disabled={installing}
          style={{
            flex: 1,
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            gap: 5,
            height: 32,
            borderRadius: 7,
            fontSize: 12,
            fontWeight: 600,
            cursor: installing ? "not-allowed" : "pointer",
            opacity: installing ? 0.5 : 1,
            transition: "all .12s",
            border: "1px solid var(--accent)",
            background: "var(--accent)",
            color: "#fff",
          }}
        >
          + Install
        </button>
        <button
          onClick={() => onViewYaml(playbook.slug)}
          title="Preview YAML"
          style={{
            width: 32,
            height: 32,
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            borderRadius: 7,
            border: "1px solid var(--border)",
            background: "transparent",
            color: "var(--text-2)",
            cursor: "pointer",
            flexShrink: 0,
            transition: "all .12s",
          }}
          onMouseEnter={(e: ReactMouseEvent<HTMLElement>) => { (e.currentTarget as HTMLButtonElement).style.background = "var(--surface-2)"; (e.currentTarget as HTMLButtonElement).style.color = "var(--text)" }}
          onMouseLeave={(e: ReactMouseEvent<HTMLElement>) => { (e.currentTarget as HTMLButtonElement).style.background = "transparent"; (e.currentTarget as HTMLButtonElement).style.color = "var(--text-2)" }}
        >
          <svg width={15} height={15} viewBox="0 0 15 15" fill="none">
            <path d="M3 4.5h9M3 7.5h6M3 10.5h4" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
            <path d="M11.5 10l1.5 1.5-1.5 1.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
      </div>
    </div>
  )
}
