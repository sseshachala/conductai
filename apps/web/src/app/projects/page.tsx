"use client"

import { useEffect, useRef, useState } from "react"
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

  async function authHeaders(): Promise<Record<string, string>> {
    const h: Record<string, string> = {}
    if (getToken) {
      const token = await getToken()
      if (token) h["Authorization"] = `Bearer ${token}`
    }
    return h
  }

  async function fetchProjects() {
    try {
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/projects`, { headers: await authHeaders() })
      if (res.ok) setProjects(await res.json())
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchProjects() }, [])

  function selectProject(id: string, name?: string) {
    document.cookie = `delegator_project_id=${id}; path=/; max-age=31536000`
    if (name) document.cookie = `delegator_project_name=${encodeURIComponent(name)}; path=/; max-age=31536000`
    router.push("/workflows")
  }

  async function renameProject(id: string, name: string) {
    const h = await authHeaders()
    h["Content-Type"] = "application/json"
    const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/projects/${id}`, {
      method: "PATCH", headers: h, body: JSON.stringify({ name }),
    })
    if (res.ok) {
      const updated = await res.json()
      setProjects(prev => prev.map(p => p.id === id ? { ...p, name: updated.name } : p))
    }
  }

  async function deleteProject(id: string) {
    const h = await authHeaders()
    await fetch(`${process.env.NEXT_PUBLIC_API_URL}/projects/${id}`, { method: "DELETE", headers: h })
    setProjects(prev => prev.filter(p => p.id !== id))
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-stone-50 flex items-center justify-center">
        <div className="w-6 h-6 border-2 border-stone-300 border-t-stone-600 rounded-full animate-spin" />
      </div>
    )
  }

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

        {projects.length === 0 ? (
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
            {projects.map(p => (
              <ProjectCard
                key={p.id}
                project={p}
                onSelect={() => selectProject(p.id, p.name)}
                onRename={(name) => renameProject(p.id, name)}
                onDelete={() => deleteProject(p.id)}
              />
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

function ProjectCard({
  project, onSelect, onRename, onDelete,
}: {
  project: Project
  onSelect: () => void
  onRename: (name: string) => Promise<void>
  onDelete: () => Promise<void>
}) {
  const [menuOpen, setMenuOpen] = useState(false)
  const [renaming, setRenaming] = useState(false)
  const [nameValue, setNameValue] = useState(project.name)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const menuRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (renaming) inputRef.current?.focus()
  }, [renaming])

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuOpen(false)
    }
    document.addEventListener("mousedown", handleClick)
    return () => document.removeEventListener("mousedown", handleClick)
  }, [])

  async function submitRename() {
    const name = nameValue.trim()
    if (name && name !== project.name) await onRename(name)
    else setNameValue(project.name)
    setRenaming(false)
  }

  if (confirmDelete) {
    return (
      <div className="flex items-center justify-between rounded-xl border border-red-200 bg-red-50 px-5 py-4">
        <p className="text-sm text-red-700">Delete <span className="font-semibold">{project.name}</span>? This removes all agents and runs.</p>
        <div className="flex gap-2 ml-4 shrink-0">
          <button onClick={() => onDelete()} className="text-xs font-medium text-white bg-red-600 hover:bg-red-700 px-3 py-1.5 rounded-lg transition-colors">Delete</button>
          <button onClick={() => setConfirmDelete(false)} className="text-xs font-medium text-stone-600 border border-stone-200 hover:bg-stone-50 px-3 py-1.5 rounded-lg transition-colors">Cancel</button>
        </div>
      </div>
    )
  }

  return (
    <div className="flex items-center justify-between rounded-xl border border-stone-200 bg-white px-5 py-4 hover:border-stone-300 hover:shadow-sm transition-all group">
      <button className="flex-1 text-left min-w-0" onClick={renaming ? undefined : onSelect}>
        {renaming ? (
          <input
            ref={inputRef}
            value={nameValue}
            onChange={e => setNameValue(e.target.value)}
            onBlur={submitRename}
            onKeyDown={e => { if (e.key === "Enter") submitRename(); if (e.key === "Escape") { setNameValue(project.name); setRenaming(false) } }}
            onClick={e => e.stopPropagation()}
            className="text-sm font-semibold text-stone-900 bg-transparent border-b border-indigo-400 outline-none w-full"
          />
        ) : (
          <p className="font-semibold text-stone-900 group-hover:text-stone-700 transition-colors truncate">{project.name}</p>
        )}
        <p className="text-xs text-stone-400 mt-0.5">
          {project.workflow_count} agent{project.workflow_count !== 1 ? "s" : ""} · created {timeAgo(project.created_at)}
        </p>
      </button>

      <div className="relative ml-3 shrink-0" ref={menuRef}>
        <button
          onClick={e => { e.stopPropagation(); setMenuOpen(v => !v) }}
          className="p-1.5 rounded-lg text-stone-300 hover:text-stone-600 hover:bg-stone-100 transition-colors opacity-0 group-hover:opacity-100"
        >
          <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
            <path d="M10 6a2 2 0 1 1 0-4 2 2 0 0 1 0 4zm0 6a2 2 0 1 1 0-4 2 2 0 0 1 0 4zm0 6a2 2 0 1 1 0-4 2 2 0 0 1 0 4z" />
          </svg>
        </button>
        {menuOpen && (
          <div className="absolute right-0 top-8 z-20 w-36 bg-white rounded-xl border border-stone-200 shadow-lg py-1">
            <button
              onClick={() => { setMenuOpen(false); setRenaming(true) }}
              className="w-full text-left px-4 py-2 text-sm text-stone-700 hover:bg-stone-50"
            >
              Rename
            </button>
            <button
              onClick={() => { setMenuOpen(false); setConfirmDelete(true) }}
              className="w-full text-left px-4 py-2 text-sm text-red-600 hover:bg-red-50"
            >
              Delete
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
