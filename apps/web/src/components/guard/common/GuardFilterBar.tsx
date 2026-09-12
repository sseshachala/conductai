// Filter bar for Guard event pages.
//
// Pill-style toggles on the left (open/triaging/resolved, blocked/warned/
// allowed, etc.) plus a slot on the right for dropdowns, date pickers,
// or actions. Pages currently roll their own — Inbox has one arrangement,
// Activity another, Approvals a third. This is the shared shell.
//
// The pills accept optional counts so a page can render
// "Open 79 | Triaging 3 | Resolved 14 | All" without redefining the
// visual style each time.

export interface FilterPill<T extends string> {
  value: T
  label: string
  count?: number
}

export function GuardFilterBar<T extends string>({
  pills,
  active,
  onChange,
  children,
}: {
  pills: readonly FilterPill<T>[]
  active: T
  onChange: (v: T) => void
  children?: React.ReactNode
}) {
  return (
    <div style={{
      display: "flex", gap: 8, marginBottom: 12,
      flexWrap: "wrap", alignItems: "center",
    }}>
      {pills.map(p => {
        const isActive = p.value === active
        return (
          <button
            key={p.value}
            onClick={() => onChange(p.value)}
            style={{
              padding: "6px 12px",
              fontSize: 12,
              borderRadius: 4,
              border: "1px solid var(--border)",
              background: isActive ? "var(--accent-bg, var(--accent-weak))" : "var(--surface)",
              color:      isActive ? "var(--accent-text, var(--accent))"    : "var(--text-muted)",
              fontWeight: isActive ? 600 : 400,
              cursor: "pointer",
            }}
          >
            {p.label}
            {p.count != null && (
              <span style={{ marginLeft: 6, fontSize: 11, opacity: 0.7 }}>
                {p.count}
              </span>
            )}
          </button>
        )
      })}
      {children != null && (
        <>
          <div style={{ width: 1, background: "var(--border)", height: 24, margin: "0 4px" }} />
          {children}
        </>
      )}
    </div>
  )
}
