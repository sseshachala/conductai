"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { useParams } from "next/navigation"
import { useAuth } from "@clerk/nextjs"
import AppShell from "@/components/AppShell"
import { useWorkspace } from "@/lib/WorkspaceContext"
import { API } from "@/lib/api/client"

interface PackRule {
  id: string
  description: string | null
  action: string
  severity: string | null
  match_tool: string | null
  match_pattern: string | null
  match_path_pattern: string | null
  message: string | null
  recommendation: string | null
  frameworks: string[]
  iso_control: string | null
  persona_affinity: string[]
}

interface PackDetail {
  slug: string
  version: string
  name: string
  description: string | null
  tier: string
  rules_count: number
  rules: PackRule[]
  installed: boolean
}

const ACTION_STYLE: Record<string, { bg: string; color: string; label: string }> = {
  block:    { bg: "var(--err-bg)",  color: "var(--err)",  label: "Block" },
  warn:     { bg: "var(--warn-bg)", color: "var(--warn)", label: "Warn" },
  audit:    { bg: "var(--info-bg)", color: "var(--info)", label: "Audit" },
  approval: { bg: "var(--info-bg)", color: "var(--info)", label: "Approval" },
  inject:   { bg: "var(--ok-bg)",   color: "var(--ok)",   label: "Inject" },
}

const SEVERITY_STYLE: Record<string, { color: string; weight: number }> = {
  critical: { color: "#b91c1c", weight: 600 },
  high:     { color: "#c2410c", weight: 600 },
  medium:   { color: "#a16207", weight: 500 },
  low:      { color: "#16a34a", weight: 500 },
}

function ActionBadge({ action }: { action: string }) {
  const s = ACTION_STYLE[action] ?? ACTION_STYLE.audit
  return (
    <span style={{
      display: "inline-block",
      padding: "2px 8px",
      borderRadius: 999,
      fontSize: 11,
      fontWeight: 600,
      background: s.bg,
      color: s.color,
    }}>{s.label}</span>
  )
}

function SeverityBadge({ severity }: { severity: string | null }) {
  if (!severity) return <span style={{ fontSize: 11, color: "var(--text-muted)" }}>—</span>
  const s = SEVERITY_STYLE[severity] ?? SEVERITY_STYLE.medium
  return (
    <span style={{ fontSize: 11, fontWeight: s.weight, color: s.color, textTransform: "capitalize" }}>
      {severity}
    </span>
  )
}

function FrameworkChips({ frameworks }: { frameworks: string[] }) {
  if (!frameworks.length) {
    return <span style={{ fontSize: 11, color: "var(--text-muted)" }}>—</span>
  }
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
      {frameworks.map(fw => (
        <span key={fw} style={{
          fontSize: 10,
          padding: "2px 6px",
          borderRadius: 4,
          background: "var(--surface-2)",
          color: "var(--text-2)",
          fontFamily: "var(--font-mono, ui-monospace, monospace)",
        }}>{fw}</span>
      ))}
    </div>
  )
}

