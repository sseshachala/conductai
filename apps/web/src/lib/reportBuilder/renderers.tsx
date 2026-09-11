/**
 * Widget renderers for the report-builder skill (#1450 PR 3, polish PR 6).
 *
 * One component per `hint`, dispatched by `<WidgetRenderer>`. Uses the
 * app's design tokens (--accent, --ok/warn/err, --surface, --text-2)
 * instead of raw Tailwind neutrals so the report builder matches the
 * rest of the app.
 *
 * `spark` widgets get a mini SVG sparkline built from whatever ordered
 * numeric series the tool exposes — currently token_usage per-agent and
 * analytics_summary aggregates. When tools start returning explicit time
 * series, feed them straight into MiniSpark.
 */
import type { WidgetData, WidgetLoadState } from "./fetchers"

// ── formatters ─────────────────────────────────────────────────────────────

function fmtInt(n: number | null | undefined): string {
  if (n == null) return "—"
  if (Math.abs(n) >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (Math.abs(n) >= 1000) return `${(n / 1000).toFixed(1)}k`
  return String(Math.round(n))
}

function fmtUsd(n: number | null | undefined): string {
  if (n == null) return "—"
  if (n >= 1000) return `$${(n / 1000).toFixed(1)}k`
  return `$${n.toFixed(2)}`
}

function fmtPct(n: number | null | undefined): string {
  if (n == null) return "—"
  return `${(n * 100).toFixed(0)}%`
}

function fmtWhen(ts: string | null | undefined): string {
  if (!ts) return "—"
  const d = new Date(ts)
  const now = Date.now()
  const diffMin = Math.floor((now - d.getTime()) / 60000)
  if (diffMin < 1) return "just now"
  if (diffMin < 60) return `${diffMin}m ago`
  if (diffMin < 60 * 24) return `${Math.floor(diffMin / 60)}h ago`
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" })
}

// ── shared primitives ──────────────────────────────────────────────────────

function LoadingBody() {
  return (
    <div style={{
      display: "flex", height: "100%", minHeight: 64,
      alignItems: "center", justifyContent: "center",
      color: "var(--text-muted)", fontSize: 12,
    }}>
      Loading…
    </div>
  )
}

function ErrorBody({ error }: { error: string }) {
  return (
    <div style={{
      display: "flex", height: "100%", minHeight: 64,
      alignItems: "center", justifyContent: "center", padding: "0 12px",
      textAlign: "center", color: "var(--err)", fontSize: 12,
    }}>
      {error}
    </div>
  )
}

function EmptyBody({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ color: "var(--text-muted)", fontSize: 12, padding: 4 }}>
      {children}
    </div>
  )
}

// ── KPI Tiles ──────────────────────────────────────────────────────────────

interface KpiTile {
  label: string
  value: string
  tone?: "default" | "ok" | "warn" | "err" | "accent"
  sub?: string
}

const TONE_COLORS: Record<NonNullable<KpiTile["tone"]>, string> = {
  default: "var(--text)",
  ok:      "var(--ok)",
  warn:    "var(--warn)",
  err:     "var(--err)",
  accent:  "var(--accent)",
}

function KpiTiles({ tiles }: { tiles: KpiTile[] }) {
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: `repeat(${Math.min(tiles.length, 3)}, minmax(0, 1fr))`,
        gap: 8,
      }}
    >
      {tiles.map((t) => (
        <div
          key={t.label}
          style={{
            background: "var(--surface-2)",
            border: "1px solid var(--border)",
            borderRadius: 8,
            padding: "10px 12px",
            textAlign: "center",
          }}
        >
          <div
            style={{
              fontSize: 22, fontWeight: 600, lineHeight: 1.1,
              color: TONE_COLORS[t.tone ?? "default"],
              fontVariantNumeric: "tabular-nums",
            }}
          >
            {t.value}
          </div>
          <div
            style={{
              marginTop: 4, fontSize: 10, fontWeight: 600,
              letterSpacing: ".08em", textTransform: "uppercase",
              color: "var(--text-muted)",
            }}
          >
            {t.label}
          </div>
          {t.sub && (
            <div style={{ marginTop: 2, fontSize: 10, color: "var(--text-3)" }}>{t.sub}</div>
          )}
        </div>
      ))}
    </div>
  )
}

