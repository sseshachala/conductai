"use client"

import { inputStyle, INTEGRATIONS, CheckIcon, ShieldIcon, LockIcon } from "./shared"

// ── Step 1 — Workspace ────────────────────────────────────────────────────────

export interface StepWorkspaceProps {
  orgName: string
  setOrgName: (v: string) => void
  wsName: string
  setWsName: (v: string) => void
}

export function StepWorkspace({ orgName, setOrgName, wsName, setWsName }: StepWorkspaceProps) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18, maxWidth: 460 }}>
      <div>
        <div style={{ fontSize: 12.5, fontWeight: 600, color: "var(--text-2)", marginBottom: 6 }}>Organisation</div>
        <input
          style={inputStyle}
          value={orgName}
          onChange={e => setOrgName(e.target.value)}
          placeholder="Your organisation"
        />
      </div>
      <div>
        <div style={{ fontSize: 12.5, fontWeight: 600, color: "var(--text-2)", marginBottom: 6 }}>Workspace name</div>
        <input
          style={inputStyle}
          value={wsName}
          onChange={e => setWsName(e.target.value)}
          placeholder="Engineering"
        />
      </div>
      <div>
        <div style={{ fontSize: 12.5, fontWeight: 600, color: "var(--text-2)", marginBottom: 6 }}>Data region</div>
        <div style={{ ...inputStyle, background: "var(--surface-2)", color: "var(--text-3)" }}>
          US · Oregon
        </div>
      </div>
    </div>
  )
}

// ── Step 2 — Connect tools ────────────────────────────────────────────────────

export interface StepToolsProps {
  connected: Record<string, boolean>
  toggle: (id: string) => void
}

export function StepTools({ connected, toggle }: StepToolsProps) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      {INTEGRATIONS.map(it => {
        const on = connected[it.id]
        return (
          <div
            key={it.id}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 14,
              padding: "13px 16px",
              borderRadius: 14,
              border: `1px solid ${on ? "var(--accent-ring)" : "var(--border)"}`,
              background: "var(--surface)",
              transition: "border-color .15s",
            }}
          >
            <div
              style={{
                width: 36,
                height: 36,
                borderRadius: 10,
                background: it.color,
                color: "#fff",
                display: "grid",
                placeItems: "center",
                flexShrink: 0,
                fontWeight: 700,
                fontSize: 14,
              }}
            >
              {it.name[0]}
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontWeight: 600, fontSize: 14, color: "var(--text)" }}>{it.name}</div>
              <div style={{ fontSize: 12, color: "var(--text-3)" }}>{it.desc}</div>
            </div>
            <button
              onClick={() => toggle(it.id)}
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 5,
                height: 30,
                padding: "0 11px",
                borderRadius: 8,
                fontSize: 12.5,
                fontWeight: 550,
                border: "1px solid",
                cursor: "pointer",
                fontFamily: "inherit",
                transition: "background .14s, border-color .14s",
                ...(on
                  ? {
                      background: "var(--surface)",
                      borderColor: "var(--ok-bd, #a7f3d0)",
                      color: "var(--ok)",
                    }
                  : {
                      background: "var(--accent)",
                      borderColor: "var(--accent)",
                      color: "#fff",
                    }),
              }}
            >
              {on ? (
                <>
                  <CheckIcon size={14} />
                  Connected
                </>
              ) : (
                "Connect"
              )}
            </button>
          </div>
        )
      })}
    </div>
  )
}

// ── Step 3 — Guard ────────────────────────────────────────────────────────────

export interface StepGuardProps {
  hardCap: boolean
  setHardCap: (v: boolean) => void
  teamBudget: string
  setTeamBudget: (v: string) => void
  perDevLimit: string
  setPerDevLimit: (v: string) => void
}