export default function PackDetailPage() {
  const params = useParams()
  const slug = (params?.slug as string) || ""
  const { activeWorkspace } = useWorkspace()
  const workspaceId = activeWorkspace?.id ?? null
  const { getToken } = useAuth()
  const [pack, setPack] = useState<PackDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [cedarText, setCedarText] = useState<string | null>(null)
  const [cedarLoading, setCedarLoading] = useState(false)
  const [cedarError, setCedarError] = useState<string | null>(null)
  const [cedarCopied, setCedarCopied] = useState(false)

  useEffect(() => {
    if (!slug || !workspaceId) return
    let cancelled = false
    const load = async () => {
      setLoading(true)
      try {
        const token = await getToken()
        const headers: Record<string, string> = {}
        if (token) headers["Authorization"] = `Bearer ${token}`
        const base = process.env.NEXT_PUBLIC_API_URL ?? ""
        const res = await fetch(`${base}/compliance/packs/${slug}?workspace_id=${workspaceId}`, { headers })
        if (!cancelled) {
          if (res.ok) setPack(await res.json())
          else if (res.status === 404) setError(`Pack '${slug}' not found.`)
          else setError(`Failed to load pack (HTTP ${res.status})`)
        }
      } catch {
        if (!cancelled) setError("Network error loading pack.")
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [slug, workspaceId, getToken])

  const toggleCedar = async () => {
    if (cedarText !== null) {
      setCedarText(null)
      setCedarError(null)
      return
    }
    if (!workspaceId) return
    setCedarLoading(true)
    setCedarError(null)
    try {
      const token = await getToken()
      const headers: Record<string, string> = {}
      if (token) headers["Authorization"] = `Bearer ${token}`
      const base = process.env.NEXT_PUBLIC_API_URL ?? ""
      const res = await fetch(`${base}/guard/registry/packs/${slug}/cedar?workspace_id=${workspaceId}`, { headers })
      if (res.ok) setCedarText(await res.text())
      else if (res.status === 404) setCedarError("Cedar rendering not available for this pack.")
      else setCedarError(`Failed to load Cedar (HTTP ${res.status})`)
    } catch {
      setCedarError("Network error loading Cedar.")
    } finally {
      setCedarLoading(false)
    }
  }

  const copyCedar = async () => {
    if (!cedarText) return
    try {
      await navigator.clipboard.writeText(cedarText)
      setCedarCopied(true)
      setTimeout(() => setCedarCopied(false), 1500)
    } catch {}
  }

  const togglePack = async () => {
    if (!pack || !workspaceId) return
    setBusy(true)
    try {
      const token = await getToken()
      const headers: Record<string, string> = { "Content-Type": "application/json" }
      if (token) headers["Authorization"] = `Bearer ${token}`
      const base = process.env.NEXT_PUBLIC_API_URL ?? ""
      const method = pack.installed ? "DELETE" : "POST"
      const path = pack.installed ? "uninstall" : "install"
      const res = await fetch(`${base}/compliance/packs/${slug}/${path}?workspace_id=${workspaceId}`, {
        method, headers,
      })
      if (res.ok) {
        setPack({ ...pack, installed: !pack.installed })
      }
    } finally {
      setBusy(false)
    }
  }

  if (loading) {
    return (
      <AppShell>
        <div style={{ padding: "24px 28px", maxWidth: 1200, margin: "0 auto" }}>
          <div style={{ fontSize: 13, color: "var(--text-3)" }}>Loading pack…</div>
        </div>
      </AppShell>
    )
  }

  if (error || !pack) {
    return (
      <AppShell>
        <div style={{ padding: "24px 28px", maxWidth: 1200, margin: "0 auto" }}>
          <Link href="/packs" style={{ fontSize: 12, color: "var(--accent-text)" }}>← Back to registry</Link>
          <div style={{ marginTop: 16, fontSize: 14, color: "var(--err)" }}>{error ?? "Pack not found"}</div>
        </div>
      </AppShell>
    )
  }

  return (
    <AppShell>
      <div style={{ padding: "24px 28px", maxWidth: 1200, margin: "0 auto" }}>
        <Link href="/packs" style={{ fontSize: 12, color: "var(--accent-text)" }}>← Back to registry</Link>

        <header style={{ marginTop: 12, marginBottom: 20, display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 16 }}>
          <div>
            <h1 style={{ fontSize: 24, fontWeight: 600, margin: 0, color: "var(--text-1)" }}>{pack.name}</h1>
            <div style={{ marginTop: 4, fontSize: 12, color: "var(--text-muted)" }}>
              {pack.slug} · v{pack.version} · {pack.tier} tier · {pack.rules_count} rules
            </div>
            {pack.description && (
              <p style={{ marginTop: 12, fontSize: 14, color: "var(--text-2)", maxWidth: 720, lineHeight: 1.5 }}>
                {pack.description}
              </p>
            )}
          </div>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <button
              onClick={toggleCedar}
              disabled={cedarLoading}
              title="Render this pack as Cedar text syntax"
              style={{
                padding: "10px 14px",
                borderRadius: 8,
                border: "1px solid var(--border)",
                background: cedarText !== null ? "var(--surface-2)" : "transparent",
                color: "var(--text-1)",
                fontSize: 12.5,
                fontWeight: 500,
                whiteSpace: "nowrap",
                cursor: cedarLoading ? "wait" : "pointer",
              }}
            >
              {cedarLoading ? "Loading…" : cedarText !== null ? "Hide Cedar" : "View as Cedar"}
            </button>
            <button
              onClick={togglePack}
              disabled={busy}
              style={{
                padding: "10px 18px",
                borderRadius: 8,
                border: "none",
                background: pack.installed ? "var(--surface-2)" : "var(--text-1)",
                color: pack.installed ? "var(--text-1)" : "white",
                cursor: busy ? "not-allowed" : "pointer",
                fontSize: 13,
                fontWeight: 600,
                opacity: busy ? 0.6 : 1,
              }}
            >
              {busy ? "…" : pack.installed ? "Uninstall" : "Install"}
            </button>
          </div>
        </header>

        {(cedarText !== null || cedarError) && (
          <section style={{ border: "1px solid var(--border)", borderRadius: 8, background: "var(--surface-1)", marginBottom: 16 }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "10px 14px", borderBottom: "1px solid var(--border)" }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text-1)" }}>
                Cedar rendering
                <span style={{ marginLeft: 8, fontSize: 11, fontWeight: 400, color: "var(--text-3)" }}>
                  human-readable syntax · runtime still evaluates JSON
                </span>
              </div>
              <div style={{ display: "flex", gap: 8 }}>
                {cedarText && (
                  <button
                    onClick={copyCedar}
                    style={{ padding: "4px 10px", borderRadius: 6, border: "1px solid var(--border)", background: "transparent", color: "var(--text-2)", fontSize: 11, cursor: "pointer" }}
                  >
                    {cedarCopied ? "✓ Copied" : "Copy"}
                  </button>
                )}
                <button
                  onClick={toggleCedar}
                  style={{ padding: "4px 10px", borderRadius: 6, border: "1px solid var(--border)", background: "transparent", color: "var(--text-2)", fontSize: 11, cursor: "pointer" }}
                >
                  Close
                </button>
              </div>
            </div>
            {cedarError ? (
              <div style={{ padding: 16, fontSize: 13, color: "var(--err)" }}>{cedarError}</div>
            ) : (
              <pre style={{
                margin: 0,
                padding: 16,
                fontSize: 12,
                lineHeight: 1.5,
                color: "var(--text-1)",
                background: "var(--surface-0, var(--surface-1))",
                overflowX: "auto",
                fontFamily: "ui-monospace, SFMono-Regular, Consolas, monospace",
                whiteSpace: "pre",
                maxHeight: 500,
                overflowY: "auto",
              }}>{cedarText}</pre>
            )}
          </section>
        )}

        <section style={{ border: "1px solid var(--border)", borderRadius: 8, overflow: "hidden", background: "var(--surface-1)" }}>
          <div style={{ padding: "12px 16px", borderBottom: "1px solid var(--border)", fontSize: 13, fontWeight: 600, color: "var(--text-1)" }}>
            Rules included
          </div>
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
              <thead>
                <tr style={{ background: "var(--surface-2)", color: "var(--text-muted)" }}>
                  <th style={{ textAlign: "left", padding: "10px 14px", fontWeight: 600, letterSpacing: ".04em", textTransform: "uppercase", fontSize: 11 }}>Rule</th>
                  <th style={{ textAlign: "left", padding: "10px 14px", fontWeight: 600, letterSpacing: ".04em", textTransform: "uppercase", fontSize: 11 }}>Action</th>
                  <th style={{ textAlign: "left", padding: "10px 14px", fontWeight: 600, letterSpacing: ".04em", textTransform: "uppercase", fontSize: 11 }}>Severity</th>
                  <th style={{ textAlign: "left", padding: "10px 14px", fontWeight: 600, letterSpacing: ".04em", textTransform: "uppercase", fontSize: 11 }}>Catches</th>
                  <th style={{ textAlign: "left", padding: "10px 14px", fontWeight: 600, letterSpacing: ".04em", textTransform: "uppercase", fontSize: 11 }}>Frameworks</th>
                </tr>
              </thead>
              <tbody>
                {pack.rules.map(r => (
                  <tr key={r.id} style={{ borderTop: "1px solid var(--border)" }}>
                    <td style={{ padding: "12px 14px", verticalAlign: "top" }}>
                      <div style={{ fontWeight: 600, color: "var(--text-1)" }}>{r.id}</div>
                      {r.description && (
                        <div style={{ marginTop: 2, color: "var(--text-3)", fontSize: 11 }}>{r.description}</div>
                      )}
                    </td>
                    <td style={{ padding: "12px 14px", verticalAlign: "top" }}>
                      <ActionBadge action={r.action} />
                    </td>
                    <td style={{ padding: "12px 14px", verticalAlign: "top" }}>
                      <SeverityBadge severity={r.severity} />
                    </td>
                    <td style={{ padding: "12px 14px", verticalAlign: "top", color: "var(--text-2)", maxWidth: 280 }}>
                      {r.match_tool && (
                        <div style={{ fontSize: 11, color: "var(--text-muted)" }}>
                          Tool: {r.match_tool}
                        </div>
                      )}
                      {r.match_pattern && (
                        <div style={{ fontFamily: "var(--font-mono, ui-monospace, monospace)", fontSize: 11, color: "var(--text-2)", wordBreak: "break-all" }}>
                          {r.match_pattern}
                        </div>
                      )}
                      {r.match_path_pattern && (
                        <div style={{ fontFamily: "var(--font-mono, ui-monospace, monospace)", fontSize: 11, color: "var(--text-2)", wordBreak: "break-all" }}>
                          path: {r.match_path_pattern}
                        </div>
                      )}
                      {!r.match_tool && !r.match_pattern && !r.match_path_pattern && (
                        <span style={{ fontSize: 11, color: "var(--text-muted)" }}>any tool call</span>
                      )}
                    </td>
                    <td style={{ padding: "12px 14px", verticalAlign: "top" }}>
                      <FrameworkChips frameworks={r.frameworks} />
                      {r.iso_control && (
                        <div style={{ marginTop: 4, fontSize: 10, color: "var(--text-muted)" }}>
                          ISO control: {r.iso_control}
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </AppShell>
  )
}
