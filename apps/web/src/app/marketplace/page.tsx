"use client"

import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import { useAuth } from "@clerk/nextjs"
import AppShell from "@/components/AppShell"

interface Playbook {
  slug: string
  name: string
  icon: string
  description: string
  tags: string[]
  featured: boolean
}

interface Project {
  id: string
  name: string
}

const ALL_TAGS = ["all", "github", "code", "code-review", "ops", "notifications", "approval"]

function getWorkspaceId(): string | null {
  if (typeof document === "undefined") return null
  return document.cookie.split("; ").find(r => r.startsWith("delegator_project_id="))?.split("=")[1] ?? null
}

const FRIENDLY_NAMES: Record<string, string> = {
  autopilot_quick:    "Autopilot Quick",
  autopilot_full:     "Autopilot Full",
  autopilot_approved: "Autopilot + Approval",
  pr_reviewer:        "PR Reviewer",
  issue_triage:       "Issue Triage",
  release_notes:      "Release Notes",
  ci_notify:          "CI Failure Alert",
  incident_responder: "Incident Responder",
  dependency_updater: "Dependency Updater",
  copilot_reviewer:   "Copilot / AI PR Reviewer",
}

export default function MarketplacePage() {
  const clerkEnabled = !!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY
  if (clerkEnabled) return <MarketplaceWithAuth />
  return <MarketplaceContent getToken={null} />
}

function MarketplaceWithAuth() {
  const { getToken } = useAuth()
  return <MarketplaceContent getToken={getToken} />
}

