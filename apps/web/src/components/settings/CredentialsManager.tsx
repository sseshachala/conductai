"use client"

import { useState, useEffect } from "react"
import { useAuth } from "@clerk/nextjs"

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
  secret?: boolean   // true = password input (default true)
  optional?: boolean // true = not required to save
  tip?: string       // helper text shown below the input
  options?: { value: string; label: string }[]  // renders a <select> instead of <input>
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
    value: "git", label: "Git", abbr: "GIT",
    description: "GitHub, GitLab, or Bitbucket — create repos, branches, and pull requests",
    color: "bg-stone-900 text-white",
    fields: [
      {
        key: "provider",
        label: "Provider",
        placeholder: "",
        secret: false,
        options: [
          { value: "github",    label: "GitHub" },
          { value: "gitlab",    label: "GitLab" },
          { value: "bitbucket", label: "Bitbucket" },
        ],
      },
      { key: "token", label: "Personal access token", placeholder: "ghp_… / glpat-… / ATB…" },
    ],
  },
  {
    value: "slack", label: "Slack", abbr: "SL",
    description: "Post messages, DMs, and approval requests",
    color: "bg-purple-600 text-white",
    fields: [
      { key: "token", label: "Bot token", placeholder: "xoxb-…" },
      {
        key: "signing_secret",
        label: "Signing secret",
        placeholder: "a1b2c3…",
        optional: true,
        tip: `Required for Approve/Reject buttons. Slack app → Basic Information → Signing Secret. Set Interactivity URL to: ${process.env.NEXT_PUBLIC_API_URL}/webhooks/slack/interactions`,
      },
    ],
  },
  {
    value: "linear", label: "Linear", abbr: "LN",
    description: "Fetch issues, post comments, update status",
    color: "bg-indigo-600 text-white",
    fields: [{ key: "api_key", label: "API key", placeholder: "lin_api_…" }],
  },
  {
    value: "digitalocean", label: "DigitalOcean", abbr: "DO",
    description: "Provision and manage cloud droplets",
    color: "bg-blue-500 text-white",
    fields: [{ key: "token", label: "Personal access token", placeholder: "dop_v1_…" }],
  },
  {
    value: "vercel", label: "Vercel", abbr: "VC",
    description: "Trigger deployments and receive deployment events",
    color: "bg-stone-950 text-white",
    fields: [
      {
        key: "token",
        label: "Personal access token",
        placeholder: "…",
        tip: "Create at vercel.com/account/tokens — used to register deployment webhooks and trigger deploys.",
      },
    ],
  },
  {
    value: "anthropic", label: "Anthropic", abbr: "AI",
    description: "Bring your own API key — agents use this instead of the platform key",
    color: "bg-amber-600 text-white",
    fields: [
      {
        key: "api_key",
        label: "API key",
        placeholder: "sk-ant-…",
        tip: "Create at console.anthropic.com — your key is encrypted at rest and never logged.",
      },
    ],
  },
  {
    value: "email", label: "Email", abbr: "EM",
    description: "Send notifications via Resend or SendGrid",
    color: "bg-emerald-600 text-white",
    fields: [
      { key: "resend_api_key",    label: "Resend API key (recommended)", placeholder: "re_…" },
      { key: "sendgrid_api_key",  label: "SendGrid API key (alternative)", placeholder: "SG.…" },
      { key: "from_name",  label: "From name",          placeholder: "Conduct AI",                      secret: false, optional: true },
      { key: "from_email", label: "From email address", placeholder: "notifications@yourdomain.com", secret: false, optional: true, tip: "The sender domain must be verified in Resend or SendGrid before emails will deliver." },
    ],
  },
]

function getWorkspaceId(): string | null {
  if (typeof document === "undefined") return null
  return document.cookie.split("; ").find(r => r.startsWith("delegator_project_id="))?.split("=")[1] ?? null
}

