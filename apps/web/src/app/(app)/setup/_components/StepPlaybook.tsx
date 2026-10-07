"use client"

import { inputStyle, FEATURED_PLAYBOOKS, PIPELINE_BLOCKS, ShieldIcon, BlockChip } from "./shared"

// ── Step 4 — Install playbook ─────────────────────────────────────────────────

export interface StepPlaybookProps {
  selectedPlaybook: string
  setSelectedPlaybook: (name: string) => void
}

export function StepPlaybook({ selectedPlaybook, setSelectedPlaybook }: StepPlaybookProps) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18, maxWidth: 560 }}>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
        <div>
          <div style={{ fontSize: 12.5, fontWeight: 600, color: "var(--text-2)", marginBottom: 6 }}>Project name</div>
          <input style={inputStyle} defaultValue="DevOps" />
        </div>
        <div>
          <div style={{ fontSize: 12.5, fontWeight: 600, color: "var(--text-2)", marginBottom: 6 }}>Repository</div>
          <input
            style={{
              ...inputStyle,
              fontFamily: "ui-monospace, 'JetBrains Mono', 'SF Mono', Menlo, monospace",
              fontSize: 13,
            }}
            defaultValue="conductai/api"
          />
        </div>
      </div>

      <div>
        <div style={{ fontSize: 12.5, fontWeight: 600, color: "var(--text-2)", marginBottom: 9 }}>Choose a starter playbook</div>
        <div style={{ display: "flex", flexDirection: "column", gap: 9 }}>
          {FEATURED_PLAYBOOKS.map(p => {
            const sel = selectedPlaybook === p.name
            return (
              <div
                key={p.name}
                onClick={() => setSelectedPlaybook(p.name)}
                style={{
                  padding: "13px 15px",
                  display: "flex",
                  alignItems: "center",
                  gap: 13,
                  cursor: "pointer",
                  borderRadius: 14,
                  border: `1px solid ${sel ? "var(--accent-ring)" : "var(--border)"}`,
                  background: sel ? "var(--accent-weak)" : "var(--surface)",
                  transition: "border-color .15s, background .15s",
                }}
              >
                <span
                  style={{
                    width: 17,
                    height: 17,
                    borderRadius: "50%",
                    border: `2px solid ${sel ? "var(--accent)" : "var(--border-2)"}`,
                    display: "grid",
                    placeItems: "center",
                    flexShrink: 0,
                    transition: "border-color .15s",
                  }}
                >
                  {sel && (
                    <span
                      style={{
                        width: 8,
                        height: 8,
                        borderRadius: "50%",
                        background: "var(--accent)",
                      }}
                    />
                  )}
                </span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontWeight: 600, fontSize: 14, color: "var(--text)" }}>{p.name}</div>
                  <div style={{ fontSize: 12, color: "var(--text-3)" }}>{p.desc}</div>
                </div>
                <span
                  style={{
                    fontFamily: "ui-monospace, 'JetBrains Mono', 'SF Mono', Menlo, monospace",
                    fontSize: 11,
                    color: "var(--text-muted)",
                    flexShrink: 0,
                  }}
                >
                  {p.blocks} blocks
                </span>
              </div>
            )
          })}
        </div>
      </div>

      <div
        style={{
          padding: "11px 14px",
          display: "flex",
          alignItems: "center",
          gap: 10,
          borderRadius: 14,
          border: "1px solid var(--border)",
          background: "var(--surface-2)",
        }}
      >
        <span style={{ color: "var(--accent-text)", flexShrink: 0 }}>
          <ShieldIcon size={16} />
        </span>
        <span style={{ fontSize: 12.5, color: "var(--text-3)" }}>
          This project will be{" "}
          <strong style={{ color: "var(--text-2)" }}>guarded automatically</strong> — every run passes through your spend caps and policies.
        </span>
      </div>
    </div>
  )
}

// ── Right panel ───────────────────────────────────────────────────────────────

export function PipelinePanel({ step }: { step: number }) {
  return (
    <div
      style={{
        background: "var(--surface-2)",
        borderLeft: "1px solid var(--border)",
        position: "relative",
        overflow: "hidden",
        display: "flex",
        flexDirection: "column",
        justifyContent: "center",
        padding: 44,
      }}
    >
      {/* Dot-grid background */}
      <div
        style={{
          position: "absolute",
          inset: 0,
          backgroundImage: "radial-gradient(var(--bg-grid) 1.2px, transparent 1.2px)",
          backgroundSize: "22px 22px",
          opacity: 0.7,
          pointerEvents: "none",
        }}
      />

      <div style={{ position: "relative" }}>
        <div
          style={{
            fontSize: 10.5,
            fontWeight: 700,
            letterSpacing: ".14em",
            textTransform: "uppercase",
            color: "var(--text-muted)",
            marginBottom: 6,
          }}
        >
          How a guarded run flows
        </div>
        <div style={{ fontSize: 12.5, color: "var(--text-muted)", marginBottom: 16 }}>
          Guard sits inside every pipeline — by default.
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 0 }}>
          {PIPELINE_BLOCKS.map((b, i) => {
            const hot = b.type === "guard" && step === 3
            return (
              <div key={b.type}>
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 11,
                    padding: "11px 13px",
                    borderRadius: 14,
                    border: `1px solid ${hot ? "var(--accent-ring)" : "var(--border)"}`,
                    background: "var(--surface)",
                    boxShadow: hot ? "var(--shadow-md)" : "none",
                    transition: "border-color .2s, box-shadow .2s",
                  }}
                >
                  <BlockChip type={b.type} label={b.label} hot={hot} />
                  <span style={{ fontSize: 13, fontWeight: 500, color: "var(--text)" }}>{b.text}</span>
                </div>
                {i < PIPELINE_BLOCKS.length - 1 && (
                  <div
                    style={{
                      width: 2,
                      height: 12,
                      background: "var(--border-2)",
                      margin: "0 0 0 26px",
                    }}
                  />
                )}
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
