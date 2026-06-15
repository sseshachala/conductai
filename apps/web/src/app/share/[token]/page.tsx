"use client"

import { useEffect, useState } from "react"
import { useParams } from "next/navigation"

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

function formatDate(iso: string | null): string {
  if (!iso) return ""
  return new Date(iso).toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" })
}

function autonomyColor(score: number): string {
  if (score >= 70) return "#059669"
  if (score >= 50) return "#d97706"
  return "#dc2626"
}

function autonomyLabel(score: number): string {
  if (score >= 80) return "High Autonomy"
  if (score >= 60) return "Moderate Autonomy"
  if (score >= 40) return "Developing"
  return "Low Autonomy"
}

// Minimal markdown → HTML: headers, bold, bullets, line breaks
function renderMd(md: string): string {
  return md
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/^### (.+)$/gm, '<h3 style="font-size:13px;font-weight:700;color:#1c1917;margin:20px 0 6px">$1</h3>')
    .replace(/^## (.+)$/gm,  '<h2 style="font-size:14px;font-weight:700;color:#1c1917;margin:24px 0 8px">$1</h2>')
    .replace(/^# (.+)$/gm,   '<h1 style="font-size:16px;font-weight:800;color:#1c1917;margin:28px 0 10px">$1</h1>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/^[-•] (.+)$/gm, '<li style="margin:3px 0;padding-left:4px">$1</li>')
    .replace(/(<li[^>]*>.*<\/li>\n?)+/g, s => `<ul style="margin:8px 0 12px;padding-left:18px;list-style:disc">${s}</ul>`)
    .replace(/\n/g, "<br>")
}

function SessionReportView({ data, expiresAt }: { data: SessionReportData; expiresAt: string }) {
  const topTools = Object.entries(data.tools_json ?? {})
    .sort(([, a], [, b]) => b - a)
    .slice(0, 10)
  const maxCalls = topTools[0]?.[1] ?? 1
  const score = data.autonomy_score

  return (
    <div style={{ minHeight: "100vh", background: "#f5f4f2", fontFamily: "'Inter', ui-sans-serif, system-ui, sans-serif", WebkitFontSmoothing: "antialiased" }}>

      {/* Top bar */}
      <div style={{ background: "#fff", borderBottom: "1px solid #e7e5e4", padding: "0 24px", height: 52, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <div style={{ width: 26, height: 26, background: "#4f46e5", borderRadius: 7, display: "flex", alignItems: "center", justifyContent: "center" }}>
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
              <rect x="2" y="2" width="5" height="5" rx="1.5" fill="white" fillOpacity=".9"/>
              <rect x="9" y="2" width="5" height="5" rx="1.5" fill="white" fillOpacity=".6"/>
              <rect x="2" y="9" width="5" height="5" rx="1.5" fill="white" fillOpacity=".6"/>
              <rect x="9" y="9" width="5" height="5" rx="1.5" fill="white" fillOpacity=".9"/>
            </svg>
          </div>
          <span style={{ fontSize: 14, fontWeight: 700, color: "#1c1917", letterSpacing: "-.01em" }}>Conduct Guard</span>
          <span style={{ fontSize: 12, color: "#a8a29e", marginLeft: 4 }}>· Developer Session Report</span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <span style={{ fontSize: 11, color: "#a8a29e" }}>Link expires {formatDate(expiresAt)}</span>
          <a
            href="https://conductai.ai"
            style={{ fontSize: 12, fontWeight: 600, color: "#4f46e5", textDecoration: "none", background: "#eef2ff", borderRadius: 7, padding: "5px 12px", border: "1px solid #c7d2fe" }}
          >
            Get Guard →
          </a>
        </div>
      </div>

      {/* Hero */}
      <div style={{ background: "#fff", borderBottom: "1px solid #e7e5e4", padding: "28px 24px 24px" }}>
        <div style={{ maxWidth: 860, margin: "0 auto" }}>
          <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 24, flexWrap: "wrap" }}>
            <div>
              <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: ".08em", textTransform: "uppercase", color: "#a8a29e", marginBottom: 8 }}>
                Developer Profile
              </div>
              <h1 style={{ fontSize: 24, fontWeight: 800, color: "#1c1917", margin: "0 0 8px", letterSpacing: "-.03em" }}>
                {data.developer_email}
              </h1>
              <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                {data.archetype && (
                  <span style={{ fontSize: 12, fontWeight: 600, background: "#eef2ff", color: "#4338ca", borderRadius: 6, padding: "3px 10px", border: "1px solid #c7d2fe" }}>
                    {data.archetype}
                  </span>
                )}
                <span style={{ fontSize: 12, color: "#a8a29e" }}>Report generated {formatDate(data.created_at)}</span>
              </div>
            </div>

            {/* Autonomy score callout */}
            {score !== null && (
              <div style={{ background: "#fafaf9", border: "1px solid #e7e5e4", borderRadius: 14, padding: "18px 24px", textAlign: "center", minWidth: 120 }}>
                <div style={{ fontSize: 9.5, fontWeight: 700, letterSpacing: ".1em", textTransform: "uppercase", color: "#a8a29e", marginBottom: 6 }}>
                  Autonomy Score
                </div>
                <div style={{ fontSize: 44, fontWeight: 900, color: autonomyColor(score), lineHeight: 1, letterSpacing: "-.03em" }}>
                  {score.toFixed(0)}
                </div>
                <div style={{ fontSize: 11, color: "#78716c", marginTop: 4 }}>{autonomyLabel(score)}</div>
                {/* Score bar */}
                <div style={{ marginTop: 10, background: "#e7e5e4", borderRadius: 4, height: 5, width: 100 }}>
                  <div style={{ height: 5, borderRadius: 4, background: autonomyColor(score), width: `${Math.min(score, 100)}%`, transition: "width .4s" }} />
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Body */}
      <div style={{ maxWidth: 860, margin: "0 auto", padding: "28px 24px 64px" }}>

        {/* Stats row */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 24 }}>
          {[
            { label: "Sessions",   value: data.sessions,                                                           unit: null  },
            { label: "Prompts",    value: data.prompts,                                                            unit: null  },
            { label: "Commits",    value: data.commits,                                                            unit: null  },
            { label: "Lines / hr", value: data.lines_per_hour !== null ? Math.round(data.lines_per_hour) : "—",   unit: null  },
          ].map(c => (
            <div key={c.label} style={{ background: "#fff", border: "1px solid #e7e5e4", borderRadius: 12, padding: "16px 18px" }}>
              <div style={{ fontSize: 9.5, fontWeight: 700, letterSpacing: ".1em", textTransform: "uppercase", color: "#a8a29e", marginBottom: 8 }}>{c.label}</div>
              <div style={{ fontSize: 26, fontWeight: 800, color: "#1c1917", lineHeight: 1 }}>{c.value}</div>
            </div>
          ))}
        </div>

        {/* Planning ratio */}
        {data.planning_ratio !== null && (
          <div style={{ background: "#fff", border: "1px solid #e7e5e4", borderRadius: 12, padding: "16px 20px", marginBottom: 24, display: "flex", alignItems: "center", gap: 16 }}>
            <div>
              <div style={{ fontSize: 9.5, fontWeight: 700, letterSpacing: ".1em", textTransform: "uppercase", color: "#a8a29e", marginBottom: 4 }}>Planning Ratio</div>
              <div style={{ fontSize: 22, fontWeight: 800, color: "#1c1917", lineHeight: 1 }}>{data.planning_ratio.toFixed(2)}</div>
            </div>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 12, color: "#78716c", marginBottom: 6 }}>
                {data.planning_ratio >= 0.4 ? "Strong planning behaviour — agent spends significant time on design before executing." :
                 data.planning_ratio >= 0.2 ? "Moderate planning. Agent balances thinking with execution." :
                 "Execution-heavy. Agent moves fast but plans less upfront."}
              </div>
              <div style={{ background: "#f5f4f2", borderRadius: 4, height: 6 }}>
                <div style={{ height: 6, borderRadius: 4, background: "#4f46e5", width: `${Math.min(data.planning_ratio * 200, 100)}%` }} />
              </div>
            </div>
          </div>
        )}

        {/* Tools */}
        {topTools.length > 0 && (
          <div style={{ background: "#fff", border: "1px solid #e7e5e4", borderRadius: 12, padding: "20px", marginBottom: 24 }}>
            <div style={{ fontSize: 9.5, fontWeight: 700, letterSpacing: ".1em", textTransform: "uppercase", color: "#a8a29e", marginBottom: 16 }}>
              Top Tools Used
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {topTools.map(([tool, calls]) => (
                <div key={tool} style={{ display: "flex", alignItems: "center", gap: 12 }}>
                  <div style={{ fontSize: 12, fontWeight: 600, color: "#1c1917", width: 160, flexShrink: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {tool}
                  </div>
                  <div style={{ flex: 1, background: "#f5f4f2", borderRadius: 4, height: 8, overflow: "hidden" }}>
                    <div style={{ height: 8, borderRadius: 4, background: "#4f46e5", opacity: 0.75, width: `${(calls / maxCalls) * 100}%` }} />
                  </div>
                  <div style={{ fontSize: 11, fontWeight: 600, color: "#78716c", width: 36, textAlign: "right", flexShrink: 0 }}>
                    {calls}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Full report */}
        {data.report_md && (
          <div style={{ background: "#fff", border: "1px solid #e7e5e4", borderRadius: 12, padding: "24px 28px" }}>
            <div style={{ fontSize: 9.5, fontWeight: 700, letterSpacing: ".1em", textTransform: "uppercase", color: "#a8a29e", marginBottom: 18 }}>
              Full Report
            </div>
            <div
              style={{ fontSize: 13, color: "#44403c", lineHeight: 1.75 }}
              dangerouslySetInnerHTML={{ __html: renderMd(data.report_md) }}
            />
          </div>
        )}

        {/* CTA footer */}
        <div style={{ marginTop: 40, background: "#fff", border: "1px solid #e7e5e4", borderRadius: 14, padding: "24px 28px", display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16, flexWrap: "wrap" }}>
          <div>
            <div style={{ fontSize: 14, fontWeight: 700, color: "#1c1917", marginBottom: 4 }}>Track your whole team with Conduct Guard</div>
            <div style={{ fontSize: 12, color: "#78716c" }}>Policies, spend limits, and session reports — MDM for AI coding tools.</div>
          </div>
          <a
            href="https://conductai.ai"
            style={{ fontSize: 13, fontWeight: 600, color: "#fff", background: "#4f46e5", borderRadius: 8, padding: "9px 18px", textDecoration: "none", whiteSpace: "nowrap" }}
          >
            Get started free →
          </a>
        </div>
      </div>
    </div>
  )
}

export default function SharePage() {
  const { token } = useParams<{ token: string }>()
  const [payload, setPayload] = useState<SharePayload | null>(null)
  const [error, setError]     = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

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

  const shell: React.CSSProperties = {
    minHeight: "100vh", background: "#f5f4f2",
    fontFamily: "'Inter', ui-sans-serif, system-ui, sans-serif",
    WebkitFontSmoothing: "antialiased",
    display: "flex", alignItems: "center", justifyContent: "center",
  }

  if (loading) return <div style={shell}><span style={{ fontSize: 13, color: "#a8a29e" }}>Loading…</span></div>

  if (error) return (
    <div style={shell}>
      <div style={{ textAlign: "center" }}>
        <div style={{ fontSize: 36, marginBottom: 14 }}>🔗</div>
        <div style={{ fontSize: 16, fontWeight: 700, color: "#1c1917", marginBottom: 6 }}>Link unavailable</div>
        <div style={{ fontSize: 13, color: "#78716c", marginBottom: 20 }}>{error}</div>
        <a href="https://conductai.ai" style={{ fontSize: 13, fontWeight: 600, color: "#4f46e5", textDecoration: "none" }}>conductai.ai →</a>
      </div>
    </div>
  )

  if (!payload) return null

  if (payload.resource_type === "session_report") {
    return <SessionReportView data={payload.data as SessionReportData} expiresAt={payload.expires_at} />
  }

  return <div style={shell}><span style={{ fontSize: 13, color: "#78716c" }}>Unknown resource type.</span></div>
}
