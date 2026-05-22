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
  const [installing, setInstalling] = useState<string | null>(null)
  const [installedSlugs, setInstalledSlugs] = useState<Set<string>>(new Set())

  useEffect(() => {
    async function load() {
      const headers: Record<string, string> = {}
      if (getToken) {
        const token = await getToken()
        if (token) headers["Authorization"] = `Bearer ${token}`
      }
      const workspaceId = getWorkspaceId()
      if (workspaceId) headers["X-Workspace-Id"] = workspaceId

      const [pbRes, wfRes] = await Promise.all([
        fetch(`${process.env.NEXT_PUBLIC_API_URL}/workflows/playbooks`),
        fetch(`${process.env.NEXT_PUBLIC_API_URL}/workflows`, { headers }),
      ])

      if (pbRes.ok) setPlaybooks(await pbRes.json())

      if (wfRes.ok) {
        const workflows: { name: string }[] = await wfRes.json()
        const installedNames = new Set(workflows.map(w => w.name))
        const matched = new Set(
          Object.entries(FRIENDLY_NAMES)
            .filter(([, name]) => installedNames.has(name))
            .map(([slug]) => slug)
        )
        setInstalledSlugs(matched)
      }

      setLoading(false)
    }
    load()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function install(slug: string) {
    setInstalling(slug)
    try {
      const headers: Record<string, string> = { "Content-Type": "application/json" }
      if (getToken) {
        const token = await getToken()
        if (token) headers["Authorization"] = `Bearer ${token}`
      }
      const workspaceId = getWorkspaceId()
      if (workspaceId) headers["X-Workspace-Id"] = workspaceId

      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/workflows`, {
        method: "POST",
        headers,
        body: JSON.stringify({ name: FRIENDLY_NAMES[slug] ?? slug, template: slug }),
      })
      if (!res.ok) return
      const wf = await res.json()
      setInstalledSlugs(prev => new Set([...prev, slug]))
      router.push(`/workflows/${wf.id}`)
    } finally {
      setInstalling(null)
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
                installing={installing}
                installed={installedSlugs.has(p.slug)}
                onInstall={install}
              />
            ))}
          </div>
        )}
      </div>
    </AppShell>
  )
}

function PlaybookCard({ playbook, installing, installed, onInstall }: {
  playbook: Playbook
  installing: string | null
  installed: boolean
  onInstall: (slug: string) => void
}) {
  const isInstalling = installing === playbook.slug
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
      <button
        onClick={() => !installed && onInstall(playbook.slug)}
        disabled={!!installing || installed}
        className={`mt-auto w-full rounded-lg px-3 py-2 text-xs font-medium transition-colors ${
          installed
            ? "bg-emerald-50 text-emerald-700 border border-emerald-200 cursor-default"
            : "bg-stone-900 text-white hover:bg-stone-700 disabled:opacity-40"
        }`}
      >
        {isInstalling ? "Installing…" : installed ? "✓ Installed" : "+ Install"}
      </button>
    </div>
  )
}
