"use client"

import { apiUrl } from "@/lib/auth/runtime"


import { useState, useEffect, useCallback } from "react"
import { useRouter } from "next/navigation"
import { useAuth } from "@/lib/auth/client"
import { useWorkspace } from "@/lib/WorkspaceContext"
import {
  ONB_STEPS,
  FEATURED_PLAYBOOKS,
  STEP_HEADS,
  ArrowIcon,
  CheckIcon,
  FlowIcon,
} from "./_components/shared"
import { StepWorkspace, StepTools, StepGuard } from "./_components/steps"
import { StepPlaybook, PipelinePanel } from "./_components/StepPlaybook"

import { invalidate } from "@/lib/api/sharedCache"
const API = apiUrl() ?? ""

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
      invalidate(`${API}/organizations`)
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
        router.push("/theguard")
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed — please try again")
    } finally {
      setSaving(false)
    }
  }

  async function skip() {
    try { await markSetupComplete() } catch { /* still navigate */ }
    router.push("/theguard")
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
