"use client"

import { useCallback, useEffect, useState } from "react"
import { useAuthFetch } from "@/hooks/useAuthFetch"
import { guard } from "@/lib/api"
import { GuardToggle } from "@/features/guard/GuardToggle"

export default function EnforcementPanel({
  workspaceId,
  isAdmin,
}: {
  workspaceId: string | null
  isAdmin: boolean
}) {
  const { authFetch } = useAuthFetch()
  const [enforcementMode, setEnforcementMode] = useState<"block" | "warn" | "audit">("warn")
  const [failMode, setFailMode] = useState<"fail_open" | "fail_closed">("fail_open")
  const [denyOnError, setDenyOnError] = useState(true)
  const [notifyOnFailOpen, setNotifyOnFailOpen] = useState(true)
  const [enforcementError, setEnforcementError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)

  const load = useCallback(async () => {
    if (!workspaceId) return
    setLoading(true)
    setLoadError(null)
    try {
      const data = await guard.config.get(authFetch, workspaceId)
      if (data.enforcement_mode) setEnforcementMode(data.enforcement_mode as "block" | "warn" | "audit")
      if (data.fail_mode) setFailMode(data.fail_mode as "fail_open" | "fail_closed")
      if (data.deny_on_error !== undefined) setDenyOnError(data.deny_on_error)
      if (data.notify_on_fail_open !== undefined) setNotifyOnFailOpen(data.notify_on_fail_open)
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e)
      if (msg.includes("404")) { setLoading(false); return }
      setLoadError(msg || "Failed to load settings")
    } finally {
      setLoading(false)
    }
  }, [authFetch, workspaceId])

  useEffect(() => { void load() }, [load])

  async function patchConfig(body: Record<string, unknown>) {
    if (!workspaceId) return
    const res = await guard.config.patch(authFetch, workspaceId, body)
    if (!res.ok) throw new Error(`Save failed (${res.status})`)
    return res.json()
  }

  if (loading) {
    return <div style={{ textAlign: "center", padding: "40px 0", fontSize: 13, color: "var(--text-muted)" }}>Loading settings…</div>
  }
  if (loadError) {
    return (
      <div style={{ borderRadius: 12, border: "1px solid var(--err-bd)", background: "var(--err-bg)", padding: "12px 16px", fontSize: 13, color: "var(--err)", marginBottom: 16 }}>
        {loadError}
      </div>
    )
  }

  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(0, 1fr))", gap: 20, alignItems: "stretch" }}>
      <div className="card" style={{ padding: "18px 20px", minWidth: 0 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 4, gap: 8 }}>
          <div className="eyebrow">Agent guard <span style={{ color: "var(--text-muted)", fontWeight: 400, textTransform: "none", letterSpacing: 0 }}>· workspace default</span></div>
          <a href="/playbooks" style={{ fontSize: 12, color: "var(--text-3)", textDecoration: "none", whiteSpace: "nowrap" }}>Learn more →</a>
        </div>
        <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 12 }}>Applied to playbook runs (brain / tool / output blocks).</div>
        {enforcementError && (
          <div style={{ fontSize: 12, color: "var(--err)", background: "var(--err-bg)", border: "1px solid var(--err-bd)", borderRadius: 6, padding: "6px 10px", marginBottom: 10 }}>
            {enforcementError}
          </div>
        )}
        {([
          ["block", "Block",      "Run halts — the AI step never executes"],
          ["warn",  "Warn",       "Flagged in the run trace, step proceeds"],
          ["audit", "Audit only", "Recorded silently, no visible interruption"],
        ] as const).map(([k, t, d], i) => (
          <label
            key={k}
            style={{
              display: "flex",
              gap: 11,
              padding: "10px 0",
              borderTop: i > 0 ? "1px solid var(--border)" : "none",
              cursor: isAdmin ? "pointer" : "default",
              alignItems: "flex-start",
            }}
          >
            <span
              onClick={async () => {
                if (!isAdmin || enforcementMode === k) return
                const prev = enforcementMode
                setEnforcementMode(k)
                setEnforcementError(null)
                try {
                  await patchConfig({ enforcement_mode: k })
                } catch (e) {
                  setEnforcementMode(prev)
                  setEnforcementError(e instanceof Error ? e.message : "Failed to save enforcement mode")
                }
              }}
              style={{
                width: 16,
                height: 16,
                borderRadius: "50%",
                border: `2px solid ${enforcementMode === k ? "var(--accent)" : "var(--border-2)"}`,
                display: "grid",
                placeItems: "center",
                marginTop: 2,
                flexShrink: 0,
                cursor: isAdmin ? "pointer" : "default",
              }}
            >
              {enforcementMode === k && (
                <span style={{ width: 7, height: 7, borderRadius: "50%", background: "var(--accent)" }} />
              )}
            </span>
            <div>
              <div style={{ fontWeight: 600, fontSize: 13 }}>{t}</div>
              <div style={{ fontSize: 11.5, color: "var(--text-3)" }}>{d}</div>
            </div>
          </label>
        ))}
      </div>
      <div className="card" style={{ padding: "18px 20px", minWidth: 0 }}>
        <div className="eyebrow" style={{ marginBottom: 4 }}>Outage behavior</div>
        <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 12 }}>
          What the CLI hook does when it can&apos;t reach Guard. Applies to conduct-cli hook calls only.
        </div>
        {([
          ["fail_open",   "Fail open",   "Tool calls proceed when Guard is unreachable. Recommended for most teams — keeps developers productive when our infra hiccups."],
          ["fail_closed", "Fail-Closed Mode", "Tool calls are blocked with rule_id=guard-unavailable until Guard responds. Use for regulated workloads where missing a policy check is worse than a paused build."],
        ] as const).map(([k, t, d], i) => (
          <label
            key={k}
            style={{
              display: "flex",
              gap: 11,
              padding: "10px 0",
              borderTop: i > 0 ? "1px solid var(--border)" : "none",
              cursor: isAdmin ? "pointer" : "default",
              alignItems: "flex-start",
            }}
          >
            <span
              onClick={async () => {
                if (!isAdmin || failMode === k) return
                const prev = failMode
                setFailMode(k)
                try {
                  await patchConfig({ fail_mode: k })
                } catch {
                  setFailMode(prev)
                }
              }}
              style={{
                width: 16,
                height: 16,
                borderRadius: "50%",
                border: `2px solid ${failMode === k ? "var(--accent)" : "var(--border-2)"}`,
                display: "grid",
                placeItems: "center",
                marginTop: 2,
                flexShrink: 0,
                cursor: isAdmin ? "pointer" : "default",
              }}
            >
              {failMode === k && (
                <span style={{ width: 7, height: 7, borderRadius: "50%", background: "var(--accent)" }} />
              )}
            </span>
            <div>
              <div style={{ fontWeight: 600, fontSize: 13 }}>{t}</div>
              <div style={{ fontSize: 11.5, color: "var(--text-3)" }}>{d}</div>
            </div>
          </label>
        ))}
        <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 6, lineHeight: 1.5 }}>
          Change takes effect on each machine the next time <code style={{ fontFamily: "ui-monospace,monospace", background: "var(--surface-2)", padding: "0 4px", borderRadius: 3 }}>conduct guard sync</code> runs (≤60s for active CLI sessions).
        </div>
      </div>
      <div className="card" style={{ padding: "18px 20px", minWidth: 0 }}>
        <div className="eyebrow" style={{ marginBottom: 4 }}>Policy error behavior</div>
        <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 12 }}>
          What Guard does if policy evaluation throws. Applies across proxy, MCP, and playbook runtime.
        </div>
        <label style={{ display: "flex", gap: 11, alignItems: "flex-start", cursor: isAdmin ? "pointer" : "default" }}
          onClick={async () => {
            if (!isAdmin) return
            const next = !denyOnError
            setDenyOnError(next)
            try { await patchConfig({ deny_on_error: next }) }
            catch { setDenyOnError(!next) }
          }}>
          <GuardToggle on={denyOnError} onClick={() => {}} disabled={!isAdmin} />
          <div>
            <div style={{ fontWeight: 600, fontSize: 13 }}>Fail closed on error</div>
            <div style={{ fontSize: 11.5, color: "var(--text-3)" }}>
              Block the request and write an audit entry if the policy engine throws. Recommended. Disable only if you prefer fail-open during policy engine incidents.
            </div>
          </div>
        </label>
        <label style={{ display: "flex", gap: 11, alignItems: "flex-start", cursor: isAdmin ? "pointer" : "default", marginTop: 14 }}
          onClick={async () => {
            if (!isAdmin) return
            const next = !notifyOnFailOpen
            setNotifyOnFailOpen(next)
            try { await patchConfig({ notify_on_fail_open: next }) }
            catch { setNotifyOnFailOpen(!next) }
          }}>
          <GuardToggle on={notifyOnFailOpen} onClick={() => {}} disabled={!isAdmin} />
          <div>
            <div style={{ fontWeight: 600, fontSize: 13 }}>Notify on fail-open</div>
            <div style={{ fontSize: 11.5, color: "var(--text-3)" }}>
              Post a Slack warning to your workspace channel when Guard could not evaluate policy and allowed the request through. Requires a Slack webhook configured for the workspace.
            </div>
          </div>
        </label>
      </div>
    </div>
  )
}
