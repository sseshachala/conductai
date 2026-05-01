"use client"

import { useState } from "react"

interface Credential {
  handle: string
  service: string
  auth_method: string
  fields: string[]
}

interface ServiceDef {
  value: string
  label: string
  description: string
  color: string
  abbr: string
  fields: { key: string; label: string; placeholder: string }[]
}

const SERVICES: ServiceDef[] = [
  {
    value: "github", label: "GitHub", abbr: "GH",
    description: "Create repos, branches, and pull requests",
    color: "bg-stone-900 text-white",
    fields: [{ key: "token", label: "Personal access token", placeholder: "ghp_… or gho_…" }],
  },
  {
    value: "slack", label: "Slack", abbr: "SL",
    description: "Post messages, DMs, and approval requests",
    color: "bg-purple-600 text-white",
    fields: [{ key: "token", label: "Bot token", placeholder: "xoxb-…" }],
  },
  {
    value: "linear", label: "Linear", abbr: "LN",
    description: "Fetch issues, post comments, update status",
    color: "bg-indigo-600 text-white",
    fields: [{ key: "api_key", label: "API key", placeholder: "lin_api_…" }],
  },
  {
    value: "vercel", label: "Vercel", abbr: "VC",
    description: "Trigger deployments and monitor status",
    color: "bg-stone-800 text-white",
    fields: [{ key: "token", label: "Access token", placeholder: "Personal access token" }],
  },
  {
    value: "railway", label: "Railway", abbr: "RW",
    description: "Deploy services and check deployment status",
    color: "bg-violet-600 text-white",
    fields: [{ key: "token", label: "API token", placeholder: "railway token from account settings" }],
  },
  {
    value: "digitalocean", label: "DigitalOcean", abbr: "DO",
    description: "Provision and manage cloud droplets",
    color: "bg-blue-500 text-white",
    fields: [{ key: "token", label: "Personal access token", placeholder: "dop_v1_…" }],
  },
  {
    value: "email", label: "Email", abbr: "EM",
    description: "Send notifications via Resend or SendGrid",
    color: "bg-emerald-600 text-white",
    fields: [
      { key: "resend_api_key",    label: "Resend API key (recommended)", placeholder: "re_…" },
      { key: "sendgrid_api_key",  label: "SendGrid API key (alternative)", placeholder: "SG.…" },
    ],
  },
]

interface Props {
  initialCredentials: Credential[]
}

export default function CredentialsManager({ initialCredentials }: Props) {
  const [credentials, setCredentials] = useState<Credential[]>(initialCredentials)
  const [openService, setOpenService] = useState<string | null>(null)
  const [fieldValues, setFieldValues] = useState<Record<string, string>>({})
  const [saving, setSaving] = useState(false)
  const [deleting, setDeleting] = useState<string | null>(null)
  const [error, setError] = useState("")

  const connectedServices = new Set(credentials.map(c => c.service))

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
      if (!fieldValues[f.key]?.trim()) {
        setError(`${f.label} is required`)
        return
      }
      credObj[f.key] = fieldValues[f.key].trim()
    }

    setSaving(true)
    setError("")
    try {
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/credentials`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ service: svc.value, handle: svc.value, credentials: credObj }),
      })
      if (!res.ok) throw new Error("Save failed")
      const list = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/credentials`).then(r => r.json())
      setCredentials(list)
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
      await fetch(`${process.env.NEXT_PUBLIC_API_URL}/credentials/${handle}`, { method: "DELETE" })
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

            {/* Inline connect form */}
            {isOpen && (
              <div className="px-4 pb-4 pt-1 border-t border-stone-100 space-y-3">
                {svc.fields.map(f => (
                  <div key={f.key}>
                    <label className="text-xs font-medium text-stone-500 block mb-1">{f.label}</label>
                    <input
                      type="password"
                      autoFocus
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
  )
}
