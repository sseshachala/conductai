"use client"

import { useState } from "react"

interface Props {
  getToken: (() => Promise<string | null>) | null
  onClose: () => void
  onCreate: (projectId: string) => void
}

export default function NewProjectModal({ getToken, onClose, onCreate }: Props) {
  const [name, setName] = useState("")
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState("")

  async function handleCreate() {
    if (!name.trim()) { setError("Project name is required"); return }
    setSaving(true)
    setError("")
    try {
      const headers: Record<string, string> = { "Content-Type": "application/json" }
      if (getToken) {
        const token = await getToken()
        if (token) headers["Authorization"] = `Bearer ${token}`
      }
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/projects`, {
        method: "POST",
        headers,
        body: JSON.stringify({ name: name.trim() }),
      })
      if (!res.ok) {
        let msg = "Failed to create project — please try again."
        try { const b = await res.json(); if (b.detail) msg = b.detail } catch {}
        setError(msg)
        return
      }
      const project = await res.json()
      onCreate(project.id)
    } catch {
      setError("Failed to create project — please try again.")
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={onClose}>
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-md mx-4 p-6" onClick={e => e.stopPropagation()}>
        <h2 className="text-lg font-semibold text-stone-900 mb-1">New project</h2>
        <p className="text-sm text-stone-400 mb-5">A project holds your agents, credentials, and settings.</p>

        <div className="mb-5">
          <label className="text-xs font-medium text-stone-500 block mb-1.5">Project name</label>
          <input
            autoFocus
            type="text"
            value={name}
            onChange={e => setName(e.target.value)}
            onKeyDown={e => e.key === "Enter" && handleCreate()}
            placeholder="e.g. Acme Backend, Mobile App"
            className="w-full border border-stone-200 rounded-lg px-3 py-2.5 text-sm text-stone-900 focus:outline-none focus:ring-2 focus:ring-indigo-200"
          />
        </div>

        {error && <p className="text-xs text-red-500 mb-3">{error}</p>}

        <div className="flex gap-2">
          <button
            onClick={handleCreate}
            disabled={saving || !name.trim()}
            className="rounded-lg bg-stone-900 px-5 py-2 text-sm font-medium text-white hover:bg-stone-700 disabled:opacity-50 transition-colors"
          >
            {saving ? "Creating…" : "Create project"}
          </button>
          <button
            onClick={onClose}
            className="rounded-lg border border-stone-200 px-5 py-2 text-sm text-stone-600 hover:bg-stone-50 transition-colors"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  )
}
