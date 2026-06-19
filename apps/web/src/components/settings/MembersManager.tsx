"use client"

import React, { useState, useEffect } from "react"
import { useAuth } from "@clerk/nextjs"
import { useWorkspace } from "@/lib/WorkspaceContext"

interface Member {
  clerk_user_id: string
  role: "admin" | "developer" | "security" | "viewer"
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

interface MemberWorkspace {
  id: string
  name: string
  role: string
  joined_at: string
}

const ROLE_COLORS: Record<string, React.CSSProperties> = {
  admin:     { background: "var(--accent-weak)", color: "var(--accent-text)" },
  developer: { background: "var(--ok-bg)", color: "var(--ok)" },
  security:  { background: "var(--info-bg, #ede9fe)", color: "var(--info, #7c3aed)" },
  viewer:    { background: "var(--surface-3)", color: "var(--text-3)" },
}

const AVATAR_PALETTE = ["#4f46e5", "#7c3aed", "#059669", "#2563eb", "#d97706", "#dc2626", "#0e7490"]

function getInitials(name: string | null, email: string | null): string {
  if (name) {
    const parts = name.trim().split(/\s+/)
    if (parts.length >= 2) return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
    return parts[0].slice(0, 2).toUpperCase()
  }
  if (email) return email[0].toUpperCase()
  return "?"
}

function getAvatarColor(initials: string): string {
  let hash = 0
  for (let i = 0; i < initials.length; i++) hash = (hash * 31 + initials.charCodeAt(i)) & 0xffffffff
  return AVATAR_PALETTE[Math.abs(hash) % AVATAR_PALETTE.length]
}

function getGuardAccess(role: string): string {
  if (role === "admin") return "Full"
  if (role === "security") return "Policies + activity"
  if (role === "developer") return "View · own spend"
  return "Own activity"
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
  const [inviteRole, setInviteRole] = useState<"admin" | "developer" | "security" | "viewer">("developer")
  const [saving, setSaving] = useState(false)
  const [removing, setRemoving] = useState<string | null>(null)
  const [cancelling, setCancelling] = useState<string | null>(null)
  const [confirmMemberId, setConfirmMemberId] = useState<string | null>(null)
  const [confirmMemberValue, setConfirmMemberValue] = useState("")
  const [confirmInviteId, setConfirmInviteId] = useState<string | null>(null)
  const [confirmInviteValue, setConfirmInviteValue] = useState("")
  const [error, setError] = useState("")
  const [emailWarning, setEmailWarning] = useState("")
  const [expandedMember, setExpandedMember] = useState<string | null>(null)
  const [memberWorkspaces, setMemberWorkspaces] = useState<Record<string, MemberWorkspace[]>>({})
  const [loadingWorkspaces, setLoadingWorkspaces] = useState<string | null>(null)

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
      setInviteRole("developer")
      setAddOpen(false)
      if (data.email_sent === false) {
        setEmailWarning(`Invite created but the notification email couldn't be delivered to ${email}. Ask them to sign in at conductai.ai and they'll be added automatically.`)
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

  async function toggleMemberWorkspaces(clerk_user_id: string) {
    if (expandedMember === clerk_user_id) {
      setExpandedMember(null)
      return
    }
    setExpandedMember(clerk_user_id)
    if (memberWorkspaces[clerk_user_id]) return
    setLoadingWorkspaces(clerk_user_id)
    try {
      const headers = await buildHeaders()
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/projects/${activeWorkspace!.id}/members/${clerk_user_id}/workspaces`,
        { headers },
      )
      if (res.ok) {
        const data = await res.json()
        setMemberWorkspaces(prev => ({ ...prev, [clerk_user_id]: data }))
      }
    } finally {
      setLoadingWorkspaces(null)
    }
  }

  const currentUserRole = members.find(m => m.clerk_user_id === currentClerkId)?.role ?? null
  const isAdmin = currentUserRole === "admin"

  if (!activeWorkspace) {
    return <p style={{ fontSize: 13, color: "var(--text-muted)" }}>No active workspace selected.</p>
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      <div style={{ display: "flex", alignItems: "center", marginBottom: 16 }}>
        <span style={{ fontSize: 13.5, color: "var(--text-3)" }}>
          <b style={{ color: "var(--text)" }}>{members.length} members</b> · roles control Guard access and approval rights
        </span>
        {isAdmin && (
          <button className="btn btn-primary btn-sm" style={{ marginLeft: "auto" }}
            onClick={() => { setAddOpen(v => !v); setError("") }}>
            + Invite member
          </button>
        )}
      </div>

      {isAdmin && addOpen && (
        <div className="card" style={{ padding: "16px 18px", display: "flex", flexDirection: "column", gap: 12 }}>
          <p className="eyebrow">Invite by email</p>
          <div style={{ display: "flex", gap: 8 }}>
            <input
              type="email"
              value={inviteEmail}
              onChange={e => setInviteEmail(e.target.value)}
              onKeyDown={e => e.key === "Enter" && handleInvite()}
              placeholder="colleague@company.com"
              style={{ flex: 1, border: "1px solid var(--border)", borderRadius: 9, padding: "8px 12px", fontSize: 13.5, color: "var(--text)", background: "var(--surface)", outline: "none" }}
              autoFocus
            />
            <select
              value={inviteRole}
              onChange={e => setInviteRole(e.target.value as typeof inviteRole)}
              style={{ border: "1px solid var(--border)", borderRadius: 9, padding: "8px 12px", fontSize: 13, color: "var(--text)", background: "var(--surface)", outline: "none" }}
            >
              <option value="admin">Admin</option>
              <option value="developer">Developer</option>
              <option value="security">Security</option>
              <option value="viewer">Viewer</option>
            </select>
          </div>
          <p style={{ fontSize: 11.5, color: "var(--text-muted)", background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: 7, padding: "6px 10px" }}>
            They&apos;ll be added automatically when they sign in to Conduct AI with this email address.
          </p>
          {error && <p style={{ fontSize: 12, color: "var(--err)" }}>{error}</p>}
          <div style={{ display: "flex", gap: 8 }}>
            <button onClick={handleInvite} disabled={saving} className="btn btn-primary btn-sm" style={{ opacity: saving ? 0.5 : 1 }}>
              {saving ? "Sending…" : "Send invite"}
            </button>
            <button onClick={() => { setAddOpen(false); setError("") }} className="btn btn-ghost btn-sm">Cancel</button>
          </div>
        </div>
      )}

      {emailWarning && (
        <div className="card" style={{ padding: "12px 16px", background: "var(--warn-bg)", borderColor: "var(--warn-bd)", fontSize: 12.5, color: "var(--warn)" }}>
          {emailWarning}
        </div>
      )}

      {isAdmin && invites.length > 0 && (
        <div>
          <p className="eyebrow" style={{ marginBottom: 8 }}>Pending invites</p>
          <div className="card" style={{ padding: 0, overflow: "hidden", borderColor: "var(--warn-bd)", background: "var(--warn-bg)" }}>
            {invites.map((inv, idx) => (
              <div key={inv.id} style={{ padding: "12px 16px", borderTop: idx ? "1px solid var(--warn-bd)" : "none" }}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
                  <div style={{ minWidth: 0 }}>
                    <p style={{ fontSize: 13.5, color: "var(--text)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{inv.invited_email}</p>
                    <p style={{ fontSize: 11.5, color: "var(--text-muted)", marginTop: 2 }}>
                      Invited {new Date(inv.created_at).toLocaleDateString()} · awaiting sign-in
                    </p>
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: 10, flexShrink: 0, marginLeft: 14 }}>
                    <span className="chip" style={{ textTransform: "capitalize" }}>{inv.role}</span>
                    <button
                      onClick={() => {
                        if (confirmInviteId === inv.id) {
                          setConfirmInviteId(null)
                          setConfirmInviteValue("")
                        } else {
                          setConfirmInviteId(inv.id)
                          setConfirmInviteValue("")
                        }
                      }}
                      disabled={cancelling === inv.id}
                      className="btn btn-ghost btn-sm"
                      style={{ fontSize: 12, opacity: cancelling === inv.id ? 0.5 : 1 }}
                    >
                      {cancelling === inv.id ? "Cancelling…" : "Cancel"}
                    </button>
                  </div>
                </div>

                {confirmInviteId === inv.id && (
                  <div style={{ marginTop: 10, padding: "10px 12px", border: "1px solid var(--err-bd)", borderRadius: 10, background: "var(--err-bg)", display: "flex", flexDirection: "column", gap: 8 }}>
                    <p style={{ fontSize: 11.5, color: "var(--err)", margin: 0 }}>
                      Type <strong>{inv.invited_email}</strong> to confirm invite cancellation.
                    </p>
                    <div style={{ display: "flex", gap: 6 }}>
                      <input
                        value={confirmInviteValue}
                        onChange={e => setConfirmInviteValue(e.target.value)}
                        onKeyDown={e => {
                          if (e.key === "Enter" && confirmInviteValue === inv.invited_email) handleCancelInvite(inv.id)
                          if (e.key === "Escape") { setConfirmInviteId(null); setConfirmInviteValue("") }
                        }}
                        placeholder={inv.invited_email}
                        style={{ flex: 1, fontSize: 12, border: "1px solid var(--err-bd, #fecaca)", borderRadius: 8, padding: "6px 10px", outline: "none", background: "var(--surface)", color: "var(--text)" }}
                      />
                      <button
                        onClick={() => handleCancelInvite(inv.id)}
                        disabled={cancelling === inv.id || confirmInviteValue !== inv.invited_email}
                        className="btn btn-sm"
                        style={{ fontSize: 12, background: "var(--err)", color: "#fff", border: "none", opacity: cancelling === inv.id || confirmInviteValue !== inv.invited_email ? 0.5 : 1 }}
                      >
                        {cancelling === inv.id ? "…" : "Confirm"}
                      </button>
                      <button
                        onClick={() => { setConfirmInviteId(null); setConfirmInviteValue("") }}
                        className="btn btn-ghost btn-sm"
                        style={{ fontSize: 12 }}
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {loading ? (
        <p style={{ fontSize: 13, color: "var(--text-muted)" }}>Loading…</p>
      ) : members.length === 0 ? (
        <p style={{ fontSize: 13, color: "var(--text-muted)" }}>No active members yet.</p>
      ) : (
        <div className="card" style={{ overflow: "hidden" }}>
          <div style={{ display: "grid", gridTemplateColumns: "1.8fr 1fr 1fr 90px", gap: 14, padding: "11px 20px", borderBottom: "1px solid var(--border)", background: "var(--surface-2)" }}>
            {["Member", "Role", "Guard access", ""].map((h, i) => (
              <div key={i} className="eyebrow" style={{ fontSize: 10 }}>{h}</div>
            ))}
          </div>
          {members.map(m => {
            const initials = getInitials(m.name, m.email)
            const avatarColor = getAvatarColor(initials)
            return (
              <div key={m.clerk_user_id}>
                <div style={{ display: "grid", gridTemplateColumns: "1.8fr 1fr 1fr 90px", gap: 14, padding: "12px 20px", borderBottom: "1px solid var(--border)", alignItems: "center" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 11 }}>
                    <div className="avatar" style={{ background: avatarColor }}>{initials}</div>
                    <div>
                      <div style={{ fontWeight: 600, fontSize: 13.5 }}>{m.name || m.email || m.clerk_user_id}</div>
                      {m.email && <div className="mono" style={{ fontSize: 11, color: "var(--text-muted)" }}>{m.email}</div>}
                    </div>
                  </div>
                  <div>
                    {isAdmin ? (
                      <select
                        value={m.role}
                        onChange={e => handleRoleChange(m.clerk_user_id, e.target.value)}
                        className="chip"
                        style={{ height: 22, textTransform: "capitalize", fontSize: 12,
                          color: m.role === "admin" ? "var(--accent-text)" : m.role === "security" ? "var(--ok)" : "var(--text-2)",
                          borderColor: m.role === "admin" ? "var(--accent-ring)" : m.role === "security" ? "var(--ok-bd)" : "var(--border)",
                          border: "1px solid", background: "transparent", cursor: "pointer", padding: "0 8px" }}
                      >
                        <option value="admin">admin</option>
                        <option value="developer">developer</option>
                        <option value="security">security</option>
                        <option value="viewer">viewer</option>
                      </select>
                    ) : (
                      <span className="chip" style={{ height: 22, textTransform: "capitalize",
                        color: m.role === "admin" ? "var(--accent-text)" : m.role === "security" ? "var(--ok)" : "var(--text-2)",
                        borderColor: m.role === "admin" ? "var(--accent-ring)" : m.role === "security" ? "var(--ok-bd)" : "var(--border)" }}>
                        {m.role}
                      </span>
                    )}
                  </div>
                  <div style={{ fontSize: 12.5, color: "var(--text-3)" }}>{getGuardAccess(m.role)}</div>
                  <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                    {isAdmin && (
                      <button className="btn btn-ghost btn-sm btn-icon" aria-label="Member workspace settings" onClick={() => toggleMemberWorkspaces(m.clerk_user_id)}>⚙</button>
                    )}
                    {isAdmin && m.clerk_user_id !== currentClerkId && (
                      <button
                        onClick={() => {
                          if (confirmMemberId === m.clerk_user_id) {
                            setConfirmMemberId(null)
                            setConfirmMemberValue("")
                          } else {
                            setConfirmMemberId(m.clerk_user_id)
                            setConfirmMemberValue("")
                          }
                        }}
                        disabled={removing === m.clerk_user_id}
                        aria-label={`Remove ${m.email || m.name || "member"}`}
                        style={{ fontSize: 13, color: "var(--text-muted)", background: "none", border: "none", cursor: "pointer", opacity: removing === m.clerk_user_id ? 0.4 : 1 }}
                      >
                        {removing === m.clerk_user_id ? "…" : "×"}
                      </button>
                    )}
                  </div>
                </div>
                {isAdmin && m.clerk_user_id !== currentClerkId && confirmMemberId === m.clerk_user_id && (
                  <div style={{ padding: "10px 20px 12px", borderBottom: "1px solid var(--border)", background: "var(--err-bg)", display: "flex", flexDirection: "column", gap: 8 }}>
                    <p style={{ fontSize: 11.5, color: "var(--err)", margin: 0 }}>
                      Type <strong>{m.email || m.name || m.clerk_user_id}</strong> to confirm member removal.
                    </p>
                    <div style={{ display: "flex", gap: 6 }}>
                      <input
                        value={confirmMemberValue}
                        onChange={e => setConfirmMemberValue(e.target.value)}
                        onKeyDown={e => {
                          const expected = m.email || m.name || m.clerk_user_id
                          if (e.key === "Enter" && confirmMemberValue === expected) handleRemove(m.clerk_user_id)
                          if (e.key === "Escape") { setConfirmMemberId(null); setConfirmMemberValue("") }
                        }}
                        placeholder={m.email || m.name || m.clerk_user_id}
                        style={{ flex: 1, fontSize: 12, border: "1px solid var(--err-bd, #fecaca)", borderRadius: 8, padding: "6px 10px", outline: "none", background: "var(--surface)", color: "var(--text)" }}
                      />
                      <button
                        onClick={() => handleRemove(m.clerk_user_id)}
                        disabled={removing === m.clerk_user_id || confirmMemberValue !== (m.email || m.name || m.clerk_user_id)}
                        className="btn btn-sm"
                        style={{ fontSize: 12, background: "var(--err)", color: "#fff", border: "none", opacity: removing === m.clerk_user_id || confirmMemberValue !== (m.email || m.name || m.clerk_user_id) ? 0.5 : 1 }}
                      >
                        {removing === m.clerk_user_id ? "…" : "Confirm"}
                      </button>
                      <button
                        onClick={() => { setConfirmMemberId(null); setConfirmMemberValue("") }}
                        style={{ fontSize: 12, color: "var(--text-muted)", background: "none", border: "none", cursor: "pointer" }}
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                )}
                {isAdmin && expandedMember === m.clerk_user_id && (
                  <div style={{ padding: "12px 20px", background: "var(--surface-2)", borderBottom: "1px solid var(--border)" }}>
                    <p className="eyebrow" style={{ marginBottom: 8 }}>Workspaces</p>
                    {loadingWorkspaces === m.clerk_user_id ? (
                      <p style={{ fontSize: 12, color: "var(--text-muted)" }}>Loading…</p>
                    ) : (memberWorkspaces[m.clerk_user_id] ?? []).length === 0 ? (
                      <p style={{ fontSize: 12, color: "var(--text-muted)" }}>No workspaces found.</p>
                    ) : (
                      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                        {(memberWorkspaces[m.clerk_user_id] ?? []).map(ws => (
                          <div key={ws.id} style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                            <p style={{ fontSize: 12.5, color: "var(--text-2)" }}>{ws.name}</p>
                            <span className="chip" style={{ textTransform: "capitalize", fontSize: 11 }}>{ws.role}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      <div className="card" style={{ padding: "12px 16px", background: "var(--surface-2)", display: "flex", flexDirection: "column", gap: 5 }}>
        <p style={{ fontSize: 12, color: "var(--text-2)" }}><span style={{ fontWeight: 600, color: "var(--text)" }}>Admin</span> — full access: manage members, credentials, environments, workflows, and runs</p>
        <p style={{ fontSize: 12, color: "var(--text-2)" }}><span style={{ fontWeight: 600, color: "var(--text)" }}>Developer</span> — run agents, edit workflows, manage credentials and environments; cannot manage members</p>
        <p style={{ fontSize: 12, color: "var(--text-2)" }}><span style={{ fontWeight: 600, color: "var(--text)" }}>Security</span> — read-only access plus Guard policy management and all-member activity review</p>
        <p style={{ fontSize: 12, color: "var(--text-2)" }}><span style={{ fontWeight: 600, color: "var(--text)" }}>Viewer</span> — read-only across all screens: view runs, workflows, credentials, and settings</p>
      </div>
    </div>
  )
}