function MarketplaceContent({ getToken }: { getToken: (() => Promise<string | null>) | null }) {
  const router = useRouter()
  const [playbooks, setPlaybooks] = useState<Playbook[]>([])
  const [loading, setLoading] = useState(true)
  const [activeTag, setActiveTag] = useState("all")
  const [installing, setInstalling] = useState(false)
  const [uninstalling, setUninstalling] = useState<string | null>(null)
  const [confirmingUninstall, setConfirmingUninstall] = useState<string | null>(null)
  // slug → { id, workspaceId } (for uninstall)
  const [installedMap, setInstalledMap] = useState<Map<string, { id: string; workspaceId: string }>>(new Map())

  // Install modal state
  const [pendingSlug, setPendingSlug] = useState<string | null>(null)
  const [projects, setProjects] = useState<Project[]>([])
  const [selectedProjectId, setSelectedProjectId] = useState<string>("")
  const [projectsLoading, setProjectsLoading] = useState(false)

  async function authHeaders(): Promise<Record<string, string>> {
    const headers: Record<string, string> = {}
    if (getToken) {
      const token = await getToken()
      if (token) headers["Authorization"] = `Bearer ${token}`
    }
    return headers
  }

  useEffect(() => {
    async function load() {
      const headers = await authHeaders()
      const workspaceId = getWorkspaceId()
      if (workspaceId) headers["X-Workspace-Id"] = workspaceId

      const [pbRes, wfRes] = await Promise.all([
        fetch(`${process.env.NEXT_PUBLIC_API_URL}/workflows/playbooks`),
        fetch(`${process.env.NEXT_PUBLIC_API_URL}/workflows`, { headers }),
      ])

      if (pbRes.ok) setPlaybooks(await pbRes.json())

      if (wfRes.ok) {
        const workflows: { id: string; name: string; workspace_id: string }[] = await wfRes.json()
        const nameToWf = new Map(workflows.map(w => [w.name, w]))
        const map = new Map<string, { id: string; workspaceId: string }>()
        for (const [slug, friendlyName] of Object.entries(FRIENDLY_NAMES)) {
          const wf = nameToWf.get(friendlyName)
          if (wf) map.set(slug, { id: wf.id, workspaceId: wf.workspace_id })
        }
        setInstalledMap(map)
      }

      setLoading(false)
    }
    load()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function openInstallModal(slug: string) {
    setPendingSlug(slug)
    setProjectsLoading(true)
    try {
      const headers = await authHeaders()
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/projects`, { headers })
      if (res.ok) {
        const data: Project[] = await res.json()
        setProjects(data)
        setSelectedProjectId(data[0]?.id ?? "")
      }
    } finally {
      setProjectsLoading(false)
    }
  }

  function closeInstallModal() {
    setPendingSlug(null)
    setProjects([])
    setSelectedProjectId("")
  }

  async function confirmInstall() {
    if (!pendingSlug || !selectedProjectId) return
    setInstalling(true)
    try {
      const headers = await authHeaders()
      headers["Content-Type"] = "application/json"
      headers["X-Workspace-Id"] = selectedProjectId

      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/workflows`, {
        method: "POST",
        headers,
        body: JSON.stringify({ name: FRIENDLY_NAMES[pendingSlug] ?? pendingSlug, template: pendingSlug }),
      })
      if (!res.ok) return
      const wf = await res.json()
      setInstalledMap(prev => new Map(prev).set(pendingSlug, { id: wf.id, workspaceId: selectedProjectId }))
      closeInstallModal()
      router.push(`/workflows/${wf.id}`)
    } finally {
      setInstalling(false)
    }
  }

  async function uninstall(slug: string) {
    const entry = installedMap.get(slug)
    if (!entry) return
    setUninstalling(slug)
    setConfirmingUninstall(null)
    try {
      const headers = await authHeaders()
      headers["X-Workspace-Id"] = entry.workspaceId

      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/workflows/${entry.id}`, {
        method: "DELETE",
        headers,
      })
      if (!res.ok) return
      setInstalledMap(prev => { const m = new Map(prev); m.delete(slug); return m })
    } finally {
      setUninstalling(null)
    }
  }

  const filtered = activeTag === "all" ? playbooks : playbooks.filter(p => p.tags.includes(activeTag))

  return (
    <AppShell>
      <div className="mx-auto max-w-5xl px-6 py-10">

        {/* Header */}
        <div className="mb-8">
          <h1 className="text-xl font-semibold text-stone-900">Playbooks</h1>
          <p className="text-xs text-stone-400 mt-0.5">Pre-built agent workflows — install in one click, configure and run</p>
        </div>

        {/* Tag filters */}
        <div className="flex flex-wrap gap-2 mb-8">
          {ALL_TAGS.map(tag => (
            <button
              key={tag}
              onClick={() => setActiveTag(tag)}
              className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${
                activeTag === tag
                  ? "bg-stone-900 text-white"
                  : "bg-stone-100 text-stone-500 hover:bg-stone-200"
              }`}
            >
              {tag}
            </button>
          ))}
        </div>

        {loading ? (
          <div className="grid grid-cols-3 gap-4">
            {[1,2,3,4,5,6,7,8,9].map(i => <div key={i} className="h-48 rounded-xl bg-stone-100 animate-pulse" />)}
          </div>
        ) : (
          <div className="grid grid-cols-3 gap-4">
            {filtered.map(p => (
              <PlaybookCard
                key={p.slug}
                playbook={p}
                installing={false}
                installed={installedMap.has(p.slug)}
                uninstalling={uninstalling === p.slug}
                confirming={confirmingUninstall === p.slug}
                onInstall={openInstallModal}
                onUninstallRequest={() => setConfirmingUninstall(p.slug)}
                onUninstallConfirm={() => uninstall(p.slug)}
                onUninstallCancel={() => setConfirmingUninstall(null)}
              />
            ))}
          </div>
        )}
      </div>

      {/* Install modal */}
      {pendingSlug && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="bg-white rounded-xl shadow-xl w-full max-w-sm mx-4 p-6 flex flex-col gap-5">
            <div>
              <h2 className="text-sm font-semibold text-stone-900">Install to project</h2>
              <p className="text-xs text-stone-400 mt-1">
                Choose which project to install <span className="font-medium text-stone-600">{FRIENDLY_NAMES[pendingSlug] ?? pendingSlug}</span> into.
              </p>
            </div>

            {projectsLoading ? (
              <div className="h-9 rounded-lg bg-stone-100 animate-pulse" />
            ) : (
              <select
                value={selectedProjectId}
                onChange={e => setSelectedProjectId(e.target.value)}
                className="w-full rounded-lg border border-stone-200 bg-white px-3 py-2 text-xs text-stone-900 focus:outline-none focus:ring-2 focus:ring-stone-400"
              >
                {projects.map(p => (
                  <option key={p.id} value={p.id}>{p.name}</option>
                ))}
              </select>
            )}

            <div className="flex gap-2 justify-end">
              <button
                onClick={closeInstallModal}
                className="px-4 py-2 text-xs text-stone-500 hover:text-stone-700 rounded-lg hover:bg-stone-100 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={confirmInstall}
                disabled={installing || projectsLoading || !selectedProjectId}
                className="px-4 py-2 text-xs font-medium bg-stone-900 text-white rounded-lg hover:bg-stone-700 disabled:opacity-40 transition-colors"
              >
                {installing ? "Installing…" : "Install"}
              </button>
            </div>
          </div>
        </div>
      )}
    </AppShell>
  )
}

