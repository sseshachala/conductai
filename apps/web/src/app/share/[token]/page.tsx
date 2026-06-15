"use client"

import { useEffect, useState } from "react"
import { useParams } from "next/navigation"

// ── Types ─────────────────────────────────────────────────────────────────────

interface SessionReportData {
  id: string
  developer_email: string
  archetype: string | null
  autonomy_score: number | null
  planning_ratio: number | null
  sessions: number
  prompts: number
  commits: number
  lines_per_hour: number | null
  tools_json: Record<string, number> | null
  report_md: string | null
  created_at: string | null
}

interface SharePayload {
  resource_type: string
  expires_at: string
  data: SessionReportData
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatDate(iso: string | null): string {
  if (!iso) return ""
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })
}

function autonomyColor(score: number): string {
  if (score >= 70) return "var(--ok, #059669)"
  if (score >= 50) return "var(--warn, #d97706)"
  return "var(--err, #dc2626)"
}

// ── Session Report View ────────────────────────────────────────────────────────

function SessionReportView({ data, expiresAt }: { data: SessionReportData; expiresAt: string }) {
  const topTools = Object.entries(data.tools_json ?? {})
    .sort(([, a], [, b]) => b - a)
    .slice(0, 8)

  return (
    <div style={{ maxWidth: 900, margin: "0 auto", padding: "32px 24px 64px" }}>
      {/* Header */}
      <div style={{ marginBottom: 28 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
          <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: ".08em", textTransform: "uppercase", color: "var(--text-muted, #a8a29e)" }}>
            Conduct Guard
          </span>
          <span style={{ fontSize: 11, color: "var(--text-muted, #a8a29e)" }}>·</span>
          <span style={{ fontSize: 11, color: "var(--text-muted, #a8a29e)" }}>
            Shared · expires {formatDate(expiresAt)}
          </span>
        </div>
        <h1 style={{ fontSize: 22, fontWeight: 700, color: "var(--text, #1c1917)", margin: "0 0 4px", letterSpacing: "-.02em" }}>
          Session Report
        </h1>
        <div style={{ fontSize: 13, color: "var(--text-3, #78716c)", display: "flex", alignItems: "center", gap: 10 }}>
          <span>{data.developer_email}</span>
          {data.archetype && (
            <>
              <span>·</span>
              <span style={{
                fontSize: 12, fontWeight: 600,
                background: "#eef2ff", color: "#4338ca",
                borderRadius: 6, padding: "2px 8px",
              }}>
                {data.archetype}
              </span>
            </>
          )}
          <span>·</span>
          <span>{formatDate(data.created_at)}</span>
        </div>
      </div>

      {/* KPI grid */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 24 }}>
        {[
          {
            label: "Autonomy",
            value: data.autonomy_score !== null ? data.autonomy_score.toFixed(1) : "—",
            unit: "/ 100",
            color: data.autonomy_score !== null ? autonomyColor(data.autonomy_score) : "#a8a29e",
          },
          { label: "Sessions", value: data.sessions, unit: null, color: "#1c1917" },
          { label: "Prompts",  value: data.prompts,  unit: null, color: "#1c1917" },
          { label: "Commits",  value: data.commits,  unit: null, color: "#1c1917" },
        ].map(card => (
          <div key={card.label} style={{
            background: "#fff",
            border: "1px solid #e7e5e4",
            borderRadius: 12,
            padding: "18px 20px",
          }}>
            <div style={{ fontSize: 9.5, fontWeight: 700, letterSpacing: ".1em", textTransform: "uppercase", color: "#a8a29e", marginBottom: 8 }}>
              {card.label}
            </div>
            <div style={{ fontSize: 28, fontWeight: 800, color: card.color, lineHeight: 1 }}>
              {card.value}
            </div>
            {card.unit && <div style={{ fontSize: 12, color: "#a8a29e", marginTop: 2 }}>{card.unit}</div>}
          </div>
        ))}
      </div>

      {/* Tools */}
      {topTools.length > 0 && (
        <div style={{ marginBottom: 24 }}>
          <div style={{ fontSize: 9.5, fontWeight: 700, letterSpacing: ".1em", textTransform: "uppercase", color: "#a8a29e", marginBottom: 10 }}>
            Top Tools
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
            {topTools.map(([tool]) => (
              <span key={tool} style={{
                fontSize: 12, fontWeight: 600,
                background: "#faf9f7", border: "1px solid #e7e5e4",
                borderRadius: 6, padding: "4px 10px", color: "#57534e",
              }}>
                {tool}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Report markdown */}
      <div>
        <div style={{ fontSize: 9.5, fontWeight: 700, letterSpacing: ".1em", textTransform: "uppercase", color: "#a8a29e", marginBottom: 10 }}>
          Full Report
        </div>
        {data.report_md ? (
          <div style={{
            background: "#fff",
            border: "1px solid #e7e5e4",
            borderRadius: 12,
            padding: "20px 24px",
            fontSize: 13,
            color: "#57534e",
            lineHeight: 1.7,
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
          }}>
            {data.report_md}
          </div>
        ) : (
          <div style={{ fontSize: 13, color: "#a8a29e" }}>No report text available.</div>
        )}
      </div>

      {/* Footer */}
      <div style={{ marginTop: 48, textAlign: "center", fontSize: 11, color: "#a8a29e" }}>
        Shared via{" "}
        <a href="https://conductai.ai" style={{ color: "#4f46e5", textDecoration: "none", fontWeight: 600 }}>
          Conduct Guard
        </a>
        {" "}· link expires {formatDate(expiresAt)}
      </div>
    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function SharePage() {
  const { token } = useParams<{ token: string }>()
  const [payload, setPayload]   = useState<SharePayload | null>(null)
  const [error, setError]       = useState<string | null>(null)
  const [loading, setLoading]   = useState(true)

  useEffect(() => {
    if (!token) return
    const base = process.env.NEXT_PUBLIC_API_URL ?? ""
    fetch(`${base}/share/${token}`)
      .then(r => {
        if (!r.ok) throw new Error(r.status === 404 ? "Share link not found or expired." : "Failed to load.")
        return r.json()
      })
      .then(setPayload)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [token])

  const containerStyle: React.CSSProperties = {
    minHeight: "100vh",
    background: "#faf9f7",
    fontFamily: "'Inter', ui-sans-serif, system-ui, sans-serif",
    WebkitFontSmoothing: "antialiased",
  }

  if (loading) return (
    <div style={{ ...containerStyle, display: "flex", alignItems: "center", justifyContent: "center" }}>
      <span style={{ fontSize: 13, color: "#a8a29e" }}>Loading…</span>
    </div>
  )

  if (error) return (
    <div style={{ ...containerStyle, display: "flex", alignItems: "center", justifyContent: "center" }}>
      <div style={{ textAlign: "center" }}>
        <div style={{ fontSize: 32, marginBottom: 12 }}>🔗</div>
        <div style={{ fontSize: 15, fontWeight: 600, color: "#1c1917", marginBottom: 6 }}>Link unavailable</div>
        <div style={{ fontSize: 13, color: "#78716c" }}>{error}</div>
      </div>
    </div>
  )

  if (!payload) return null

  if (payload.resource_type === "session_report") {
    return (
      <div style={containerStyle}>
        <SessionReportView data={payload.data as SessionReportData} expiresAt={payload.expires_at} />
      </div>
    )
  }

  return (
    <div style={{ ...containerStyle, display: "flex", alignItems: "center", justifyContent: "center" }}>
      <div style={{ fontSize: 13, color: "#78716c" }}>Unknown resource type.</div>
    </div>
  )
}
