"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { useAuthFetch } from "@/hooks/useAuthFetch"
import { guard } from "@/lib/api"
import type { AlertChannel, AlertRegistry, AlertSourceDef } from "@/lib/api/guard"
import type { NotificationChannelType } from "@/lib/api/guard-types"

// ─── Unified alerts table (#2142): source → event → channels ──────────────────
// Rendered from the API registry, so a new source/event needs no UI change.
// Guard-rule channels stay in the card above (they are managed on
// /guard/notifications); this table covers every other registered source.

export interface AlertFilter {
  sourceType: string
  sourceId: string | null
}

/** Parse the `?source=` query value: `gateway`, or `gateway:<profile_id>`. */
export function parseSourceFilter(raw: string | null | undefined): AlertFilter | null {
  if (!raw) return null
  const [sourceType, ...rest] = raw.split(":")
  if (!sourceType) return null
  const id = rest.join(":")
  return { sourceType, sourceId: id || null }
}

const CHANNEL_LABEL: Record<NotificationChannelType, string> = {
  slack: "Slack", email: "Email", pagerduty: "PagerDuty", webhook: "Webhook",
}

function maskRef(ch: AlertChannel): string {
  if (ch.channel_type === "slack") return `#${ch.channel_ref}`
  if (ch.channel_type === "pagerduty") return `${ch.channel_ref.slice(0, 6)}…${ch.channel_ref.slice(-4)}`
  if (ch.channel_type === "webhook") {
    try { return new URL(ch.channel_ref).host } catch { return "webhook" }
  }
  return ch.channel_ref
}

