/**
 * Widget renderers for the report-builder skill (#1450 PR 3).
 *
 * One component per `hint`, dispatched by `<WidgetRenderer>`. Each takes
 * a `WidgetLoadState` and renders loading / error / data states.
 *
 * ponytail: no charting library. `spark` and `agent_row` show headline
 * numbers, not sparkline SVGs. Upgrade the visualization when tools
 * start returning time series.
 */
import type { WidgetData, WidgetLoadState } from "./fetchers"

function fmtInt(n: number | null | undefined): string {
  if (n == null) return "—"
  if (Math.abs(n) >= 1000) return `${(n / 1000).toFixed(1)}k`
  return String(n)
}

function fmtUsd(n: number | null | undefined): string {
  if (n == null) return "—"
  return `$${n.toFixed(2)}`
}

function fmtPct(n: number | null | undefined): string {
  if (n == null) return "—"
  return `${(n * 100).toFixed(0)}%`
}

function fmtWhen(ts: string | null | undefined): string {
  if (!ts) return "—"
  const d = new Date(ts)
  return d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })
}

// ── loading / error primitives ─────────────────────────────────────────────

function LoadingBody() {
  return (
    <div className="flex h-full min-h-16 items-center justify-center text-xs text-neutral-400">
      Loading…
    </div>
  )
}

function ErrorBody({ error }: { error: string }) {
  return (
    <div className="flex h-full min-h-16 items-center justify-center px-3 text-center text-xs text-red-500">
      {error}
    </div>
  )
}

// ── KPI card ───────────────────────────────────────────────────────────────

interface KpiTile { label: string; value: string; sub?: string }

function KpiTiles({ tiles }: { tiles: KpiTile[] }) {
  return (
    <div className="grid grid-cols-3 gap-3 text-center">
      {tiles.map((t) => (
        <div key={t.label} className="rounded bg-neutral-50 px-2 py-2">
          <div className="text-xl font-semibold">{t.value}</div>
          <div className="mt-0.5 text-[10px] uppercase tracking-wide text-neutral-500">{t.label}</div>
          {t.sub && <div className="mt-0.5 text-[10px] text-neutral-400">{t.sub}</div>}
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
          { label: "PRs",      value: fmtInt(o.prs_opened) },
          { label: "Issues",   value: fmtInt(o.issues_triaged) },
          { label: "Reviews",  value: fmtInt(o.reviews_completed) },
          { label: "Incidents",value: fmtInt(o.incidents_investigated) },
          { label: "Succeeded",value: fmtInt(o.successful_automations) },
          { label: "Failed",   value: fmtInt(o.failed_automations) },
        ]}
      />
    )
  }
  if (data.tool === "get_observability_health") {
    const o = data.data
    return (
      <KpiTiles
        tiles={[
          { label: "Runs 1h",   value: fmtInt(o.runs_last_hour) },
          { label: "Runs 24h",  value: fmtInt(o.runs_last_24h) },
          { label: "Error Rate",value: fmtPct(o.error_rate) },
          { label: "P95 latency", value: o.p95_latency_ms == null ? "—" : `${o.p95_latency_ms} ms` },
        ]}
      />
    )
  }
  if (data.tool === "get_dora_metrics") {
    const d = data.data
    return (
      <KpiTiles
        tiles={[
          { label: "Deploys/wk", value: fmtInt(d.deployment_frequency) },
          { label: "Lead time",  value: d.lead_time_hours == null ? "—" : `${d.lead_time_hours.toFixed(1)} h` },
          { label: "MTTR",       value: d.mttr_hours == null ? "—" : `${d.mttr_hours.toFixed(1)} h` },
          { label: "Change fail",value: fmtPct(d.change_failure_rate) },
        ]}
      />
    )
  }
  return null
}

// ── Spark (headline + delta stand-in) ──────────────────────────────────────

function SparkBody({ data }: { data: WidgetData }) {
  if (data.tool === "get_dashboard_token_usage") {
    const t = data.data
    return (
      <div className="flex flex-col items-center justify-center">
        <div className="text-3xl font-semibold">{fmtUsd(t.estimated_cost_usd)}</div>
        <div className="mt-1 text-[11px] uppercase tracking-wide text-neutral-500">Est. cost</div>
        <div className="mt-2 text-xs text-neutral-500">
          {fmtInt(t.total_input_tokens)} in · {fmtInt(t.total_output_tokens)} out
        </div>
      </div>
    )
  }
  if (data.tool === "get_analytics_summary") {
    const a = data.data
    return (
      <div className="flex flex-col items-center justify-center">
        <div className="text-3xl font-semibold">{fmtInt(a.total_runs)}</div>
        <div className="mt-1 text-[11px] uppercase tracking-wide text-neutral-500">
          Runs ({a.window_days}d)
        </div>
        <div className="mt-2 text-xs text-neutral-500">
          {fmtPct(a.success_rate)} success · {fmtUsd(a.total_cost_usd)}
        </div>
      </div>
    )
  }
  return null
}

