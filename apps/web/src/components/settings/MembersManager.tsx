"use client"

import { useState, useEffect } from "react"
import { useAuth } from "@clerk/nextjs"
import { useWorkspace } from "@/lib/WorkspaceContext"

interface Member {
  clerk_user_id: string
  role: "admin" | "editor" | "viewer"
  invited_by: string | null
  joined_at: string
  email: string | null
  name: string | null
}

interface Invite {
  id: string
  invited_email: string
  role: string
  invited_by: string | null
  created_at: string
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
  return <MembersManagerInner getToken={null} currentClerkId={null} />
}

function MembersManagerWithAuth() {
  const { getToken, userId } = useAuth()
  return <MembersManagerInner getToken={getToken} currentClerkId={userId ?? null} />
}

function MembersManagerInner({ getToken, currentClerkId }: { getToken: (() => Promise<string | null>) | null; currentClerkId: string | null }) {
  const { activeWorkspace } = useWorkspace()
  const [members, setMembers] = useState<Member[]>([])
  const [invites, setInvites] = useState<Invite[]>([])
  const [loading, setLoading] = useState(true)
  const [addOpen, setAddOpen] = useState(false)
  const [inviteEmail, setInviteEmail] = useState("")
  const [inviteRole, setInviteRole] = useState<"admin" | "editor" | "viewer">("editor")
  const [saving, setSaving] = useState(false)
  const [removing, setRemoving] = useState<string | null>(null)
  const [cancelling, setCancelling] = useState<string | null>(null)
  const [error, setError] = useState("")
  const [emailWarning, setEmailWarning] = useState("")

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

  async function loadData() {
    if (!activeWorkspace) return
    setLoading(true)
    try {
      const headers = await buildHeaders()
      const [membersRes, invitesRes] = await Promise.all([
        fetch(`${process.env.NEXT_PUBLIC_API_URL}/projects/${activeWorkspace.id}/members`, { headers }),
        fetch(`${process.env.NEXT_PUBLIC_API_URL}/projects/${activeWorkspace.id}/invites`, { headers }),
      ])
      if (membersRes.ok) {
        const data = await membersRes.json()
        if (Array.isArray(data)) setMembers(data)
      }
      if (invitesRes.ok) {
        const data = await invitesRes.json()
        if (Array.isArray(data)) setInvites(data)
      }
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadData() }, [activeWorkspace?.id])

  async function handleInvite() {
    const email = inviteEmail.trim()
    if (!email || !email.includes("@")) { setError("Enter a valid email address"); return }
    setSaving(true)
    setError("")
    setEmailWarning("")
    try {
      const headers = await buildHeaders(true)
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/projects/${activeWorkspace!.id}/members`, {
        method: "POST",
        headers,
        body: JSON.stringify({ email, role: inviteRole }),
      })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        if (res.status >= 500) {
          setError("Something went wrong on our end. Please try again.")
        } else {
          setError(body.detail ?? "Failed to send invite")
        }
        return
      }
      const data = await res.json().catch(() => ({}))
      setInviteEmail("")
      setInviteRole("editor")
      setAddOpen(false)
      if (data.email_sent === false) {
        setEmailWarning(`Invite created but the email couldn't be sent — no email provider is configured. Ask ${email} to sign in at conductai.ai and they'll be added automatically.`)
      }
      await loadData()
    } finally {
      setSaving(false)
    }
  }

  async function handleRoleChange(clerk_user_id: string, role: string) {
    const prev_role = members.find(m => m.clerk_user_id === clerk_user_id)?.role
    setMembers(prev => prev.map(m => m.clerk_user_id === clerk_user_id ? { ...m, role: role as Member["role"] } : m))
    const headers = await buildHeaders(true)
    const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/projects/${activeWorkspace!.id}/members/${clerk_user_id}`, {
      method: "PATCH",
      headers,
      body: JSON.stringify({ role }),
    })
    if (!res.ok) {
      // revert on failure
      setMembers(prev => prev.map(m => m.clerk_user_id === clerk_user_id ? { ...m, role: prev_role as Member["role"] } : m))
      const body = await res.json().catch(() => ({}))
      setError(body.detail ?? "Failed to update role")
    }
  }

  async function handleRemove(clerk_user_id: string) {
    setRemoving(clerk_user_id)
    try {
      const headers = await buildHeaders()
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/projects/${activeWorkspace!.id}/members/${clerk_user_id}`, {
        method: "DELETE", headers,
      })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        setError(body.detail ?? "Failed to remove member")
        return
      }
      setMembers(prev => prev.filter(m => m.clerk_user_id !== clerk_user_id))
    } finally {
      setRemoving(null)
    }
  }

  async function handleCancelInvite(invite_id: string) {
    setCancelling(invite_id)
    try {
      const headers = await buildHeaders()
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/projects/${activeWorkspace!.id}/invites/${invite_id}`, {
        method: "DELETE", headers,
      })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        setError(body.detail ?? "Failed to cancel invite")
        return
      }
      setInvites(prev => prev.filter(i => i.id !== invite_id))
    } finally {
      setCancelling(null)
    }
  }

  const currentUserRole = members.find(m => m.clerk_user_id === currentClerkId)?.role ?? null
  const isAdmin = currentUserRole === "admin"

  if (!activeWorkspace) {
    return <p className="text-sm text-stone-400">No active workspace selected.</p>
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <p className="text-sm text-stone-500">Members of <span className="font-medium text-stone-800">{activeWorkspace.name}</span></p>
        {isAdmin && (
          <button
            onClick={() => { setAddOpen(v => !v); setError("") }}
            className="text-xs font-medium bg-stone-900 text-white px-3 py-1.5 rounded-lg hover:bg-stone-700 transition-colors"
          >
            + Invite member
          </button>
        )}
      </div>

      {/* Invite form — admin only */}
      {isAdmin && addOpen && (
        <div className="rounded-xl border border-stone-200 bg-white px-4 py-4 space-y-3">
          <p className="text-xs font-semibold text-stone-500 uppercase tracking-wider">Invite by email</p>
          <div className="flex gap-2">
            <input
              type="email"
              value={inviteEmail}
              onChange={e => setInviteEmail(e.target.value)}
              onKeyDown={e => e.key === "Enter" && handleInvite()}
              placeholder="colleague@company.com"
              className="flex-1 border border-stone-200 rounded-lg px-3 py-2 text-sm text-stone-900 focus:outline-none focus:ring-2 focus:ring-indigo-200"
              autoFocus
            />
            <select
              value={inviteRole}
              onChange={e => setInviteRole(e.target.value as typeof inviteRole)}
              className="border border-stone-200 rounded-lg px-3 py-2 text-sm text-stone-700 focus:outline-none focus:ring-2 focus:ring-indigo-200"
            >
              <option value="admin">Admin</option>
              <option value="editor">Editor</option>
              <option value="viewer">Viewer</option>
            </select>
          </div>
          <p className="text-[11px] text-stone-500 bg-stone-50 border border-stone-200 rounded-md px-2 py-1.5">
            They'll be added automatically when they sign in to Conduct AI with this email address.
          </p>
          {error && <p className="text-xs text-red-500">{error}</p>}
          <div className="flex gap-2">
            <button
              onClick={handleInvite}
              disabled={saving}
              className="rounded-lg bg-stone-900 px-4 py-2 text-sm font-medium text-white hover:bg-stone-700 disabled:opacity-50 transition-colors"
            >
              {saving ? "Sending…" : "Send invite"}
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

      {emailWarning && (
        <div className="rounded-lg bg-amber-50 border border-amber-200 px-4 py-3 text-xs text-amber-800">
          {emailWarning}
        </div>
      )}

      {/* Pending invites — admin only */}
      {isAdmin && invites.length > 0 && (
        <div>
          <p className="text-xs font-semibold text-stone-400 uppercase tracking-wider mb-2">Pending invites</p>
          <div className="rounded-xl border border-amber-200 bg-amber-50 divide-y divide-amber-100 overflow-hidden">
            {invites.map(inv => (
              <div key={inv.id} className="flex items-center justify-between px-4 py-3">
                <div className="min-w-0">
                  <p className="text-sm text-stone-700 truncate">{inv.invited_email}</p>
                  <p className="text-xs text-stone-400">
                    Invited {new Date(inv.created_at).toLocaleDateString()} · awaiting sign-in
                  </p>
                </div>
                <div className="flex items-center gap-3 shrink-0 ml-4">
                  <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${ROLE_COLORS[inv.role]}`}>
                    {inv.role}
                  </span>
                  <button
                    onClick={() => handleCancelInvite(inv.id)}
                    disabled={cancelling === inv.id}
                    className="text-xs text-stone-400 hover:text-red-500 disabled:opacity-50 transition-colors"
                  >
                    {cancelling === inv.id ? "Cancelling…" : "Cancel"}
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Active members */}
      {loading ? (
        <p className="text-sm text-stone-400">Loading…</p>
      ) : members.length === 0 ? (
        <p className="text-sm text-stone-400">No active members yet.</p>
      ) : (
        <div>
          <p className="text-xs font-semibold text-stone-400 uppercase tracking-wider mb-2">Active members</p>
          <div className="rounded-xl border border-stone-200 bg-white divide-y divide-stone-100 overflow-hidden">
            {members.map(m => (
              <div key={m.clerk_user_id} className="flex items-center justify-between px-4 py-3">
                <div className="min-w-0">
                  <p className="text-sm font-medium text-stone-700 truncate">
                    {m.name || m.email || m.clerk_user_id}
                  </p>
                  {m.email && m.name && (
                    <p className="text-xs text-stone-400 truncate">{m.email}</p>
                  )}
                  <p className="text-xs text-stone-400">Joined {new Date(m.joined_at).toLocaleDateString()}</p>
                </div>
                <div className="flex items-center gap-3 shrink-0 ml-4">
                  {isAdmin ? (
                    <>
                      <select
                        value={m.role}
                        onChange={e => handleRoleChange(m.clerk_user_id, e.target.value)}
                        className={`text-xs font-medium px-2 py-1 rounded-full border-0 focus:outline-none focus:ring-2 focus:ring-indigo-200 cursor-pointer ${ROLE_COLORS[m.role]}`}
                      >
                        <option value="admin">Admin</option>
                        <option value="editor">Editor</option>
                        <option value="viewer">Viewer</option>
                      </select>
                      {m.clerk_user_id !== currentClerkId && (
                        <button
                          onClick={() => handleRemove(m.clerk_user_id)}
                          disabled={removing === m.clerk_user_id}
                          className="text-xs text-stone-400 hover:text-red-500 disabled:opacity-50 transition-colors"
                        >
                          {removing === m.clerk_user_id ? "Removing…" : "Remove"}
                        </button>
                      )}
                    </>
                  ) : (
                    <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${ROLE_COLORS[m.role]}`}>
                      {m.role}
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="rounded-lg bg-stone-50 border border-stone-200 px-4 py-3 text-xs text-stone-500 space-y-1">
        <p><span className="font-medium text-stone-700">Admin</span> — full access: manage members, credentials, environments, workflows, and runs</p>
        <p><span className="font-medium text-stone-700">Editor</span> — run agents, edit workflows, manage credentials and environments; cannot manage members</p>
        <p><span className="font-medium text-stone-700">Viewer</span> — read-only across all screens: view runs, workflows, credentials, and settings</p>
      </div>

      {isAdmin && <GuardInviteSection getToken={getToken} workspaceId={activeWorkspace.id} />}
    </div>
  )
}

// ── Guard invite section ───────────────────────────────────────────────────────

interface GuardMember {
  id: string
  email: string
  role: string
  joined_at: string | null
}

function GuardInviteSection({
  getToken,
  workspaceId,
}: {
  getToken: (() => Promise<string | null>) | null
  workspaceId: string
}) {
  const [teamId, setTeamId] = useState<string | null>(null)
  const [inviteCode, setInviteCode] = useState<string | null>(null)
  const [guardMembers, setGuardMembers] = useState<GuardMember[]>([])
  const [copied, setCopied] = useState(false)
  const [regenerating, setRegenerating] = useState(false)

  async function headers() {
    const h: Record<string, string> = { "Content-Type": "application/json" }
    if (getToken) { const t = await getToken(); if (t) h["Authorization"] = `Bearer ${t}` }
    return h
  }

  useEffect(() => {
    async function load() {
      const base = process.env.NEXT_PUBLIC_API_URL ?? ""
      const h = await headers()
      const res = await fetch(`${base}/guard/teams/installed?workspace_id=${workspaceId}`, { headers: h })
      if (!res.ok) return
      const data = await res.json()
      if (!data.installed) return
      setTeamId(data.team_id)
      setInviteCode(data.invite_code)

      const mRes = await fetch(`${base}/guard/teams/${data.team_id}/members`, { headers: h })
      if (mRes.ok) setGuardMembers(await mRes.json())
    }
    load()
  }, [workspaceId])

  async function regenerate() {
    if (!teamId) return
    setRegenerating(true)
    try {
      const base = process.env.NEXT_PUBLIC_API_URL ?? ""
      const h = await headers()
      const res = await fetch(`${base}/guard/teams/${teamId}/invite/regenerate`, { method: "POST", headers: h })
      if (res.ok) { const d = await res.json(); setInviteCode(d.invite_code) }
    } finally {
      setRegenerating(false)
    }
  }

  function copyCommand() {
    if (!inviteCode) return
    navigator.clipboard.writeText(`conduct guard join ${inviteCode}`)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  if (!inviteCode) return null

  const cmd = `conduct guard join ${inviteCode}`

  return (
    <div className="space-y-3 pt-2">
      <div className="flex items-center gap-2">
        <div className="w-2 h-2 rounded-full bg-indigo-500" />
        <p className="text-xs font-semibold text-stone-700 uppercase tracking-wider">ConductGuard</p>
      </div>

      <div className="rounded-xl border border-indigo-100 bg-indigo-50 px-4 py-4 space-y-3">
        <div>
          <p className="text-xs font-medium text-stone-700 mb-1">Developer invite command</p>
          <p className="text-[11px] text-stone-500 mb-2">
            Share this with developers — they run it once to install Guard and start enforcing your policies.
          </p>
          <div className="flex items-center gap-2">
            <code className="flex-1 bg-stone-900 text-green-400 text-xs font-mono px-3 py-2 rounded-lg truncate">
              {cmd}
            </code>
            <button
              onClick={copyCommand}
              className="shrink-0 text-xs font-medium text-white bg-indigo-600 hover:bg-indigo-700 px-3 py-2 rounded-lg transition-colors"
            >
              {copied ? "Copied!" : "Copy"}
            </button>
          </div>
        </div>
        <div className="flex justify-end">
          <button
            onClick={regenerate}
            disabled={regenerating}
            className="text-[11px] text-stone-400 hover:text-red-500 disabled:opacity-50 transition-colors"
          >
            {regenerating ? "Regenerating…" : "Regenerate invite code"}
          </button>
        </div>
      </div>

      {guardMembers.length > 0 && (
        <div>
          <p className="text-xs font-semibold text-stone-400 uppercase tracking-wider mb-2">
            Guard members ({guardMembers.length})
          </p>
          <div className="rounded-xl border border-stone-200 bg-white divide-y divide-stone-100 overflow-hidden">
            {guardMembers.map(m => (
              <div key={m.id} className="flex items-center justify-between px-4 py-2.5">
                <div>
                  <p className="text-sm text-stone-700">{m.email}</p>
                  {m.joined_at && (
                    <p className="text-xs text-stone-400">Joined {new Date(m.joined_at).toLocaleDateString()}</p>
                  )}
                </div>
                <span className="text-xs font-medium text-stone-500 bg-stone-100 px-2 py-0.5 rounded-full">
                  {m.role}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {guardMembers.length === 0 && (
        <p className="text-xs text-stone-400">No developers have joined yet. Share the command above.</p>
      )}
    </div>
  )
}
