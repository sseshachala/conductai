"use client"

import { useEffect, useState } from "react"

interface Template {
  id: string
  slug: string
  name: string
  description: string
}

interface Props {
  getToken: (() => Promise<string | null>) | null
  onClose: () => void
  onCreate: (projectId: string) => void
}

export default function NewProjectModal({ getToken, onClose, onCreate }: Props) {
  const [name, setName] = useState("")
  const [templates, setTemplates] = useState<Template[]>([])
  const [selectedTemplate, setSelectedTemplate] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState("")

  useEffect(() => {
    fetch(`${process.env.NEXT_PUBLIC_API_URL}/projects/templates`)
      .then(r => r.json())
      .then(setTemplates)
      .catch(() => {})
  }, [])

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
        body: JSON.stringify({ name: name.trim(), template_id: selectedTemplate }),
      })
      if (!res.ok) throw new Error("Failed")
      const project = await res.json()
      onCreate(project.id)
    } catch {
      setError("Failed to create project — please try again")
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={onClose}>
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-lg mx-4 p-6" onClick={e => e.stopPropagation()}>
        <h2 className="text-lg font-semibold text-stone-900 mb-4">New project</h2>

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

        <div className="mb-5">
          <p className="text-xs font-medium text-stone-500 mb-2">
            Start from a template <span className="font-normal text-stone-400">(optional)</span>
          </p>
          <div className="grid gap-2">
            <TemplateCard id={null} name="Blank" description="Empty canvas — build your own agent from scratch" selected={selectedTemplate === null} onSelect={() => setSelectedTemplate(null)} />
            {templates.map(t => (
              <TemplateCard key={t.id} id={t.id} name={t.name} description={t.description} selected={selectedTemplate === t.id} onSelect={() => setSelectedTemplate(t.id)} />
            ))}
          </div>
        </div>

        {error && <p className="text-xs text-red-500 mb-3">{error}</p>}

        <div className="flex gap-2">
          <button onClick={handleCreate} disabled={saving} className="rounded-lg bg-stone-900 px-5 py-2 text-sm font-medium text-white hover:bg-stone-700 disabled:opacity-50 transition-colors">
            {saving ? "Creating…" : "Create project"}
          </button>
          <button onClick={onClose} className="rounded-lg border border-stone-200 px-5 py-2 text-sm text-stone-600 hover:bg-stone-50 transition-colors">
            Cancel
          </button>
        </div>
      </div>
    </div>
  )
}

function TemplateCard({ id, name, description, selected, onSelect }: {
  id: string | null; name: string; description: string; selected: boolean; onSelect: () => void
}) {
  return (
    <button onClick={onSelect} className={`text-left rounded-lg border px-4 py-3 transition-all ${selected ? "border-indigo-400 bg-indigo-50 ring-1 ring-indigo-300" : "border-stone-200 hover:border-stone-300"}`}>
      <p className={`text-sm font-medium ${selected ? "text-indigo-900" : "text-stone-900"}`}>{name}</p>
      <p className="text-xs text-stone-400 mt-0.5">{description}</p>
    </button>
  )
}
