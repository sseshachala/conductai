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

  useEffect(() => {
    fetch(`${process.env.NEXT_PUBLIC_API_URL}/workflows/playbooks`)
      .then(r => r.json())
      .then(data => setPlaybooks(data))
      .finally(() => setLoading(false))
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
      router.push(`/workflows/${wf.id}`)
    } finally {
      setInstalling(null)
    }
  }

  const filtered = activeTag === "all" ? playbooks : playbooks.filter(p => p.tags.includes(activeTag))
  const featured = filtered.filter(p => p.featured)
  const rest = filtered.filter(p => !p.featured)

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
            {filtered.map(p => <PlaybookCard key={p.slug} playbook={p} installing={installing} onInstall={install} />)}
          </div>
        )}
      </div>
    </AppShell>
  )
}

function PlaybookCard({ playbook, installing, onInstall }: {
  playbook: Playbook
  installing: string | null
  onInstall: (slug: string) => void
}) {
  const isInstalling = installing === playbook.slug
  return (
    <div className="rounded-xl border border-stone-200 bg-white p-5 flex flex-col gap-3 hover:border-stone-300 transition-colors">
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
        onClick={() => onInstall(playbook.slug)}
        disabled={!!installing}
        className="mt-auto w-full rounded-lg bg-stone-900 px-3 py-2 text-xs font-medium text-white hover:bg-stone-700 transition-colors disabled:opacity-40"
      >
        {isInstalling ? "Installing…" : "+ Install"}
      </button>
    </div>
  )
}
