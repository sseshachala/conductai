"use client"

import {
  CURRENCY_SYMBOLS,
  fromUsd,
  type Currency,
  type ModelBreakdown,
  type ProviderBreakdown,
} from "./shared"

// ─── Model + provider spend panel ───────────────────────────────────────
//
// Groups this month's proxy-flowing audit events by (provider, model) and
// by provider alone. Hook-only rows (no provider / model recorded) are
// filtered server-side, so this panel stays honest even when the workspace
// has heavy CLI hook traffic. Renders nothing when there is no proxy
// activity yet — most trial / new workspaces will see the empty state.
export function ModelSpendPanel({
  byModel,
  byProvider,
  currency,
  limit = 8,
}: {
  byModel: ModelBreakdown[]
  byProvider: ProviderBreakdown[]
  currency: Currency
  limit?: number
}) {
  const sym = CURRENCY_SYMBOLS[currency] ?? "$"
  const displayCost = (usd: number): string =>
    `${sym}${(Math.round(fromUsd(usd, currency) * 100) / 100).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`

  if (byModel.length === 0 && byProvider.length === 0) {
    return null
  }

  // Client-side sort — belt and braces against server NULL-ordering quirks
  // and to keep the "biggest bill first" invariant even if the endpoint's
  // ORDER BY drifts. Primary key: cost desc; tie-break by tokens desc so
  // two zero-cost models still order by usage.
  const modelRows = [...byModel]
    .sort((a, b) => (b.cost_usd - a.cost_usd) || (b.tokens_after - a.tokens_after))
    .slice(0, limit)
  const providerRows = [...byProvider].sort((a, b) => b.cost_usd - a.cost_usd)

  return (
    <div className="card" style={{ borderColor: "var(--border)", marginBottom: 22, overflow: "hidden" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "16px 22px", borderBottom: "1px solid var(--border)" }}>
        <span style={{ width: 32, height: 32, borderRadius: 9, background: "var(--surface-2)", color: "var(--text-2)", display: "grid", placeItems: "center", flexShrink: 0 }}>
          <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M3 3v18h18" />
            <path d="M7 15l4-6 4 3 5-8" />
          </svg>
        </span>
        <div>
          <div style={{ fontWeight: 650, fontSize: 15 }}>Spend by model</div>
          <div style={{ fontSize: 12.5, color: "var(--text-3)" }}>
            Proxy-routed calls only — CLI hook events don&apos;t carry model metadata.
          </div>
        </div>
      </div>

      {providerRows.length > 0 && (
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            gap: 8,
            padding: "12px 22px",
            borderBottom: "1px solid var(--border)",
            background: "var(--surface-1)",
          }}
        >
          {providerRows.map(p => (
            <span
              key={p.provider}
              style={{
                fontSize: 12.5,
                padding: "4px 10px",
                borderRadius: 999,
                border: "1px solid var(--border-2)",
                background: "var(--surface)",
                color: "var(--text-2)",
              }}
            >
              {p.provider} · <strong style={{ color: "var(--text-1)" }}>{displayCost(p.cost_usd)}</strong>
            </span>
          ))}
        </div>
      )}

      {modelRows.length > 0 ? (
        <div>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "1fr 120px 140px",
              gap: 16,
              alignItems: "center",
              padding: "10px 22px",
              fontSize: 11.5,
              color: "var(--text-3)",
              textTransform: "uppercase",
              letterSpacing: "0.04em",
              borderTop: "1px solid var(--border)",
              background: "var(--surface-1)",
            }}
          >
            <span>Model</span>
            <span style={{ textAlign: "right" }}>Tokens</span>
            <span style={{ textAlign: "right" }}>This month</span>
          </div>
          {modelRows.map(r => (
            <div
              key={`${r.provider}::${r.model}`}
              style={{
                display: "grid",
                gridTemplateColumns: "1fr 120px 140px",
                gap: 16,
                alignItems: "center",
                padding: "10px 22px",
                borderTop: "1px solid var(--border)",
              }}
            >
              <div style={{ fontSize: 13.5 }}>
                <div style={{ fontWeight: 600 }}>{r.model}</div>
                <div style={{ fontSize: 11.5, color: "var(--text-muted)" }}>{r.provider}</div>
              </div>
              <div style={{ textAlign: "right", fontSize: 13, color: "var(--text-2)" }}>
                {r.tokens_after.toLocaleString()}
              </div>
              <div style={{ textAlign: "right", fontSize: 13.5, fontWeight: 600 }}>
                {displayCost(r.cost_usd)}
              </div>
            </div>
          ))}
          {byModel.length > modelRows.length && (
            <div style={{ padding: "10px 22px", fontSize: 12, color: "var(--text-muted)", borderTop: "1px solid var(--border)" }}>
              Showing top {modelRows.length} of {byModel.length}.
            </div>
          )}
        </div>
      ) : (
        <div style={{ padding: "18px 22px", color: "var(--text-muted)", fontSize: 13 }}>
          No proxy-recorded model activity yet this month.
        </div>
      )}
    </div>
  )
}
