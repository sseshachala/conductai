"use client"

import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import { useAuth } from "@clerk/nextjs"
import AuthButton from "@/components/AuthButton"
import NewProjectModal from "@/components/NewProjectModal"

interface Project {
  id: string
  name: string
  workflow_count: number
  created_at: string
  is_approved: boolean
}

function timeAgo(ts: string): string {
  const diff = Date.now() - new Date(ts).getTime()
  const days = Math.floor(diff / 86400000)
  if (days === 0) return "today"
  if (days === 1) return "yesterday"
  if (days < 30) return `${days}d ago`
  return new Date(ts).toLocaleDateString()
}

export default function ProjectsPage() {
  const clerkEnabled = !!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY
  if (clerkEnabled) return <ProjectsWithAuth />
  return <ProjectsContent getToken={null} />
}

function ProjectsWithAuth() {
  const router = useRouter()
  const { getToken, isLoaded, isSignedIn } = useAuth()

  useEffect(() => {
    if (isLoaded && !isSignedIn) router.replace("/")
  }, [isLoaded, isSignedIn, router])

  if (!isLoaded) return null
  return <ProjectsContent getToken={getToken} />
}

function ProjectsContent({ getToken }: { getToken: (() => Promise<string | null>) | null }) {
  const clerkEnabled = !!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY
  const router = useRouter()
  const [projects, setProjects] = useState<Project[]>([])
  const [loading, setLoading] = useState(true)
  const [showModal, setShowModal] = useState(false)

  async function fetchProjects() {
    try {
      const headers: Record<string, string> = {}
      if (getToken) {
        const token = await getToken()
        if (token) headers["Authorization"] = `Bearer ${token}`
      }
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/projects`, { headers })
      if (res.ok) setProjects(await res.json())
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchProjects() }, [])

  function selectProject(id: string) {
    document.cookie = `delegator_project_id=${id}; path=/; max-age=31536000`
    router.push("/workflows")
  }

  const approvedProjects = projects.filter(p => p.is_approved)
  const isPending = !loading && projects.length > 0 && approvedProjects.length === 0

  if (loading) {
    return (
      <div className="min-h-screen bg-stone-50 flex items-center justify-center">
        <div className="w-6 h-6 border-2 border-stone-300 border-t-stone-600 rounded-full animate-spin" />
      </div>
    )
  }

  if (isPending) return <WaitlistScreen />

  return (
    <div className="min-h-screen bg-stone-50">
      <header className="border-b border-stone-200 bg-white px-6 py-3.5 flex items-center justify-between">
        <span className="text-base font-bold text-stone-900 tracking-tight">Delegator</span>
        {clerkEnabled && <AuthButton afterSignOutUrl="/" />}
      </header>

      <main className="mx-auto max-w-3xl px-6 py-10">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-xl font-semibold text-stone-900">Your projects</h1>
            <p className="text-sm text-stone-400 mt-0.5">Each project has its own agents, credentials, and settings</p>
          </div>
          <button
            onClick={() => setShowModal(true)}
            className="rounded-lg bg-stone-900 px-4 py-2 text-sm font-medium text-white hover:bg-stone-700 transition-colors"
          >
            + New project
          </button>
        </div>

        {approvedProjects.length === 0 ? (
          <div className="rounded-xl border border-dashed border-stone-300 p-16 text-center">
            <p className="text-stone-800 font-medium mb-1">No projects yet</p>
            <p className="text-stone-400 text-sm mb-6">Create your first project to get started</p>
            <button
              onClick={() => setShowModal(true)}
              className="inline-block rounded-lg bg-stone-900 px-5 py-2.5 text-sm font-medium text-white hover:bg-stone-700 transition-colors"
            >
              Create your first project
            </button>
          </div>
        ) : (
          <div className="grid gap-2">
            {approvedProjects.map(p => (
              <button
                key={p.id}
                onClick={() => selectProject(p.id)}
                className="flex items-center justify-between rounded-xl border border-stone-200 bg-white px-5 py-4 hover:border-stone-300 hover:shadow-sm transition-all group text-left w-full"
              >
                <div>
                  <p className="font-semibold text-stone-900 group-hover:text-stone-700 transition-colors">{p.name}</p>
                  <p className="text-xs text-stone-400 mt-0.5">
                    {p.workflow_count} agent{p.workflow_count !== 1 ? "s" : ""} · created {timeAgo(p.created_at)}
                  </p>
                </div>
                <span className="text-stone-300 group-hover:text-stone-500 transition-colors text-sm">→</span>
              </button>
            ))}
          </div>
        )}
      </main>

      {showModal && (
        <NewProjectModal
          getToken={getToken}
          onClose={() => setShowModal(false)}
          onCreate={(id) => selectProject(id)}
        />
      )}
    </div>
  )
}

function WaitlistScreen() {
  const clerkEnabled = !!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY
  return (
    <div className="min-h-screen bg-stone-50 flex flex-col">
      <header className="px-6 py-4 flex items-center justify-between max-w-5xl mx-auto w-full">
        <span className="font-bold text-stone-900 text-lg tracking-tight">Delegator</span>
        {clerkEnabled && <AuthButton afterSignOutUrl="/" />}
      </header>

      <main className="flex-1 flex flex-col items-center justify-center px-6 text-center">
        <div className="w-14 h-14 rounded-2xl bg-indigo-50 flex items-center justify-center mb-6">
          <svg className="w-7 h-7 text-indigo-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        </div>

        <h1 className="text-2xl font-bold text-stone-900 mb-2">You&apos;re on the list</h1>
        <p className="text-stone-500 max-w-sm leading-relaxed">
          Thanks for signing up. We&apos;re onboarding teams gradually — we&apos;ll email you as soon as your access is ready.
        </p>

        <div className="mt-8 bg-white border border-stone-200 rounded-xl px-6 py-5 max-w-sm w-full text-left space-y-3">
          <p className="text-xs font-semibold text-stone-400 uppercase tracking-wide">While you wait</p>
          {[
            "Star the repo on GitHub",
            "Join our Slack community",
            "Read the docs",
          ].map(item => (
            <div key={item} className="flex items-center gap-2.5 text-sm text-stone-600">
              <span className="w-1.5 h-1.5 rounded-full bg-indigo-400 shrink-0" />
              {item}
            </div>
          ))}
        </div>
      </main>
    </div>
  )
}
