"use client"

import { useState, useEffect, useCallback } from "react"
import { useRouter } from "next/navigation"
import { useAuth } from "@clerk/nextjs"
import { useWorkspace } from "@/lib/WorkspaceContext"

const API = process.env.NEXT_PUBLIC_API_URL ?? ""

// ── Data ─────────────────────────────────────────────────────────────────────

const ONB_STEPS = ["Workspace", "Connect tools", "Guard", "Install playbook"] as const

const INTEGRATIONS = [
  { id: "github",  name: "GitHub",   desc: "Repos, issues, PRs, webhooks", color: "#1c1917" },
  { id: "slack",   name: "Slack",    desc: "Messages, DMs, approvals",      color: "#4a154b" },
  // ponytail: Linear/Vercel/Railway deferred — re-enable when /integrations supports them (#858 slice 2 redesigns this whole step)
  // { id: "linear",  name: "Linear",   desc: "Issues, projects, labels",            color: "#5b5bd6" },
  // { id: "vercel",  name: "Vercel",   desc: "Deployments, logs, domains",          color: "#000000" },
  // { id: "railway", name: "Railway",  desc: "Services, deployments, environments", color: "#0f172a" },
] as const

const FEATURED_PLAYBOOKS = [
  { name: "Autopilot + Approval", desc: "Issue → branch → fix → draft PR → Slack approval → merge", blocks: 9 },
  { name: "Autopilot Full",       desc: "Issue → branch → fix → tests → auto-merge if CI passes",  blocks: 7 },
  { name: "PR Review Bot",        desc: "PR opened → review comments → approve or request changes", blocks: 5 },
] as const

const PIPELINE_BLOCKS = [
  { type: "trigger",  label: "TRIGGER",    text: "GitHub issue labelled ai-ready" },
  { type: "memory",   label: "MEMORY",     text: "Recall what the agent learned here" },
  { type: "brain",    label: "AGENT STEP", text: "Claude reads, clones, writes the fix" },
  { type: "guard",    label: "GUARD",      text: "Guard: spend cap + policy check" },
  { type: "tool",     label: "ACTION",     text: "Open a draft pull request" },
  { type: "approval", label: "APPROVAL",   text: "Slack: Approve / Reject" },
  { type: "output",   label: "NOTIFY",     text: "Post result to #eng" },
] as const

const STEP_HEADS: Record<number, [string, string]> = {
  1: [
    "Set up your workspace",
    "Workspaces live inside your organisation. Each one keeps its own projects, runs, memory, and credentials.",
  ],
  2: [
    "Connect your tools",
    "Agents act through real integrations. Credentials are encrypted at rest and scoped per environment.",
  ],
  3: [
    "Guard protects everything",
    "Guard is on by default for the whole workspace — you don't install it per project.",
  ],
  4: [
    "Create a project & install a playbook",
    "Your first project is created here. Guard governs it automatically — no extra setup.",
  ],
}

// ── Icons ────────────────────────────────────────────────────────────────────

function ArrowIcon() {
  return (
    <svg width={16} height={16} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M5 12h14M12 5l7 7-7 7" />
    </svg>
  )
}

function CheckIcon({ size = 16 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <polyline points="20 6 9 17 4 12" />
    </svg>
  )
}

function ShieldIcon({ size = 19 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
    </svg>
  )
}

function LockIcon() {
  return (
    <svg width={14} height={14} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
      <path d="M7 11V7a5 5 0 0 1 10 0v4" />
    </svg>
  )
}

function FlowIcon() {
  return (
    <svg width={17} height={17} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="5" cy="12" r="2" />
      <circle cx="19" cy="5" r="2" />
      <circle cx="19" cy="19" r="2" />
      <path d="M7 12h3l2-7h2M7 12h3l2 7h2" />
    </svg>
  )
}

// ── Shared input style ────────────────────────────────────────────────────────

const inputStyle: React.CSSProperties = {
  width: "100%",
  height: 40,
  padding: "0 13px",
  borderRadius: 9,
  border: "1px solid var(--border)",
  background: "var(--surface)",
  color: "var(--text)",
  fontSize: 14,
  outline: "none",
  fontFamily: "inherit",
}