function KpiCardBody({ data }: { data: WidgetData }) {
  if (data.tool === "get_dashboard_outcomes") {
    const o = data.data
    return (
      <KpiTiles
        tiles={[
          { label: "PRs",       value: fmtInt(o.prs_opened),             tone: "accent" },
          { label: "Issues",    value: fmtInt(o.issues_triaged) },
          { label: "Reviews",   value: fmtInt(o.reviews_completed) },
          { label: "Incidents", value: fmtInt(o.incidents_investigated), tone: o.incidents_investigated ? "warn" : "default" },
          { label: "Succeeded", value: fmtInt(o.successful_automations), tone: "ok" },
          { label: "Failed",    value: fmtInt(o.failed_automations),     tone: o.failed_automations ? "err" : "default" },
        ]}
      />
    )
  }
  if (data.tool === "get_observability_health") {
    const o = data.data
    const errTone = o.error_rate > 0.1 ? "err" : o.error_rate > 0.02 ? "warn" : "ok"
    return (
      <KpiTiles
        tiles={[
          { label: "Runs 1h",     value: fmtInt(o.runs_last_hour),  tone: "accent" },
          { label: "Runs 24h",    value: fmtInt(o.runs_last_24h) },
          { label: "Error rate",  value: fmtPct(o.error_rate),      tone: errTone },
          { label: "P95 latency", value: o.p95_latency_ms == null ? "—" : `${o.p95_latency_ms}ms` },
        ]}
      />
    )
  }
  if (data.tool === "get_dora_metrics") {
    const d = data.data
    return (
      <KpiTiles
        tiles={[
          { label: "Deploys/wk",  value: fmtInt(d.deployment_frequency), tone: "accent" },
          { label: "Lead time",   value: d.lead_time_hours == null ? "—" : `${d.lead_time_hours.toFixed(1)}h` },
          { label: "MTTR",        value: d.mttr_hours == null ? "—" : `${d.mttr_hours.toFixed(1)}h` },
          { label: "Change fail", value: fmtPct(d.change_failure_rate),  tone: d.change_failure_rate > 0.15 ? "err" : d.change_failure_rate > 0.05 ? "warn" : "ok" },
        ]}
      />
    )
  }
  return null
}

// ── Spark (headline + mini sparkline) ──────────────────────────────────────

function MiniSpark({ points, color = "var(--accent)" }: { points: number[]; color?: string }) {
  if (points.length < 2) return null
  const w = 120, h = 32, pad = 2
  const min = Math.min(...points), max = Math.max(...points)
  const span = max - min || 1
  const step = (w - pad * 2) / (points.length - 1)
  const coords = points.map((p, i) => {
    const x = pad + i * step
    const y = h - pad - ((p - min) / span) * (h - pad * 2)
    return `${x.toFixed(1)},${y.toFixed(1)}`
  }).join(" ")
  const areaCoords = `${pad},${h - pad} ${coords} ${(w - pad).toFixed(1)},${h - pad}`
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} style={{ display: "block", marginTop: 4 }}>
      <polygon points={areaCoords} fill={color} opacity={0.12} />
      <polyline points={coords} fill="none" stroke={color} strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function SparkBody({ data }: { data: WidgetData }) {
  if (data.tool === "get_dashboard_token_usage") {
    const t = data.data
    const perAgent = (t.per_agent ?? []).map((a) => a.cost_usd).slice(0, 20)
    return (
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
        <div style={{ fontSize: 30, fontWeight: 600, color: "var(--accent)", fontVariantNumeric: "tabular-nums" }}>
          {fmtUsd(t.estimated_cost_usd)}
        </div>
        <div style={{ marginTop: 2, fontSize: 10, fontWeight: 600, letterSpacing: ".08em", textTransform: "uppercase", color: "var(--text-muted)" }}>
          Est. cost
        </div>
        {perAgent.length >= 2 && <MiniSpark points={perAgent} />}
        <div style={{ marginTop: 6, fontSize: 11, color: "var(--text-3)" }}>
          {fmtInt(t.total_input_tokens)} in · {fmtInt(t.total_output_tokens)} out
        </div>
      </div>
    )
  }
  if (data.tool === "get_analytics_summary") {
    const a = data.data
    const successPct = fmtPct(a.success_rate)
    const successTone = a.success_rate < 0.9 ? "var(--warn)" : "var(--ok)"
    return (
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
        <div style={{ fontSize: 30, fontWeight: 600, color: "var(--accent)", fontVariantNumeric: "tabular-nums" }}>
          {fmtInt(a.total_runs)}
        </div>
        <div style={{ marginTop: 2, fontSize: 10, fontWeight: 600, letterSpacing: ".08em", textTransform: "uppercase", color: "var(--text-muted)" }}>
          Runs · {a.window_days}d
        </div>
        {a.total_runs > 0 && <MiniSpark points={[a.succeeded, a.failed, Math.max(0, a.total_runs - a.succeeded - a.failed)]} />}
        <div style={{ marginTop: 6, fontSize: 11, color: "var(--text-3)" }}>
          <span style={{ color: successTone, fontWeight: 600 }}>{successPct}</span> success · {fmtUsd(a.total_cost_usd)}
        </div>
      </div>
    )
  }
  return null
}

