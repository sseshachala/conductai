"use client"

import { useEffect, useState } from "react"
import Link from "next/link"

interface Playbook {
  slug: string
  name: string
  icon: string
  description: string
  tags: string[]
  category: string
  featured: boolean
}

const CATEGORY_ORDER = [
  "All",
  "Issue to PR",
  "Code Review",
  "Issue Triage",
  "CI/CD",
  "Testing",
  "Security",
  "AI Governance",
  "Incidents & Ops",
  "Release Management",
  "Docs",
  "Platform & Infra",
]

const CATEGORY_COLORS: Record<string, string> = {
  "Issue to PR":        "bg-violet-100",
  "Code Review":        "bg-stone-200",
  "Issue Triage":       "bg-amber-100",
  "CI/CD":              "bg-emerald-100",
  "Testing":            "bg-blue-100",
  "Security":           "bg-red-100",
  "AI Governance":      "bg-teal-100",
  "Incidents & Ops":    "bg-orange-100",
  "Release Management": "bg-indigo-100",
  "Docs":               "bg-lime-100",
  "Platform & Infra":   "bg-sky-100",
}

function PlaybookCard({ p }: { p: Playbook }) {
  const tileBg = CATEGORY_COLORS[p.category] ?? "bg-stone-100"
  return (
    <Link
      href={`/playbooks/${p.slug}`}
      className="flex items-center gap-4 bg-white border border-stone-200 rounded-xl px-5 py-4 hover:border-stone-300 hover:shadow-sm transition-all group"
    >
      <div className={`w-11 h-11 rounded-xl ${tileBg} flex items-center justify-center text-xl shrink-0`}>
        {p.icon}
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium text-stone-900 truncate">{p.name}</p>
        <p className="text-xs text-stone-500 mt-0.5 line-clamp-2 leading-relaxed">{p.description}</p>
      </div>
      <svg className="w-4 h-4 text-stone-300 group-hover:text-stone-500 shrink-0 transition-colors" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
      </svg>
    </Link>
  )
}

export default function AutomationsPage() {
  const [playbooks, setPlaybooks] = useState<Playbook[]>([])
  const [loading, setLoading] = useState(true)
  const [activeCategory, setActiveCategory] = useState("All")

  useEffect(() => {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL
    if (!apiUrl) return
    fetch(`${apiUrl}/workflows/playbooks`)
      .then(r => r.ok ? r.json() : [])
      .then(setPlaybooks)
      .finally(() => setLoading(false))
  }, [])

  const categories = CATEGORY_ORDER.filter(
    c => c === "All" || playbooks.some(p => p.category === c)
  )

  const visible = activeCategory === "All"
    ? playbooks
    : playbooks.filter(p => p.category === activeCategory)

  return (
    <div className="min-h-screen bg-stone-50">
      {/* Nav */}
      <header className="border-b border-stone-200 bg-white sticky top-0 z-10">
        <div className="max-w-5xl mx-auto px-6 h-14 flex items-center justify-between">
          <Link href="/" className="text-sm font-semibold text-stone-900">Conduct</Link>
          <div className="flex items-center gap-2">
            <Link href="/sign-in" className="text-xs text-stone-600 hover:text-stone-900 px-3 py-1.5 rounded-lg hover:bg-stone-100 transition-colors">
              Sign in
            </Link>
            <Link href="/sign-up" className="text-xs font-medium bg-stone-900 text-white px-3 py-1.5 rounded-lg hover:bg-stone-700 transition-colors">
              Get started
            </Link>
          </div>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-6 py-12">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-2xl font-semibold text-stone-900">All Automations</h1>
          <p className="text-sm text-stone-500 mt-1">
            Pre-built YAML playbooks for AI-assisted engineering teams.{" "}
            <Link href="/sign-up" className="text-stone-700 font-medium hover:underline">Install in your workspace →</Link>
          </p>
        </div>

        {/* Category tabs */}
        <div className="flex gap-1.5 flex-wrap mb-8">
          {categories.map(cat => (
            <button
              key={cat}
              onClick={() => setActiveCategory(cat)}
              className={`text-xs px-3 py-1.5 rounded-lg font-medium transition-colors ${
                activeCategory === cat
                  ? "bg-stone-900 text-white"
                  : "bg-stone-100 text-stone-600 hover:bg-stone-200"
              }`}
            >
              {cat}
            </button>
          ))}
        </div>

        {/* Grid */}
        {loading ? (
          <div className="flex items-center justify-center py-20">
            <div className="w-5 h-5 border-2 border-stone-300 border-t-stone-600 rounded-full animate-spin" />
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {visible.map(p => <PlaybookCard key={p.slug} p={p} />)}
          </div>
        )}
      </main>
    </div>
  )
}
