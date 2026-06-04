"use client"

import { useState, useEffect, useCallback, useRef } from "react"
import { useAuth } from "@clerk/nextjs"
import {
  SERVICE_DETECTION,
  affectedServices,
  type ServiceFieldDef,
  type ServiceDetection,
} from "@/lib/service-key-map"

interface Environment {
  id: string
  name: string
  created_at: string
  allowed_hosts?: string[] | null
  connectedServices?: string[]
}

interface Credential {
  handle: string
  service: string
  auth_method: string
  fields: string[]
}

interface FieldDef {
  key: string
  label: string
  placeholder: string
  secret?: boolean
  optional?: boolean
}

interface ServiceDef {
  value: string
  label: string
  description: string
  color: string
  abbr: string
  fields: FieldDef[]
}

const SERVICES: ServiceDef[] = [
  {
    value: "github", label: "GitHub", abbr: "GH",
    description: "Create branches and pull requests",
    color: "bg-stone-900 text-white",
    fields: [{ key: "token", label: "Personal access token", placeholder: "ghp_… or gho_…" }],
  },
  {
    value: "slack", label: "Slack", abbr: "SL",
    description: "Post messages and approval requests",
    color: "bg-purple-600 text-white",
    fields: [{ key: "token", label: "Bot token", placeholder: "xoxb-…" }],
  },
  {
    value: "linear", label: "Linear", abbr: "LN",
    description: "Fetch issues and post comments",
    color: "bg-indigo-600 text-white",
    fields: [{ key: "api_key", label: "API key", placeholder: "lin_api_…" }],
  },
  {
    value: "digitalocean", label: "DigitalOcean", abbr: "DO",
    description: "Provision and manage droplets",
    color: "bg-blue-500 text-white",
    fields: [{ key: "token", label: "Personal access token", placeholder: "dop_v1_…" }],
  },
  {
    value: "anthropic", label: "Anthropic", abbr: "AI",
    description: "Bring your own API key — agents use this instead of the platform key",
    color: "bg-amber-600 text-white",
    fields: [{ key: "api_key", label: "API key", placeholder: "sk-ant-…" }],
  },
  {
    value: "email", label: "Email", abbr: "EM",
    description: "Send notifications via Resend or SendGrid",
    color: "bg-emerald-600 text-white",
    fields: [
      { key: "resend_api_key", label: "Resend API key (recommended)", placeholder: "re_…" },
      { key: "sendgrid_api_key", label: "SendGrid API key (alternative)", placeholder: "SG.…", optional: true },
      { key: "from_name", label: "From name", placeholder: "e.g. Acme Alerts", secret: false },
      { key: "from_email", label: "From email address", placeholder: "e.g. alerts@acme.com", secret: false },
    ],
  },
]

interface Integration {
  id: string
  name: string
  desc: string
  credKey: string
  color: string
}

const INTEGRATIONS: Integration[] = [
  { id: "github",       name: "GitHub",       desc: "Clone, branch, push, open & merge PRs, add secrets",  credKey: "GITHUB_TOKEN",         color: "#1c1917" },
  { id: "slack",        name: "Slack",        desc: "Post messages, DMs, approval buttons, Guard alerts",   credKey: "SLACK_BOT_TOKEN",      color: "#7c3aed" },
  { id: "linear",       name: "Linear",       desc: "Create and update issues, post comments, query cycles", credKey: "LINEAR_API_KEY",       color: "#5b5bd6" },
  { id: "vercel",       name: "Vercel",       desc: "Deploy projects, manage env vars, read deployment logs", credKey: "VERCEL_TOKEN",        color: "#1c1917" },
  { id: "railway",      name: "Railway",      desc: "Deploy services, run migrations, read metrics",         credKey: "RAILWAY_TOKEN",       color: "#7c4dff" },
  { id: "digitalocean", name: "DigitalOcean", desc: "Provision droplets, manage DNS and databases",          credKey: "DIGITALOCEAN_TOKEN",  color: "#0ea5e9" },
  { id: "email",        name: "Email",        desc: "Send transactional and alert emails via Resend",        credKey: "RESEND_API_KEY",      color: "#059669" },
]

function EyeIcon({ open }: { open: boolean }) {
  return open ? (
    <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" />
    </svg>
  ) : (
    <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
    </svg>
  )
}

function getWorkspaceId(): string | null {
  if (typeof document === "undefined") return null
  return document.cookie.split("; ").find(r => r.startsWith("delegator_project_id="))?.split("=")[1] ?? null
}

export default function EnvironmentsManager({ isAdmin = true }: { isAdmin?: boolean }) {
  const clerkEnabled = !!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY
  if (clerkEnabled) return <EnvironmentsManagerWithAuth isAdmin={isAdmin} />
  return <EnvironmentsManagerInner getToken={null} isAdmin={isAdmin} />
}

function EnvironmentsManagerWithAuth({ isAdmin }: { isAdmin: boolean }) {
  const { getToken } = useAuth()
  return <EnvironmentsManagerInner getToken={getToken} isAdmin={isAdmin} />
}

interface EnvVar { key: string; value: string; handle?: string }

