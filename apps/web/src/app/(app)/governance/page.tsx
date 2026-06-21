"use client"

import AppShell from "@/components/AppShell"

export default function GovernancePage() {
  return (
    <AppShell>
      <div style={{ padding: "24px 28px", maxWidth: 1280, margin: "0 auto" }}>
        <header style={{ marginBottom: 24 }}>
          <h1 style={{ fontSize: 22, fontWeight: 600, margin: 0, color: "var(--text-1)" }}>
            Governance
          </h1>
          <p style={{ fontSize: 13, color: "var(--text-3)", margin: "4px 0 0" }}>
            One outcome surface for engineering, security, and finance — ROI, behavioral insights, compliance proof.
          </p>
        </header>

        {/* AI Narrative Strip — placeholder, real LLM-generated paragraph lands in 750e */}
        <section style={{
          border: "1px solid var(--border)",
          borderRadius: 8,
          padding: "16px 18px",
          background: "var(--surface-2)",
          marginBottom: 20,
        }}>
          <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: ".08em", textTransform: "uppercase", color: "var(--text-muted)", marginBottom: 6 }}>
            This week in plain English
          </div>
          <p style={{ fontSize: 14, lineHeight: 1.55, color: "var(--text-2)", margin: 0 }}>
            Narrative summary not yet generated. The daily LLM job will fill this in once analytics data is flowing.
          </p>
        </section>

        {/* KPI cards — placeholders, real data lands in 750b */}
        <section style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 20 }}>
          {["AI ROI", "Spend (7d)", "Risk trend", "Compliance"].map(label => (
            <div key={label} style={{
              border: "1px solid var(--border)",
              borderRadius: 8,
              padding: "14px 16px",
              background: "var(--surface-1)",
            }}>
              <div style={{ fontSize: 11, color: "var(--text-muted)", letterSpacing: ".06em", textTransform: "uppercase" }}>
                {label}
              </div>
              <div style={{ fontSize: 24, fontWeight: 600, color: "var(--text-1)", marginTop: 6 }}>—</div>
              <div style={{ fontSize: 11, color: "var(--text-3)", marginTop: 4 }}>Pending data</div>
            </div>
          ))}
        </section>

        {/* Framework matrix — placeholder, real data lands in 750c */}
        <section style={{
          border: "1px solid var(--border)",
          borderRadius: 8,
          padding: 18,
          background: "var(--surface-1)",
        }}>
          <div style={{ fontSize: 14, fontWeight: 600, color: "var(--text-1)", marginBottom: 12 }}>
            Framework coverage
          </div>
          <div style={{ fontSize: 13, color: "var(--text-3)" }}>
            Multi-framework matrix renders here once rules are installed and the `/governance/frameworks` endpoint ships (750c).
          </div>
        </section>
      </div>
    </AppShell>
  )
}