// ── List ───────────────────────────────────────────────────────────────────

function ListBody({ data }: { data: WidgetData }) {
  if (data.tool === "list_attention_runs") {
    const rows = data.data
    if (rows.length === 0) return <div className="text-xs text-neutral-500">Nothing needs attention.</div>
    return (
      <ul className="divide-y divide-neutral-100 text-xs">
        {rows.map((r) => (
          <li key={r.run_id} className="py-2">
            <div className="flex items-center justify-between gap-2">
              <span className="truncate font-medium">{r.workflow_name}</span>
              <span className="shrink-0 rounded bg-neutral-100 px-1.5 py-0.5 text-[10px] uppercase text-neutral-600">
                {r.status}
              </span>
            </div>
            <div className="text-neutral-500">{fmtWhen(r.created_at)}</div>
          </li>
        ))}
      </ul>
    )
  }
  if (data.tool === "list_agent_status") {
    const rows = data.data
    if (rows.length === 0) return <div className="text-xs text-neutral-500">No agents.</div>
    return (
      <ul className="divide-y divide-neutral-100 text-xs">
        {rows.slice(0, 8).map((r) => (
          <li key={r.name} className="py-2">
            <div className="flex items-center justify-between gap-2">
              <span className="truncate font-medium">{r.name}</span>
              <span className="shrink-0 text-neutral-500">{r.status}</span>
            </div>
            <div className="text-neutral-500">
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

function TableBody({ data }: { data: WidgetData }) {
  if (data.tool === "get_top_policy_hits") {
    const rows = data.data
    if (rows.length === 0) return <div className="text-xs text-neutral-500">No policy hits.</div>
    return (
      <table className="w-full text-xs">
        <thead className="border-b border-neutral-200 text-left text-neutral-500">
          <tr>
            <th className="py-1.5 font-normal">Rule</th>
            <th className="py-1.5 text-right font-normal">Blocked</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-neutral-100">
          {rows.slice(0, 8).map((r) => (
            <tr key={r.rule_id}>
              <td className="py-1.5 pr-2">{r.rule_id}</td>
              <td className="py-1.5 text-right font-medium">{fmtInt(r.count)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    )
  }
  if (data.tool === "get_playbook_scorecards") {
    const rows = data.data
    if (rows.length === 0) return <div className="text-xs text-neutral-500">No playbook runs.</div>
    return (
      <table className="w-full text-xs">
        <thead className="border-b border-neutral-200 text-left text-neutral-500">
          <tr>
            <th className="py-1.5 font-normal">Playbook</th>
            <th className="py-1.5 text-right font-normal">Runs</th>
            <th className="py-1.5 text-right font-normal">Success</th>
            <th className="py-1.5 text-right font-normal">Cost</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-neutral-100">
          {rows.slice(0, 8).map((r) => (
            <tr key={r.playbook_slug}>
              <td className="py-1.5 pr-2 font-medium">{r.playbook_slug}</td>
              <td className="py-1.5 text-right">{fmtInt(r.run_count)}</td>
              <td className="py-1.5 text-right">{fmtPct(r.success_rate)}</td>
              <td className="py-1.5 text-right">{fmtUsd(r.avg_cost_usd)}</td>
            </tr>
          ))}
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
  if (rows.length === 0) return <div className="text-xs text-neutral-500">No agents.</div>
  return (
    <div className="flex gap-3 overflow-x-auto pb-1">
      {rows.slice(0, 12).map((r) => (
        <div
          key={r.workflow_id}
          className="min-w-[160px] shrink-0 rounded border border-neutral-200 px-3 py-2 text-xs"
        >
          <div className="truncate font-medium">{r.name}</div>
          <div className="mt-1 flex items-center justify-between text-neutral-500">
            <span>{fmtInt(r.run_count)} runs</span>
            <span>{fmtPct(r.success_rate)}</span>
          </div>
          <div className="mt-0.5 text-[10px] text-neutral-400">
            last {fmtWhen(r.last_run_at)} · {r.last_run_status ?? "—"}
          </div>
        </div>
      ))}
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
