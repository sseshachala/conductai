"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import Link from "next/link"

const TEMPLATES = [
  {
    id: "blank",
    label: "Blank",
    description: "Start from scratch with an empty canvas",
    tags: [],
  },
  {
    id: "story_pr",
    label: "Story → Pull Request",
    description: "Fetch a Linear issue, create a GitHub branch and open a draft PR",
    tags: ["Linear", "GitHub"],
  },
  {
    id: "deploy",
    label: "Deploy & Notify",
    description: "Trigger a Vercel or Railway deployment and post the result to Slack",
    tags: ["Vercel", "Railway", "Slack"],
  },
  {
    id: "triage",
    label: "Issue Triage",
    description: "Classify incoming Linear issues and route them to the right team",
    tags: ["Linear", "Slack"],
  },
]

export default function NewWorkflowPage() {
  const [name, setName] = useState("")
  const [template, setTemplate] = useState("blank")
  const [loading, setLoading] = useState(false)
  const router = useRouter()

  async function handleCreate() {
    if (!name.trim()) return
    setLoading(true)
    try {
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/workflows`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: name.trim(), template }),
      })
      const workflow = await res.json()
      router.push(`/workflows/${workflow.id}`)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-stone-50">
      <header className="border-b border-stone-200 bg-white px-6 py-4 flex items-center gap-3">
        <Link href="/workflows" className="text-stone-400 hover:text-stone-700 text-sm transition-colors">←</Link>
        <span className="font-semibold text-stone-900">New agent</span>
      </header>

      <main className="mx-auto max-w-xl px-6 py-12">

        {/* Name */}
        <div className="mb-8">
          <label className="block text-xs font-semibold text-stone-500 uppercase tracking-wide mb-2">
            Agent name
          </label>
          <input
            autoFocus
            value={name}
            onChange={e => setName(e.target.value)}
            onKeyDown={e => e.key === "Enter" && handleCreate()}
            placeholder="e.g. Story → PR agent"
            className="w-full rounded-xl border border-stone-200 bg-white px-4 py-3 text-sm text-stone-900 focus:outline-none focus:ring-2 focus:ring-indigo-200 shadow-sm"
          />
        </div>

        {/* Template picker */}
        <div className="mb-10">
          <label className="block text-xs font-semibold text-stone-500 uppercase tracking-wide mb-3">
            Start with a template
          </label>
          <div className="grid grid-cols-2 gap-3">
            {TEMPLATES.map(t => (
              <button
                key={t.id}
                onClick={() => setTemplate(t.id)}
                className={`text-left rounded-xl border p-4 transition-all ${
                  template === t.id
                    ? "border-stone-900 bg-white shadow-sm ring-1 ring-stone-900"
                    : "border-stone-200 bg-white hover:border-stone-300"
                }`}
              >
                <p className={`text-sm font-medium mb-1 ${template === t.id ? "text-stone-900" : "text-stone-700"}`}>
                  {t.label}
                </p>
                <p className="text-xs text-stone-400 leading-relaxed">{t.description}</p>
                {t.tags.length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-2.5">
                    {t.tags.map(tag => (
                      <span key={tag} className="text-[10px] bg-stone-100 text-stone-500 px-1.5 py-0.5 rounded">
                        {tag}
                      </span>
                    ))}
                  </div>
                )}
              </button>
            ))}
          </div>
        </div>

        {/* Create button */}
        <button
          onClick={handleCreate}
          disabled={!name.trim() || loading}
          className="w-full rounded-xl bg-stone-900 px-4 py-3 text-sm font-medium text-white hover:bg-stone-700 transition-colors disabled:opacity-40"
        >
          {loading ? "Creating…" : "Create agent"}
        </button>

      </main>
    </div>
  )
}