function PlaybookCard({ playbook, installing, installed, uninstalling, confirming, onInstall, onUninstallRequest, onUninstallConfirm, onUninstallCancel }: {
  playbook: Playbook
  installing: boolean
  installed: boolean
  uninstalling: boolean
  confirming: boolean
  onInstall: (slug: string) => void
  onUninstallRequest: () => void
  onUninstallConfirm: () => void
  onUninstallCancel: () => void
}) {
  return (
    <div className={`rounded-xl border bg-white p-5 flex flex-col gap-3 transition-colors ${
      installed ? "border-emerald-200 bg-emerald-50/30" : "border-stone-200 hover:border-stone-300"
    }`}>
      <div className="flex items-start justify-between gap-2">
        <span className="text-2xl leading-none">{playbook.icon}</span>
        <div className="flex flex-wrap gap-1 justify-end">
          {playbook.tags.map(tag => (
            <span key={tag} className="text-[10px] bg-stone-100 text-stone-500 px-1.5 py-0.5 rounded">
              {tag}
            </span>
          ))}
        </div>
      </div>
      <div>
        <p className="text-sm font-semibold text-stone-900 mb-1">
          {FRIENDLY_NAMES[playbook.slug] ?? playbook.name}
        </p>
        <p className="text-xs text-stone-500 leading-relaxed">{playbook.description}</p>
      </div>

      {installed ? (
        confirming ? (
          <div className="mt-auto flex gap-2">
            <button
              onClick={onUninstallCancel}
              className="flex-1 rounded-lg px-3 py-2 text-xs font-medium border border-stone-200 text-stone-500 hover:bg-stone-100 transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={onUninstallConfirm}
              disabled={uninstalling}
              className="flex-1 rounded-lg px-3 py-2 text-xs font-medium bg-red-600 text-white hover:bg-red-700 disabled:opacity-40 transition-colors"
            >
              {uninstalling ? "Removing…" : "Confirm"}
            </button>
          </div>
        ) : (
          <div className="mt-auto flex gap-2">
            <div className="flex-1 rounded-lg px-3 py-2 text-xs font-medium bg-emerald-50 text-emerald-700 border border-emerald-200 text-center">
              ✓ Installed
            </div>
            <button
              onClick={onUninstallRequest}
              className="rounded-lg px-3 py-2 text-xs font-medium border border-stone-200 text-stone-400 hover:text-red-600 hover:border-red-200 transition-colors"
            >
              Remove
            </button>
          </div>
        )
      ) : (
        <button
          onClick={() => onInstall(playbook.slug)}
          disabled={installing}
          className="mt-auto w-full rounded-lg px-3 py-2 text-xs font-medium bg-stone-900 text-white hover:bg-stone-700 disabled:opacity-40 transition-colors"
        >
          {installing ? "Installing…" : "+ Install"}
        </button>
      )}
    </div>
  )
}
