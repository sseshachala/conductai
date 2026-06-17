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

const MODULES = [
  {
    id: "conductguard",
    icon: "🛡️",
    name: "ConductGuard",
    description: "Real-time AI activity monitoring. Tracks tool usage, enforces policies, and surfaces spend across your team's AI coding tools.",
    href: "/marketplace?tab=modules",
    badge: "Governance",
    badgeColor: "bg-teal-100 text-teal-700",
  },
  {
    id: "security-loop",
    icon: "🔒",
    name: "Security Loop",
    description: "Automated security scanning on every PR. Runs BugHunter, posts findings to Slack, and creates fix issues for critical vulnerabilities.",
    href: "/marketplace?tab=modules",
    badge: "Security",
    badgeColor: "bg-red-100 text-red-700",
  },
]

const COMPLIANCE_PACKS = [
  {
    id: "owasp_top10",
    icon: "🔐",
    name: "OWASP Top 10",
    description: "6 guard rules + 10 security rules covering injection, broken access control, weak session management, SSRF, and more.",
    rules: "16 rules",
    badgeColor: "bg-orange-100 text-orange-700",
  },
  {
    id: "soc2",
    icon: "📋",
    name: "SOC 2",
    description: "Blocks hardcoded secrets and PII logging. Keeps your audit trail clean for SOC 2 Type II compliance.",
    rules: "5 rules",
    badgeColor: "bg-blue-100 text-blue-700",
  },
  {
    id: "hipaa",
    icon: "🏥",
    name: "HIPAA",
    description: "Detects PHI patterns (SSN, DOB, medical record numbers) and blocks unencrypted health data in AI-generated code.",
    rules: "5 rules",
    badgeColor: "bg-emerald-100 text-emerald-700",
  },
  {
    id: "pci_dss",
    icon: "💳",
    name: "PCI DSS",
    description: "Guards against PAN, CVV, and card number exposure in AI-generated code. Blocks logging of cardholder data.",
    rules: "4 rules",
    badgeColor: "bg-violet-100 text-violet-700",
  },
]

function ProductsDropdown() {
  return (
    <div className="relative group">
      <a href="/sign-up" className="flex items-center gap-1 text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">
        Products
        <svg width="12" height="12" viewBox="0 0 12 12" fill="currentColor" className="opacity-40 mt-0.5"><path d="M2 4l4 4 4-4"/></svg>
      </a>
      <div className="absolute left-0 top-full pt-2 hidden group-hover:block z-50 min-w-[220px]">
        <div className="bg-white border border-stone-200 rounded-xl shadow-lg py-2">
          <a href="/guard-landing" className="flex items-center gap-3 px-4 py-2.5 text-sm text-stone-700 hover:bg-stone-50 transition-colors">
            <span>🛡️</span>
            <div>
              <p className="font-semibold">Conduct Guard</p>
              <p className="text-xs text-stone-400">AI session governance</p>
            </div>
          </a>
          <a href="/tools/security-loop" className="flex items-center gap-3 px-4 py-2.5 text-sm text-stone-700 hover:bg-stone-50 transition-colors">
            <span>🔒</span>
            <div>
              <p className="font-semibold">Security Loop</p>
              <p className="text-xs text-stone-400">Automated PR scanning</p>
            </div>
          </a>
          <a href="/playbooks" className="flex items-center gap-3 px-4 py-2.5 text-sm text-stone-700 hover:bg-stone-50 transition-colors">
            <span>⚡</span>
            <div>
              <p className="font-semibold">Playbooks</p>
              <p className="text-xs text-stone-400">Pre-built AI automations</p>
            </div>
          </a>
          <a href="/tools/conduct-cli" className="flex items-center gap-3 px-4 py-2.5 text-sm text-stone-700 hover:bg-stone-50 transition-colors">
            <span className="text-indigo-600 font-bold text-base">◈</span>
            <div>
              <p className="font-semibold">Conduct CLI</p>
              <p className="text-xs text-stone-400">Terminal governance + token savings</p>
            </div>
          </a>
        </div>
      </div>
    </div>
  )
}

