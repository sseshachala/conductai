export type SessionUsageEvidence = {
  source: "client_reported"
  observed_at: string
  reconciliation: "unreconciled"
  budget_eligible: false
  pricing_version: string
  cost_status: "estimated" | "unpriced"
  estimated_microdollars: number | null
  slices: Array<{
    model: string | null
    provider: string | null
    uncached_input_tokens: number
    cache_read_tokens: number
    cache_write_tokens: number
    output_tokens: number
  }>
}

export function SessionUsageDetails({ value }: { value: SessionUsageEvidence }) {
  return (
    <div style={{ gridColumn: "1 / -1", minWidth: 0 }}>
      <strong>Reported session usage</strong>
      <div style={{ color: "var(--text-muted)", marginTop: 6 }}>
        {value.cost_status === "estimated" && value.estimated_microdollars != null
          ? `Estimated cost: $${(value.estimated_microdollars / 1_000_000).toFixed(6)}`
          : "Cost unavailable"}
        {" · Unreconciled with Gateway · Excluded from budgets"}
      </div>
      <div style={{ color: "var(--text-muted)", marginTop: 4 }}>
        Observed {value.observed_at} · Pricing {value.pricing_version}
      </div>
      {value.slices.map((part, index) => (
        <div key={index} style={{ marginTop: 8, overflowWrap: "anywhere" }}>
          <span>{[part.provider, part.model].filter(Boolean).join(" / ") || "Model unavailable"}</span>
          <div style={{ color: "var(--text-muted)" }}>
            Input {part.uncached_input_tokens.toLocaleString()} · Cache read {part.cache_read_tokens.toLocaleString()}
            {" · "}Cache write {part.cache_write_tokens.toLocaleString()} · Output {part.output_tokens.toLocaleString()}
          </div>
        </div>
      ))}
    </div>
  )
}
