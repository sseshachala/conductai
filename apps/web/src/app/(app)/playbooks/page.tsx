"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { useAuth } from "@clerk/nextjs"
import AppShell from "@/components/AppShell"

interface Playbook {
  slug: string
  name: string
  icon: string
  description: string
  tags: string[]
  category: string
  featured: boolean
  source: string
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

// Muted bg per category for the icon tile
const CATEGORY_COLORS: Record<string, string> = {
  "Issue to PR":       "bg-violet-100",
  "Code Review":       "bg-stone-200",
  "Issue Triage":      "bg-amber-100",
  "CI/CD":             "bg-emerald-100",
  "Testing":           "bg-blue-100",
  "Security":          "bg-red-100",
  "AI Governance":     "bg-teal-100",
  "Incidents & Ops":   "bg-orange-100",
  "Release Management":"bg-indigo-100",
  "Docs":              "bg-lime-100",
  "Platform & Infra":  "bg-sky-100",
}

function PlaybookCard({ p }: { p: Playbook }) {
  const tileBg = CATEGORY_COLORS[p.category] ?? "bg-stone-100"
  return (
    <Link
      href={`/marketplace?install=${p.slug}`}
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

function PlaybooksContent({ getToken }: { getToken: (() => Promise<string | null>) | null }) {
  const [playbooks, setPlaybooks] = useState<Playbook[]>([])
  const [loading, setLoading] = useState(true)
  const [activeCategory, setActiveCategory] = useState("All")

  useEffect(() => {
    async function load() {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL
      if (!apiUrl) return
      const headers: Record<string, string> = {}
      if (getToken) {
        const token = await getToken()
        if (token) headers["Authorization"] = `Bearer ${token}`
      }
      try {
        const res = await fetch(`${apiUrl}/workflows/playbooks`, { headers })
        if (res.ok) setPlaybooks(await res.json())
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [getToken])

  const categories = CATEGORY_ORDER.filter(
    c => c === "All" || playbooks.some(p => p.category === c)
  )

  const visible = activeCategory === "All"
    ? playbooks
    : playbooks.filter(p => p.category === activeCategory)

  return (
    <AppShell>
      <div className="max-w-4xl mx-auto px-6 py-8">
        {/* Header */}
        <div className="mb-6">
          <h1 className="text-lg font-semibold text-stone-900">Automations</h1>
          <p className="text-sm text-stone-500 mt-0.5">Pre-built YAML playbooks your team can install and run.</p>
        </div>

        {/* Category tabs */}
        <div className="flex gap-1 flex-wrap mb-6">
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
        ) : visible.length === 0 ? (
          <p className="text-sm text-stone-400 py-10 text-center">No playbooks found.</p>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {visible.map(p => <PlaybookCard key={p.slug} p={p} />)}
          </div>
        )}
      </div>
    </AppShell>
  )
}

function PlaybooksGate() {
  const { getToken, isLoaded } = useAuth()
  if (!isLoaded) return null
  return <PlaybooksContent getToken={getToken} />
}

export default PlaybooksGate
