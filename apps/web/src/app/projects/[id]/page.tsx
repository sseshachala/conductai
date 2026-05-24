"use client"

import { useEffect, useRef, useState } from "react"
import Link from "next/link"
import { useParams, useRouter } from "next/navigation"
import { useAuth } from "@clerk/nextjs"
import AppShell from "@/components/AppShell"

interface Workflow {
  id: string
  name: string
  project_id: string | null
  updated_at: string
  last_run_status: string | null
  last_run_at: string | null
}

interface Project {
  id: string
  name: string
  workspace_id: string
  agent_count: number
}

const RUN_STATUS: Record<string, { label: string; dot: string; text: string; bg: string }> = {
  succeeded: { label: "Last run succeeded", dot: "bg-green-400",  text: "text-green-700",  bg: "bg-green-50"  },
  failed:    { label: "Last run failed",    dot: "bg-red-400",    text: "text-red-600",    bg: "bg-red-50"    },
  running:   { label: "Running now",        dot: "bg-blue-400 animate-pulse", text: "text-blue-700", bg: "bg-blue-50" },
  pending:   { label: "Queued",             dot: "bg-stone-300",  text: "text-stone-500",  bg: "bg-stone-100" },
}

function timeAgo(ts: string): string {
  const diff = Date.now() - new Date(ts).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return "just now"
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}

export default function ProjectPage() {
  const clerkEnabled = !!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY
  if (clerkEnabled) return <ProjectWithAuth />
  return <ProjectContent getToken={null} currentUserId={null} />
}

function ProjectWithAuth() {
  const router = useRouter()
  const { getToken, isLoaded, isSignedIn, userId } = useAuth()
  useEffect(() => {
    if (isLoaded && !isSignedIn) router.replace("/")
  }, [isLoaded, isSignedIn, router])
  if (!isLoaded) return null
  return <ProjectContent getToken={getToken} currentUserId={userId ?? null} />
}

