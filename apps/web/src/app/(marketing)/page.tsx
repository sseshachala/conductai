"use client"

import { DecisionCard } from "@/components/marketing/facelift/DecisionCard"
import { AgentSurfaceStrip } from "@/components/marketing/facelift/AgentSurfaceStrip"
import { EvidenceReceipt } from "@/components/marketing/facelift/EvidenceReceipt"
import { RuntimeFlow } from "@/components/marketing/facelift/RuntimeFlow"
import { CapabilityStatus, type CapabilityItem, type CapStatus } from "@/components/marketing/facelift/CapabilityStatus"


export default function HomePage() {
  return (
    <>
      <HeroSection />
      <ProblemSection />
      <CoreLoopSection />
      <ConsequentialActionsSection />
      <OnePolicySection />
      <NativeControlsSection />
      <EvidenceSection />
      <HonestSecuritySection />
      <OpenSourceSection />
      <DeploymentSection />
      <FinalCTASection />
    </>
  )
}

function HeroSection() {
  return (
    <section className="max-w-6xl mx-auto px-4 sm:px-6 pt-12 sm:pt-20 pb-12 sm:pb-16">
      <div className="grid lg:grid-cols-2 gap-10 lg:gap-12 items-center">
        {/* Left: copy */}
        <div>
          <p className="text-xs font-mono font-bold uppercase tracking-widest text-stone-400 mb-5 sm:mb-6">
            Built for engineering teams.
          </p>
          <h1 className="text-4xl sm:text-5xl lg:text-6xl font-black tracking-tight text-stone-900 leading-[1.05] mb-5 sm:mb-6">
            One policy across your AI agent stack.
          </h1>
          <p className="text-base sm:text-lg text-stone-500 leading-relaxed mb-4 sm:mb-5 max-w-xl">
            Conduct Guard enforces runtime policy across any MCP-compatible AI agent, model gateway, and MCP tool — before consequential actions execute.
          </p>
          <p className="text-sm sm:text-base font-semibold text-stone-700 mb-7 sm:mb-8 max-w-xl">
            Install in 10 minutes. Evidence for the CISO from day one.
          </p>

          {/* Verbs */}
          <div className="flex items-center gap-2 sm:gap-3 mb-8 sm:mb-10 font-mono text-sm font-bold flex-wrap">
            <span className="text-emerald-600">Allow.</span>
            <span className="text-amber-500">Approve.</span>
            <span className="text-red-600">Block.</span>
            <span className="text-stone-600">Prove.</span>
          </div>

          {/* CTAs */}
          <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3 mb-4">
            <a
              href="/discovery"
              className="rounded-xl bg-stone-900 text-white px-7 py-3.5 text-base font-semibold hover:bg-stone-700 transition-colors text-center min-h-[48px] flex items-center justify-center"
            >
              Start Agent Discovery — 14 days free
            </a>
            <a
              href="/book-demo"
              className="rounded-xl border border-stone-200 text-stone-700 px-7 py-3.5 text-base font-semibold hover:bg-stone-50 transition-colors text-center min-h-[48px] flex items-center justify-center"
            >
              Book a Demo
            </a>
          </div>
          <a
            href="/open-source"
            className="text-sm text-stone-400 hover:text-stone-700 transition-colors underline underline-offset-2 inline-block py-1"
          >
            View the open-source runtime →
          </a>
        </div>

        {/* Right: Decision card — stacks below copy on mobile */}
        <div className="flex flex-col gap-4 mt-2 lg:mt-0">
          <DecisionCard
            agent="claude-code / deploy-agent"
            action="deploy_production"
            resource="payments-api"
            policy="production-change-v4"
            decision="APPROVE"
            showButtons
          />
          <AgentSurfaceStrip />
        </div>
      </div>
    </section>
  )
}

/* ─── 2. Problem ──────────────────────────────────────────────────────── */