// ── Status pill ────────────────────────────────────────────────────────────

const STATUS_TONES: Record<string, { bg: string; text: string; bd: string }> = {
  succeeded: { bg: "var(--ok-bg)",     text: "var(--ok)",         bd: "var(--ok-bd)" },
  running:   { bg: "var(--info-bg)",   text: "var(--info)",       bd: "var(--info-bd)" },
  pending:   { bg: "var(--info-bg)",   text: "var(--info)",       bd: "var(--info-bd)" },
  paused:    { bg: "var(--warn-bg)",   text: "var(--warn)",       bd: "var(--warn-bd)" },
  failed:    { bg: "var(--err-bg)",    text: "var(--err)",        bd: "var(--err-bd)" },
  cancelled: { bg: "var(--surface-3)", text: "var(--text-muted)", bd: "var(--border)" },
}

function StatusPill({ status }: { status: string | null | undefined }) {
  const s = (status ?? "unknown").toLowerCase()
  const tone = STATUS_TONES[s] ?? { bg: "var(--surface-3)", text: "var(--text-2)", bd: "var(--border)" }
  return (
    <span
      style={{
        display: "inline-block",
        padding: "1px 8px",
        borderRadius: 999,
        fontSize: 10,
        fontWeight: 600,
        letterSpacing: ".03em",
        textTransform: "uppercase",
        background: tone.bg,
        color: tone.text,
        border: `1px solid ${tone.bd}`,
      }}
    >
      {s}
    </span>
  )
}

// ── List ───────────────────────────────────────────────────────────────────