export function StepGuard({ hardCap, setHardCap, teamBudget, setTeamBudget, perDevLimit, setPerDevLimit }: StepGuardProps) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16, maxWidth: 540 }}>
      {/* ConductGuard enabled card */}
      <div
        style={{
          padding: "15px 18px",
          display: "flex",
          alignItems: "center",
          gap: 13,
          borderRadius: 14,
          border: "1px solid var(--accent-ring)",
          background: "var(--accent-weak)",
        }}
      >
        <span
          style={{
            width: 38,
            height: 38,
            borderRadius: 10,
            background: "var(--accent)",
            color: "#fff",
            display: "grid",
            placeItems: "center",
            flexShrink: 0,
          }}
        >
          <ShieldIcon size={19} />
        </span>
        <div style={{ flex: 1 }}>
          <div style={{ fontWeight: 650, fontSize: 14.5, color: "var(--text)" }}>ConductGuard is enabled</div>
          <div style={{ fontSize: 12.5, color: "var(--text-3)" }}>
            Governs every project, agent run, and developer&apos;s Claude Code / Codex / Cursor calls.
          </div>
        </div>
        <span
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 6,
            height: 22,
            padding: "0 9px",
            borderRadius: 7,
            fontSize: 11.5,
            fontWeight: 600,
            color: "var(--ok)",
            background: "var(--ok-bg)",
          }}
        >
          <CheckIcon size={13} />
          On
        </span>
      </div>

      {/* Spend limits card */}
      <div
        style={{
          padding: "16px 18px",
          borderRadius: 14,
          border: "1px solid var(--border)",
          background: "var(--surface)",
        }}
      >
        <div
          style={{
            fontSize: 10.5,
            fontWeight: 700,
            letterSpacing: ".14em",
            textTransform: "uppercase",
            color: "var(--text-muted)",
            marginBottom: 14,
          }}
        >
          Set your spend limits
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
          <div>
            <div style={{ fontSize: 12.5, fontWeight: 600, color: "var(--text-2)", marginBottom: 6 }}>Team monthly budget (USD)</div>
            <input
              type="number"
              min={0}
              step={10}
              style={inputStyle}
              value={teamBudget}
              onChange={e => setTeamBudget(e.target.value)}
              placeholder="500"
            />
          </div>
          <div>
            <div style={{ fontSize: 12.5, fontWeight: 600, color: "var(--text-2)", marginBottom: 6 }}>Default per-developer limit (USD)</div>
            <input
              type="number"
              min={0}
              step={5}
              style={inputStyle}
              value={perDevLimit}
              onChange={e => setPerDevLimit(e.target.value)}
              placeholder="75"
            />
          </div>
        </div>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 12,
            marginTop: 16,
            paddingTop: 14,
            borderTop: "1px solid var(--border)",
          }}
        >
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: 600, fontSize: 13.5, color: "var(--text)" }}>Hard cap at 100%</div>
            <div style={{ fontSize: 12, color: "var(--text-3)" }}>Block all sessions once the budget is reached.</div>
          </div>
          <button
            type="button"
            onClick={() => setHardCap(!hardCap)}
            aria-checked={hardCap}
            role="switch"
            style={{
              width: 40,
              height: 23,
              borderRadius: 20,
              background: hardCap ? "var(--accent)" : "var(--border-2)",
              border: "none",
              position: "relative",
              cursor: "pointer",
              flexShrink: 0,
              transition: "background .15s",
            }}
          >
            <span
              style={{
                position: "absolute",
                top: 2.5,
                left: hardCap ? 19.5 : 2.5,
                width: 18,
                height: 18,
                borderRadius: "50%",
                background: "#fff",
                transition: "left .15s",
                boxShadow: "var(--shadow-sm)",
              }}
            />
          </button>
        </div>
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 9, fontSize: 12.5, color: "var(--text-muted)" }}>
        <LockIcon />
        Developers sync policies with{" "}
        <code
          style={{
            fontFamily: "ui-monospace, 'JetBrains Mono', 'SF Mono', Menlo, monospace",
            color: "var(--text-2)",
            fontSize: 12.5,
          }}
        >
          conduct guard sync
        </code>{" "}
        — within 60s.
      </div>
    </div>
  )
}