function ProjectContent({ getToken, currentUserId }: {
  getToken: (() => Promise<string | null>) | null
  currentUserId: string | null
}) {
  const { id: projectId } = useParams<{ id: string }>()
  const clerkEnabled = !!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY
  const [project, setProject] = useState<Project | null>(null)
  const [workflows, setWorkflows] = useState<Workflow[]>([])
  const [loading, setLoading] = useState(true)
  const [isAdmin, setIsAdmin] = useState(!clerkEnabled)

  async function authHeaders(): Promise<Record<string, string>> {
    const h: Record<string, string> = {}
    if (getToken) {
      const token = await getToken()
      if (token) h["Authorization"] = `Bearer ${token}`
    }
    // workspace id from cookie
    const wsId = document.cookie.match(/(?:^|;\s*)delegator_project_id=([^;]+)/)?.[1]
    if (wsId) h["X-Workspace-ID"] = wsId
    return h
  }

  useEffect(() => {
    if (!projectId) return
    loadProject()
    loadWorkflows()
  }, [projectId, currentUserId])

  async function loadProject() {
    try {
      const wsId = document.cookie.match(/(?:^|;\s*)delegator_project_id=([^;]+)/)?.[1]
      if (!wsId) return
      const h = await authHeaders()
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/workspaces/${wsId}/projects`,
        { headers: h }
      )
      if (!res.ok) return
      const projects: Project[] = await res.json()
      const found = projects.find(p => p.id === projectId)
      if (found) setProject(found)

      if (clerkEnabled && currentUserId) {
        const mRes = await fetch(
          `${process.env.NEXT_PUBLIC_API_URL}/projects/${wsId}/members`,
          { headers: h }
        )
        if (mRes.ok) {
          const members: { clerk_user_id: string; role: string }[] = await mRes.json()
          setIsAdmin(members.find(m => m.clerk_user_id === currentUserId)?.role === "admin")
        }
      }
    } catch {}
  }

  async function loadWorkflows() {
    try {
      const h = await authHeaders()
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/workflows?project_id=${projectId}`,
        { headers: h }
      )
      if (res.ok) setWorkflows(await res.json())
    } finally {
      setLoading(false)
    }
  }

  async function renameAgent(id: string, name: string) {
    const h = await authHeaders()
    h["Content-Type"] = "application/json"
    const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/workflows/${id}`, {
      method: "PUT", headers: h, body: JSON.stringify({ name }),
    })
    if (res.ok) {
      const updated = await res.json()
      setWorkflows(prev => prev.map(w => w.id === id ? { ...w, name: updated.name } : w))
    }
  }

  async function deleteAgent(id: string) {
    const h = await authHeaders()
    await fetch(`${process.env.NEXT_PUBLIC_API_URL}/workflows/${id}`, { method: "DELETE", headers: h })
    setWorkflows(prev => prev.filter(w => w.id !== id))
  }

  return (
    <AppShell>
      <div className="mx-auto max-w-3xl px-6 py-10">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <p className="text-xs text-stone-400 mb-1">Project</p>
            <h1 className="text-xl font-semibold text-stone-900">
              {project?.name ?? "Loading..."}
            </h1>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-xs text-stone-400">{workflows.length} agent{workflows.length !== 1 ? "s" : ""}</span>
            <Link
              href={`/workflows/new?project_id=${projectId}`}
              className="rounded-lg bg-stone-900 px-4 py-2 text-sm font-medium text-white hover:bg-stone-700 transition-colors"
            >
              + New agent
            </Link>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 border-b border-stone-200 mb-6">
          {["Agents", "Runs"].map(tab => (
            <button
              key={tab}
              className={`px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px ${
                tab === "Agents"
                  ? "border-stone-900 text-stone-900"
                  : "border-transparent text-stone-400 hover:text-stone-700"
              }`}
            >
              {tab}
            </button>
          ))}
        </div>

        {/* Agents list */}
        {loading ? (
          <div className="space-y-2">
            {[1, 2, 3].map(i => (
              <div key={i} className="h-20 rounded-xl border border-stone-200 bg-white animate-pulse" />
            ))}
          </div>
        ) : workflows.length === 0 ? (
          <div className="rounded-xl border border-dashed border-stone-300 px-8 py-12 text-center">
            <p className="text-stone-800 font-semibold mb-2">No agents in this project</p>
            <p className="text-stone-400 text-sm mb-6">Create your first agent or install a playbook.</p>
            <div className="flex items-center justify-center gap-3">
              <Link
                href={`/workflows/new?project_id=${projectId}`}
                className="rounded-lg bg-stone-900 px-5 py-2.5 text-sm font-medium text-white hover:bg-stone-700 transition-colors"
              >
                Create agent →
              </Link>
              <Link
                href="/marketplace"
                className="rounded-lg border border-stone-200 px-5 py-2.5 text-sm font-medium text-stone-700 hover:bg-stone-50 transition-colors"
              >
                Browse playbooks
              </Link>
            </div>
          </div>
        ) : (
          <div className="grid gap-2">
            {workflows.map(w => (
              <AgentCard
                key={w.id}
                workflow={w}
                isAdmin={isAdmin}
                onRename={name => renameAgent(w.id, name)}
                onDelete={() => deleteAgent(w.id)}
              />
            ))}
          </div>
        )}
      </div>
    </AppShell>
  )
}

function AgentCard({ workflow, isAdmin, onRename, onDelete }: {
  workflow: Workflow
  isAdmin: boolean
  onRename: (name: string) => Promise<void>
  onDelete: () => Promise<void>
}) {
  const [menuOpen, setMenuOpen] = useState(false)
  const [renaming, setRenaming] = useState(false)
  const [nameValue, setNameValue] = useState(workflow.name)
  const [confirmValue, setConfirmValue] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const confirmInputRef = useRef<HTMLInputElement>(null)
  const menuRef = useRef<HTMLDivElement>(null)

  useEffect(() => { if (renaming) inputRef.current?.focus() }, [renaming])

  useEffect(() => { if (confirmValue !== null) confirmInputRef.current?.focus() }, [confirmValue])

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuOpen(false)
    }
    document.addEventListener("mousedown", handleClick)
    return () => document.removeEventListener("mousedown", handleClick)
  }, [])

  async function submitRename() {
    const name = nameValue.trim()
    if (name && name !== workflow.name) await onRename(name)
    else setNameValue(workflow.name)
    setRenaming(false)
  }

  const status = workflow.last_run_status ? RUN_STATUS[workflow.last_run_status] : null

  if (confirmValue !== null) {
    return (
      <div className="rounded-xl border border-red-200 bg-red-50 px-5 py-4">
        <p className="text-sm text-red-700 mb-2">
          Type <strong>{workflow.name}</strong> to permanently delete this agent and all its data.
        </p>
        <div className="flex gap-2">
          <input
            ref={confirmInputRef}
            value={confirmValue}
            onChange={e => setConfirmValue(e.target.value)}
            onKeyDown={e => {
              if (e.key === "Enter" && confirmValue === workflow.name) onDelete()
              if (e.key === "Escape") setConfirmValue(null)
            }}
            placeholder={workflow.name}
            className="flex-1 text-sm border border-red-200 rounded-lg px-3 py-1.5 outline-none focus:ring-2 focus:ring-red-300 bg-white"
          />
          <button
            onClick={() => onDelete()}
            disabled={confirmValue !== workflow.name}
            className="text-xs font-medium text-white bg-red-600 hover:bg-red-700 disabled:opacity-40 px-3 py-1.5 rounded-lg transition-colors"
          >Delete</button>
          <button
            onClick={() => setConfirmValue(null)}
            className="text-xs font-medium text-stone-600 border border-stone-200 hover:bg-stone-50 px-3 py-1.5 rounded-lg transition-colors"
          >Cancel</button>
        </div>
      </div>
    )
  }

  return (
    <div className="flex items-center justify-between rounded-xl border border-stone-200 bg-white px-5 py-4 hover:border-stone-300 hover:shadow-sm transition-all group">
      <Link href={renaming ? "#" : `/workflows/${workflow.id}`} className="flex-1 min-w-0" onClick={renaming ? e => e.preventDefault() : undefined}>
        {renaming ? (
          <input
            ref={inputRef}
            value={nameValue}
            onChange={e => setNameValue(e.target.value)}
            onBlur={submitRename}
            onKeyDown={e => { if (e.key === "Enter") submitRename(); if (e.key === "Escape") { setNameValue(workflow.name); setRenaming(false) } }}
            onClick={e => e.preventDefault()}
            className="text-sm font-semibold text-stone-900 bg-transparent border-b border-indigo-400 outline-none w-full"
          />
        ) : (
          <p className="font-semibold text-stone-900 truncate">{workflow.name}</p>
        )}
        <p className="text-xs text-stone-400 mt-0.5">edited {timeAgo(workflow.updated_at)}</p>
      </Link>

      <div className="flex items-center gap-3 ml-3 shrink-0">
        {status ? (
          <span className={`flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full ${status.bg} ${status.text}`}>
            <span className={`w-1.5 h-1.5 rounded-full ${status.dot}`} />
            {status.label}
          </span>
        ) : (
          <span className="text-xs text-stone-400 italic">never run</span>
        )}
        {workflow.last_run_at && <span className="text-xs text-stone-400">{timeAgo(workflow.last_run_at)}</span>}

        {isAdmin && (
          <div className="relative" ref={menuRef}>
            <button
              onClick={e => { e.preventDefault(); setMenuOpen(v => !v) }}
              className="p-1.5 rounded-lg text-stone-300 hover:text-stone-600 hover:bg-stone-100 transition-colors opacity-0 group-hover:opacity-100"
            >
              <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                <path d="M10 6a2 2 0 1 1 0-4 2 2 0 0 1 0 4zm0 6a2 2 0 1 1 0-4 2 2 0 0 1 0 4zm0 6a2 2 0 1 1 0-4 2 2 0 0 1 0 4z" />
              </svg>
            </button>
            {menuOpen && (
              <div className="absolute right-0 top-8 z-20 w-36 bg-white rounded-xl border border-stone-200 shadow-lg py-1">
                <button onClick={() => { setMenuOpen(false); setRenaming(true) }} className="w-full text-left px-4 py-2 text-sm text-stone-700 hover:bg-stone-50">Rename</button>
                <button onClick={() => { setMenuOpen(false); setConfirmValue("") }} className="w-full text-left px-4 py-2 text-sm text-red-600 hover:bg-red-50">Delete</button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
