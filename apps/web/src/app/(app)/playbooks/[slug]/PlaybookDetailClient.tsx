"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { useParams } from "next/navigation"

interface Block {
  id: string
  type: string
  label: string
  description: string | null
  integration: string | null
  model: string | null
}

interface PlaybookDetail {
  slug: string
  name: string
  icon: string
  description: string
  tags: string[]
  category: string
  featured: boolean
  blocks: Block[]
  yaml_source: string
}

const BLOCK_STYLES: Record<string, { bg: string; border: string; badge: string; badgeText: string; dot: string }> = {
  trigger:  { bg: "bg-blue-50",    border: "border-blue-200",   badge: "bg-blue-100 text-blue-700",    badgeText: "TRIGGER",    dot: "bg-blue-400"    },
  brain:    { bg: "bg-violet-50",  border: "border-violet-200", badge: "bg-violet-100 text-violet-700",badgeText: "AGENT",      dot: "bg-violet-400"  },
  tool:     { bg: "bg-emerald-50", border: "border-emerald-200",badge: "bg-emerald-100 text-emerald-700",badgeText: "ACTION",   dot: "bg-emerald-400" },
  logic:    { bg: "bg-stone-50",   border: "border-stone-200",  badge: "bg-stone-100 text-stone-600",  badgeText: "CONDITION",  dot: "bg-stone-400"   },
  memory:   { bg: "bg-amber-50",   border: "border-amber-200",  badge: "bg-amber-100 text-amber-700",  badgeText: "MEMORY",     dot: "bg-amber-400"   },
  approval: { bg: "bg-orange-50",  border: "border-orange-200", badge: "bg-orange-100 text-orange-700",badgeText: "APPROVAL",   dot: "bg-orange-400"  },
  output:   { bg: "bg-rose-50",    border: "border-rose-200",   badge: "bg-rose-100 text-rose-700",    badgeText: "NOTIFY",     dot: "bg-rose-400"    },
  cleanup:  { bg: "bg-stone-50",   border: "border-stone-200",  badge: "bg-stone-100 text-stone-600",  badgeText: "CLEANUP",    dot: "bg-stone-400"   },
}

const MODEL_SHORT: Record<string, string> = {
  "{{inputs.spec_model}}":  "Opus",
  "{{inputs.impl_model}}":  "Sonnet",
  "claude-opus-4-7":        "Opus",
  "claude-sonnet-4-6":      "Sonnet",
  "claude-haiku-4-5-20251001": "Haiku",
}

const INTEGRATION_STYLES: Record<string, string> = {
  github: "bg-stone-900 text-white",
  slack:  "bg-purple-600 text-white",
  linear: "bg-indigo-600 text-white",
  email:  "bg-emerald-600 text-white",
}

const FRIENDLY_NAMES: Record<string, string> = {
  factory:              "Software Factory",
  autopilot_quick:      "Autopilot Quick",
  autopilot_full:       "Autopilot Full",
  autopilot_approved:   "Autopilot + Approval",
  pr_reviewer:          "PR Reviewer",
  issue_triage:         "Issue Triage",
  security_scanner:     "Security Scanner",
  copilot_reviewer:     "Copilot / AI PR Reviewer",
  flaky_test_detective: "Flaky Test Detective",
  postmortem_drafter:   "Postmortem Drafter",
  docs_drift_detector:  "Docs Drift Detector",
  terraform_reviewer:   "Terraform Plan Reviewer",
  release_readiness:    "Release Readiness Reviewer",
}

// Blocks that are "off the happy path" — shown collapsed at the bottom
const SIDE_BLOCK_PREFIXES = ["abort_", "notify_failure"]

function BlockIcon({ type }: { type: string }) {
  const props = {
    viewBox: "0 0 24 24", fill: "none", stroke: "currentColor",
    strokeWidth: 2.5, strokeLinecap: "round" as const, strokeLinejoin: "round" as const,
    className: "w-3 h-3",
  }
  switch (type) {
    case "trigger":  return <svg {...props}><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></svg>
    case "brain":    return <svg {...props}><path d="M12 2a4 4 0 014 4c0 .34-.04.67-.1 1H17a3 3 0 010 6h-.5M12 2a4 4 0 00-4 4c0 .34.04.67.1 1H7a3 3 0 000 6h.5"/><path d="M12 2v18M8.5 13h7"/></svg>
    case "tool":     return <svg {...props}><path d="M14.7 6.3a1 1 0 000 1.4l1.6 1.6a1 1 0 001.4 0l3.77-3.77a6 6 0 01-7.94 7.94l-6.91 6.91a2.12 2.12 0 01-3-3l6.91-6.91a6 6 0 017.94-7.94l-3.76 3.76z"/></svg>
    case "logic":    return <svg {...props}><path d="M16 3h5v5M4 20L21 3"/><path d="M21 16v5h-5M15 15l6 6M4 4l5 5"/></svg>
    case "memory":   return <svg {...props}><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5v14a9 3 0 0018 0V5"/><path d="M3 12a9 3 0 0018 0"/></svg>
    case "approval": return <svg {...props}><path d="M22 11.08V12a10 10 0 11-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
    case "output":   return <svg {...props}><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
    case "cleanup":  return <svg {...props}><path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6"/><path d="M10 11v6M14 11v6"/></svg>
    default:         return null
  }
}

