// Section divider used inside Guard pages — e.g. "Ad-hoc sessions ·
// 50 events" on Activity, "More metrics" on Overview, "Recent events"
// on Inbox row expand. Same treatment everywhere so section boundaries
// scan the same.

export function GuardSectionHeader({
  title,
  subtitle,
  right,
}: {
  title: string
  subtitle?: string
  right?: React.ReactNode
}) {
  return (
    <div style={{
      display: "flex", alignItems: "center", gap: 12, marginBottom: 10,
    }}>
      <span style={{
        fontSize: 11, textTransform: "uppercase", letterSpacing: 0.5,
        color: "var(--text-muted)", fontWeight: 600,
      }}>
        {title}
      </span>
      {subtitle && (
        <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
          {subtitle}
        </span>
      )}
      <div style={{ flex: 1, height: 1, background: "var(--border)" }} />
      {right}
    </div>
  )
}
