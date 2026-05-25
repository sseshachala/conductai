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
// Environment detail — simple key-value env var editor
// ---------------------------------------------------------------------------

interface EnvVar { key: string; value: string; handle?: string }

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

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const headers = await buildHeaders()
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/credentials/env-vars/${environment.id}`, { headers })
      if (res.ok) setVars(await res.json())
    } finally { setLoading(false) }
  }, [buildHeaders, environment.id])

  useEffect(() => { load() }, [load])

  async function saveAll(updated: EnvVar[]) {
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
    } catch { setError("Save failed") } finally { setSaving(false) }
  }

  function updateVar(i: number, field: "key" | "value", val: string) {
    setVars(prev => prev.map((v, idx) => idx === i ? { ...v, [field]: val } : v))
  }

  function removeVar(i: number) {
    const updated = vars.filter((_, idx) => idx !== i)
    setVars(updated)
    saveAll(updated)
  }

  function addVar() {
    if (!newKey.trim()) return
    const updated = [...vars, { key: newKey.trim(), value: newValue }]
    setVars(updated)
    setNewKey(""); setNewValue(""); setShowNew(false)
    saveAll(updated)
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
    setPasteText("")
    setShowPaste(false)
  }

  return (
    <div>
      {/* Header */}
      <div className="flex items-center gap-3 mb-6">
        <button onClick={onBack} className="text-stone-400 hover:text-stone-700 text-sm transition-colors">←</button>
        <span className="w-8 h-8 rounded-lg text-xs font-bold flex items-center justify-center bg-violet-100 text-violet-700">
          {environment.name.slice(0, 2).toUpperCase()}
        </span>
        <div>
          <h2 className="text-sm font-semibold text-stone-900">{environment.name}</h2>
          <p className="text-xs text-stone-400">{vars.length} variable{vars.length !== 1 ? "s" : ""}</p>
        </div>
        <div className="ml-auto flex items-center gap-2">
          <button
            onClick={() => { setShowPaste(p => !p); setError("") }}
            className="text-xs border border-stone-200 text-stone-600 hover:bg-stone-50 px-3 py-1.5 rounded-lg transition-colors"
          >
            Paste .env
          </button>
          <button
            onClick={() => saveAll(vars)}
            disabled={saving}
            className="text-xs font-medium bg-stone-900 text-white hover:bg-stone-700 px-3 py-1.5 rounded-lg transition-colors disabled:opacity-50"
          >
            {saving ? "Saving…" : saved ? "Saved ✓" : "Save"}
          </button>
        </div>
      </div>

      {/* Paste .env panel */}
      {showPaste && (
        <div className="mb-4 rounded-xl border border-stone-200 bg-stone-50 p-4 space-y-3">
          <p className="text-xs text-stone-500">Paste the contents of your <span className="font-mono">.env</span> file. Existing keys will be overwritten; new keys will be added.</p>
          <textarea
            autoFocus
            value={pasteText}
            onChange={e => setPasteText(e.target.value)}
            placeholder={"GITHUB_TOKEN=ghp_...\nANTHROPIC_API_KEY=sk-ant-...\nSLACK_BOT_TOKEN=xoxb-..."}
            rows={7}
            className="w-full font-mono text-xs text-stone-800 border border-stone-200 rounded-lg px-3 py-2.5 bg-white focus:outline-none focus:ring-2 focus:ring-indigo-200 resize-none"
          />
          <div className="flex gap-2">
            <button
              onClick={handlePasteImport}
              className="text-xs font-medium bg-stone-900 text-white hover:bg-stone-700 px-4 py-2 rounded-lg transition-colors"
            >
              Import
            </button>
            <button
              onClick={() => { setShowPaste(false); setPasteText(""); setError("") }}
              className="text-xs border border-stone-200 text-stone-600 hover:bg-stone-50 px-4 py-2 rounded-lg transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {error && <p className="mb-3 text-xs text-red-500">{error}</p>}

      {/* Key-value table */}
      <div className="rounded-xl border border-stone-200 bg-white overflow-hidden">
        {/* Column headers */}
        <div className="grid grid-cols-[1fr_1fr_auto] gap-0 border-b border-stone-100 px-4 py-2 bg-stone-50">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-stone-400">Key</p>
          <p className="text-[10px] font-semibold uppercase tracking-wider text-stone-400">Value</p>
          <p className="w-16" />
        </div>

        {loading ? (
          <p className="text-sm text-stone-400 px-4 py-6">Loading…</p>
        ) : vars.length === 0 ? (
          <p className="text-sm text-stone-400 px-4 py-6">No variables yet — add one or import a .env file.</p>
        ) : (
          vars.map((v, i) => (
            <div key={i} className="grid grid-cols-[1fr_1fr_auto] gap-0 border-b border-stone-100 last:border-0 px-4 py-2 items-center group">
              <input
                value={v.key}
                onChange={e => updateVar(i, "key", e.target.value)}
                onBlur={() => saveAll(vars)}
                className="font-mono text-xs text-stone-800 bg-transparent border-none outline-none w-full pr-4"
              />
              <div className="relative flex items-center">
                <input
                  type={showValues[i] ? "text" : "password"}
                  value={v.value}
                  onChange={e => updateVar(i, "value", e.target.value)}
                  onBlur={() => saveAll(vars)}
                  className="font-mono text-xs text-stone-600 bg-transparent border-none outline-none w-full pr-7"
                />
                <button
                  type="button"
                  onClick={() => setShowValues(prev => ({ ...prev, [i]: !prev[i] }))}
                  className="absolute right-1 text-stone-300 hover:text-stone-600 transition-colors"
                >
                  <EyeIcon open={!!showValues[i]} />
                </button>
              </div>
              <button
                onClick={() => removeVar(i)}
                className="text-stone-200 hover:text-red-500 transition-colors w-16 text-right text-xs"
              >
                Remove
              </button>
            </div>
          ))
        )}

        {/* Add new row */}
        {isAdmin && (showNew ? (
          <div className="grid grid-cols-[1fr_1fr_auto] gap-0 border-t border-stone-100 px-4 py-2 items-center bg-stone-50">
            <input
              autoFocus
              value={newKey}
              onChange={e => setNewKey(e.target.value)}
              onKeyDown={e => e.key === "Enter" && addVar()}
              placeholder="VARIABLE_NAME"
              className="font-mono text-xs text-stone-800 bg-transparent border-none outline-none w-full pr-4 placeholder:text-stone-300"
            />
            <input
              value={newValue}
              onChange={e => setNewValue(e.target.value)}
              onKeyDown={e => e.key === "Enter" && addVar()}
              placeholder="value"
              type="password"
              className="font-mono text-xs text-stone-600 bg-transparent border-none outline-none w-full pr-4 placeholder:text-stone-300"
            />
            <div className="flex gap-2 w-16 justify-end">
              <button onClick={addVar} className="text-xs font-medium text-green-600 hover:text-green-800">Add</button>
              <button onClick={() => { setShowNew(false); setNewKey(""); setNewValue("") }} className="text-xs text-stone-400 hover:text-stone-600">✕</button>
            </div>
          </div>
        ) : (
          <div className="border-t border-stone-100 px-4 py-2">
            <button
              onClick={() => setShowNew(true)}
              className="text-xs text-stone-400 hover:text-stone-700 transition-colors"
            >
              + Add Environment Variable
            </button>
          </div>
        ))}
      </div>
    </div>
  )
}
