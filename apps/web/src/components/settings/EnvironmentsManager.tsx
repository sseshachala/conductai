"use client"

import { useState, useEffect } from "react"
import { useAuth } from "@clerk/nextjs"

interface Environment {
  id: string
  name: string
  created_at: string
}

function getWorkspaceId(): string | null {
  if (typeof document === "undefined") return null
  return document.cookie.split("; ").find(r => r.startsWith("delegator_project_id="))?.split("=")[1] ?? null
}

export default function EnvironmentsManager() {
  const clerkEnabled = !!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY
  if (clerkEnabled) return <EnvironmentsManagerWithAuth />
  return <EnvironmentsManagerInner getToken={null} />
}

function EnvironmentsManagerWithAuth() {
  const { getToken } = useAuth()
  return <EnvironmentsManagerInner getToken={getToken} />
}

function EnvironmentsManagerInner({ getToken }: { getToken: (() => Promise<string | null>) | null }) {
  const [environments, setEnvironments] = useState<Environment[]>([])
  const [newName, setNewName] = useState("")
  const [creating, setCreating] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null)
  const [deleting, setDeleting] = useState<string | null>(null)
  const [error, setError] = useState("")

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

  async function loadEnvironments() {
    try {
      const headers = await buildHeaders()
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/environments`, { headers })
      if (res.ok) setEnvironments(await res.json())
    } catch { /* silent */ }
  }

  useEffect(() => { loadEnvironments() }, [])

  async function handleCreate() {
    const name = newName.trim()
    if (!name) { setError("Environment name is required"); return }
    setCreating(true)
    setError("")
    try {
      const headers = await buildHeaders(true)
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/environments`, {
        method: "POST",
        headers,
        body: JSON.stringify({ name }),
      })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error(body.detail || "Failed to create environment")
      }
      setNewName("")
      await loadEnvironments()
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to create environment")
    } finally {
      setCreating(false)
    }
  }

  async function handleDelete(id: string) {
    setDeleting(id)
    setError("")
    try {
      const headers = await buildHeaders()
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/environments/${id}`, {
        method: "DELETE",
        headers,
      })
      if (!res.ok) throw new Error("Failed to delete environment")
      setEnvironments(prev => prev.filter(e => e.id !== id))
      setConfirmDelete(null)
    } catch {
      setError("Failed to delete environment")
    } finally {
      setDeleting(null)
    }
  }

  function formatDate(iso: string) {
    try {
      return new Date(iso).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" })
    } catch {
      return iso
    }
  }

  return (
    <div className="space-y-3">
      {/* Default (workspace global) row — always shown, non-deletable */}
      <div className="rounded-xl border border-stone-200 bg-white">
        <div className="flex items-center justify-between px-4 py-3.5">
          <div className="flex items-center gap-3">
            <span className="w-9 h-9 rounded-lg text-xs font-bold flex items-center justify-center shrink-0 bg-stone-100 text-stone-500">
              WS
            </span>
            <div>
              <div className="flex items-center gap-2">
                <p className="text-sm font-medium text-stone-900">Default (workspace global)</p>
                <span className="text-[10px] font-medium text-stone-400 bg-stone-50 border border-stone-200 px-1.5 py-0.5 rounded-full">
                  built-in
                </span>
              </div>
              <p className="text-xs text-stone-400">Credentials available to all agents with no environment assigned</p>
            </div>
          </div>
        </div>
      </div>

      {/* Existing environments */}
      {environments.map(env => (
        <div
          key={env.id}
          className="rounded-xl border border-stone-200 bg-white"
        >
          <div className="flex items-center justify-between px-4 py-3.5">
            <div className="flex items-center gap-3">
              <span className="w-9 h-9 rounded-lg text-xs font-bold flex items-center justify-center shrink-0 bg-violet-100 text-violet-700">
                {env.name.slice(0, 2).toUpperCase()}
              </span>
              <div>
                <p className="text-sm font-medium text-stone-900">{env.name}</p>
                <p className="text-xs text-stone-400">Created {formatDate(env.created_at)}</p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              {confirmDelete === env.id ? (
                <>
                  <span className="text-xs text-stone-500">Delete this environment?</span>
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
                  onClick={() => setConfirmDelete(env.id)}
                  className="text-xs text-stone-400 hover:text-red-500 transition-colors"
                >
                  Delete
                </button>
              )}
            </div>
          </div>
        </div>
      ))}

      {/* Create new environment */}
      <div className="rounded-xl border border-dashed border-stone-200 bg-white px-4 py-4">
        <p className="text-xs font-medium text-stone-500 mb-2">New environment</p>
        <div className="flex gap-2">
          <input
            type="text"
            value={newName}
            onChange={e => { setNewName(e.target.value); setError("") }}
            onKeyDown={e => e.key === "Enter" && handleCreate()}
            placeholder="e.g. staging, production, testing"
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
        {error && <p className="text-xs text-red-500 mt-2">{error}</p>}
      </div>
    </div>
  )
}