function Nav() {
  return (
    <header className="px-6 py-4 flex items-center justify-between max-w-6xl mx-auto w-full sticky top-0 bg-white/95 backdrop-blur-sm z-50 border-b border-stone-100">
      <a href="/">
        <img src="/logo.png" alt="Conduct AI" className="h-10 w-auto" />
      </a>
      <nav className="hidden md:flex items-center gap-6">
        <ProductsDropdown />
        <a href="/playbooks" className="text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">Playbooks</a>
        <a href="/blog" className="text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">Blog</a>
        <a href="/docs" className="text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">Docs</a>
        <a href="https://pypi.org/project/conduct-cli/" target="_blank" rel="noopener noreferrer" className="text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">PyPI</a>
      </nav>
      <div className="flex items-center gap-3">
        <a href="mailto:hello@conductai.ai" className="text-sm font-medium text-stone-600 hover:text-stone-900 transition-colors hidden sm:block">Talk to Us</a>
        <a href="/sign-up" className="rounded-lg bg-stone-900 text-white px-4 py-2 text-sm font-semibold hover:bg-stone-700 transition-colors">
          Start Free
        </a>
      </div>
    </header>
  )
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

function SectionHeader({ title, description }: { title: string; description: string }) {
  return (
    <div className="mb-5">
      <h2 className="text-base font-semibold text-stone-900">{title}</h2>
      <p className="text-xs text-stone-500 mt-0.5">{description}</p>
    </div>
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
      <Nav />

      <main className="max-w-5xl mx-auto px-6 py-12 space-y-16">

        {/* Automations */}
        <section>
          <div className="mb-8">
            <h1 className="text-2xl font-semibold text-stone-900">All Automations</h1>
            <p className="text-sm text-stone-500 mt-1">
              Pre-built YAML playbooks for AI-assisted engineering teams.{" "}
              <Link href="/sign-up" className="text-stone-700 font-medium hover:underline">Install in your workspace →</Link>
            </p>
          </div>

          {/* Category tabs */}
          <div className="flex gap-1.5 flex-wrap mb-6">
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

          {loading ? (
            <div className="flex items-center justify-center py-20">
              <div className="w-5 h-5 border-2 border-stone-300 border-t-stone-600 rounded-full animate-spin" />
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {visible.map(p => <PlaybookCard key={p.slug} p={p} />)}
            </div>
          )}
        </section>

        {/* Modules */}
        <section>
          <SectionHeader
            title="Modules"
            description="Full-stack features that add new capabilities to your workspace."
          />
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {MODULES.map(m => (
              <Link
                key={m.id}
                href={m.href}
                className="flex items-start gap-4 bg-white border border-stone-200 rounded-xl px-5 py-4 hover:border-stone-300 hover:shadow-sm transition-all group"
              >
                <div className="w-11 h-11 rounded-xl bg-stone-100 flex items-center justify-center text-xl shrink-0">
                  {m.icon}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 mb-0.5">
                    <p className="text-sm font-medium text-stone-900">{m.name}</p>
                    <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded ${m.badgeColor}`}>{m.badge}</span>
                  </div>
                  <p className="text-xs text-stone-500 leading-relaxed">{m.description}</p>
                </div>
              </Link>
            ))}
          </div>
        </section>

        {/* Compliance Packs */}
        <section>
          <SectionHeader
            title="Compliance Packs"
            description="Pre-built guard + security rule sets mapped to industry standards. Install in one click."
          />
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {COMPLIANCE_PACKS.map(pack => (
              <Link
                key={pack.id}
                href="/marketplace?tab=compliance"
                className="flex items-start gap-4 bg-white border border-stone-200 rounded-xl px-5 py-4 hover:border-stone-300 hover:shadow-sm transition-all group"
              >
                <div className="w-11 h-11 rounded-xl bg-stone-100 flex items-center justify-center text-xl shrink-0">
                  {pack.icon}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 mb-0.5">
                    <p className="text-sm font-medium text-stone-900">{pack.name}</p>
                    <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded ${pack.badgeColor}`}>{pack.rules}</span>
                  </div>
                  <p className="text-xs text-stone-500 leading-relaxed">{pack.description}</p>
                </div>
              </Link>
            ))}
          </div>
        </section>

      </main>
    </div>
  )
}
