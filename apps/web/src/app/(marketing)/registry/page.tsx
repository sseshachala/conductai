"use client"

import { useState, useEffect } from "react"
import { CtaLink } from "@/components/marketing/CtaLink"

/* ─── Static data ───────────────────────────────────────────────────────── */

const COMPLIANCE_PACKS = [
  {
    icon: "🔐",
    name: "OWASP LLM Top 10",
    description:
      "16 guard rules covering injection, broken access control, weak session management, SSRF, and more. Mapped to OWASP LLM Top 10 identifiers.",
    rules: "16 rules",
    badge: "bg-orange-100 text-orange-700",
    href: "/docs#owasp",
  },
  {
    icon: "📋",
    name: "SOC 2",
    description:
      "Blocks hardcoded secrets and PII logging. Keeps your audit trail clean for SOC 2 Type II evidence generation.",
    rules: "5 rules",
    badge: "bg-blue-100 text-blue-700",
    href: "/docs#soc2",
  },
  {
    icon: "🏥",
    name: "HIPAA",
    description:
      "Detects PHI patterns (SSN, DOB, medical record numbers) and blocks unencrypted health data in AI-generated code.",
    rules: "5 rules",
    badge: "bg-emerald-100 text-emerald-700",
    href: "/docs#hipaa",
  },
  {
    icon: "💳",
    name: "PCI DSS",
    description:
      "Guards against PAN, CVV, and card number exposure. Blocks logging of cardholder data in AI-generated code.",
    rules: "4 rules",
    badge: "bg-violet-100 text-violet-700",
    href: "/docs#pci",
  },
]

interface AutomationPack {
  name: string
  description: string
  category: string
  icon?: string
  tags?: string[]
}

const CATEGORY_ALL = "All"

/* ─── Page ──────────────────────────────────────────────────────────────── */

export default function RegistryPage() {
  const [tab, setTab] = useState<"all" | "compliance" | "automation">("all")
  const [automationCategory, setAutomationCategory] = useState(CATEGORY_ALL)
  const [automationPacks, setAutomationPacks] = useState<AutomationPack[]>([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    setLoading(true)
    fetch(`${process.env.NEXT_PUBLIC_API_URL}/workflows/playbooks`)
      .then((r) => r.json())
      .then((data) => {
        const items: AutomationPack[] = Array.isArray(data)
          ? data
          : Array.isArray(data?.playbooks)
          ? data.playbooks
          : []
        // Marketing registry shows real playbooks only. Demo playbooks (branch-42,
        // prompt-injection scenarios, Acme fixtures) are tagged `demo` in
        // apps/api/playbooks/registry.yaml — filter them out here.
        const real = items.filter((p) => !(p.tags ?? []).includes("demo"))
        setAutomationPacks(real)
      })
      .catch(() => setAutomationPacks([]))
      .finally(() => setLoading(false))
  }, [])

  const automationCategories = [
    CATEGORY_ALL,
    ...Array.from(new Set(automationPacks.map((p) => p.category).filter(Boolean))),
  ]

  const filteredAutomation =
    automationCategory === CATEGORY_ALL
      ? automationPacks
      : automationPacks.filter((p) => p.category === automationCategory)

  const showCompliance = tab === "all" || tab === "compliance"
  const showAutomation = tab === "all" || tab === "automation"

  return (
    <>
      <HeroSection tab={tab} setTab={setTab} />

      {showCompliance && <ComplianceSection />}

      {showAutomation && (
        <AutomationSection
          packs={filteredAutomation}
          loading={loading}
          categories={automationCategories}
          activeCategory={automationCategory}
          setCategory={setAutomationCategory}
          showCategoryTabs={tab === "automation"}
        />
      )}

      <CtaStrip />
    </>
  )
}

/* ─── Hero ──────────────────────────────────────────────────────────────── */