function ListBody({ data }: { data: WidgetData }) {
  if (data.tool === "list_attention_runs") {
    const rows = data.data
    if (rows.length === 0) return <EmptyBody>Nothing needs attention.</EmptyBody>
    return (
      <ul style={{ listStyle: "none", padding: 0, margin: 0, fontSize: 12 }}>
        {rows.map((r, i) => (
          <li
            key={r.run_id}
            style={{
              padding: "8px 0",
              borderTop: i === 0 ? "none" : "1px solid var(--border)",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", gap: 8, alignItems: "baseline" }}>
              <span style={{ fontWeight: 500, color: "var(--text)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {r.workflow_name}
              </span>
              <StatusPill status={r.status} />
            </div>
            <div style={{ marginTop: 2, color: "var(--text-3)", fontSize: 11 }}>{fmtWhen(r.created_at)}</div>
          </li>
        ))}
      </ul>
    )
  }
  if (data.tool === "list_agent_status") {
    const rows = data.data
    if (rows.length === 0) return <EmptyBody>No workflows.</EmptyBody>
    return (
      <ul style={{ listStyle: "none", padding: 0, margin: 0, fontSize: 12 }}>
        {rows.slice(0, 8).map((r, i) => (
          <li
            key={r.name}
            style={{
              padding: "8px 0",
              borderTop: i === 0 ? "none" : "1px solid var(--border)",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", gap: 8, alignItems: "baseline" }}>
              <span style={{ fontWeight: 500, color: "var(--text)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {r.name}
              </span>
              <StatusPill status={r.status} />
            </div>
            <div style={{ marginTop: 2, color: "var(--text-3)", fontSize: 11 }}>
              {fmtInt(r.run_count_24h)} runs · last {fmtWhen(r.last_run_at)}
            </div>
          </li>
        ))}
      </ul>
    )
  }
  return null
}

// ── Table ──────────────────────────────────────────────────────────────────

const TH: React.CSSProperties = {
  padding: "6px 8px",
  textAlign: "left",
  fontSize: 10,
  fontWeight: 600,
  letterSpacing: ".08em",
  textTransform: "uppercase",
  color: "var(--text-muted)",
  borderBottom: "1px solid var(--border)",
}
const TD: React.CSSProperties = {
  padding: "8px",
  fontSize: 12,
  color: "var(--text-2)",
  borderBottom: "1px solid var(--border)",
}
const TDR: React.CSSProperties = { ...TD, textAlign: "right", fontVariantNumeric: "tabular-nums" }

function TableBody({ data }: { data: WidgetData }) {
  if (data.tool === "get_top_policy_hits") {
    const rows = data.data
    if (rows.length === 0) return <EmptyBody>No policy hits.</EmptyBody>
    return (
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr>
            <th style={TH}>Rule</th>
            <th style={{ ...TH, textAlign: "right" }}>Blocked</th>
          </tr>
        </thead>
        <tbody>
          {rows.slice(0, 8).map((r) => (
            <tr key={r.rule_id}>
              <td style={{ ...TD, fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace", color: "var(--text)" }}>{r.rule_id}</td>
              <td style={{ ...TDR, fontWeight: 600, color: "var(--err)" }}>{fmtInt(r.count)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    )
  }
  if (data.tool === "get_playbook_scorecards") {
    const rows = data.data
    if (rows.length === 0) return <EmptyBody>No playbook runs.</EmptyBody>
    return (
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr>
            <th style={TH}>Playbook</th>
            <th style={{ ...TH, textAlign: "right" }}>Runs</th>
            <th style={{ ...TH, textAlign: "right" }}>Success</th>
            <th style={{ ...TH, textAlign: "right" }}>Cost</th>
          </tr>
        </thead>
        <tbody>
          {rows.slice(0, 8).map((r) => {
            const successColor = r.success_rate < 0.9 ? "var(--warn)" : "var(--ok)"
            return (
              <tr key={r.playbook_slug}>
                <td style={{ ...TD, fontWeight: 500, color: "var(--text)" }}>{r.playbook_slug}</td>
                <td style={TDR}>{fmtInt(r.run_count)}</td>
                <td style={{ ...TDR, color: successColor, fontWeight: 600 }}>{fmtPct(r.success_rate)}</td>
                <td style={TDR}>{fmtUsd(r.avg_cost_usd)}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    )
  }
  return null
}

// ── Agent row (horizontal cards) ───────────────────────────────────────────

function AgentRowBody({ data }: { data: WidgetData }) {
  if (data.tool !== "list_agent_health") return null
  const rows = data.data
  if (rows.length === 0) return <EmptyBody>No workflows.</EmptyBody>
  return (
    <div style={{ display: "flex", gap: 8, overflowX: "auto", paddingBottom: 4 }}>
      {rows.slice(0, 12).map((r) => {
        const rateTone = r.success_rate < 0.9 ? "var(--warn)" : "var(--ok)"
        return (
          <div
            key={r.workflow_id}
            style={{
              minWidth: 168, flexShrink: 0,
              background: "var(--surface-2)",
              border: "1px solid var(--border)",
              borderRadius: 8,
              padding: "8px 10px",
              fontSize: 11,
            }}
          >
            <div style={{ fontWeight: 500, color: "var(--text)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {r.name}
            </div>
            <div style={{ marginTop: 4, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <span style={{ color: "var(--text-3)" }}>{fmtInt(r.run_count)} runs</span>
              <span style={{ color: rateTone, fontWeight: 600 }}>{fmtPct(r.success_rate)}</span>
            </div>
            <div style={{ marginTop: 4, display: "flex", alignItems: "center", justifyContent: "space-between", fontSize: 10, color: "var(--text-muted)" }}>
              <span>last {fmtWhen(r.last_run_at)}</span>
              <StatusPill status={r.last_run_status} />
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ── Dispatcher ─────────────────────────────────────────────────────────────

export function WidgetRenderer({
  hint,
  state,
}: {
  hint: string
  state: WidgetLoadState | undefined
}) {
  if (!state || state.status === "loading") return <LoadingBody />
  if (state.status === "error") return <ErrorBody error={state.error} />
  switch (hint) {
    case "kpi_card":  return <KpiCardBody  data={state.data} />
    case "spark":     return <SparkBody    data={state.data} />
    case "list":      return <ListBody     data={state.data} />
    case "table":     return <TableBody    data={state.data} />
    case "agent_row": return <AgentRowBody data={state.data} />
    default:          return <ErrorBody error={`Unknown hint: ${hint}`} />
  }
}
