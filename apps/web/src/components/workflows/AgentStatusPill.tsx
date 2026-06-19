export default function AgentStatusPill({ s }: { s: string }) {
  const map: Record<string, { label: string; bg: string; color: string }> = {
    run:  { label: "Running",   bg: "var(--info-weak, #eff6ff)",  color: "var(--info, #2563eb)" },
    wait: { label: "Awaiting",  bg: "var(--warn-weak, #fffbeb)",  color: "var(--warn, #d97706)" },
    ok:   { label: "Succeeded", bg: "var(--ok-weak, #f0fdf4)",    color: "var(--ok, #16a34a)"   },
    err:  { label: "Failed",    bg: "var(--err-weak, #fff5f5)",   color: "var(--err, #dc2626)"  },
    idle: { label: "Never run", bg: "var(--surface-2)",           color: "var(--text-muted)"    },
  }
  const { label, bg, color } = map[s] ?? map.idle
  return (
    <span style={{ fontSize: 11, fontWeight: 650, padding: "2px 8px", borderRadius: 20, background: bg, color }}>
      {label}
    </span>
  )
}
