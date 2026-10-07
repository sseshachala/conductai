// Friendly display names for known framework prefixes.
export const FRAMEWORK_LABEL: Record<string, string> = {
  SOC2: "SOC 2",
  ISO_42001: "ISO 42001",
  ISO_27001: "ISO 27001",
  EU_AI_ACT: "EU AI Act",
  GDPR: "GDPR",
  HIPAA: "HIPAA",
  PCI_DSS: "PCI DSS",
  OWASP: "OWASP Top 10",
  NIST: "NIST AI RMF",
  NIS2: "NIS 2",
  DORA: "DORA",
}

export function KpiCard({ label, value, sub, tone = "neutral", delta, deltaSemantic = "neutral" }: {
  label: string
  value: string
  sub?: string
  tone?: "neutral" | "good" | "warn"
  delta?: number | null              // signed % vs baseline; null/undefined hides
  deltaSemantic?: "neutral" | "more_is_better" | "less_is_better"
}) {
  const valueColor =
    tone === "good" ? "var(--accent-text)" :
    tone === "warn" ? "var(--text-1)" : "var(--text-1)"

  // Color the delta arrow based on direction + semantic.
  let deltaColor = "var(--text-3)"
  if (typeof delta === "number" && delta !== 0) {
    if (deltaSemantic === "more_is_better") {
      deltaColor = delta > 0 ? "#16a34a" : "#dc2626"
    } else if (deltaSemantic === "less_is_better") {
      deltaColor = delta > 0 ? "#dc2626" : "#16a34a"
    }
  }

  return (
    <div style={{
      border: "1px solid var(--border)",
      borderRadius: 8,
      padding: "14px 16px",
      background: "var(--surface-1)",
    }}>
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 6 }}>
        <div style={{ fontSize: 11, color: "var(--text-muted)", letterSpacing: ".06em", textTransform: "uppercase" }}>
          {label}
        </div>
        {typeof delta === "number" && (
          <span title="vs 7-day average" style={{ fontSize: 11, fontWeight: 600, color: deltaColor }}>
            {delta > 0 ? "↑" : delta < 0 ? "↓" : "—"} {Math.abs(delta)}%
          </span>
        )}
      </div>
      <div style={{ fontSize: 24, fontWeight: 600, color: valueColor, marginTop: 6 }}>{value}</div>
      <div style={{ fontSize: 11, color: "var(--text-3)", marginTop: 4 }}>{sub ?? "\u00a0"}</div>
    </div>
  )
}

export const fmtUsd = (n: number) =>
  n >= 1000 ? `$${(n / 1000).toFixed(1)}k` : `$${n.toFixed(0)}`

// Reusable shimmer skeleton — for progressive section loads.
export function Skeleton({ height = 14, width = "100%", radius = 6, style }: { height?: number | string; width?: number | string; radius?: number; style?: React.CSSProperties }) {
  return (
    <span
      aria-hidden="true"
      style={{
        display: "inline-block",
        height: typeof height === "number" ? `${height}px` : height,
        width: typeof width === "number" ? `${width}px` : width,
        borderRadius: radius,
        background: "linear-gradient(90deg, var(--surface-2) 0%, var(--surface-3, var(--border)) 50%, var(--surface-2) 100%)",
        backgroundSize: "200% 100%",
        animation: "conduct-skel 1.4s ease-in-out infinite",
        ...style,
      }}
    />
  )
}

// Format a drilled rule as YAML for inline preview.
export function formatRuleYaml(r: {
  rule_id: string
  description?: string | null
  action: string
  severity?: string | null
  match_tool?: string | null
  match_pattern?: string | null
  match_path_pattern?: string | null
  recommendation?: string | null
  iso_control?: string | null
  frameworks?: string[]
  pack_slug: string
}): string {
  const yq = (v: string) => /[:#\-?{}\[\],&*!|>'"%@`]/.test(v) || v.includes("  ") ? JSON.stringify(v) : v
  const lines: string[] = []
  lines.push(`- id: ${r.rule_id}`)
  if (r.description) lines.push(`  description: ${yq(r.description)}`)
  lines.push(`  action: ${r.action}`)
  if (r.severity) lines.push(`  severity: ${r.severity}`)
  if (r.match_tool) lines.push(`  match_tool: ${r.match_tool}`)
  if (r.match_pattern) lines.push(`  match_pattern: ${yq(r.match_pattern)}`)
  if (r.match_path_pattern) lines.push(`  match_path_pattern: ${yq(r.match_path_pattern)}`)
  if (r.frameworks && r.frameworks.length > 0) {
    lines.push(`  frameworks:`)
    for (const f of r.frameworks) lines.push(`    - ${f}`)
  }
  if (r.iso_control) lines.push(`  iso_control: ${r.iso_control}`)
  if (r.recommendation) lines.push(`  recommendation: ${yq(r.recommendation)}`)
  lines.push(`  pack: ${r.pack_slug}`)
  return lines.join("\n")
}

export const fmtInt = (n: number) =>
  n >= 1000 ? `${(n / 1000).toFixed(1)}k` : `${n}`

export const DECISION_COLOR: Record<string, string> = {
  blocked: "#dc2626",
  warned: "#d97706",
  audited: "#2563eb",
  allowed: "#16a34a",
  approval: "#7c3aed",
}

export function DecisionDot({ decision }: { decision: string }) {
  const color = DECISION_COLOR[decision] ?? "#6b7280"
  return (
    <span title={decision} style={{
      display: "inline-flex",
      alignItems: "center",
      gap: 6,
      fontSize: 11,
      fontWeight: 600,
      color,
      textTransform: "capitalize",
    }}>
      <span style={{ width: 8, height: 8, borderRadius: "50%", background: color, display: "inline-block" }} />
      {decision}
    </span>
  )
}

export function timeAgo(iso: string): string {
  try {
    const t = new Date(iso).getTime()
    if (Number.isNaN(t)) return ""
    const delta = Math.max(0, Date.now() - t)
    const m = Math.floor(delta / 60000)
    if (m < 1) return "just now"
    if (m < 60) return `${m}m ago`
    const h = Math.floor(m / 60)
    if (h < 24) return `${h}h ago`
    const d = Math.floor(h / 24)
    return `${d}d ago`
  } catch {
    return ""
  }
}
