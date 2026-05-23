"use client"

import { useState, useEffect } from "react"
import { useAuth } from "@clerk/nextjs"
import { useWorkspace } from "@/lib/WorkspaceContext"

interface Member {
  clerk_user_id: string
  role: "admin" | "editor" | "viewer"
  invited_by: string | null
  joined_at: string
}

const ROLE_COLORS: Record<string, string> = {
  admin:  "bg-indigo-50 text-indigo-700",
  editor: "bg-emerald-50 text-emerald-700",
  viewer: "bg-stone-100 text-stone-600",
}

function getCookie(name: string): string | null {
  if (typeof document === "undefined") return null
  return document.cookie.split("; ").find(r => r.startsWith(`${name}=`))?.split("=")[1] ?? null
}

export default function MembersManager() {
  const clerkEnabled = !!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY
  if (clerkEnabled) return <MembersManagerWithAuth />
  return <MembersManagerInner getToken={null} />
}

function MembersManagerWithAuth() {
  const { getToken } = useAuth()
  return <MembersManagerInner getToken={getToken} />
}

function MembersManagerInner({ getToken }: { getToken: (() => Promise<string | null>) | null }) {
  const { activeWorkspace } = useWorkspace()
  const [members, setMembers] = useState<Member[]>([])
  const [loading, setLoading] = useState(true)
  const [addOpen, setAddOpen] = useState(false)
  const [newClerkId, setNewClerkId] = useState("")
  const [newRole, setNewRole] = useState<"admin" | "editor" | "viewer">("editor")
  const [saving, setSaving] = useState(false)
  const [removing, setRemoving] = useState<string | null>(null)
  const [error, setError] = useState("")

  async function buildHeaders(contentType = false): Promise<Record<string, string>> {
    const headers: Record<string, string> = {}
    if (contentType) headers["Content-Type"] = "application/json"
    if (getToken) {
      const token = await getToken()
      if (token) headers["Authorization"] = `Bearer ${token}`
    }
    const ws = getCookie("delegator_project_id")
    if (ws) headers["X-Workspace-Id"] = ws
    return headers
  }

  async function loadMembers() {
    if (!activeWorkspace) return
    setLoading(true)
    try {
      const headers = await buildHeaders()
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/projects/${activeWorkspace.id}/members`, { headers })
      if (res.ok) {
        const data = await res.json()
        if (Array.isArray(data)) setMembers(data)
      }
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadMembers() }, [activeWorkspace?.id])

  async function handleAdd() {
    const id = newClerkId.trim()
    if (!id) { setError("Clerk user ID is required"); return }
    setSaving(true)
    setError("")
    try {
      const headers = await buildHeaders(true)
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/projects/${activeWorkspace!.id}/members`, {
        method: "POST",
        headers,
        body: JSON.stringify({ clerk_user_id: id, role: newRole }),
      })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        setError(body.detail ?? "Failed to add member")
        return
      }
      setNewClerkId("")
      setNewRole("editor")
      setAddOpen(false)
      await loadMembers()
    } finally {
      setSaving(false)
    }
  }

  async function handleRoleChange(clerk_user_id: string, role: string) {
    const headers = await buildHeaders(true)
    await fetch(`${process.env.NEXT_PUBLIC_API_URL}/projects/${activeWorkspace!.id}/members/${clerk_user_id}`, {
      method: "PATCH",
      headers,
      body: JSON.stringify({ role }),
    })
    setMembers(prev => prev.map(m => m.clerk_user_id === clerk_user_id ? { ...m, role: role as Member["role"] } : m))
  }

  async function handleRemove(clerk_user_id: string) {
    setRemoving(clerk_user_id)
    try {
      const headers = await buildHeaders()
      await fetch(`${process.env.NEXT_PUBLIC_API_URL}/projects/${activeWorkspace!.id}/members/${clerk_user_id}`, {
        method: "DELETE",
        headers,
      })
      setMembers(prev => prev.filter(m => m.clerk_user_id !== clerk_user_id))
    } finally {
      setRemoving(null)
    }
  }

  if (!activeWorkspace) {
    return <p className="text-sm text-stone-400">No active workspace selected.</p>
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm text-stone-500">Members of <span className="font-medium text-stone-800">{activeWorkspace.name}</span></p>
        </div>
        <button
          onClick={() => { setAddOpen(v => !v); setError("") }}
          className="text-xs font-medium bg-stone-900 text-white px-3 py-1.5 rounded-lg hover:bg-stone-700 transition-colors"
        >
          + Add member
        </button>
      </div>

      {/* Add member form */}
      {addOpen && (
        <div className="rounded-xl border border-stone-200 bg-white px-4 py-4 space-y-3">
          <p className="text-xs font-medium text-stone-500 uppercase tracking-wider">Add member</p>
          <div className="flex gap-2">
            <input
              type="text"
              value={newClerkId}
              onChange={e => setNewClerkId(e.target.value)}
              onKeyDown={e => e.key === "Enter" && handleAdd()}
              placeholder="Clerk user ID (user_…)"
              className="flex-1 border border-stone-200 rounded-lg px-3 py-2 text-sm font-mono text-stone-900 focus:outline-none focus:ring-2 focus:ring-indigo-200"
              autoFocus
            />
            <select
              value={newRole}
              onChange={e => setNewRole(e.target.value as Member["role"])}
              className="border border-stone-200 rounded-lg px-3 py-2 text-sm text-stone-700 focus:outline-none focus:ring-2 focus:ring-indigo-200"
            >
              <option value="admin">Admin</option>
              <option value="editor">Editor</option>
              <option value="viewer">Viewer</option>
            </select>
          </div>
          <p className="text-[11px] text-amber-700 bg-amber-50 border border-amber-200 rounded-md px-2 py-1">
            💡 Find the Clerk user ID in your Clerk dashboard under Users. Format: <span className="font-mono">user_…</span>
          </p>
          {error && <p className="text-xs text-red-500">{error}</p>}
          <div className="flex gap-2">
            <button
              onClick={handleAdd}
              disabled={saving}
              className="rounded-lg bg-stone-900 px-4 py-2 text-sm font-medium text-white hover:bg-stone-700 disabled:opacity-50 transition-colors"
            >
              {saving ? "Adding…" : "Add"}
            </button>
            <button
              onClick={() => { setAddOpen(false); setError("") }}
              className="rounded-lg border border-stone-200 px-4 py-2 text-sm text-stone-600 hover:bg-stone-50 transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Member list */}
      {loading ? (
        <p className="text-sm text-stone-400">Loading members…</p>
      ) : members.length === 0 ? (
        <p className="text-sm text-stone-400">No members yet.</p>
      ) : (
        <div className="rounded-xl border border-stone-200 bg-white divide-y divide-stone-100 overflow-hidden">
          {members.map(m => (
            <div key={m.clerk_user_id} className="flex items-center justify-between px-4 py-3">
              <div className="min-w-0">
                <p className="text-sm font-mono text-stone-700 truncate">{m.clerk_user_id}</p>
                <p className="text-xs text-stone-400">
                  Joined {new Date(m.joined_at).toLocaleDateString()}
                  {m.invited_by && ` · invited by ${m.invited_by}`}
                </p>
              </div>
              <div className="flex items-center gap-3 shrink-0 ml-4">
                <select
                  value={m.role}
                  onChange={e => handleRoleChange(m.clerk_user_id, e.target.value)}
                  className={`text-xs font-medium px-2 py-1 rounded-full border-0 focus:outline-none focus:ring-2 focus:ring-indigo-200 cursor-pointer ${ROLE_COLORS[m.role]}`}
                >
                  <option value="admin">Admin</option>
                  <option value="editor">Editor</option>
                  <option value="viewer">Viewer</option>
                </select>
                <button
                  onClick={() => handleRemove(m.clerk_user_id)}
                  disabled={removing === m.clerk_user_id}
                  className="text-xs text-stone-400 hover:text-red-500 disabled:opacity-50 transition-colors"
                >
                  {removing === m.clerk_user_id ? "Removing…" : "Remove"}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="rounded-lg bg-stone-50 border border-stone-200 px-4 py-3 text-xs text-stone-500 space-y-1">
        <p><span className="font-medium text-stone-700">Admin</span> — full access: manage members, credentials, environments, agents</p>
        <p><span className="font-medium text-stone-700">Editor</span> — can run agents, edit workflows, manage credentials</p>
        <p><span className="font-medium text-stone-700">Viewer</span> — read-only: can view runs, workflows, and settings</p>
      </div>
    </div>
  )
}