// ── Block chip helper ─────────────────────────────────────────────────────────

function BlockChip({ type, label, hot }: { type: string; label: string; hot: boolean }) {
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        height: 20,
        padding: "0 7px",
        borderRadius: 20,
        fontSize: 9.5,
        letterSpacing: ".08em",
        fontWeight: 700,
        border: "1px solid",
        background: `var(--blk-${type}-bg)`,
        borderColor: hot && type === "guard" ? "var(--accent-ring)" : `var(--blk-${type}-bd)`,
        color: `var(--blk-${type}-tx)`,
        transition: "border-color .2s",
        flexShrink: 0,
      }}
    >
      {label}
    </span>
  )
}

// ── Step 1 — Workspace ────────────────────────────────────────────────────────

interface StepWorkspaceProps {
  orgName: string
  setOrgName: (v: string) => void
  wsName: string
  setWsName: (v: string) => void
}

function StepWorkspace({ orgName, setOrgName, wsName, setWsName }: StepWorkspaceProps) {
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

interface StepToolsProps {
  connected: Record<string, boolean>
  toggle: (id: string) => void
}

function StepTools({ connected, toggle }: StepToolsProps) {
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

interface StepGuardProps {
  hardCap: boolean
  setHardCap: (v: boolean) => void
  teamBudget: string
  setTeamBudget: (v: string) => void
  perDevLimit: string
  setPerDevLimit: (v: string) => void
}

function StepGuard({ hardCap, setHardCap, teamBudget, setTeamBudget, perDevLimit, setPerDevLimit }: StepGuardProps) {
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

// ── Step 4 — Install playbook ─────────────────────────────────────────────────

interface StepPlaybookProps {
  selectedPlaybook: string
  setSelectedPlaybook: (name: string) => void
}

function StepPlaybook({ selectedPlaybook, setSelectedPlaybook }: StepPlaybookProps) {
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

function PipelinePanel({ step }: { step: number }) {
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

// ── Main page component ───────────────────────────────────────────────────────

export default function SetupPage() {
  const router = useRouter()
  const { getToken } = useAuth()
  const { activeWorkspace, refresh: refreshWorkspaces } = useWorkspace()

  const [step, setStep] = useState(1)
  const [connected, setConnected] = useState<Record<string, boolean>>({
    github: false,
    slack: false,
  })
  const [hardCap, setHardCap] = useState(true)
  const [selectedPlaybook, setSelectedPlaybook] = useState<string>(FEATURED_PLAYBOOKS[0].name)

  // Slice 1: controlled state for Step 1 + Step 3
  const [orgId, setOrgId] = useState<string>("")
  const [orgName, setOrgName] = useState<string>("")
  const [wsName, setWsName] = useState<string>("")
  const [teamBudget, setTeamBudget] = useState<string>("500")
  const [perDevLimit, setPerDevLimit] = useState<string>("75")
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const authHeaders = useCallback(async (): Promise<Record<string, string>> => {
    const h: Record<string, string> = { "Content-Type": "application/json" }
    try {
      const token = await getToken?.()
      if (token) h["Authorization"] = `Bearer ${token}`
    } catch { /* unauthenticated dev mode */ }
    return h
  }, [getToken])

  // Initial load: org name + workspace name
  useEffect(() => {
    let cancelled = false
    async function load() {
      const h = await authHeaders()
      try {
        const orgRes = await fetch(`${API}/organizations`, { headers: h })
        if (orgRes.ok) {
          const orgs = await orgRes.json()
          const first = Array.isArray(orgs) ? orgs[0] : null
          if (first && !cancelled) {
            setOrgId(first.id ?? "")
            setOrgName(first.name ?? "")
          }
        }
      } catch { /* network error — leave defaults */ }
      if (activeWorkspace && !cancelled) setWsName(activeWorkspace.name ?? "")
    }
    load()
    return () => { cancelled = true }
  }, [authHeaders, activeWorkspace])

  const connectedCount = Object.values(connected).filter(Boolean).length

  function toggle(id: string) {
    setConnected(prev => ({ ...prev, [id]: !prev[id] }))
  }

  async function ensureOk(res: Response, label: string): Promise<void> {
    if (res.ok) return
    let detail = ""
    try { detail = (await res.json())?.detail ?? "" } catch { /* non-JSON body */ }
    throw new Error(`${label} failed (${res.status})${detail ? ": " + detail : ""}`)
  }

  async function saveStep1() {
    const h = await authHeaders()
    const wsId = activeWorkspace?.id
    if (orgId && orgName.trim()) {
      const r = await fetch(`${API}/organizations/${orgId}`, {
        method: "PATCH",
        headers: h,
        body: JSON.stringify({ name: orgName.trim() }),
      })
      await ensureOk(r, "Save organisation")
    }
    if (wsId && wsName.trim()) {
      const r = await fetch(`${API}/workspaces/${wsId}`, {
        method: "PATCH",
        headers: h,
        body: JSON.stringify({ name: wsName.trim() }),
      })
      await ensureOk(r, "Save workspace name")
      await refreshWorkspaces()
    }
  }

  async function saveStep3() {
    const h = await authHeaders()
    const wsId = activeWorkspace?.id
    if (!wsId) return
    const monthly = Number.parseFloat(teamBudget) || 0
    const perDev = Number.parseFloat(perDevLimit) || 0
    const r = await fetch(`${API}/guard/spend/budgets?workspace_id=${wsId}`, {
      method: "POST",
      headers: h,
      body: JSON.stringify({
        workspace_id: wsId,
        clerk_user_id: null,
        monthly_limit_usd: monthly,
        alert_threshold_pct: 80,
        hard_limit_usd: hardCap ? monthly : null,
        default_per_developer_usd: perDev,
      }),
    })
    await ensureOk(r, "Save Guard budget")
  }

  async function markSetupComplete() {
    const h = await authHeaders()
    await fetch(`${API}/me/setup-complete`, { method: "POST", headers: h })
  }

  async function next() {
    setError(null)
    setSaving(true)
    try {
      if (step === 1) await saveStep1()
      if (step === 3) await saveStep3()
      if (step < 4) {
        setStep(step + 1)
      } else {
        await markSetupComplete()
        router.push("/guard")
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed — please try again")
    } finally {
      setSaving(false)
    }
  }

  async function skip() {
    try { await markSetupComplete() } catch { /* still navigate */ }
    router.push("/guard")
  }

  function back() {
    setStep(Math.max(1, step - 1))
  }

  const [title, subtitle] = STEP_HEADS[step]
  const step1Required = orgName.trim().length === 0 || wsName.trim().length === 0
  const continueDisabled = saving || (step === 1 && step1Required) || (step === 2 && connectedCount === 0)

  return (
    <div
      style={{
        minHeight: "100vh",
        display: "grid",
        gridTemplateColumns: "minmax(0, 1fr) 432px",
      }}
    >
      {/* ── Left: form col ─────────────────────────────────────────────── */}
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          padding: "40px 56px",
          maxWidth: 740,
          margin: "0 auto",
          width: "100%",
        }}
      >
        {/* Brand */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 10,
            marginBottom: 38,
          }}
        >
          <div
            style={{
              width: 30,
              height: 30,
              borderRadius: 8,
              background: "var(--text)",
              color: "#fff",
              display: "grid",
              placeItems: "center",
              flexShrink: 0,
              boxShadow: "var(--shadow-sm)",
            }}
          >
            <FlowIcon />
          </div>
          <span style={{ fontWeight: 650, fontSize: 15.5, letterSpacing: "-.01em", color: "var(--text)" }}>
            Conduct
          </span>
        </div>

        {/* Progress bar */}
        <div style={{ display: "flex", gap: 10, marginBottom: 32 }}>
          {ONB_STEPS.map((label, i) => {
            const n = i + 1
            const active = n <= step
            return (
              <div
                key={n}
                style={{ flex: 1, cursor: "pointer" }}
                onClick={() => setStep(n)}
              >
                <div
                  style={{
                    height: 4,
                    borderRadius: 4,
                    background: active ? "var(--accent)" : "var(--border-2)",
                    marginBottom: 8,
                    transition: "background .2s",
                  }}
                />
                <div
                  style={{
                    fontSize: 11.5,
                    fontWeight: 600,
                    color: active ? "var(--text)" : "var(--text-muted)",
                  }}
                >
                  {label}
                </div>
              </div>
            )
          })}
        </div>

        {/* Step heading */}
        <div
          style={{
            fontSize: 10.5,
            fontWeight: 700,
            letterSpacing: ".14em",
            textTransform: "uppercase",
            color: "var(--text-muted)",
            marginBottom: 8,
          }}
        >
          Step {step} of 4
        </div>
        <h1
          style={{
            fontSize: 29,
            fontWeight: 700,
            letterSpacing: "-.025em",
            margin: "0 0 8px",
            color: "var(--text)",
          }}
        >
          {title}
        </h1>
        <p
          style={{
            color: "var(--text-3)",
            fontSize: 15,
            margin: "0 0 26px",
            maxWidth: 500,
            lineHeight: 1.5,
          }}
        >
          {subtitle}
        </p>

        {/* Step content */}
        <div style={{ flex: 1 }}>
          {step === 1 && <StepWorkspace orgName={orgName} setOrgName={setOrgName} wsName={wsName} setWsName={setWsName} />}
          {step === 2 && <StepTools connected={connected} toggle={toggle} />}
          {step === 3 && <StepGuard hardCap={hardCap} setHardCap={setHardCap} teamBudget={teamBudget} setTeamBudget={setTeamBudget} perDevLimit={perDevLimit} setPerDevLimit={setPerDevLimit} />}
          {step === 4 && (
            <StepPlaybook
              selectedPlaybook={selectedPlaybook}
              setSelectedPlaybook={setSelectedPlaybook}
            />
          )}
        </div>

        {error && (
          <div
            role="alert"
            style={{
              marginTop: 20,
              padding: "10px 14px",
              borderRadius: 10,
              border: "1px solid var(--danger-bd, #fecaca)",
              background: "var(--danger-bg, #fef2f2)",
              color: "var(--danger, #b91c1c)",
              fontSize: 13,
            }}
          >
            {error}
          </div>
        )}

        {/* Navigation */}
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 30 }}>
          {step > 1 && (
            <button
              onClick={back}
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 7,
                height: 36,
                padding: "0 15px",
                borderRadius: 9,
                fontSize: 13.5,
                fontWeight: 550,
                border: "1px solid var(--border)",
                color: "var(--text-2)",
                background: "var(--surface)",
                cursor: "pointer",
                fontFamily: "inherit",
                transition: "background .14s, border-color .14s",
              }}
            >
              Back
            </button>
          )}

          <button
            onClick={next}
            disabled={continueDisabled}
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 7,
              height: 36,
              padding: "0 15px",
              borderRadius: 9,
              fontSize: 13.5,
              fontWeight: 550,
              border: "1px solid transparent",
              background: "var(--accent)",
              color: "#fff",
              cursor: continueDisabled ? "not-allowed" : "pointer",
              opacity: continueDisabled ? 0.5 : 1,
              fontFamily: "inherit",
              transition: "background .14s",
            }}
          >
            {step === 4 ? (
              <>
                <CheckIcon size={16} />
                Finish setup
              </>
            ) : (
              <>
                Continue
                <ArrowIcon />
              </>
            )}
          </button>

          <button
            onClick={skip}
            style={{
              display: "inline-flex",
              alignItems: "center",
              height: 36,
              padding: "0 15px",
              borderRadius: 9,
              fontSize: 13.5,
              fontWeight: 550,
              border: "none",
              background: "transparent",
              color: "var(--text-3)",
              cursor: "pointer",
              marginLeft: "auto",
              fontFamily: "inherit",
              textDecoration: "underline",
              textUnderlineOffset: 3,
            }}
          >
            Skip setup
          </button>
        </div>
      </div>

      {/* ── Right: pipeline panel ───────────────────────────────────────── */}
      <PipelinePanel step={step} />
    </div>
  )
}
