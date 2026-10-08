/** Shared first-load placeholder rows for Guard lists. `gap` = spaced rounded cards; default = flush table-style rows. */
export function GuardSkeletonRows({ count = 4, gap = false }: { count?: number; gap?: boolean }) {
  return (
    <div aria-hidden="true" style={gap ? { display: "flex", flexDirection: "column", gap: 8 } : undefined}>
      {Array.from({ length: count }, (_, i) => (
        <div key={i} style={{
          height: 44, background: "var(--surface-2)",
          opacity: gap ? 0.6 : 0.5, borderRadius: gap ? 8 : 0,
          borderBottom: gap ? undefined : "1px solid var(--border)",
        }} />
      ))}
    </div>
  )
}