export default function AlertsCard({
  workspaceId,
  isAdmin,
  filter,
}: {
  workspaceId: string | null
  isAdmin: boolean
  filter: AlertFilter | null
}) {
  const { authFetch } = useAuthFetch()
  const [registry, setRegistry] = useState<AlertRegistry | null>(null)
  const [channels, setChannels] = useState<AlertChannel[]>([])
  const [error, setError] = useState<string | null>(null)
  const [adding, setAdding] = useState<string | null>(null) // "source:event"
  const [addType, setAddType] = useState<NotificationChannelType>("slack")
  const [addRef, setAddRef] = useState("")
  const [addThreshold, setAddThreshold] = useState("")

  const load = useCallback(async () => {
    if (!workspaceId) return
    try {
      const [reg, list] = await Promise.all([
        guard.alerts.registry(authFetch),
        guard.alerts.list(authFetch, workspaceId, filter ? {
          source_type: filter.sourceType,
          source_id: filter.sourceId ?? undefined,
        } : undefined),
      ])
      setRegistry(reg)
      setChannels(list.channels)
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load alerts")
    }
  }, [authFetch, workspaceId, filter])

  useEffect(() => { void load() }, [load])

  const sources: AlertSourceDef[] = useMemo(() => {
    const all = (registry?.sources ?? []).filter(s => s.source_type !== "guard")
    return filter ? all.filter(s => s.source_type === filter.sourceType) : all
  }, [registry, filter])

  async function handleAdd(src: AlertSourceDef, eventType: string, supportsThreshold: boolean) {
    if (!workspaceId || !addRef.trim()) return
    const threshold = supportsThreshold && addThreshold.trim() ? Number(addThreshold) : null
    if (threshold !== null && (!Number.isInteger(threshold) || threshold < 1)) {
      setError("Threshold must be a whole number of events per minute (1 or more)")
      return
    }
    try {
      await guard.alerts.create(authFetch, workspaceId, {
        source_type: src.source_type,
        source_id: src.scoped ? filter?.sourceId ?? null : null,
        event_type: eventType,
        channel_type: addType,
        channel_ref: addType === "slack" ? addRef.trim().replace(/^#+/, "") : addRef.trim(),
        threshold_per_min: threshold,
      })
      setAdding(null)
      setAddRef("")
      setAddThreshold("")
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to add channel")
    }
  }

  async function handleRemove(id: string) {
    if (!workspaceId) return
    try {
      await guard.alerts.remove(authFetch, id, workspaceId)
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to remove channel")
    }
  }

  async function handleTest(id: string) {
    if (!workspaceId) return
    try {
      const res = await guard.notifications.test(authFetch, id, workspaceId)
      setError(res.ok ? null : (res.error ?? "Test failed"))
    } catch (e) {
      setError(e instanceof Error ? e.message : "Test failed")
    }
  }

  if (!registry && !error) {
    return <div className="card" style={{ padding: 20, fontSize: 12, color: "var(--text-muted)" }}>Loading alerts…</div>
  }

  return (
    <div className="card" style={{ overflow: "hidden" }} data-testid="alerts-card">
      <div style={{ padding: "15px 20px", borderBottom: "1px solid var(--border)" }}>
        <div style={{ fontWeight: 650, fontSize: 14.5 }}>Alerts</div>
        <div style={{ fontSize: 12, color: "var(--text-3)" }}>
          {filter?.sourceId
            ? `Showing ${filter.sourceType} alerts for profile ${filter.sourceId.slice(0, 8)}…`
            : "Source → event → channels. Repeats are grouped, so a burst sends one message per window."}
        </div>
      </div>
      {error && <div style={{ padding: "8px 20px", fontSize: 12, color: "var(--err)" }}>{error}</div>}

      <div style={{ padding: "4px 20px 16px" }}>
        {sources.map(src => (
          <div key={src.source_type} style={{ paddingTop: 12 }}>
            <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: ".05em", textTransform: "uppercase", color: "var(--text-muted)" }}>
              {src.label}
            </div>
            {src.events.map(ev => {
              const key = `${src.source_type}:${ev.event_type}`
              const rows = channels.filter(c => c.source_type === src.source_type && c.event_type === ev.event_type)
              return (
                <div key={key} style={{ padding: "10px 0", borderTop: "1px solid var(--border)" }}>
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
                    <div>
                      <div style={{ fontWeight: 600, fontSize: 13 }}>{ev.label}</div>
                      {ev.description && <div style={{ fontSize: 11.5, color: "var(--text-3)" }}>{ev.description}</div>}
                    </div>
                    {isAdmin && adding !== key && (
                      <button type="button" className="btn btn-ghost btn-sm" onClick={() => { setAdding(key); setAddRef(""); setAddThreshold("") }}>
                        + Add channel
                      </button>
                    )}
                  </div>

                  {rows.length === 0 && adding !== key && (
                    <div style={{ fontSize: 11.5, color: "var(--text-muted)", padding: "4px 0" }}>(none)</div>
                  )}
                  {rows.map(ch => (
                    <div key={ch.id} style={{ display: "flex", alignItems: "center", gap: 8, padding: "4px 0", fontSize: 12.5 }}>
                      <span style={{ fontSize: 10, fontWeight: 700, color: "var(--text-muted)", background: "var(--surface-2)", borderRadius: 4, padding: "1px 6px", textTransform: "uppercase" }}>
                        {ch.channel_type}
                      </span>
                      <span style={{ fontFamily: "var(--font-mono, ui-monospace, monospace)", flex: 1, wordBreak: "break-all" }}>
                        {maskRef(ch)}
                        {src.scoped && !filter?.sourceId && (
                          <span style={{ marginLeft: 8, fontSize: 11, color: "var(--text-muted)", fontFamily: "inherit" }}>
                            · {ch.source_id ? `profile ${ch.source_id.slice(0, 8)}…` : "all profiles"}
                          </span>
                        )}
                        {ch.threshold_per_min ? (
                          <span style={{ marginLeft: 8, fontSize: 11, color: "var(--text-muted)", fontFamily: "inherit" }}>
                            · ≥ {ch.threshold_per_min}/min
                          </span>
                        ) : null}
                      </span>
                      {isAdmin && (
                        <>
                          <button type="button" className="btn btn-ghost btn-sm" style={{ padding: "0 8px", fontSize: 11 }} onClick={() => void handleTest(ch.id)}>Test</button>
                          <button type="button" className="btn btn-ghost btn-sm" style={{ padding: "0 8px", fontSize: 11, color: "var(--err)" }} onClick={() => void handleRemove(ch.id)}>Remove</button>
                        </>
                      )}
                    </div>
                  ))}

                  {adding === key && (
                    <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 8, padding: "6px 8px", background: "var(--surface-2)", borderRadius: 6, flexWrap: "wrap" }}>
                      <select
                        aria-label="Channel type"
                        value={addType}
                        onChange={e => setAddType(e.target.value as NotificationChannelType)}
                        style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 4, padding: "4px 6px", fontSize: 12.5 }}
                      >
                        {(Object.keys(CHANNEL_LABEL) as NotificationChannelType[]).map(t => (
                          <option key={t} value={t}>{CHANNEL_LABEL[t]}</option>
                        ))}
                      </select>
                      <input
                        autoFocus
                        aria-label="Channel target"
                        value={addRef}
                        onChange={e => setAddRef(e.target.value)}
                        placeholder={
                          addType === "slack" ? "channel-name" :
                          addType === "email" ? "oncall@company.com" :
                          addType === "pagerduty" ? "PagerDuty routing key" :
                          "https://example.com/hooks/alerts"
                        }
                        style={{ flex: 1, minWidth: 160, background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 4, padding: "4px 8px", fontSize: 12.5 }}
                        onKeyDown={e => { if (e.key === "Enter") void handleAdd(src, ev.event_type, ev.supports_threshold); if (e.key === "Escape") setAdding(null) }}
                      />
                      {ev.supports_threshold && (
                        <input
                          aria-label="Threshold per minute"
                          value={addThreshold}
                          onChange={e => setAddThreshold(e.target.value)}
                          placeholder="min/min (optional)"
                          inputMode="numeric"
                          style={{ width: 120, background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 4, padding: "4px 8px", fontSize: 12.5 }}
                        />
                      )}
                      <button type="button" className="btn btn-primary btn-sm" style={{ fontSize: 11, opacity: addRef.trim() ? 1 : 0.5 }}
                        disabled={!addRef.trim()} onClick={() => void handleAdd(src, ev.event_type, ev.supports_threshold)}>
                        Save
                      </button>
                      <button type="button" className="btn btn-ghost btn-sm" style={{ fontSize: 11 }} onClick={() => setAdding(null)}>Cancel</button>
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        ))}
        {sources.length === 0 && (
          <div style={{ fontSize: 12, color: "var(--text-muted)", paddingTop: 12 }}>No alertable sources match this filter.</div>
        )}
      </div>
    </div>
  )
}