function EnvironmentsManagerInner({ getToken, isAdmin }: { getToken: (() => Promise<string | null>) | null; isAdmin: boolean }) {
  const [environments, setEnvironments] = useState<Environment[]>([])
  const [listLoading, setListLoading] = useState(true)
  const [active, setActive] = useState(0)
  const [envVars, setEnvVars] = useState<EnvVar[]>([])
  const [varsLoading, setVarsLoading] = useState(false)
  const [settingKey, setSettingKey] = useState<string | null>(null)
  const [inputValue, setInputValue] = useState("")
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState("")
  const [showNewEnv, setShowNewEnv] = useState(false)
  const [newEnvName, setNewEnvName] = useState("")
  const [creatingEnv, setCreatingEnv] = useState(false)
  const [viewingDetail, setViewingDetail] = useState(false)
  const loadingRef = useRef(false)

  const buildHeaders = useCallback(async (contentType = false): Promise<Record<string, string>> => {
    const headers: Record<string, string> = {}
    if (contentType) headers["Content-Type"] = "application/json"
    if (getToken) {
      const token = await getToken()
      if (token) headers["Authorization"] = `Bearer ${token}`
    }
    const ws = getWorkspaceId()
    if (ws) headers["X-Workspace-Id"] = ws
    return headers
  }, [getToken])

  const loadEnvironments = useCallback(async () => {
    if (loadingRef.current) return
    loadingRef.current = true
    try {
      const headers = await buildHeaders()
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/environments`, { headers })
      if (!res.ok) return
      const envs: Environment[] = await res.json()
      const enriched = await Promise.all(envs.map(async env => {
        try {
          const r = await fetch(
            `${process.env.NEXT_PUBLIC_API_URL}/credentials/by-environment/${env.id}`,
            { headers }
          )
          const creds: Credential[] = r.ok ? await r.json() : []
          return { ...env, connectedServices: creds.map(c => c.service) }
        } catch { return env }
      }))
      setEnvironments(enriched.map((env, i) => ({ ...env, allowed_hosts: envs[i]?.allowed_hosts ?? null })))
    } catch { /* silent */ }
    finally {
      loadingRef.current = false
      setListLoading(false)
    }
  }, [buildHeaders])

  const loadVarsForEnv = useCallback(async (envId: string) => {
    setVarsLoading(true)
    try {
      const headers = await buildHeaders()
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/credentials/env-vars/${envId}`, { headers })
      if (res.ok) setEnvVars(await res.json())
      else setEnvVars([])
    } catch { setEnvVars([]) }
    finally { setVarsLoading(false) }
  }, [buildHeaders])

  useEffect(() => { loadEnvironments() }, [loadEnvironments])

  useEffect(() => {
    if (environments.length > 0) {
      loadVarsForEnv(environments[active]?.id ?? "")
    }
  }, [active, environments, loadVarsForEnv])

  async function addEnv() {
    const name = newEnvName.trim()
    if (!name) return
    setCreatingEnv(true)
    try {
      const headers = await buildHeaders(true)
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/environments`, {
        method: "POST", headers, body: JSON.stringify({ name }),
      })
      if (res.ok) {
        setNewEnvName("")
        setShowNewEnv(false)
        await loadEnvironments()
      }
    } catch { /* silent */ }
    finally { setCreatingEnv(false) }
  }

  async function saveCredential(credKey: string, value: string) {
    const env = environments[active]
    if (!env) return
    setSaving(true)
    setSaveError("")
    try {
      const updated = envVars.some(v => v.key === credKey)
        ? envVars.map(v => v.key === credKey ? { ...v, value } : v)
        : [...envVars, { key: credKey, value }]
      const headers = await buildHeaders(true)
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/credentials/env-vars/${env.id}`, {
        method: "PUT", headers,
        body: JSON.stringify(updated.map(v => ({ key: v.key, value: v.value }))),
      })
      if (!res.ok) throw new Error("Save failed")
      setEnvVars(updated)
      setSettingKey(null)
      setInputValue("")
    } catch { setSaveError("Save failed") }
    finally { setSaving(false) }
  }

  function isSet(credKey: string): boolean {
    return envVars.some(v => v.key === credKey && v.value)
  }

  function maskedFor(credKey: string): string {
    const v = envVars.find(v => v.key === credKey)
    if (!v?.value) return ""
    return v.value.length > 8 ? v.value.slice(0, 4) + "••••••••" : "••••••••"
  }

  const env = environments[active]
  const required = INTEGRATIONS.length
  const setCount = INTEGRATIONS.filter(it => isSet(it.credKey)).length
  const missing = required - setCount

  if (listLoading) {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {[1, 2].map(i => (
          <div key={i} style={{ height: 64, borderRadius: 12, background: "var(--surface-2)", border: "1px solid var(--border)", opacity: 0.7 }} />
        ))}
      </div>
    )
  }

  if (viewingDetail && env) {
    return (
      <EnvironmentDetail
        environment={env}
        buildHeaders={buildHeaders}
        onBack={() => setViewingDetail(false)}
        isAdmin={isAdmin}
      />
    )
  }

  if (environments.length === 0) {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: 14, alignItems: "center", padding: "40px 0", textAlign: "center" }}>
        <p style={{ fontSize: 13, color: "var(--text-muted)" }}>No environments yet.</p>
        {showNewEnv ? (
          <div style={{ display: "flex", gap: 8, maxWidth: 380 }}>
            <input autoFocus value={newEnvName} onChange={e => setNewEnvName(e.target.value)}
              onKeyDown={e => { if (e.key === "Enter") addEnv(); if (e.key === "Escape") { setShowNewEnv(false); setNewEnvName("") } }}
              placeholder="e.g. Production"
              style={{ flex: 1, border: "1px solid var(--border)", borderRadius: 9, padding: "8px 12px", fontSize: 13.5, color: "var(--text)", background: "var(--surface)", outline: "none" }} />
            <button onClick={addEnv} disabled={creatingEnv || !newEnvName.trim()} className="btn btn-primary btn-sm" style={{ opacity: (creatingEnv || !newEnvName.trim()) ? 0.4 : 1 }}>
              {creatingEnv ? "Creating…" : "Create"}
            </button>
            <button onClick={() => { setShowNewEnv(false); setNewEnvName("") }} className="btn btn-ghost btn-sm">Cancel</button>
          </div>
        ) : (
          <button className="btn btn-primary btn-sm" onClick={() => setShowNewEnv(true)}>+ New environment</button>
        )}
      </div>
    )
  }

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 14, flexWrap: "wrap" }}>
        {environments.map((e, i) => {
          const on = i === active
          const miss = 0
          return (
            <button key={e.name} onClick={() => setActive(i)} className="chip" style={{ height: 32, cursor: "pointer", fontWeight: 600, gap: 7,
              background: on ? "var(--accent-weak)" : "var(--surface)", borderColor: on ? "var(--accent-ring)" : "var(--border)", color: on ? "var(--accent-text)" : "var(--text-2)" }}>
              {e.name}
              {miss > 0 && <span style={{ fontSize: 10, fontWeight: 700, color: "var(--warn)", background: "var(--warn-bg)", borderRadius: 20, padding: "0 6px", lineHeight: "15px" }}>{miss} needed</span>}
            </button>
          )
        })}
        {showNewEnv ? (
          <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
            <input autoFocus value={newEnvName} onChange={e => setNewEnvName(e.target.value)}
              onKeyDown={e => { if (e.key === "Enter") addEnv(); if (e.key === "Escape") { setShowNewEnv(false); setNewEnvName("") } }}
              placeholder="Environment name"
              style={{ height: 32, border: "1px solid var(--border)", borderRadius: 8, padding: "0 10px", fontSize: 13, color: "var(--text)", background: "var(--surface)", outline: "none" }} />
            <button onClick={addEnv} disabled={creatingEnv || !newEnvName.trim()} className="btn btn-primary btn-sm" style={{ height: 32, opacity: (creatingEnv || !newEnvName.trim()) ? 0.4 : 1 }}>
              {creatingEnv ? "…" : "Create"}
            </button>
            <button onClick={() => { setShowNewEnv(false); setNewEnvName("") }} className="btn btn-ghost btn-sm" style={{ height: 32 }}>✕</button>
          </div>
        ) : (
          <button onClick={() => setShowNewEnv(true)} className="btn btn-ghost btn-sm" style={{ height: 32 }}>+ New environment</button>
        )}
      </div>

      {env && (
        <div className="card" style={{ padding: "12px 16px", marginBottom: 16, display: "flex", alignItems: "center", gap: 12,
          background: missing > 0 ? "var(--warn-bg)" : "var(--surface-2)", borderColor: missing > 0 ? "var(--warn-bd)" : "var(--border)" }}>
          <div style={{ flex: 1, fontSize: 12.5, color: "var(--text-2)", lineHeight: 1.5 }}>
            {missing > 0
              ? <><b style={{ color: "var(--text)" }}>{env.name}</b> needs {missing} of {required} variables filled in.</>
              : <><b style={{ color: "var(--text)" }}>{env.name}</b> has all {required} credentials set.</>}
          </div>
          <span className="mono" style={{ fontSize: 12, fontWeight: 700, color: missing > 0 ? "var(--warn)" : "var(--ok)", flexShrink: 0 }}>{setCount}/{required} set</span>
          <button onClick={() => setViewingDetail(true)} className="btn btn-ghost btn-sm" style={{ flexShrink: 0, fontSize: 12 }}>
            Manage variables →
          </button>
        </div>
      )}

      {varsLoading ? (
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {[1, 2, 3].map(i => <div key={i} style={{ height: 112, borderRadius: 12, background: "var(--surface-2)", border: "1px solid var(--border)", opacity: 0.7 }} />)}
        </div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(330px, 1fr))", gap: 14 }}>
          {INTEGRATIONS.map(it => {
            const on = isSet(it.credKey)
            const isEditing = settingKey === it.credKey
            return (
              <div key={it.id} className="card" style={{ padding: "16px 18px", borderColor: on ? "var(--ok-bd)" : "var(--border)" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 12 }}>
                  <div style={{ width: 38, height: 38, borderRadius: 10, background: it.color, color: "#fff", display: "grid", placeItems: "center", fontWeight: 700, fontSize: 15, flexShrink: 0 }}>{it.name[0]}</div>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontWeight: 650, fontSize: 14.5 }}>{it.name}</div>
                    <div style={{ fontSize: 11.5, color: "var(--text-muted)" }}>{it.desc}</div>
                  </div>
                  {on
                    ? <span className="sbadge ok"><span className="dot" style={{ background: "var(--ok)" }} />Set</span>
                    : <span className="sbadge warn"><span className="dot" style={{ background: "var(--warn)" }} />Needs value</span>}
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 10px", borderRadius: 8, background: "var(--surface-2)", border: "1px solid var(--border)", marginBottom: 12 }}>
                  <span className="mono" style={{ fontSize: 12, fontWeight: 600, color: "var(--text-2)" }}>{it.credKey}</span>
                  <span className="mono" style={{ marginLeft: "auto", fontSize: 11.5, color: on ? "var(--text-3)" : "var(--warn)" }}>
                    {on ? (maskedFor(it.credKey) || "••••••••") : "not set"}
                  </span>
                </div>
                {isEditing ? (
                  <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                    <input
                      autoFocus
                      type="password"
                      value={inputValue}
                      onChange={e => setInputValue(e.target.value)}
                      onKeyDown={e => { if (e.key === "Enter") saveCredential(it.credKey, inputValue); if (e.key === "Escape") { setSettingKey(null); setInputValue("") } }}
                      placeholder={`Paste ${it.credKey}`}
                      className="mono"
                      style={{ fontSize: 12, padding: "7px 10px", borderRadius: 7, border: "1px solid var(--border)", background: "var(--surface)", color: "var(--text)", width: "100%", boxSizing: "border-box" }}
                    />
                    {saveError && <span style={{ fontSize: 11.5, color: "var(--err)" }}>{saveError}</span>}
                    <div style={{ display: "flex", gap: 7 }}>
                      <button className="btn btn-primary btn-sm" style={{ flex: 1, justifyContent: "center" }} onClick={() => saveCredential(it.credKey, inputValue)} disabled={saving || !inputValue.trim()}>
                        {saving ? "Saving…" : "Save"}
                      </button>
                      <button className="btn btn-ghost btn-sm" onClick={() => { setSettingKey(null); setInputValue(""); setSaveError("") }}>Cancel</button>
                    </div>
                  </div>
                ) : (
                  <button className={"btn btn-sm " + (on ? "btn-ghost" : "btn-primary")} style={{ width: "100%", justifyContent: "center" }}
                    onClick={() => { setSettingKey(it.credKey); setInputValue("") }}>
                    {on ? "Rotate value" : `Set ${it.credKey}`}
                  </button>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Test connections panel
// ---------------------------------------------------------------------------

type TestResult = { ok: boolean; detail: string } | "testing" | "idle"

function resultDetail(body: Record<string, unknown>): string {
  if (body.user  && body.team)  return `${body.team} · ${body.user}`
  if (body.user)                return `Connected as ${body.user}`
  if (body.email)               return `Connected: ${body.email}`
  return "Connected"
}

function TestConnectionsPanel({
  vars,
  buildHeaders,
  autoRun,
}: {
  vars: EnvVar[]
  buildHeaders: (contentType?: boolean) => Promise<Record<string, string>>
  autoRun?: { services: string[]; at: number } | null
}) {
  const [manualSel, setManualSel] = useState<Record<string, Record<string, string>>>({})
  const [results,   setResults]   = useState<Record<string, TestResult>>({})

  const varKeys = vars.filter(v => v.value).map(v => v.key)

  useEffect(() => {
    if (!autoRun?.services.length) return
    const t = setTimeout(() => {
      autoRun.services.forEach(service => {
        const svc = SERVICE_DETECTION[service]
        if (!svc) return
        const hasAnyKey = svc.fields.some(f => f.envKeys.some(k => vars.some(v => v.key === k && v.value)))
        if (hasAnyKey) runTest(service)
      })
    }, 200)
    return () => clearTimeout(t)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoRun?.at])

  function autoKey(field: ServiceFieldDef): string {
    return field.envKeys.find(k => vars.some(v => v.key === k && v.value)) ?? ""
  }

  function selectedKey(service: string, field: ServiceFieldDef): string {
    return manualSel[service]?.[field.fieldKey] ?? autoKey(field)
  }

  function varValue(key: string): string {
    return vars.find(v => v.key === key)?.value ?? ""
  }

  function buildCreds(service: string): Record<string, string> {
    const svc = SERVICE_DETECTION[service]
    const creds: Record<string, string> = {}
    for (const field of svc.fields) {
      const key = selectedKey(service, field)
      const val = varValue(key)
      if (val) creds[field.fieldKey] = val
    }
    return creds
  }

  function isTestable(service: string): boolean {
    const svc = SERVICE_DETECTION[service]
    if (service === "email") {
      const creds = buildCreds(service)
      return !!(creds.resend_api_key || creds.sendgrid_api_key)
    }
    return svc.fields.filter(f => f.required).every(f => !!varValue(selectedKey(service, f)))
  }

  async function runTest(service: string) {
    setResults(prev => ({ ...prev, [service]: "testing" }))
    try {
      const headers = await buildHeaders(true)
      const res  = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/credentials/test`, {
        method: "POST", headers,
        body: JSON.stringify({ service, credentials: buildCreds(service) }),
      })
      const body = await res.json() as Record<string, unknown>
      if (body.ok) {
        setResults(prev => ({ ...prev, [service]: { ok: true, detail: resultDetail(body) } }))
      } else {
        setResults(prev => ({ ...prev, [service]: { ok: false, detail: (body.error as string) ?? "Connection failed" } }))
      }
    } catch {
      setResults(prev => ({ ...prev, [service]: { ok: false, detail: "Request failed" } }))
    }
  }

  return (
    <div style={{ marginTop: 24 }}>
      <div style={{ marginBottom: 12 }}>
        <p style={{ fontSize: 13.5, fontWeight: 600, color: "var(--text)" }}>Test connections</p>
        <p style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 3 }}>
          Verify each credential is valid. Values are sent directly to the provider — nothing is stored or re-encrypted.
        </p>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))", gap: 12 }}>
        {Object.entries(SERVICE_DETECTION).map(([service, svc]) => {
          const result  = results[service] ?? "idle"
          const testing = result === "testing"
          const ok      = result !== "idle" && result !== "testing" && result.ok
          const err     = result !== "idle" && result !== "testing" && !result.ok
          const testable = isTestable(service)

          return (
            <div key={service} className="card" style={{ padding: "14px 16px", display: "flex", flexDirection: "column", gap: 10,
              borderColor: ok ? "var(--ok-bd)" : err ? "var(--err-bd)" : "var(--border)",
              background: ok ? "var(--ok-bg, var(--surface-2))" : err ? "var(--err-bg)" : "var(--surface)" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ width: 28, height: 28, borderRadius: 7, background: svc.color.includes("bg-stone") ? "#1c1917" : svc.color.includes("bg-purple") ? "#7c3aed" : svc.color.includes("bg-indigo") ? "#4f46e5" : svc.color.includes("bg-blue") ? "#2563eb" : svc.color.includes("bg-emerald") ? "#059669" : svc.color.includes("bg-amber") ? "#d97706" : "#4f46e5",
                  color: "#fff", display: "grid", placeItems: "center", fontSize: 10, fontWeight: 700, flexShrink: 0 }}>
                  {svc.abbr}
                </span>
                <span style={{ fontSize: 13.5, fontWeight: 600, color: "var(--text)" }}>{svc.label}</span>
                {ok && <span className="sbadge ok" style={{ marginLeft: "auto" }}>✓ OK</span>}
                {err && <span className="sbadge err" style={{ marginLeft: "auto" }}>✗ Failed</span>}
              </div>

              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {svc.fields.map(field => {
                  const auto    = autoKey(field)
                  const current = selectedKey(service, field)
                  const hasVal  = !!varValue(current)

                  return (
                    <div key={field.fieldKey}>
                      <p style={{ fontSize: 10.5, color: "var(--text-muted)", marginBottom: 3 }}>{field.label}</p>
                      {auto && manualSel[service]?.[field.fieldKey] === undefined ? (
                        <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                          <span className="mono" style={{ fontSize: 10.5, background: "var(--surface-2)", color: "var(--text-3)", padding: "2px 6px", borderRadius: 4, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: 140 }}>
                            {auto}
                          </span>
                          <button onClick={() => setManualSel(prev => ({ ...prev, [service]: { ...prev[service], [field.fieldKey]: "" } }))}
                            style={{ fontSize: 10, color: "var(--text-muted)", background: "none", border: "none", cursor: "pointer" }} title="Change">✎</button>
                        </div>
                      ) : (
                        <select value={current}
                          onChange={e => setManualSel(prev => ({ ...prev, [service]: { ...prev[service], [field.fieldKey]: e.target.value } }))}
                          className="mono"
                          style={{ width: "100%", fontSize: 10.5, border: `1px ${hasVal ? "solid" : "dashed"} var(--border)`, borderRadius: 5, padding: "3px 6px", color: hasVal ? "var(--text-2)" : "var(--text-muted)", background: "var(--surface)", outline: "none" }}>
                          <option value="">— pick a var —</option>
                          {varKeys.map(k => <option key={k} value={k}>{k}</option>)}
                        </select>
                      )}
                    </div>
                  )
                })}
              </div>

              {ok  && <p style={{ fontSize: 11.5, color: "var(--ok)", fontWeight: 500 }}>{(result as {ok:boolean;detail:string}).detail}</p>}
              {err && <p style={{ fontSize: 11.5, color: "var(--err)" }}>{(result as {ok:boolean;detail:string}).detail}</p>}

              <button onClick={() => runTest(service)} disabled={!testable || testing}
                className={testable && !testing ? "btn btn-primary btn-sm" : "btn btn-ghost btn-sm"}
                style={{ marginTop: "auto", justifyContent: "center", opacity: (!testable || testing) ? 0.5 : 1, cursor: (!testable || testing) ? "not-allowed" : "pointer" }}>
                {testing ? "Testing…" : testable ? "Test connection" : "Add key to test"}
              </button>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Environment detail — simple key-value env var editor
// ---------------------------------------------------------------------------

function EnvironmentDetail({
  environment,
  buildHeaders,
  onBack,
  isAdmin,
}: {
  environment: Environment
  buildHeaders: (contentType?: boolean) => Promise<Record<string, string>>
  onBack: () => void
  isAdmin: boolean
}) {
  const [vars, setVars] = useState<EnvVar[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState("")
  const [saved, setSaved] = useState(false)
  const [showValues, setShowValues] = useState<Record<number, boolean>>({})
  const [newKey, setNewKey] = useState("")
  const [newValue, setNewValue] = useState("")
  const [showNew, setShowNew] = useState(false)
  const [showPaste, setShowPaste] = useState(false)
  const [pasteText, setPasteText] = useState("")
  const [testTrigger, setTestTrigger] = useState<{ services: string[]; at: number } | null>(null)
  const [confirmVarIndex, setConfirmVarIndex] = useState<number | null>(null)
  const [confirmVarValue, setConfirmVarValue] = useState("")
  const [confirmHost, setConfirmHost] = useState<string | null>(null)
  const [confirmHostValue, setConfirmHostValue] = useState("")

  function triggerTestsForKeys(keys: string[]) {
    const services = affectedServices(keys)
    if (services.length) setTestTrigger({ services, at: Date.now() })
  }

  const [hosts, setHosts] = useState<string[]>(environment.allowed_hosts ?? [])
  const [hostInput, setHostInput] = useState("")
  const [hostSaving, setHostSaving] = useState(false)

  async function saveHosts(updated: string[]) {
    setHostSaving(true)
    try {
      const headers = await buildHeaders(true)
      await fetch(`${process.env.NEXT_PUBLIC_API_URL}/environments/${environment.id}`, {
        method: "PATCH", headers,
        body: JSON.stringify({ allowed_hosts: updated.length > 0 ? updated : null }),
      })
    } finally { setHostSaving(false) }
  }

  function addHost() {
    const h = hostInput.trim().toLowerCase().replace(/^https?:\/\//, "").replace(/\/.*$/, "")
    if (!h || hosts.includes(h)) { setHostInput(""); return }
    const updated = [...hosts, h]
    setHosts(updated)
    setHostInput("")
    saveHosts(updated)
  }

  function removeHost(h: string) {
    const updated = hosts.filter(x => x !== h)
    setHosts(updated)
    saveHosts(updated)
  }

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const headers = await buildHeaders()
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/credentials/env-vars/${environment.id}`, { headers })
      if (res.ok) setVars(await res.json())
    } finally { setLoading(false) }
  }, [buildHeaders, environment.id])

  useEffect(() => { load() }, [load])

  async function saveAll(updated: EnvVar[], changedKeys?: string[]) {
    setSaving(true); setError(""); setSaved(false)
    try {
      const headers = await buildHeaders(true)
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/credentials/env-vars/${environment.id}`, {
        method: "PUT", headers,
        body: JSON.stringify(updated.map(v => ({ key: v.key, value: v.value }))),
      })
      if (!res.ok) throw new Error("Save failed")
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
      if (changedKeys?.length) triggerTestsForKeys(changedKeys)
    } catch { setError("Save failed") } finally { setSaving(false) }
  }

  function updateVar(i: number, field: "key" | "value", val: string) {
    setVars(prev => prev.map((v, idx) => idx === i ? { ...v, [field]: val } : v))
  }

  function removeVar(i: number) {
    const updated = vars.filter((_, idx) => idx !== i)
    setVars(updated)
    setConfirmVarIndex(null)
    setConfirmVarValue("")
    saveAll(updated)
  }

  function addVar() {
    if (!newKey.trim()) return
    const key = newKey.trim()
    const updated = [...vars, { key, value: newValue }]
    setVars(updated)
    setNewKey(""); setNewValue(""); setShowNew(false)
    saveAll(updated)
    triggerTestsForKeys([key])
  }

  function parseEnvText(text: string): EnvVar[] {
    const parsed: EnvVar[] = []
    for (const raw of text.split("\n")) {
      const line = raw.trim()
      if (!line || line.startsWith("#")) continue
      const eq = line.indexOf("=")
      if (eq === -1) continue
      const key = line.slice(0, eq).trim()
      const value = line.slice(eq + 1).trim().replace(/^["']|["']$/g, "")
      if (key) parsed.push({ key, value })
    }
    return parsed
  }

  function handlePasteImport() {
    const parsed = parseEnvText(pasteText)
    if (parsed.length === 0) { setError("No KEY=value pairs found — check the format."); return }
    const merged = [...vars]
    for (const p of parsed) {
      const existing = merged.findIndex(v => v.key === p.key)
      if (existing >= 0) merged[existing] = p
      else merged.push(p)
    }
    setVars(merged)
    saveAll(merged)
    triggerTestsForKeys(parsed.map(p => p.key))
    setPasteText("")
    setShowPaste(false)
  }

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 22 }}>
        <button onClick={onBack} style={{ color: "var(--text-muted)", background: "none", border: "none", fontSize: 18, cursor: "pointer", lineHeight: 1 }}>←</button>
        <span style={{ width: 32, height: 32, borderRadius: 8, background: "var(--accent-weak)", color: "var(--accent-text)", display: "grid", placeItems: "center", fontSize: 11, fontWeight: 700, flexShrink: 0 }}>
          {environment.name.slice(0, 2).toUpperCase()}
        </span>
        <div>
          <h2 style={{ fontSize: 14, fontWeight: 600, color: "var(--text)", margin: 0 }}>{environment.name}</h2>
          <p style={{ fontSize: 11.5, color: "var(--text-muted)", margin: 0 }}>{vars.length} variable{vars.length !== 1 ? "s" : ""}</p>
        </div>
        <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 8 }}>
          <button onClick={() => { setShowPaste(p => !p); setError("") }} className="btn btn-ghost btn-sm">Paste .env</button>
          <button onClick={() => saveAll(vars)} disabled={saving} className="btn btn-primary btn-sm" style={{ opacity: saving ? 0.5 : 1 }}>
            {saving ? "Saving…" : saved ? "Saved ✓" : "Save"}
          </button>
        </div>
      </div>

      {showPaste && (
        <div className="card" style={{ padding: "14px 16px", background: "var(--surface-2)", marginBottom: 14, display: "flex", flexDirection: "column", gap: 10 }}>
          <p style={{ fontSize: 12, color: "var(--text-2)" }}>Paste the contents of your <code className="mono" style={{ fontSize: 11 }}>.env</code> file. Existing keys will be overwritten; new keys will be added.</p>
          <textarea
            autoFocus
            value={pasteText}
            onChange={e => setPasteText(e.target.value)}
            placeholder={"GITHUB_TOKEN=ghp_...\nANTHROPIC_API_KEY=sk-ant-...\nSLACK_BOT_TOKEN=xoxb-..."}
            rows={7}
            className="mono"
            style={{ width: "100%", fontSize: 12, color: "var(--text)", border: "1px solid var(--border)", borderRadius: 8, padding: "10px 12px", background: "var(--surface)", outline: "none", resize: "vertical", boxSizing: "border-box" }}
          />
          <div style={{ display: "flex", gap: 8 }}>
            <button onClick={handlePasteImport} className="btn btn-primary btn-sm">Import</button>
            <button onClick={() => { setShowPaste(false); setPasteText(""); setError("") }} className="btn btn-ghost btn-sm">Cancel</button>
          </div>
        </div>
      )}

      {error && <p style={{ marginBottom: 10, fontSize: 12, color: "var(--err)" }}>{error}</p>}

      <div className="card" style={{ padding: 0, overflow: "hidden" }}>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr auto", borderBottom: "1px solid var(--border)", padding: "8px 16px", background: "var(--surface-2)" }}>
          <p className="eyebrow">Key</p>
          <p className="eyebrow">Value</p>
          <p style={{ width: 64 }} />
        </div>

        {loading ? (
          <p style={{ fontSize: 13, color: "var(--text-muted)", padding: "20px 16px" }}>Loading…</p>
        ) : vars.length === 0 ? (
          <p style={{ fontSize: 13, color: "var(--text-muted)", padding: "20px 16px" }}>No variables yet — add one or import a .env file.</p>
        ) : (
          vars.map((v, i) => (
            <div key={i} style={{ display: "grid", gridTemplateColumns: "1fr 1fr auto", borderBottom: i < vars.length - 1 ? "1px solid var(--border)" : "none", padding: "8px 16px", alignItems: "center" }}>
              <input
                value={v.key}
                onChange={e => updateVar(i, "key", e.target.value)}
                onBlur={() => saveAll(vars, [v.key])}
                className="mono"
                style={{ fontSize: 12, color: "var(--text)", background: "transparent", border: "none", outline: "none", width: "100%", paddingRight: 16 }}
              />
              <div style={{ position: "relative", display: "flex", alignItems: "center" }}>
                <input
                  type={showValues[i] ? "text" : "password"}
                  value={v.value}
                  onChange={e => updateVar(i, "value", e.target.value)}
                  onBlur={() => saveAll(vars, [v.key])}
                  className="mono"
                  style={{ fontSize: 12, color: "var(--text-2)", background: "transparent", border: "none", outline: "none", width: "100%", paddingRight: 28 }}
                />
                <button type="button" onClick={() => setShowValues(prev => ({ ...prev, [i]: !prev[i] }))}
                  style={{ position: "absolute", right: 4, color: "var(--text-muted)", background: "none", border: "none", cursor: "pointer", display: "flex", alignItems: "center" }}>
                  <EyeIcon open={!!showValues[i]} />
                </button>
              </div>
              {confirmVarIndex === i ? (
                <div style={{ minWidth: 230, display: "flex", flexDirection: "column", gap: 6, alignItems: "flex-end" }}>
                  <p style={{ margin: 0, fontSize: 11, color: "var(--err)", textAlign: "right" }}>
                    Type <strong>{v.key || "key"}</strong> to remove.
                  </p>
                  <div style={{ display: "flex", gap: 6, width: "100%" }}>
                    <input
                      value={confirmVarValue}
                      onChange={e => setConfirmVarValue(e.target.value)}
                      onKeyDown={e => {
                        if (e.key === "Enter" && confirmVarValue === v.key) removeVar(i)
                        if (e.key === "Escape") { setConfirmVarIndex(null); setConfirmVarValue("") }
                      }}
                      placeholder={v.key || "key"}
                      className="mono"
                      style={{ flex: 1, minWidth: 0, fontSize: 11.5, border: "1px solid var(--err-bd, #fecaca)", borderRadius: 8, padding: "5px 8px", outline: "none" }}
                    />
                    <button
                      onClick={() => removeVar(i)}
                      disabled={confirmVarValue !== v.key}
                      className="btn btn-sm"
                      style={{ background: "var(--err)", color: "#fff", border: "none", opacity: confirmVarValue !== v.key ? 0.4 : 1 }}
                    >
                      Remove
                    </button>
                    <button
                      onClick={() => { setConfirmVarIndex(null); setConfirmVarValue("") }}
                      className="btn btn-ghost btn-sm"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              ) : (
                <button
                  onClick={() => { setConfirmVarIndex(i); setConfirmVarValue("") }}
                  style={{ fontSize: 12, color: "var(--text-muted)", background: "none", border: "none", cursor: "pointer", width: 64, textAlign: "right" }}
                >
                  Remove
                </button>
              )}
            </div>
          ))
        )}

        {isAdmin && (showNew ? (
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr auto", borderTop: "1px solid var(--border)", padding: "8px 16px", alignItems: "center", background: "var(--surface-2)" }}>
            <input autoFocus value={newKey} onChange={e => setNewKey(e.target.value)} onKeyDown={e => e.key === "Enter" && addVar()}
              placeholder="VARIABLE_NAME" className="mono"
              style={{ fontSize: 12, color: "var(--text)", background: "transparent", border: "none", outline: "none", width: "100%", paddingRight: 16 }} />
            <input value={newValue} onChange={e => setNewValue(e.target.value)} onKeyDown={e => e.key === "Enter" && addVar()}
              placeholder="value" type="password" className="mono"
              style={{ fontSize: 12, color: "var(--text-2)", background: "transparent", border: "none", outline: "none", width: "100%", paddingRight: 16 }} />
            <div style={{ display: "flex", gap: 8, width: 64, justifyContent: "flex-end" }}>
              <button onClick={addVar} style={{ fontSize: 12, fontWeight: 600, color: "var(--ok)", background: "none", border: "none", cursor: "pointer" }}>Add</button>
              <button onClick={() => { setShowNew(false); setNewKey(""); setNewValue("") }} style={{ fontSize: 12, color: "var(--text-muted)", background: "none", border: "none", cursor: "pointer" }}>✕</button>
            </div>
          </div>
        ) : (
          <div style={{ borderTop: "1px solid var(--border)", padding: "8px 16px" }}>
            <button onClick={() => setShowNew(true)} style={{ fontSize: 12.5, color: "var(--text-muted)", background: "none", border: "none", cursor: "pointer" }}>
              + Add Environment Variable
            </button>
          </div>
        ))}
      </div>

      {!loading && <TestConnectionsPanel vars={vars} buildHeaders={buildHeaders} autoRun={testTrigger} />}

      <div style={{ marginTop: 24 }}>
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 8 }}>
          <div>
            <p style={{ fontSize: 13.5, fontWeight: 600, color: "var(--text)" }}>Allowed hosts</p>
            <p style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 3 }}>Leave empty for unrestricted outbound access. Use <code className="mono" style={{ fontSize: 11 }}>*.example.com</code> for subdomains. Applies to integration blocks only.</p>
          </div>
          {hostSaving && <span style={{ fontSize: 10.5, color: "var(--text-muted)" }}>Saving…</span>}
        </div>
        <div className="card" style={{ padding: "12px 16px", display: "flex", flexDirection: "column", gap: 10 }}>
          {hosts.length > 0 && (
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
              {hosts.map(h => (
                <span key={h} style={{ display: "inline-flex", alignItems: "center", gap: 5, fontSize: 12, background: "var(--warn-bg)", color: "var(--warn)", border: "1px solid var(--warn-bd)", padding: "3px 10px", borderRadius: 20 }} className="mono">
                  {h}
                  {isAdmin && (
                    <button
                      onClick={() => { setConfirmHost(h); setConfirmHostValue("") }}
                      style={{ color: "var(--warn)", background: "none", border: "none", cursor: "pointer", lineHeight: 1, fontSize: 13 }}
                    >
                      ×
                    </button>
                  )}
                </span>
              ))}
            </div>
          )}

          {isAdmin && confirmHost && (
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <p style={{ margin: 0, fontSize: 12, color: "var(--err)" }}>
                Type <strong>{confirmHost}</strong> to remove allowed host.
              </p>
              <div style={{ display: "flex", gap: 8 }}>
                <input
                  value={confirmHostValue}
                  onChange={e => setConfirmHostValue(e.target.value)}
                  onKeyDown={e => {
                    if (e.key === "Enter" && confirmHostValue === confirmHost) {
                      removeHost(confirmHost)
                      setConfirmHost(null)
                      setConfirmHostValue("")
                    }
                    if (e.key === "Escape") { setConfirmHost(null); setConfirmHostValue("") }
                  }}
                  placeholder={confirmHost}
                  className="mono"
                  style={{ flex: 1, fontSize: 12, border: "1px solid var(--err-bd, #fecaca)", borderRadius: 8, padding: "6px 10px", outline: "none" }}
                />
                <button
                  className="btn btn-sm"
                  onClick={() => {
                    if (confirmHostValue !== confirmHost) return
                    removeHost(confirmHost)
                    setConfirmHost(null)
                    setConfirmHostValue("")
                  }}
                  disabled={confirmHostValue !== confirmHost}
                  style={{ background: "var(--err)", color: "#fff", border: "none", opacity: confirmHostValue !== confirmHost ? 0.4 : 1 }}
                >
                  Remove
                </button>
                <button className="btn btn-ghost btn-sm" onClick={() => { setConfirmHost(null); setConfirmHostValue("") }}>
                  Cancel
                </button>
              </div>
            </div>
          )}
          {isAdmin && (
            <div style={{ display: "flex", gap: 8 }}>
              <input
                value={hostInput}
                onChange={e => setHostInput(e.target.value)}
                onKeyDown={e => { if (e.key === "Enter") { e.preventDefault(); addHost() } }}
                placeholder="e.g. api.github.com or *.slack.com"
                className="mono"
                style={{ flex: 1, fontSize: 12, color: "var(--text)", border: "1px solid var(--border)", borderRadius: 8, padding: "7px 10px", background: "var(--surface)", outline: "none" }}
              />
              <button onClick={addHost} disabled={!hostInput.trim()} className="btn btn-ghost btn-sm" style={{ opacity: hostInput.trim() ? 1 : 0.4 }}>Add</button>
            </div>
          )}
          {hosts.length === 0 && !isAdmin && (
            <p style={{ fontSize: 12, color: "var(--text-muted)" }}>No restrictions — agents can reach any host.</p>
          )}
        </div>
      </div>
    </div>
  )
}