function HeroSection({
  tab,
  setTab,
}: {
  tab: string
  setTab: (t: "all" | "compliance" | "automation") => void
}) {
  const tabs: { label: string; value: "all" | "compliance" | "automation" }[] = [
    { label: "All", value: "all" },
    { label: "Compliance packs", value: "compliance" },
    { label: "Automation packs", value: "automation" },
  ]

  return (
    <section className="max-w-5xl mx-auto px-6 pt-20 pb-12 text-center">
      <div className="inline-flex items-center gap-2 bg-indigo-50 text-indigo-700 px-4 py-1.5 rounded-full text-xs font-semibold uppercase tracking-widest mb-8">
        <span className="w-1.5 h-1.5 rounded-full bg-indigo-500 inline-block" />
        Conduct Registry
      </div>
      <h1 className="text-5xl sm:text-6xl font-black tracking-tight text-stone-900 leading-[1.05] mb-5">
        Conduct Registry
      </h1>
      <p className="text-xl text-stone-500 max-w-2xl mx-auto leading-relaxed mb-10">
        Browse the Conduct Registry. Install a pack. It runs under Guard enforcement.
      </p>

      <div className="inline-flex gap-1 bg-stone-100 rounded-xl p-1">
        {tabs.map((t) => (
          <button
            key={t.value}
            onClick={() => setTab(t.value)}
            className={`px-5 py-2 rounded-lg text-sm font-semibold transition-all ${
              tab === t.value
                ? "bg-white text-stone-900 shadow-sm"
                : "text-stone-500 hover:text-stone-700"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>
    </section>
  )
}

/* ─── Compliance packs ──────────────────────────────────────────────────── */

function ComplianceSection() {
  return (
    <section className="max-w-5xl mx-auto px-6 pb-16">
      <div className="mb-6">
        <p className="text-xs font-semibold uppercase tracking-widest text-stone-400 mb-1">Compliance packs</p>
        <h2 className="text-2xl font-black text-stone-900 tracking-tight">
          Pre-built rule sets for regulated industries.
        </h2>
      </div>
      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {COMPLIANCE_PACKS.map((pack) => (
          <a
            key={pack.name}
            href={pack.href}
            className="border border-stone-200 rounded-xl p-5 bg-white hover:border-stone-300 hover:shadow-sm transition-all flex flex-col gap-3 group"
          >
            <span className="text-2xl">{pack.icon}</span>
            <div>
              <p className="font-bold text-stone-900 text-sm leading-snug mb-1 group-hover:text-indigo-600 transition-colors">
                {pack.name}
              </p>
              <p className="text-xs text-stone-500 leading-relaxed">{pack.description}</p>
            </div>
            <span className={`self-start text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full ${pack.badge}`}>
              {pack.rules}
            </span>
          </a>
        ))}
      </div>
    </section>
  )
}

/* ─── Automation packs ──────────────────────────────────────────────────── */

function AutomationSection({
  packs,
  loading,
  categories,
  activeCategory,
  setCategory,
  showCategoryTabs,
}: {
  packs: AutomationPack[]
  loading: boolean
  categories: string[]
  activeCategory: string
  setCategory: (c: string) => void
  showCategoryTabs: boolean
}) {
  return (
    <section className="max-w-5xl mx-auto px-6 pb-16">
      <div className="mb-6 flex flex-col sm:flex-row sm:items-end gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-widest text-stone-400 mb-1">Automation packs</p>
          <h2 className="text-2xl font-black text-stone-900 tracking-tight">
            Playbooks for engineering, security, and ops.
          </h2>
        </div>

        {showCategoryTabs && categories.length > 1 && (
          <div className="flex flex-wrap gap-2 sm:ml-auto">
            {categories.map((cat) => (
              <button
                key={cat}
                onClick={() => setCategory(cat)}
                className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                  activeCategory === cat
                    ? "bg-indigo-600 text-white"
                    : "bg-stone-100 text-stone-600 hover:bg-stone-200"
                }`}
              >
                {cat}
              </button>
            ))}
          </div>
        )}
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-24">
          <div className="w-6 h-6 border-2 border-indigo-300 border-t-indigo-600 rounded-full animate-spin" />
        </div>
      ) : packs.length === 0 ? (
        <div className="border border-stone-200 rounded-xl p-12 text-center text-stone-400 text-sm">
          No automation packs found.
        </div>
      ) : (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {packs.map((pack) => (
            <a
              key={pack.name}
              href="/docs"
              className="border border-stone-200 rounded-xl p-5 bg-white hover:border-stone-300 hover:shadow-sm transition-all flex flex-col gap-3 group"
            >
              {pack.icon && <span className="text-2xl">{pack.icon}</span>}
              <div>
                <p className="font-bold text-stone-900 text-sm leading-snug mb-1 group-hover:text-indigo-600 transition-colors">
                  {pack.name}
                </p>
                <p className="text-xs text-stone-500 leading-relaxed line-clamp-3">{pack.description}</p>
              </div>
              {pack.category && (
                <span className="self-start text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full bg-stone-100 text-stone-600">
                  {pack.category}
                </span>
              )}
            </a>
          ))}
        </div>
      )}
    </section>
  )
}

/* ─── CTA strip ─────────────────────────────────────────────────────────── */

function CtaStrip() {
  return (
    <section className="border-t border-stone-200 bg-stone-50 px-6 py-14">
      <div className="max-w-5xl mx-auto text-center">
        <p className="text-stone-700 font-semibold text-lg mb-2">
          Every pack runs under Guard enforcement.
        </p>
        <p className="text-stone-500 text-sm mb-8">
          Policies apply instantly — no redeploy.
        </p>
        <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
          <a
            href="/docs"
            className="rounded-xl border border-stone-300 bg-white text-stone-700 px-7 py-3.5 text-sm font-semibold hover:border-stone-400 hover:shadow-sm transition-all w-full sm:w-auto text-center"
          >
            Read the docs →
          </a>
          <CtaLink className="rounded-xl bg-stone-900 text-white px-7 py-3.5 text-sm font-semibold hover:bg-stone-700 transition-colors w-full sm:w-auto text-center" />
        </div>
      </div>
    </section>
  )
}