function ProblemSection() {
  const cols = [
    {
      title: "One policy model per tool",
      body: "Claude Code has hooks. Cursor has settings. Copilot has org controls. Each enforces differently, stores differently, audits differently. You can't write a rule once and trust it runs everywhere.",
    },
    {
      title: "Consequential actions run without review",
      body: "A refund processes. A production deploy lands. A secret is read. By the time you know, the action is done. Policies in documents don't stop actions at runtime.",
    },
    {
      title: "No tamper-evident trail",
      body: "Log files change. Agent activity disappears when the session ends. When security or compliance asks what happened, the answer shouldn't be 'we think.'",
    },
  ]

  return (
    <section className="border-t border-stone-100 bg-stone-50 py-12 sm:py-20 px-4 sm:px-6">
      <div className="max-w-5xl mx-auto">
        <h2 className="text-2xl sm:text-3xl lg:text-4xl font-bold text-stone-900 tracking-tight mb-4">
          Five agent tools shouldn&apos;t require five policy models.
        </h2>
        <p className="text-stone-500 mb-10 sm:mb-12 max-w-2xl text-sm sm:text-base">
          Every new agent surface creates a new enforcement gap. The problem compounds every time a new tool lands in your stack.
        </p>
        <div className="grid sm:grid-cols-3 gap-6 sm:gap-8">
          {cols.map((col) => (
            <div key={col.title}>
              <p className="font-semibold text-stone-900 mb-2 text-sm sm:text-base">{col.title}</p>
              <p className="text-sm text-stone-500 leading-relaxed">{col.body}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

/* ─── 3. Core loop ────────────────────────────────────────────────────── */

function CoreLoopSection() {
  const verbs = [
    {
      word: "Allow.",
      colour: "text-emerald-600",
      line: "Actions within policy proceed immediately. No friction for compliant work.",
      decision: "ALLOW" as const,
    },
    {
      word: "Approve.",
      colour: "text-amber-500",
      line: "Consequential actions pause for human review before they execute.",
      decision: "APPROVE" as const,
    },
    {
      word: "Block.",
      colour: "text-red-600",
      line: "Actions outside policy are stopped before they reach a model or tool.",
      decision: "BLOCK" as const,
    },
    {
      word: "Prove.",
      colour: "text-stone-700",
      line: "Every decision lands in a hash-chained audit trail. Integrity is verifiable.",
      decision: null,
    },
  ]

  const DOT: Record<string, string> = {
    ALLOW: "bg-emerald-400",
    APPROVE: "bg-amber-400",
    BLOCK: "bg-red-400",
    PROVE: "bg-stone-400",
  }
  const VERB_ON_DARK: Record<string, string> = {
    "Allow.": "text-emerald-400",
    "Approve.": "text-amber-400",
    "Block.": "text-red-400",
    "Prove.": "text-white",
  }

  return (
    <section className="py-16 sm:py-24 px-4 sm:px-6 bg-stone-950">
      <div className="max-w-5xl mx-auto">
        <h2 className="text-2xl sm:text-3xl lg:text-4xl font-bold text-white tracking-tight mb-4">
          Allow. Approve. Block. Prove.
        </h2>
        <p className="text-stone-400 mb-10 sm:mb-14 max-w-2xl text-sm sm:text-base">
          Four outcomes. Every agent action gets one. Runtime, not retrospective.
        </p>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 md:gap-5">
          {verbs.map((v) => {
            const key = v.decision ?? "PROVE"
            return (
              <div key={v.word} className="border border-stone-800 rounded-2xl bg-stone-900 p-5 sm:p-6">
                <div className="flex items-center gap-2 mb-4">
                  <span className={`inline-block w-2 h-2 rounded-full ${DOT[key]}`} />
                  <span className="font-mono text-[10px] font-bold uppercase tracking-widest text-stone-400">
                    {v.decision ?? "Hash-chained"}
                  </span>
                </div>
                <p className={`text-2xl sm:text-3xl font-black tracking-tight mb-3 ${VERB_ON_DARK[v.word]}`}>
                  {v.word}
                </p>
                <p className="text-stone-400 text-sm leading-relaxed">{v.line}</p>
              </div>
            )
          })}
        </div>
      </div>
    </section>
  )
}

/* ─── 4. Consequential actions ────────────────────────────────────────── */

function ConsequentialActionsSection() {
  const cards = [
    {
      agent: "codex / release-agent",
      action: "process_refund",
      resource: "customer C-8911",
      policy: "refund-cap",
      decision: "BLOCK" as const,
      reason: "Refunds over $500 require human approval per FIN-07. Amount: $840.",
    },
    {
      agent: "claude-code / deploy-agent",
      action: "deploy_production",
      resource: "payments-api",
      policy: "production-change-v4",
      decision: "APPROVE" as const,
      reason: "Production deployment outside approved change window",
      showButtons: true,
    },
    {
      agent: "cursor-agent-17",
      action: "read_env",
      resource: "orders-db",
      policy: "secret-access",
      decision: "BLOCK" as const,
      reason: "Secret access from non-hardened session context.",
    },
    {
      agent: "copilot-reviewer",
      action: "send_email",
      resource: "customer C-8911",
      policy: "email-external",
      decision: "APPROVE" as const,
      reason: "External email requires confirmation before send.",
    },
  ]

  return (
    <section className="py-12 sm:py-20 px-4 sm:px-6 border-t border-stone-100 bg-stone-50">
      <div className="max-w-5xl mx-auto">
        <h2 className="text-2xl sm:text-3xl lg:text-4xl font-bold text-stone-900 tracking-tight mb-4">
          Control the action before it becomes an outcome.
        </h2>
        <p className="text-stone-500 mb-10 sm:mb-12 max-w-2xl text-sm sm:text-base">
          Guard intercepts at the point of intent — not after a refund processes, a deploy lands, or a secret is read.
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {cards.map((card) => (
            <DecisionCard key={card.action} {...card} compact />
          ))}
        </div>
      </div>
    </section>
  )
}

/* ─── 5. One policy across surfaces ──────────────────────────────────── */

function OnePolicySection() {
  return (
    <section className="py-12 sm:py-20 px-4 sm:px-6 border-t border-stone-100">
      <div className="max-w-5xl mx-auto">
        <div className="grid lg:grid-cols-2 gap-10 lg:gap-12 items-start">
          <div>
            <h2 className="text-2xl sm:text-3xl lg:text-4xl font-bold text-stone-900 tracking-tight mb-4">
              Write the rule once. Apply it where agents work.
            </h2>
            <p className="text-stone-500 leading-relaxed mb-6 text-sm sm:text-base">
              One policy definition — one set of rules for which actions require approval, which are blocked, and which are audited. Guard applies it across your entire agent fleet: CLI hooks, HTTP proxy, and MCP layer.
            </p>
            <ul className="space-y-3 text-sm text-stone-600">
              <li className="flex items-start gap-2">
                <span className="text-emerald-600 font-bold mt-0.5 shrink-0">→</span>
                <span>3 enforcement surfaces: CLI hook, HTTP proxy, MCP layer</span>
              </li>
              <li className="flex items-start gap-2">
                <span className="text-emerald-600 font-bold mt-0.5 shrink-0">→</span>
                <span>6 BYO gateway adapters: Azure, OpenRouter, Portkey, Helicone, LiteLLM (Preview), ConductAI</span>
              </li>
              <li className="flex items-start gap-2">
                <span className="text-emerald-600 font-bold mt-0.5 shrink-0">→</span>
                <span>39 pre-built playbooks with Guard enforcement built in</span>
              </li>
            </ul>
          </div>
          <div className="mt-2 lg:mt-0">
            <AgentSurfaceStrip />
          </div>
        </div>
      </div>
    </section>
  )
}

/* ─── 6. Native controls ──────────────────────────────────────────────── */

function NativeControlsSection() {
  return (
    <section className="py-12 sm:py-20 px-4 sm:px-6 border-t border-stone-100 bg-stone-50">
      <div className="max-w-5xl mx-auto">
        <div className="text-center mb-10 sm:mb-14">
          <h2 className="text-2xl sm:text-3xl lg:text-4xl font-bold text-stone-900 tracking-tight mb-4">
            One policy across your agent stack.
          </h2>
          <p className="text-stone-500 leading-relaxed max-w-2xl mx-auto text-sm sm:text-base">
            Native platform controls stay in place. Conduct applies one policy and evidence model <em>across</em> the mix of agent tools your team actually runs.
          </p>
        </div>
        <div className="flex justify-center mb-12 overflow-x-auto">
          <RuntimeFlow />
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-6 max-w-3xl mx-auto text-sm text-stone-600">
          <p className="flex items-start gap-2">
            <span className="text-stone-400 font-mono shrink-0">SDK</span>
            <span>Drop-in base URL replacement. No SDK changes.</span>
          </p>
          <p className="flex items-start gap-2">
            <span className="text-stone-400 font-mono shrink-0">CLI</span>
            <span>Post-tool-use hook on Claude Code, Cursor, Codex, Copilot.</span>
          </p>
          <p className="flex items-start gap-2">
            <span className="text-stone-400 font-mono shrink-0">MCP</span>
            <span>Guard wraps MCP tool invocations before they reach the server.</span>
          </p>
        </div>
      </div>
    </section>
  )
}

/* ─── 7. Evidence ─────────────────────────────────────────────────────── */

function EvidenceSection() {
  return (
    <section className="py-12 sm:py-20 px-4 sm:px-6 border-t border-stone-100">
      <div className="max-w-5xl mx-auto">
        <div className="grid lg:grid-cols-2 gap-10 lg:gap-12 items-start">
          <div>
            <h2 className="text-2xl sm:text-3xl lg:text-4xl font-bold text-stone-900 tracking-tight mb-4">
              Know exactly what happened — and why.
            </h2>
            <p className="text-stone-500 leading-relaxed mb-6 text-sm sm:text-base">
              Every Guard decision is recorded with agent, action, resource, matched rule, reason, user, and timestamp — in a SHA-256 hash-chained audit trail. Altered entries break the chain. Export-ready for SOC 2, HIPAA, and PCI DSS.
            </p>
            <ul className="space-y-2 text-sm text-stone-600">
              {[
                "Hash-chained integrity — not just logged, cryptographically ordered",
                "Approval decisions captured with actor, timestamp, and rationale",
                "Compliance report generation: SOC 2, HIPAA, PCI DSS",
                "Export and verification API — machine-readable proof",
              ].map((item) => (
                <li key={item} className="flex items-start gap-2">
                  <span className="text-emerald-600 font-bold mt-0.5 shrink-0">✓</span>
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </div>
          <div className="flex justify-start lg:justify-end mt-2 lg:mt-0">
            <EvidenceReceipt />
          </div>
        </div>
      </div>
    </section>
  )
}

/* ─── 8. Honest security ──────────────────────────────────────────────── */

const HONEST_CAPABILITIES: CapabilityItem[] = [
  { name: "Pre-call policy evaluation (allow / block / approve / audit)", status: "SHIPPED" },
  { name: "SHA-256 hash-chained audit trail", status: "SHIPPED" },
  { name: "CLI hook — Claude Code, Cursor, Codex, Copilot", status: "SHIPPED" },
  { name: "HTTP proxy enforcement", status: "SHIPPED" },
  { name: "MCP tool interception", status: "SHIPPED" },
  { name: "Human approval gates (Slack + UI)", status: "SHIPPED" },
  { name: "15 compliance packs (OWASP, SOC 2, HIPAA, PCI, EU AI Act, NIST, ISO 42001...)", status: "SHIPPED" },
  { name: "Kubernetes deployment templates", status: "PREVIEW" },
  { name: "LiteLLM Guard integration", status: "PREVIEW" },
  { name: "Air-gapped / on-prem deployment", status: "PLANNED" },
  { name: "Cross-agent workflow correlation (Operations)", status: "PLANNED" },
]

function HonestSecuritySection() {
  return (
    <section className="py-12 sm:py-20 px-4 sm:px-6 border-t border-stone-100 bg-stone-50">
      <div className="max-w-5xl mx-auto">
        <div className="grid lg:grid-cols-2 gap-10 lg:gap-12">
          <div>
            <h2 className="text-2xl sm:text-3xl lg:text-4xl font-bold text-stone-900 tracking-tight mb-4">
              We publish where Guard stops.
            </h2>
            <p className="text-stone-500 leading-relaxed mb-4 text-sm sm:text-base">
              Every capability on this list maps to code in the repo. SHIPPED means it is in production. PREVIEW means it is working but not GA. PLANNED means it is on the roadmap, not in the codebase.
            </p>
            <p className="text-sm text-stone-400">
              Last audit: 2026-09-01 · Source: automated codebase scan
            </p>
          </div>
          <div className="mt-2 lg:mt-0">
            <CapabilityStatus items={HONEST_CAPABILITIES} showLegend />
          </div>
        </div>
      </div>
    </section>
  )
}

/* ─── 9. Open source ──────────────────────────────────────────────────── */

const OSS_COMPONENTS = [
  {
    name: "conduct-cli",
    license: "Apache-2.0",
    repo: "packages/conduct-cli",
    purpose: "Agent lifecycle management, Guard sync, testing",
  },
  {
    name: "Guard runtime core",
    license: "Apache-2.0",
    repo: "apps/api/app/guard",
    purpose: "Core enforcement engine — evaluation, scoring, audit",
  },
  {
    name: "Playbook DSL compiler",
    license: "Apache-2.0",
    repo: "apps/api/app/compiler",
    purpose: "YAML playbook definition and execution graph",
  },
  {
    name: "Agent Booster MCP",
    license: "Apache-2.0",
    repo: "tools/booster",
    purpose: "Developer productivity tools for Claude and Cursor",
  },
]

function OpenSourceSection() {
  return (
    <section className="py-12 sm:py-20 px-4 sm:px-6 border-t border-stone-100">
      <div className="max-w-5xl mx-auto">
        <h2 className="text-2xl sm:text-3xl lg:text-4xl font-bold text-stone-900 tracking-tight mb-4">
          Open where trust matters.
        </h2>
        <p className="text-stone-500 mb-8 sm:mb-10 max-w-2xl text-sm sm:text-base">
          The enforcement engine, CLI, compiler, and developer tools are Apache-2.0. You can read, audit, fork, and self-host them. The hosted product adds workspace management, multi-user access, and the managed SaaS layer.
        </p>

        {/* Desktop table */}
        <div className="hidden sm:block border border-stone-200 rounded-xl overflow-hidden bg-white">
          <div className="grid grid-cols-4 text-[10px] font-mono font-bold uppercase tracking-widest text-stone-400 px-5 py-3 border-b border-stone-100 bg-stone-50">
            <span>Component</span>
            <span>Licence</span>
            <span>Repository path</span>
            <span>Purpose</span>
          </div>
          {OSS_COMPONENTS.map((c, i) => (
            <div
              key={c.name}
              className={`grid grid-cols-4 gap-2 px-5 py-3 text-sm ${
                i < OSS_COMPONENTS.length - 1 ? "border-b border-stone-100" : ""
              }`}
            >
              <span className="font-semibold text-stone-900 font-mono text-xs">{c.name}</span>
              <span className="text-emerald-700 text-xs font-mono">{c.license}</span>
              <span className="text-stone-400 text-xs font-mono truncate">{c.repo}</span>
              <span className="text-stone-500 text-xs">{c.purpose}</span>
            </div>
          ))}
        </div>

        {/* Mobile card stack */}
        <div className="sm:hidden space-y-3">
          {OSS_COMPONENTS.map((c) => (
            <div key={c.name} className="border border-stone-200 rounded-xl p-4 bg-white">
              <div className="flex items-start justify-between gap-2 mb-2">
                <span className="font-semibold text-stone-900 font-mono text-sm">{c.name}</span>
                <span className="text-emerald-700 text-xs font-mono shrink-0">{c.license}</span>
              </div>
              <p className="text-xs text-stone-400 font-mono mb-1">{c.repo}</p>
              <p className="text-xs text-stone-500">{c.purpose}</p>
            </div>
          ))}
        </div>

        <p className="mt-4 text-xs text-stone-400">
          Apache-2.0 includes an explicit patent grant.{" "}
          <a href="https://github.com/sseshachala/conductai" className="underline hover:text-stone-700 transition-colors">
            View on GitHub →
          </a>
        </p>
      </div>
    </section>
  )
}

/* ─── 10. Deployment ──────────────────────────────────────────────────── */

const DEPLOYMENT_OPTIONS: Array<{
  label: string
  status: CapStatus
  desc: string
  cta: { text: string; href: string } | null
}> = [
  {
    label: "SaaS",
    status: "SHIPPED",
    desc: "Managed at conductai.ai. No infrastructure to run. US-hosted.",
    cta: { text: "Start Agent Discovery", href: "/discovery" },
  },
  {
    label: "Docker",
    status: "SHIPPED",
    desc: "Self-hosted via Docker Compose. Full control. Apache-2.0.",
    cta: { text: "View docs", href: "/docs/self-hosted" },
  },
  {
    label: "Kubernetes",
    status: "PREVIEW",
    desc: "Reference deployment templates. Working but not GA.",
    cta: { text: "Join preview", href: "/book-demo" },
  },
  {
    label: "Air-gapped",
    status: "PLANNED",
    desc: "On-prem deployment with no external connectivity. On the roadmap.",
    cta: null,
  },
]

const DEPLOY_BORDER: Record<CapStatus, string> = {
  SHIPPED: "border-stone-200",
  PREVIEW: "border-amber-200",
  PLANNED: "border-stone-200",
}

function DeploymentSection() {
  return (
    <section className="py-12 sm:py-20 px-4 sm:px-6 border-t border-stone-100 bg-stone-50">
      <div className="max-w-5xl mx-auto">
        <h2 className="text-2xl sm:text-3xl lg:text-4xl font-bold text-stone-900 tracking-tight mb-4">
          Deploy Guard where your controls need to live.
        </h2>
        <p className="text-stone-500 mb-10 sm:mb-12 max-w-2xl text-sm sm:text-base">
          Start on SaaS in minutes. Move to self-hosted Docker when you need data residency. Kubernetes templates are in preview.
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {DEPLOYMENT_OPTIONS.map((opt) => (
            <div
              key={opt.label}
              className={`border ${DEPLOY_BORDER[opt.status]} rounded-xl p-5 bg-white flex flex-col gap-3`}
            >
              <div className="flex items-center justify-between gap-2">
                <p className="font-bold text-stone-900">{opt.label}</p>
                {/* CapabilityStatus chip — single item, name intentionally empty */}
                <div className="shrink-0">
                  <CapabilityStatus
                    items={[{ name: "", status: opt.status }]}
                    showLegend={false}
                  />
                </div>
              </div>
              <p className="text-sm text-stone-500 leading-relaxed flex-1">{opt.desc}</p>
              {opt.cta && (
                <a
                  href={opt.cta.href}
                  className="text-sm font-semibold text-stone-900 hover:underline mt-auto min-h-[44px] flex items-center"
                >
                  {opt.cta.text} →
                </a>
              )}
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

/* ─── Final CTA ───────────────────────────────────────────────────────── */

function FinalCTASection() {
  return (
    <section className="py-16 sm:py-24 px-4 sm:px-6 bg-indigo-600">
      <div className="max-w-3xl mx-auto text-center">
        <h2 className="text-2xl sm:text-3xl lg:text-4xl font-bold text-white tracking-tight mb-4">
          Put runtime policy in front of your agents.
        </h2>
        <p className="text-indigo-100 mb-8 text-sm sm:text-base leading-relaxed">
          Agent Discovery mode runs for 14 days, read-only. See every agent action across your team before you enforce anything.
        </p>
        <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-center gap-3">
          <a
            href="/discovery"
            className="rounded-xl bg-white text-indigo-700 px-8 py-4 text-base font-semibold hover:bg-indigo-50 transition-colors text-center min-h-[48px] flex items-center justify-center"
          >
            Start Agent Discovery — 14 days free
          </a>
          <a
            href="/book-demo"
            className="rounded-xl border border-indigo-300 text-white px-8 py-4 text-base font-semibold hover:bg-indigo-700 transition-colors text-center min-h-[48px] flex items-center justify-center"
          >
            Book a Demo
          </a>
        </div>
      </div>
    </section>
  )
}

/* ─── Footer ──────────────────────────────────────────────────────────── */
