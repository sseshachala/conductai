"use client"

/**
 * Section tab bar — underline style. Used to switch primary sections on a
 * single page (e.g. /settings, /agent-identity). NOT for marketplace-style
 * pill filters (see /packs for that pattern).
 *
 * Callers own state and URL persistence. This component is pure display.
 *
 * Usage:
 *   const [tab, setTab] = useState<Tab>("tokens")
 *   <TabBar
 *     tabs={["tokens", "run_tokens", "identities"]}
 *     labels={{ tokens: "Tokens", run_tokens: "Run tokens", identities: "Identities" }}
 *     activeTab={tab}
 *     onSelect={setTab}
 *   />
 */
export function TabBar<T extends string>({
  tabs,
  labels,
  activeTab,
  onSelect,
  idPrefix = "tab",
}: {
  tabs: readonly T[]
  labels: Record<T, string>
  activeTab: T
  onSelect: (tab: T) => void
  idPrefix?: string
}) {
  return (
    <div role="tablist" style={{ display: "flex", gap: 4, borderBottom: "1px solid var(--border)" }}>
      {tabs.map(tab => (
        <button
          key={tab}
          role="tab"
          aria-selected={activeTab === tab}
          aria-controls={`tabpanel-${tab}`}
          id={`${idPrefix}-${tab}`}
          onClick={() => onSelect(tab)}
          style={{
            background: "none",
            border: "none",
            padding: "9px 14px",
            fontSize: 13.5,
            fontWeight: 600,
            cursor: "pointer",
            marginBottom: -1,
            color: activeTab === tab ? "var(--text)" : "var(--text-3)",
            borderBottom: activeTab === tab ? "2px solid var(--accent)" : "2px solid transparent",
          }}
        >
          {labels[tab]}
        </button>
      ))}
    </div>
  )
}
