"use client"

import { useEffect, useState } from "react"
import { Clock } from "lucide-react"
import { useAuthFetch } from "@/hooks/useAuthFetch"
import { guard } from "@/lib/api"
import styles from "./RateLimitsPanel.module.css"

const RATE_LIMIT_PRESETS: Array<{ label: string; rpm: number; tpm: number; why: string }> = [
  { label: "Solo dev / smoke test",   rpm: 2,   tpm: 500,     why: "trips the cap in a 3-call test — good for verifying enforcement" },
  { label: "Small team, exploratory", rpm: 60,  tpm: 100000,  why: "~1 req/sec sustained; enough for Cursor / Claude Code chat" },
  { label: "Team of 10-20 devs",      rpm: 300, tpm: 500000,  why: "absorbs bursts, still catches runaway agents" },
]

function RateLimitPresets({ isAdmin, onPick }: { isAdmin: boolean; onPick: (rpm: number, tpm: number) => void }) {
  return (
    <div className={styles.presets}>
      <div style={{ fontSize: 11, fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase", marginBottom: 8 }}>
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
            className={styles.preset}
          >
            <span style={{ fontWeight: 600, color: "var(--text)" }}>{p.label}</span>
            <span style={{ fontVariantNumeric: "tabular-nums" }}>{p.rpm} rpm</span>
            <span style={{ fontVariantNumeric: "tabular-nums" }}>{p.tpm.toLocaleString()} tpm</span>
            <span style={{ color: "var(--text-3)", fontSize: 11.5 }}>{p.why}</span>
          </button>
        ))}
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
    <section aria-label="Gateway workspace rate limits" className={styles.panel}>
      <div style={{ padding: "15px 0", borderBottom: "1px solid var(--border)", display: "flex", alignItems: "center", gap: 10 }}>
        <span style={{ width: 30, height: 30, borderRadius: 8, background: "var(--accent)", color: "#fff", display: "grid", placeItems: "center", flexShrink: 0 }}>
          <Clock size={15} aria-hidden="true" />
        </span>
        <div style={{ fontWeight: 650, fontSize: 14.5 }}>Workspace default</div>
        {saved && <span style={{ marginLeft: "auto", fontSize: 12, color: "var(--ok)", fontWeight: 600 }}>Saved</span>}
      </div>

      <div style={{ padding: "16px 0", display: "grid", gap: 14 }}>
        <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
          Gateway traffic limits for this workspace. Leave a field blank for no cap.
          {overrideCount > 0 && ` ${overrideCount} agent override${overrideCount === 1 ? "" : "s"} active.`}
        </div>

        <div className={styles.inputs}>
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
    </section>
  )
}