function BlockCard({ block }: { block: Block }) {
  const style = BLOCK_STYLES[block.type] ?? BLOCK_STYLES.tool
  const modelShort = block.model ? MODEL_SHORT[block.model] : null

  return (
    <div className={`rounded-lg border ${style.border} ${style.bg} px-4 py-3 flex items-start gap-3`}>
      <div className={`mt-0.5 w-5 h-5 rounded flex items-center justify-center flex-shrink-0 ${style.badge}`}>
        <BlockIcon type={block.type} />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className={`text-[10px] font-semibold tracking-wide ${style.badge} px-1.5 py-0.5 rounded`}>
            {style.badgeText}
          </span>
          {block.integration && (
            <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded ${INTEGRATION_STYLES[block.integration] ?? "bg-stone-100 text-stone-600"}`}>
              {block.integration.charAt(0).toUpperCase() + block.integration.slice(1)}
            </span>
          )}
          {modelShort && (
            <span className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-white border border-violet-200 text-violet-700">
              {modelShort}
            </span>
          )}
        </div>
        <p className="text-sm font-medium text-stone-800 mt-1 leading-snug">{block.label}</p>
        {block.description && (
          <p className="text-xs text-stone-500 mt-0.5 leading-relaxed line-clamp-2">{block.description}</p>
        )}
      </div>
    </div>
  )
}

export default function PublicPlaybookPage() {
  const params = useParams()
  const slug = params.slug as string
  const [playbook, setPlaybook] = useState<PlaybookDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [notFound, setNotFound] = useState(false)
  const [showYaml, setShowYaml] = useState(false)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL
    if (!apiUrl || !slug) return
    fetch(`${apiUrl}/workflows/playbooks/${slug}`)
      .then(r => { if (!r.ok) throw new Error("not found"); return r.json() })
      .then(setPlaybook)
      .catch(() => setNotFound(true))
      .finally(() => setLoading(false))
  }, [slug])

  if (loading) {
    return (
      <div className="min-h-screen bg-stone-50 flex items-center justify-center">
        <div className="w-5 h-5 border-2 border-stone-300 border-t-stone-600 rounded-full animate-spin" />
      </div>
    )
  }

  if (notFound || !playbook) {
    return (
      <div className="min-h-screen bg-stone-50 flex items-center justify-center">
        <div className="text-center">
          <p className="text-stone-500 text-sm">Playbook not found.</p>
          <Link href="/playbooks" className="text-xs text-stone-400 hover:text-stone-600 mt-2 inline-block">
            Browse playbooks →
          </Link>
        </div>
      </div>
    )
  }

  const mainBlocks = playbook.blocks.filter(b =>
    !SIDE_BLOCK_PREFIXES.some(p => b.id.startsWith(p))
  )
  const sideBlocks = playbook.blocks.filter(b =>
    SIDE_BLOCK_PREFIXES.some(p => b.id.startsWith(p))
  )
  const friendlyName = FRIENDLY_NAMES[playbook.slug] ?? playbook.name

  return (
    <div className="min-h-screen bg-stone-50">
      {/* Nav */}
      <header className="border-b border-stone-200 bg-white sticky top-0 z-10">
        <div className="max-w-3xl mx-auto px-6 h-14 flex items-center justify-between">
          <Link href="/" className="flex items-center gap-2">
            <span className="text-sm font-semibold text-stone-900">Conduct</span>
            <span className="text-stone-300 text-xs">/ Agent Templates</span>
          </Link>
          <div className="flex items-center gap-2">
            <Link
              href="/sign-in"
              className="text-xs text-stone-600 hover:text-stone-900 px-3 py-1.5 rounded-lg hover:bg-stone-100 transition-colors"
            >
              Sign in
            </Link>
            <Link
              href={`/playbooks?install=${playbook.slug}`}
              className="text-xs font-medium bg-stone-900 text-white px-3 py-1.5 rounded-lg hover:bg-stone-700 transition-colors"
            >
              Install
            </Link>
          </div>
        </div>
      </header>

      <main className="max-w-3xl mx-auto px-6 py-12">
        {/* Breadcrumb */}
        <div className="mb-8">
          <Link href="/playbooks" className="text-xs text-stone-400 hover:text-stone-600 transition-colors">
            ← Back to Playbooks
          </Link>
        </div>

        {/* Hero */}
        <div className="mb-10">
          <div className="flex items-start gap-4 mb-4">
            <span className="text-5xl leading-none">{playbook.icon}</span>
            <div>
              <h1 className="text-2xl font-bold text-stone-900 leading-tight">{friendlyName}</h1>
              <div className="flex items-center gap-2 mt-2 flex-wrap">
                <span className="text-xs font-medium bg-stone-100 text-stone-600 px-2 py-0.5 rounded-full">
                  {playbook.category}
                </span>
                {playbook.tags.map(tag => (
                  <span key={tag} className="text-xs text-stone-400 bg-stone-100 px-2 py-0.5 rounded-full">
                    {tag}
                  </span>
                ))}
              </div>
            </div>
          </div>
          <p className="text-stone-600 text-sm leading-relaxed max-w-2xl">{playbook.description}</p>
        </div>

        {/* Pipeline */}
        <div className="mb-10">
          <h2 className="text-xs font-semibold text-stone-400 uppercase tracking-wider mb-4">Pipeline</h2>
          <div className="flex flex-col gap-1.5">
            {mainBlocks.map((block, i) => (
              <div key={block.id}>
                <BlockCard block={block} />
                {i < mainBlocks.length - 1 && (
                  <div className="flex justify-start pl-[22px]">
                    <div className="w-px h-3 bg-stone-200" />
                  </div>
                )}
              </div>
            ))}
          </div>

          {sideBlocks.length > 0 && (
            <div className="mt-4">
              <p className="text-[11px] text-stone-400 uppercase tracking-wide mb-2 font-medium">Failure paths</p>
              <div className="flex flex-col gap-1.5">
                {sideBlocks.map(block => (
                  <BlockCard key={block.id} block={block} />
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Stats strip */}
        <div className="flex items-center gap-6 py-4 border-y border-stone-200 mb-10 text-xs text-stone-500">
          <span><span className="font-semibold text-stone-700">{playbook.blocks.length}</span> blocks</span>
          <span><span className="font-semibold text-stone-700">{playbook.blocks.filter(b => b.type === "brain").length}</span> agent steps</span>
          <span><span className="font-semibold text-stone-700">{playbook.blocks.filter(b => b.type === "approval").length}</span> human gate{playbook.blocks.filter(b => b.type === "approval").length !== 1 ? "s" : ""}</span>
          <span><span className="font-semibold text-stone-700">{playbook.blocks.filter(b => b.type === "memory").length}</span> memory ops</span>
        </div>

        {/* CTA */}
        <div className="flex items-center gap-3 mb-10">
          <Link
            href={`/playbooks?install=${playbook.slug}`}
            className="inline-flex items-center gap-2 bg-stone-900 text-white text-sm font-medium px-5 py-2.5 rounded-lg hover:bg-stone-700 transition-colors"
          >
            Install in your workspace
          </Link>
          <button
            onClick={() => setShowYaml(v => !v)}
            aria-expanded={showYaml}
            className="inline-flex items-center gap-2 border border-stone-200 text-stone-600 text-sm font-medium px-5 py-2.5 rounded-lg hover:bg-stone-50 transition-colors"
          >
            {showYaml ? "Hide YAML" : "Show YAML"}
          </button>
        </div>

        {/* YAML source */}
        {showYaml && playbook.yaml_source && (
          <div className="mb-10 rounded-xl border border-stone-200 bg-stone-950 overflow-hidden">
            <div className="flex items-center justify-between px-4 py-2 border-b border-stone-800">
              <span className="text-xs text-stone-400 font-mono">{playbook.slug}.yaml</span>
              <button
                onClick={() => {
                  navigator.clipboard?.writeText(playbook.yaml_source).then(() => {
                    setCopied(true)
                    setTimeout(() => setCopied(false), 2000)
                  }).catch(() => {
                    // clipboard write failed silently — browser may block without HTTPS or user gesture
                  })
                }}
                className="text-[11px] text-stone-500 hover:text-stone-300 transition-colors"
              >
                {copied ? "Copied!" : "Copy"}
              </button>
            </div>
            <pre className="text-xs text-stone-300 font-mono p-4 overflow-x-auto leading-relaxed max-h-[500px] overflow-y-auto">
              {playbook.yaml_source}
            </pre>
          </div>
        )}

        {/* Footer */}
        <div className="border-t border-stone-200 pt-8 flex items-center justify-between">
          <p className="text-xs text-stone-400">
            Built with{" "}
            <Link href="/" className="text-stone-600 hover:text-stone-900 font-medium">
              Conduct
            </Link>
            {" "}— YAML playbooks for AI-operated software teams
          </p>
          <Link
            href="/playbooks"
            className="text-xs text-stone-400 hover:text-stone-600 transition-colors"
          >
            Browse all playbooks →
          </Link>
        </div>
      </main>
    </div>
  )
}
