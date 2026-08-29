"use client"

/**
 * Workspace-default RPM/TPM caps on proxy traffic. Blocks return 429 with
 * x-guard reason. Extracted from Guard settings during #1359 so the workspace
 * defaults live under /settings alongside other workspace-level config. The
 * enforcement backend (guard.rateLimits) is unchanged.
 *
 * ponytail: workspace default only in V1. Per-agent overrides land when the
 * agent identity picker ships (backend already accepts agent_identity_id).
 */

import { useEffect, useState } from "react"
import { useAuthFetch } from "@/hooks/useAuthFetch"
import { guard } from "@/lib/api"

const RATE_LIMIT_PRESETS: Array<{ label: string; rpm: number; tpm: number; why: string }> = [
  { label: "Solo dev / smoke test",   rpm: 2,   tpm: 500,     why: "trips the cap in a 3-call test — good for verifying enforcement" },
  { label: "Small team, exploratory", rpm: 60,  tpm: 100000,  why: "~1 req/sec sustained; enough for Cursor / Claude Code chat" },
  { label: "Team of 10-20 devs",      rpm: 300, tpm: 500000,  why: "absorbs bursts, still catches runaway agents" },
]

function RateLimitPresets({ isAdmin, onPick }: { isAdmin: boolean; onPick: (rpm: number, tpm: number) => void }) {
  return (
    <div style={{ border: "1px dashed var(--border)", borderRadius: 8, padding: "10px 14px" }}>
      <div style={{ fontSize: 11, fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: ".06em", marginBottom: 8 }}>
        Suggested defaults
      </div>
      <div style={{ display: "grid", gap: 6 }}>
        {RATE_LIMIT_PRESETS.map(p => (
          <button
            key={p.label}
            type="button"
            onClick={() => onPick(p.rpm, p.tpm)}
            disabled={!isAdmin}
            style={{
              display: "grid",
              gridTemplateColumns: "160px 60px 80px 1fr",
              gap: 10,
              alignItems: "center",
              padding: "6px 8px",
              background: "transparent",
              border: "1px solid transparent",
              borderRadius: 6,
              cursor: isAdmin ? "pointer" : "default",
              textAlign: "left",
              color: "var(--text-2)",
              fontSize: 12.5,
            }}
            onMouseEnter={e => { if (isAdmin) e.currentTarget.style.background = "var(--surface-2)" }}
            onMouseLeave={e => { e.currentTarget.style.background = "transparent" }}
            title={isAdmin ? "Apply to fields" : "Admin only"}
          >
            <span style={{ fontWeight: 600, color: "var(--text)" }}>{p.label}</span>
            <span style={{ fontVariantNumeric: "tabular-nums" }}>{p.rpm} rpm</span>
            <span style={{ fontVariantNumeric: "tabular-nums" }}>{p.tpm.toLocaleString()} tpm</span>
            <span style={{ color: "var(--text-3)", fontSize: 11.5 }}>{p.why}</span>
          </button>
        ))}
      </div>
      <div style={{ fontSize: 11, color: "var(--text-3)", marginTop: 8 }}>
        Per-agent identity gets its own limits once the picker ships. Anthropic Tier 1 default for reference: 50 rpm, 40k tpm.
      </div>
    </div>
  )
}

export default function RateLimitsPanel({ isAdmin }: { isAdmin: boolean }) {
  const { authFetch } = useAuthFetch()
  const [rpm, setRpm] = useState<string>("")
  const [tpm, setTpm] = useState<string>("")
  const [loaded, setLoaded] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [overrideCount, setOverrideCount] = useState(0)

  useEffect(() => {
    if (!isAdmin) return  // GET requires admin; skip fetch for viewers/developers
    let cancelled = false
    guard.rateLimits.list(authFetch).then((rows) => {
      if (cancelled) return
      const def = rows.find(r => !r.agent_identity_id)
      setRpm(def?.rpm != null ? String(def.rpm) : "")
      setTpm(def?.tpm != null ? String(def.tpm) : "")
      setOverrideCount(rows.filter(r => r.agent_identity_id).length)
      setLoaded(true)
    }).catch(() => setLoaded(true))
    return () => { cancelled = true }
  }, [authFetch, isAdmin])

  if (!isAdmin) return null

  async function save() {
    setSaving(true); setErr(null); setSaved(false)
    try {
      const body: { agent_identity_id: null; rpm: number | null; tpm: number | null } = {
        agent_identity_id: null,
        rpm: rpm.trim() === "" ? null : Number(rpm),
        tpm: tpm.trim() === "" ? null : Number(tpm),
      }
      await guard.rateLimits.upsert(authFetch, body)
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch (e: any) {
      setErr(e?.message || "Save failed")
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="card" style={{ overflow: "hidden" }}>
      <div style={{ padding: "15px 20px", borderBottom: "1px solid var(--border)", display: "flex", alignItems: "center", gap: 10 }}>
        <span style={{ width: 30, height: 30, borderRadius: 8, background: "var(--accent)", color: "#fff", display: "grid", placeItems: "center", flexShrink: 0 }}>
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>
          </svg>
        </span>
        <div style={{ fontWeight: 650, fontSize: 14.5 }}>Workspace default</div>
        {saved && <span style={{ marginLeft: "auto", fontSize: 12, color: "var(--ok)", fontWeight: 600 }}>Saved</span>}
      </div>

      <div style={{ padding: "16px 20px", display: "grid", gap: 14 }}>
        <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
          Requests-per-minute and tokens-per-minute caps on proxy traffic. Blocks return 429 with x-guard reason. Leave a field blank to remove that cap. Overrides per-agent identity land soon
          {overrideCount > 0 ? ` — ${overrideCount} override${overrideCount === 1 ? "" : "s"} currently active.` : "."}
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
          <label style={{ display: "grid", gap: 4 }}>
            <span style={{ fontSize: 12, fontWeight: 600, color: "var(--text-2)" }}>Requests / min (RPM)</span>
            <input
              type="number"
              min={1}
              placeholder="unlimited"
              value={rpm}
              onChange={e => setRpm(e.target.value)}
              disabled={!isAdmin || !loaded}
              style={{ padding: "9px 12px", fontSize: 13, border: "1px solid var(--border)", borderRadius: 6, background: "var(--surface)", color: "var(--text)" }}
            />
          </label>
          <label style={{ display: "grid", gap: 4 }}>
            <span style={{ fontSize: 12, fontWeight: 600, color: "var(--text-2)" }}>Tokens / min (TPM)</span>
            <input
              type="number"
              min={1}
              placeholder="unlimited"
              value={tpm}
              onChange={e => setTpm(e.target.value)}
              disabled={!isAdmin || !loaded}
              style={{ padding: "9px 12px", fontSize: 13, border: "1px solid var(--border)", borderRadius: 6, background: "var(--surface)", color: "var(--text)" }}
            />
          </label>
        </div>

        <RateLimitPresets isAdmin={isAdmin} onPick={(r, t) => { setRpm(String(r)); setTpm(String(t)) }} />

        {err && <div style={{ fontSize: 12, color: "var(--danger)" }}>{err}</div>}

        <div>
          <button
            type="button"
            onClick={save}
            disabled={!isAdmin || saving || !loaded}
            className="btn btn-primary btn-sm"
          >
            {saving ? "Saving…" : "Save"}
          </button>
        </div>
      </div>
    </div>
  )
}