export default function CredentialsManager({ isAdmin = true }: { isAdmin?: boolean }) {
  const clerkEnabled = !!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY
  if (clerkEnabled) return <CredentialsManagerWithAuth isAdmin={isAdmin} />
  return <CredentialsManagerInner getToken={null} isAdmin={isAdmin} />
}

function CredentialsManagerWithAuth({ isAdmin }: { isAdmin: boolean }) {
  const { getToken } = useAuth()
  return <CredentialsManagerInner getToken={getToken} isAdmin={isAdmin} />
}

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

function CredentialsManagerInner({ getToken, isAdmin }: { getToken: (() => Promise<string | null>) | null; isAdmin: boolean }) {
  const [credentials, setCredentials] = useState<Credential[]>([])
  const [openService, setOpenService] = useState<string | null>(null)
  const [fieldValues, setFieldValues] = useState<Record<string, string>>({})
  const [showFields, setShowFields] = useState<Record<string, boolean>>({})
  const [revealedValues, setRevealedValues] = useState<Record<string, Record<string, string>>>({})
  const [revealing, setRevealing] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [deleting, setDeleting] = useState<string | null>(null)
  const [error, setError] = useState("")

  const connectedServices = new Set(credentials.map(c => c.service))

  async function buildHeaders(contentType = false): Promise<Record<string, string>> {
    const headers: Record<string, string> = {}
    if (contentType) headers["Content-Type"] = "application/json"
    if (getToken) {
      const token = await getToken()
      if (token) headers["Authorization"] = `Bearer ${token}`
    }
    const ws = getWorkspaceId()
    if (ws) headers["X-Workspace-Id"] = ws
    return headers
  }

  async function revealCredential(handle: string) {
    if (revealedValues[handle]) {
      // toggle off
      setRevealedValues(prev => { const n = { ...prev }; delete n[handle]; return n })
      return
    }
    setRevealing(handle)
    try {
      const headers = await buildHeaders()
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/credentials/reveal/${handle}`, { headers })
      if (res.ok) {
        const data = await res.json()
        setRevealedValues(prev => ({ ...prev, [handle]: data }))
        setTimeout(() => setRevealedValues(prev => { const n = { ...prev }; delete n[handle]; return n }), 30_000)
      }
    } finally { setRevealing(null) }
  }

  async function loadCredentials() {
    try {
      const headers = await buildHeaders()
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/credentials`, { headers })
      if (res.ok) {
        const data = await res.json()
        if (Array.isArray(data)) setCredentials(data)
      }
    } catch { /* silent */ }
  }

  useEffect(() => { loadCredentials() }, [])

  function toggleService(svc: string) {
    if (openService === svc) {
      setOpenService(null)
      setError("")
    } else {
      setOpenService(svc)
      setFieldValues({})
      setError("")
    }
  }

  async function handleSave(svc: ServiceDef) {
    const credObj: Record<string, string> = {}
    for (const f of svc.fields) {
      // For select fields, fall back to first option if user never touched it
      const defaultVal = f.options ? f.options[0].value : ""
      const val = (fieldValues[f.key] ?? defaultVal).trim()
      if (!val && !f.optional) {
        setError(`${f.label} is required`)
        return
      }
      if (val) credObj[f.key] = val
    }

    setSaving(true)
    setError("")
    try {
      const postHeaders = await buildHeaders(true)
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/credentials`, {
        method: "POST",
        headers: postHeaders,
        body: JSON.stringify({ service: svc.value, handle: svc.value, credentials: credObj }),
      })
      if (!res.ok) throw new Error("Save failed")
      const listHeaders = await buildHeaders()
      const listRes = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/credentials`, { headers: listHeaders })
      if (listRes.ok) {
        const list = await listRes.json()
        if (Array.isArray(list)) setCredentials(list)
      }
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
    setError("")
    try {
      const headers = await buildHeaders()
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/credentials/${handle}`, { method: "DELETE", headers })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        setError(body.detail ?? "Failed to remove credential")
        return
      }
      setCredentials(prev => prev.filter(c => c.handle !== handle))
    } finally {
      setDeleting(null)
    }
  }

  return (
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
            {/* Card header */}
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
                {isAdmin && isConnected && cred && (
                  <button
                    onClick={() => revealCredential(cred.handle)}
                    disabled={revealing === cred.handle}
                    title={revealedValues[cred.handle] ? "Hide" : "Reveal credential"}
                    className="text-stone-300 hover:text-stone-600 disabled:opacity-50 transition-colors"
                  >
                    <EyeIcon open={!!revealedValues[cred.handle]} />
                  </button>
                )}
                {isAdmin && isConnected && cred && (
                  <button
                    onClick={() => handleRemove(cred.handle)}
                    disabled={deleting === cred.handle}
                    className="text-xs text-stone-400 hover:text-red-500 disabled:opacity-50 transition-colors"
                  >
                    {deleting === cred.handle ? "Removing…" : "Remove"}
                  </button>
                )}
                {isAdmin && (
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
                )}
                {!isAdmin && isConnected && (
                  <span className="text-xs text-stone-400">Connected</span>
                )}
              </div>
            </div>

            {/* Revealed values panel */}
            {cred && revealedValues[cred.handle] && (
              <div className="px-4 pb-3 pt-2 border-t border-stone-100 bg-stone-50 rounded-b-xl space-y-1">
                {Object.entries(revealedValues[cred.handle]).map(([k, v]) => (
                  <div key={k} className="flex items-center gap-2 group">
                    <span className="text-[10px] font-medium text-stone-400 w-24 shrink-0">{k}</span>
                    <span className="text-xs font-mono text-stone-700 break-all blur-sm group-hover:blur-none transition-all select-all">{v as string}</span>
                  </div>
                ))}
              </div>
            )}

            {/* Inline connect form — admin only */}
            {isAdmin && isOpen && (
              <div className="px-4 pb-4 pt-1 border-t border-stone-100 space-y-3">
                {svc.fields.map((f, i) => (
                  <div key={f.key}>
                    <label className="text-xs font-medium text-stone-500 block mb-1">
                      {f.label}
                      {f.optional && <span className="ml-1 text-stone-300 font-normal">optional</span>}
                    </label>
                    <div className="relative">
                      {f.options ? (
                        <select
                          autoFocus={i === 0}
                          value={fieldValues[f.key] ?? f.options[0].value}
                          onChange={e => setFieldValues(prev => ({ ...prev, [f.key]: e.target.value }))}
                          className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm text-stone-900 bg-white focus:outline-none focus:ring-2 focus:ring-indigo-200"
                        >
                          {f.options.map(o => (
                            <option key={o.value} value={o.value}>{o.label}</option>
                          ))}
                        </select>
                      ) : (
                        <>
                          <input
                            type={f.secret !== false && !showFields[f.key] ? "password" : "text"}
                            autoFocus={i === 0}
                            value={fieldValues[f.key] ?? ""}
                            onChange={e => setFieldValues(prev => ({ ...prev, [f.key]: e.target.value }))}
                            onKeyDown={e => e.key === "Enter" && handleSave(svc)}
                            placeholder={f.placeholder}
                            className="w-full border border-stone-200 rounded-lg px-3 py-2 pr-9 text-sm font-mono text-stone-900 focus:outline-none focus:ring-2 focus:ring-indigo-200"
                          />
                          {f.secret !== false && (
                            <button
                              type="button"
                              onClick={() => setShowFields(prev => ({ ...prev, [f.key]: !prev[f.key] }))}
                              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-stone-300 hover:text-stone-600 transition-colors"
                            >
                              <EyeIcon open={!!showFields[f.key]} />
                            </button>
                          )}
                        </>
                      )}
                    </div>
                    {f.tip && (
                      <p className="mt-1 text-[11px] text-amber-700 bg-amber-50 border border-amber-200 rounded-md px-2 py-1 leading-relaxed">
                        💡 {f.tip}
                      </p>
                    )}
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
  )
}
