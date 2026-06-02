"use client"

import { useState, useEffect, useCallback } from "react"
import { useAuth } from "@clerk/nextjs"
import { useWorkspace } from "@/lib/WorkspaceContext"
import { useGuardRole } from "@/hooks/useGuardRole"

interface ApiKey {
  id: string
  name: string
  key_prefix: string
  role: string
  created_at: string
  last_used_at: string | null
  expires_at: string | null
}

export default function ApiKeysManager() {
  const { getToken } = useAuth()
  const { activeWorkspace } = useWorkspace()
  const workspaceId = activeWorkspace?.id ?? ""
  const apiUrl = process.env.NEXT_PUBLIC_API_URL
  const { role } = useGuardRole(null, workspaceId || null)
  const isAdmin = role === "admin"
  const canGenerateKey = role === "admin" || role === "developer"

  const [keys, setKeys] = useState<ApiKey[]>([])
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)
  const [newName, setNewName] = useState("")
  const [newKey, setNewKey] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  const [revoking, setRevoking] = useState<string | null>(null)
  const [revokeConfirm, setRevokeConfirm] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const headers = useCallback(async (): Promise<Record<string, string>> => {
    const h: Record<string, string> = { "Content-Type": "application/json" }
    if (getToken) { const t = await getToken(); if (t) h["Authorization"] = `Bearer ${t}` }
    if (workspaceId) h["X-Workspace-Id"] = workspaceId
    return h
  }, [getToken, workspaceId])

  const load = useCallback(async () => {
    if (!workspaceId || !apiUrl) return
    try {
      const h = await headers()
      const r = await fetch(`${apiUrl}/workspaces/${workspaceId}/api-keys`, { headers: h })
      if (r.ok) setKeys(await r.json())
    } catch {}
    setLoading(false)
  }, [workspaceId, apiUrl, headers])

  useEffect(() => { load() }, [load])

  async function create() {
    if (!newName.trim()) return
    setCreating(true)
    setError(null)
    try {
      const h = await headers()
      const r = await fetch(`${apiUrl}/workspaces/${workspaceId}/api-keys`, {
        method: "POST",
        headers: h,
        body: JSON.stringify({ name: newName.trim() }),
      })
      if (r.ok) {
        const data = await r.json()
        setNewKey(data.key)
        setNewName("")
        await load()
      } else {
        const body = await r.json().catch(() => ({}))
        setError(body.detail ?? "Could not generate key — please try again.")
      }
    } catch { setError("Could not generate key — check your connection.") }
    setCreating(false)
  }

  async function revoke(id: string) {
    setRevokeConfirm(null)
    setRevoking(id)
    setError(null)
    try {
      const h = await headers()
      const r = await fetch(`${apiUrl}/workspaces/${workspaceId}/api-keys/${id}`, { method: "DELETE", headers: h })
      if (r.ok) setKeys(k => k.filter(x => x.id !== id))
      else {
        const body = await r.json().catch(() => ({}))
        setError(body.detail ?? "Could not revoke key — please try again.")
      }
    } catch { setError("Could not revoke key — check your connection.") }
    setRevoking(null)
  }

  function copy() {
    if (!newKey) return
    navigator.clipboard.writeText(newKey)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  function fmt(dateStr: string | null) {
    if (!dateStr) return "—"
    return new Date(dateStr).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })
  }

  return (
    <div className="space-y-6">
      {/* Error banner */}
      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 flex items-center justify-between gap-3">
          <p className="text-xs text-red-700">{error}</p>
          <button onClick={() => setError(null)} aria-label="Dismiss" className="text-xs text-red-400 hover:text-red-700">✕</button>
        </div>
      )}

      {/* New key — shown once after creation */}
      {newKey && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 space-y-3">
          <p className="text-sm font-semibold text-amber-800">Copy your API key — it won&apos;t be shown again.</p>
          <div className="flex items-center gap-2">
            <code className="flex-1 bg-white border border-amber-200 rounded px-3 py-2 text-xs font-mono text-stone-800 break-all select-all">
              {newKey}
            </code>
            <button
              onClick={copy}
              className={`shrink-0 px-3 py-2 rounded text-xs font-medium transition-colors ${
                copied
                  ? "bg-green-100 text-green-700 border border-green-300"
                  : "bg-amber-100 text-amber-800 border border-amber-300 hover:bg-amber-200"
              }`}
            >
              {copied ? "Copied!" : "Copy"}
            </button>
          </div>
          <p className="text-xs text-amber-600">
            Use this key with <code className="bg-amber-100 px-1 rounded">X-Api-Key</code> header or{" "}
            <code className="bg-amber-100 px-1 rounded">conduct login --api-key</code>.
          </p>
          <button
            onClick={() => setNewKey(null)}
            className="text-xs text-amber-500 hover:text-amber-700 underline"
          >
            I&apos;ve saved it, dismiss
          </button>
        </div>
      )}

      {/* Create form — admin + developer */}
      {canGenerateKey && (
        <div className="flex gap-2">
          <input
            type="text"
            value={newName}
            onChange={e => setNewName(e.target.value)}
            onKeyDown={e => e.key === "Enter" && create()}
            placeholder="Key name (e.g. My laptop, CI pipeline)"
            className="flex-1 border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-300"
          />
          <button
            onClick={create}
            disabled={creating || !newName.trim()}
            className="px-4 py-2 bg-stone-900 text-white text-sm rounded-lg hover:bg-stone-700 disabled:opacity-40 transition-colors"
          >
            {creating ? "Generating…" : "Generate key"}
          </button>
        </div>
      )}

      {/* Keys table */}
      {loading ? (
        <p className="text-sm text-stone-400">Loading…</p>
      ) : keys.length === 0 ? (
        <p className="text-sm text-stone-400">No API keys yet. Generate one above.</p>
      ) : (
        <div className="border border-stone-200 rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-stone-50 text-stone-500 text-xs">
              <tr>
                <th className="text-left px-4 py-2 font-medium">Name</th>
                <th className="text-left px-4 py-2 font-medium">Prefix</th>
                <th className="text-left px-4 py-2 font-medium">Created</th>
                <th className="text-left px-4 py-2 font-medium">Last used</th>
                <th className="px-4 py-2" />
              </tr>
            </thead>
            <tbody className="divide-y divide-stone-100">
              {keys.map(k => (
                <tr key={k.id} className="hover:bg-stone-50">
                  <td className="px-4 py-3 font-medium text-stone-800">{k.name}</td>
                  <td className="px-4 py-3 font-mono text-xs text-stone-500">{k.key_prefix}…</td>
                  <td className="px-4 py-3 text-stone-500">{fmt(k.created_at)}</td>
                  <td className="px-4 py-3 text-stone-500">{fmt(k.last_used_at)}</td>
                  <td className="px-4 py-3 text-right">
                    {isAdmin && (revokeConfirm === k.id ? (
                      <span className="inline-flex items-center gap-2">
                        <span className="text-xs text-stone-500">Revoke?</span>
                        <button
                          onClick={() => revoke(k.id)}
                          disabled={revoking === k.id}
                          className="text-xs font-medium text-red-600 hover:text-red-800 disabled:opacity-40 transition-colors"
                        >
                          {revoking === k.id ? "Revoking…" : "Yes, revoke"}
                        </button>
                        <button
                          onClick={() => setRevokeConfirm(null)}
                          className="text-xs text-stone-400 hover:text-stone-600 transition-colors"
                        >
                          Cancel
                        </button>
                      </span>
                    ) : (
                      <button
                        onClick={() => setRevokeConfirm(k.id)}
                        disabled={revoking === k.id}
                        className="text-xs text-stone-400 hover:text-red-500 disabled:opacity-40 transition-colors"
                      >
                        Revoke
                      </button>
                    ))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <p className="text-xs text-stone-400">
        Keys are stored as SHA-256 hashes — Conduct never sees your key again after generation.
        Admins and developers can generate keys. Only admins can revoke keys.
      </p>
    </div>
  )
}
