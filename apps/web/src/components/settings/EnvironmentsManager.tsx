"use client"

import { useState, useEffect, useCallback } from "react"
import { useAuth } from "@clerk/nextjs"

interface Environment {
  id: string
  name: string
  created_at: string
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

function EnvironmentsManagerInner({ getToken, isAdmin }: { getToken: (() => Promise<string | null>) | null; isAdmin: boolean }) {
  const [environments, setEnvironments] = useState<Environment[]>([])
  const [selected, setSelected] = useState<Environment | null>(null)
  const [newName, setNewName] = useState("")
  const [creating, setCreating] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null)
  const [deleting, setDeleting] = useState<string | null>(null)
  const [listError, setListError] = useState("")

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
    try {
      const headers = await buildHeaders()
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/environments`, { headers })
      if (!res.ok) return
      const envs: Environment[] = await res.json()
      // Fetch credentials for each environment to show connected services inline
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
      setEnvironments(enriched)
    } catch { /* silent */ }
  }, [buildHeaders])

  useEffect(() => { loadEnvironments() }, [loadEnvironments])

  async function handleCreate() {
    const name = newName.trim()
    if (!name) { setListError("Environment name is required"); return }
    setCreating(true)
    setListError("")
    try {
      const headers = await buildHeaders(true)
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/environments`, {
        method: "POST", headers, body: JSON.stringify({ name }),
      })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error(body.detail || "Failed to create environment")
      }
      setNewName("")
      await loadEnvironments()
    } catch (e: unknown) {
      setListError(e instanceof Error ? e.message : "Failed to create environment")
    } finally {
      setCreating(false)
    }
  }

  async function handleDelete(id: string) {
    setDeleting(id)
    setListError("")
    try {
      const headers = await buildHeaders()
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/environments/${id}`, {
        method: "DELETE", headers,
      })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        setListError(body.detail ?? "Failed to delete environment")
        setConfirmDelete(null)
        return
      }
      setEnvironments(prev => prev.filter(e => e.id !== id))
      setConfirmDelete(null)
    } catch {
      setListError("Failed to delete environment")
    } finally {
      setDeleting(null)
    }
  }

  function formatDate(iso: string) {
    try {
      return new Date(iso).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" })
    } catch { return iso }
  }

  // Drill into an environment
  if (selected) {
    return (
      <EnvironmentDetail
        environment={selected}
        buildHeaders={buildHeaders}
        onBack={() => setSelected(null)}
        isAdmin={isAdmin}
      />
    )
  }

  return (
    <div className="space-y-3">
      {environments.map(env => (
        <div key={env.id} className="rounded-xl border border-stone-200 bg-white">
          <div className="flex items-center justify-between px-4 py-3.5">
            <button
              className="flex items-center gap-3 flex-1 text-left"
              onClick={() => setSelected(env)}
            >
              <span className="w-9 h-9 rounded-lg text-xs font-bold flex items-center justify-center shrink-0 bg-violet-100 text-violet-700">
                {env.name.slice(0, 2).toUpperCase()}
              </span>
              <div>
                <p className="text-sm font-medium text-stone-900">{env.name}</p>
                {env.connectedServices && env.connectedServices.length > 0 ? (
                  <div className="flex items-center gap-1 mt-1 flex-wrap">
                    {env.connectedServices.map(svc => (
                      <span key={svc} className="text-[10px] font-medium bg-emerald-50 text-emerald-700 border border-emerald-100 px-1.5 py-0.5 rounded-full">
                        {svc}
                      </span>
                    ))}
                  </div>
                ) : (
                  <p className="text-xs text-stone-400 mt-0.5">No integrations yet · click to add</p>
                )}
              </div>
            </button>

            <div className="flex items-center gap-2 ml-4">
              {isAdmin && (confirmDelete === env.id ? (
                  <>
                    <span className="text-xs text-stone-500">Delete?</span>
                    <button
                      onClick={() => handleDelete(env.id)}
                      disabled={deleting === env.id}
                      className="text-xs font-medium text-red-600 hover:text-red-800 disabled:opacity-50 transition-colors"
                    >
                      {deleting === env.id ? "Deleting…" : "Confirm"}
                    </button>
                    <button
                      onClick={() => setConfirmDelete(null)}
                      className="text-xs text-stone-400 hover:text-stone-600 transition-colors"
                    >
                      Cancel
                    </button>
                  </>
                ) : (
                  <button
                    onClick={e => { e.stopPropagation(); setConfirmDelete(env.id) }}
                    className="text-xs text-stone-400 hover:text-red-500 transition-colors"
                  >
                    Delete
                  </button>
                ))}
              <span className="text-stone-300 text-sm">→</span>
            </div>
          </div>
        </div>
      ))}

      {/* Create new environment — admin only */}
      {isAdmin && <div className="rounded-xl border border-dashed border-stone-200 bg-white px-4 py-4">
        <p className="text-xs font-medium text-stone-500 mb-2">New environment</p>
        <div className="flex gap-2">
          <input
            type="text"
            value={newName}
            onChange={e => { setNewName(e.target.value); setListError("") }}
            onKeyDown={e => e.key === "Enter" && handleCreate()}
            placeholder="e.g. staging, production, customer-A"
            className="flex-1 border border-stone-200 rounded-lg px-3 py-2 text-sm text-stone-900 focus:outline-none focus:ring-2 focus:ring-violet-200"
          />
          <button
            onClick={handleCreate}
            disabled={creating || !newName.trim()}
            className="rounded-lg bg-stone-900 px-4 py-2 text-sm font-medium text-white hover:bg-stone-700 disabled:opacity-50 transition-colors"
          >
            {creating ? "Creating…" : "Create"}
          </button>
        </div>
        {listError && <p className="text-xs text-red-500 mt-2">{listError}</p>}
      </div>}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Environment detail — credential management for one environment
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
  const [credentials, setCredentials] = useState<Credential[]>([])
  const [openService, setOpenService] = useState<string | null>(null)
  const [fieldValues, setFieldValues] = useState<Record<string, string>>({})
  const [saving, setSaving] = useState(false)
  const [deleting, setDeleting] = useState<string | null>(null)
  const [error, setError] = useState("")

  const loadCredentials = useCallback(async () => {
    try {
      const headers = await buildHeaders()
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/credentials/by-environment/${environment.id}`,
        { headers }
      )
      if (res.ok) setCredentials(await res.json())
    } catch { /* silent */ }
  }, [buildHeaders, environment.id])

  useEffect(() => { loadCredentials() }, [loadCredentials])

  const connectedServices = new Set(credentials.map(c => c.service))

  function toggleService(svc: string) {
    if (openService === svc) { setOpenService(null); setError("") }
    else { setOpenService(svc); setFieldValues({}); setError("") }
  }

  async function handleSave(svc: ServiceDef) {
    const credObj: Record<string, string> = {}
    for (const f of svc.fields) {
      const val = fieldValues[f.key]?.trim() ?? ""
      if (!val && !f.optional) { setError(`${f.label} is required`); return }
      if (val) credObj[f.key] = val
    }
    setSaving(true)
    setError("")
    try {
      const headers = await buildHeaders(true)
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/credentials`, {
        method: "POST",
        headers,
        body: JSON.stringify({
          service: svc.value,
          handle: `${svc.value}_${environment.name.toLowerCase().replace(/\s+/g, "_")}`,
          credentials: credObj,
          environment_id: environment.id,
        }),
      })
      if (!res.ok) throw new Error("Save failed")
      await loadCredentials()
      setOpenService(null)
      setFieldValues({})
    } catch {
      setError("Failed to save — check your token and try again")
    } finally {
      setSaving(false)
    }
  }

  async function handleRemove(handle: string) {
    setDeleting(handle)
    try {
      const headers = await buildHeaders()
      await fetch(`${process.env.NEXT_PUBLIC_API_URL}/credentials/${handle}`, {
        method: "DELETE", headers,
      })
      setCredentials(prev => prev.filter(c => c.handle !== handle))
    } finally {
      setDeleting(null)
    }
  }

  return (
    <div>
      {/* Header */}
      <div className="flex items-center gap-3 mb-6">
        <button
          onClick={onBack}
          className="text-stone-400 hover:text-stone-700 text-sm transition-colors"
        >
          ←
        </button>
        <span className="w-8 h-8 rounded-lg text-xs font-bold flex items-center justify-center bg-violet-100 text-violet-700">
          {environment.name.slice(0, 2).toUpperCase()}
        </span>
        <div>
          <h2 className="text-sm font-semibold text-stone-900">{environment.name}</h2>
          <p className="text-xs text-stone-400">Credentials scoped to this environment</p>
        </div>
      </div>

      {/* Services */}
      <div className="space-y-3">
        {SERVICES.map(svc => {
          const isConnected = connectedServices.has(svc.value)
          const isOpen = openService === svc.value
          const cred = credentials.find(c => c.service === svc.value)

          return (
            <div
              key={svc.value}
              className={`rounded-xl border bg-white transition-all ${
                isOpen ? "border-stone-300 shadow-sm" : "border-stone-200"
              }`}
            >
              <div className="flex items-center justify-between px-4 py-3.5">
                <div className="flex items-center gap-3">
                  <span className={`w-9 h-9 rounded-lg text-xs font-bold flex items-center justify-center shrink-0 ${svc.color}`}>
                    {svc.abbr}
                  </span>
                  <div>
                    <div className="flex items-center gap-2">
                      <p className="text-sm font-medium text-stone-900">{svc.label}</p>
                      {isConnected && (
                        <span className="flex items-center gap-1 text-[10px] font-medium text-green-600 bg-green-50 px-1.5 py-0.5 rounded-full">
                          <span className="w-1.5 h-1.5 rounded-full bg-green-500 inline-block" />
                          Connected
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-stone-400">{svc.description}</p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {isConnected && cred && (
                    <button
                      onClick={() => handleRemove(cred.handle)}
                      disabled={deleting === cred.handle}
                      className="text-xs text-stone-400 hover:text-red-500 disabled:opacity-50 transition-colors"
                    >
                      {deleting === cred.handle ? "Removing…" : "Remove"}
                    </button>
                  )}
                  <button
                    onClick={() => toggleService(svc.value)}
                    className={`text-xs font-medium px-3 py-1.5 rounded-lg transition-colors ${
                      isConnected
                        ? "border border-stone-200 text-stone-500 hover:bg-stone-50"
                        : "bg-stone-900 text-white hover:bg-stone-700"
                    }`}
                  >
                    {isConnected ? "Update" : "Connect"}
                  </button>
                </div>
              </div>

              {isOpen && (
                <div className="px-4 pb-4 pt-1 border-t border-stone-100 space-y-3">
                  {svc.fields.map((f, i) => (
                    <div key={f.key}>
                      <label className="text-xs font-medium text-stone-500 block mb-1">
                        {f.label}
                        {f.optional && <span className="ml-1 text-stone-300 font-normal">optional</span>}
                      </label>
                      <input
                        type={f.secret !== false ? "password" : "text"}
                        autoFocus={i === 0}
                        value={fieldValues[f.key] ?? ""}
                        onChange={e => setFieldValues(prev => ({ ...prev, [f.key]: e.target.value }))}
                        onKeyDown={e => e.key === "Enter" && handleSave(svc)}
                        placeholder={f.placeholder}
                        className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm font-mono text-stone-900 focus:outline-none focus:ring-2 focus:ring-indigo-200"
                      />
                    </div>
                  ))}
                  {error && <p className="text-xs text-red-500">{error}</p>}
                  <div className="flex gap-2 pt-1">
                    <button
                      onClick={() => handleSave(svc)}
                      disabled={saving}
                      className="rounded-lg bg-stone-900 px-4 py-2 text-sm font-medium text-white hover:bg-stone-700 disabled:opacity-50 transition-colors"
                    >
                      {saving ? "Saving…" : "Save"}
                    </button>
                    <button
                      onClick={() => { setOpenService(null); setError("") }}
                      className="rounded-lg border border-stone-200 px-4 py-2 text-sm text-stone-600 hover:bg-stone-50 transition-colors"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
