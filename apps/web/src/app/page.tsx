"use client"

import { useState } from "react"
import { DecisionCard } from "@/components/marketing/facelift/DecisionCard"
import { AgentSurfaceStrip } from "@/components/marketing/facelift/AgentSurfaceStrip"
import { EvidenceReceipt } from "@/components/marketing/facelift/EvidenceReceipt"
import { RuntimeFlow } from "@/components/marketing/facelift/RuntimeFlow"
import { CapabilityStatus, type CapabilityItem, type CapStatus } from "@/components/marketing/facelift/CapabilityStatus"

export default function HomePage() {
  return (
    <div className="min-h-screen bg-white flex flex-col">
      <Nav />
      <main className="flex-1">
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
      </main>
      <PageFooter />
    </div>
  )
}

/* ─── Nav ─────────────────────────────────────────────────────────────── */

function Nav() {
  const [mobileOpen, setMobileOpen] = useState(false)

  return (
    <header className="sticky top-0 bg-white/95 backdrop-blur-sm z-50 border-b border-stone-100">
      <div className="px-4 sm:px-6 py-3 sm:py-4 flex items-center justify-between max-w-6xl mx-auto w-full">
        <a href="/">
          <img src="/logo.png" alt="Conduct AI" className="h-8 sm:h-10 w-auto" />
        </a>

        {/* Desktop nav */}
        <nav className="hidden md:flex items-center gap-6">
          <ProductDropdown />
          <SolutionsDropdown />
          <DevelopersDropdown />
          <a href="/security" className="text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">Security</a>
          <a href="/pricing" className="text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">Pricing</a>
          <a href="/partners" className="text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">Partners</a>
          <a href="/blog" className="text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">Blog</a>
        </nav>

        <div className="flex items-center gap-2 sm:gap-3">
          <a href="/sign-in" className="text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors hidden sm:block">
            Sign in
          </a>
          <a href="/book-demo" className="text-sm font-medium text-stone-600 hover:text-stone-900 transition-colors hidden sm:block">
            Book Demo
          </a>
          <a
            href="/discovery"
            className="rounded-lg bg-stone-900 text-white px-3 sm:px-4 py-2 text-sm font-semibold hover:bg-stone-700 transition-colors min-h-[44px] flex items-center"
          >
            Start Agent Discovery
          </a>
          {/* Hamburger */}
          <button
            className="md:hidden p-2 rounded-lg text-stone-600 hover:bg-stone-100 transition-colors min-h-[44px] min-w-[44px] flex items-center justify-center"
            aria-label="Open navigation menu"
            aria-expanded={mobileOpen}
            onClick={() => setMobileOpen(!mobileOpen)}
          >
            {mobileOpen ? (
              <svg width="20" height="20" viewBox="0 0 20 20" fill="currentColor">
                <path d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" />
              </svg>
            ) : (
              <svg width="20" height="20" viewBox="0 0 20 20" fill="currentColor">
                <path d="M3 5h14a1 1 0 110 2H3a1 1 0 010-2zm0 4h14a1 1 0 110 2H3a1 1 0 010-2zm0 4h14a1 1 0 110 2H3a1 1 0 010-2z" />
              </svg>
            )}
          </button>
        </div>
      </div>

      {/* Mobile drawer */}
      {mobileOpen && (
        <div className="md:hidden border-t border-stone-100 bg-white px-4 pb-4">
          <div className="pt-3 space-y-1">
            <MobileNavGroup label="Product">
              <MobileNavItem href="/guard" label="Guard" />
              <MobileNavItem href="/playbooks" label="Playbooks" />
              <MobileNavItem href="/evidence" label="Evidence" />
              <MobileNavItem href="/mcp-gateway" label="MCP" />
              <MobileNavItem href="/security" label="Security" />
              <MobileNavItem href="/pricing" label="Pricing" />
              <MobileNavItem href="/partners" label="Partners" />
            </MobileNavGroup>
            <MobileNavGroup label="Solutions">
              <MobileNavItem href="/use-cases" label="Use cases" />
              <MobileNavItem href="/solutions/engineering-leaders" label="Engineering Agents" />
              <MobileNavItem href="/solutions/security-compliance" label="Security Teams" />
              <MobileNavItem href="/solutions/action-governance" label="Business Actions" />
            </MobileNavGroup>
            <MobileNavGroup label="Developers">
              <MobileNavItem href="/docs" label="Docs" />
              <MobileNavItem href="/tools/conduct-cli" label="CLI" />
              <MobileNavItem href="/docs/lens" label="Lens" />
              <MobileNavItem href="/open-source" label="Open Source" />
              <MobileNavItem href="https://github.com/sseshachala/conductai" label="GitHub" />
            </MobileNavGroup>
            <div className="pt-3 border-t border-stone-100 flex flex-col gap-2">
              <a href="/sign-in" className="text-sm font-medium text-stone-600 py-2 hover:text-stone-900">Sign in</a>
              <a href="/book-demo" className="text-sm font-medium text-stone-600 py-2 hover:text-stone-900">Book a Demo</a>
            </div>
          </div>
        </div>
      )}
    </header>
  )
}

function MobileNavGroup({ label, children }: { label: string; children: React.ReactNode }) {
  const [open, setOpen] = useState(false)
  return (
    <div>
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between py-2.5 text-sm font-semibold text-stone-700 min-h-[44px]"
      >
        {label}
        <svg
          width="14"
          height="14"
          viewBox="0 0 14 14"
          fill="currentColor"
          className={`opacity-40 transition-transform ${open ? "rotate-180" : ""}`}
        >
          <path d="M2 4l5 5 5-5" />
        </svg>
      </button>
      {open && (
        <div className="pl-3 pb-2 space-y-1">
          {children}
        </div>
      )}
    </div>
  )
}

function MobileNavItem({ href, label }: { href: string; label: string }) {
  return (
    <a
      href={href}
      className="block py-2 text-sm text-stone-500 hover:text-stone-900 transition-colors min-h-[44px] flex items-center"
    >
      {label}
    </a>
  )
}

function ChevronDown() {
  return (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="currentColor" className="opacity-40 mt-0.5">
      <path d="M2 4l4 4 4-4" />
    </svg>
  )
}

function ProductDropdown() {
  return (
    <div className="relative group">
      <a href="#" className="flex items-center gap-1 text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">
        Product
        <ChevronDown />
      </a>
      <div className="absolute left-0 top-full pt-2 hidden group-hover:block z-50 min-w-[220px]">
        <div className="bg-white border border-stone-200 rounded-xl shadow-lg py-2">
          <NavItem href="/guard" title="Guard" desc="Runtime policy enforcement for every AI agent" />
          <NavItem href="/playbooks" title="Playbooks" desc="39 pre-built automations with Guard built in" />
          <NavItem href="/evidence" title="Evidence" desc="Hash-chained audit trail for every decision" />
          <NavItem href="/mcp-gateway" title="MCP" desc="Policy for every MCP tool invocation" />
        </div>
      </div>
    </div>
  )
}

function SolutionsDropdown() {
  return (
    <div className="relative group">
      <a href="#" className="flex items-center gap-1 text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">
        Solutions
        <ChevronDown />
      </a>
      <div className="absolute left-0 top-full pt-2 hidden group-hover:block z-50 min-w-[240px]">
        <div className="bg-white border border-stone-200 rounded-xl shadow-lg py-2">
          <NavItem href="/use-cases" title="Use cases" desc="Prove, kill, contain, answer, discover" />
          <div className="my-1 border-t border-stone-100" />
          <div className="px-4 py-1.5">
            <p className="text-[10px] font-bold uppercase tracking-widest text-stone-400">By team</p>
          </div>
          <NavItem href="/solutions/engineering-leaders" title="Engineering Agents" desc="Consistent policy across your agent fleet" />
          <NavItem href="/solutions/security-compliance" title="Security Teams" desc="Enforcement, evidence, and compliance reports" />
          <NavItem href="/solutions/action-governance" title="Business Actions" desc="Control before a refund, deploy, or email sends" />
          <div className="my-1 border-t border-stone-100" />
          <div className="px-4 py-1.5">
            <p className="text-[10px] font-bold uppercase tracking-widest text-stone-400">Industry</p>
          </div>
          <NavItem href="/solutions/financial-services" title="Financial Services" desc="PCI DSS 4.0 · refund controls · audit" />
          <NavItem href="/solutions/life-sciences" title="Life Sciences" desc="HIPAA · 21 CFR Part 11 · validation" />
          <div className="my-1 border-t border-stone-100" />
          <div className="px-4 py-1.5">
            <p className="text-[10px] font-bold uppercase tracking-widest text-stone-400">Integrations</p>
          </div>
          <NavItem href="/solutions/nemo-guardrails" title="NeMo Guardrails + Conduct" desc="App safety layer + org governance layer" />
        </div>
      </div>
    </div>
  )
}

function DevelopersDropdown() {
  return (
    <div className="relative group">
      <a href="#" className="flex items-center gap-1 text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">
        Developers
        <ChevronDown />
      </a>
      <div className="absolute left-0 top-full pt-2 hidden group-hover:block z-50 min-w-[200px]">
        <div className="bg-white border border-stone-200 rounded-xl shadow-lg py-2">
          <NavItem href="/docs" title="Docs" desc="Full API and integration reference" />
          <NavItem href="/tools/conduct-cli" title="CLI" desc="Agent lifecycle and Guard sync" />
          <NavItem href="/docs/lens" title="Lens" desc="Chat tools for Guard, playbooks, and evidence" />
          <NavItem href="/open-source" title="Open Source" desc="Apache-2.0 components" />
          <NavItem href="https://github.com/sseshachala/conductai" title="GitHub" desc="Source, issues, and releases" />
        </div>
      </div>
    </div>
  )
}

function NavItem({ href, title, desc }: { href: string; title: string; desc: string }) {
  return (
    <a href={href} className="flex flex-col px-4 py-2.5 text-sm text-stone-700 hover:bg-stone-50 transition-colors">
      <span className="font-semibold text-stone-900">{title}</span>
      <span className="text-xs text-stone-400 mt-0.5">{desc}</span>
    </a>
  )
}

/* ─── 1. Hero ─────────────────────────────────────────────────────────── */

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

  return (
    <section className="py-12 sm:py-20 px-4 sm:px-6 border-t border-stone-100">
      <div className="max-w-5xl mx-auto">
        <h2 className="text-2xl sm:text-3xl lg:text-4xl font-bold text-stone-900 tracking-tight mb-4">
          Allow. Approve. Block. Prove.
        </h2>
        <p className="text-stone-500 mb-10 sm:mb-12 max-w-2xl text-sm sm:text-base">
          Four outcomes. Every agent action gets one. Runtime, not retrospective.
        </p>
        <div className="grid grid-cols-4 md:grid-cols-4 gap-3 md:gap-5">
          {verbs.map((v) => (
            <div key={v.word} className="flex flex-col gap-3">
              {/* Detail card — hidden on mobile, shown on tablet+ */}
              <div className="hidden md:block">
                {v.decision ? (
                  <DecisionCard
                    agent="claude-code / deploy-agent"
                    action="deploy_production"
                    resource="payments-api"
                    policy="production-change-v4"
                    decision={v.decision}
                    compact
                  />
                ) : (
                  <div className="border border-stone-200 rounded-xl px-4 py-3 bg-white">
                    <div className="flex items-center gap-2 mb-2">
                      <span className="inline-block w-2 h-2 rounded-full bg-stone-400" />
                      <span className="font-mono text-[10px] font-bold uppercase tracking-wider text-stone-500">
                        Hash-chained
                      </span>
                    </div>
                    <p className="font-mono text-[10px] text-stone-400">
                      SHA-256 · integrity verified
                    </p>
                  </div>
                )}
              </div>
              {/* Mobile-compact marker — dot + verb, no description */}
              <div className="md:hidden flex flex-col items-center text-center gap-1.5">
                <span className={`inline-block w-2 h-2 rounded-full ${
                  v.decision === "ALLOW" ? "bg-emerald-500" :
                  v.decision === "APPROVE" ? "bg-amber-500" :
                  v.decision === "BLOCK" ? "bg-red-500" :
                  "bg-stone-400"
                }`} />
                <p className={`text-sm font-black tracking-tight ${v.colour}`}>{v.word}</p>
              </div>
              {/* Verb + long description — full on md+, hidden on mobile */}
              <div className="hidden md:block">
                <p className={`text-lg font-black tracking-tight ${v.colour}`}>{v.word}</p>
                <p className="text-sm text-stone-500 mt-1 leading-relaxed">{v.line}</p>
              </div>
            </div>
          ))}
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
            Cortex enforces inside Cortex. Copilot Studio inside Copilot. Bedrock inside Bedrock. Conduct enforces <em>across</em> whatever mix your team actually runs — the native controls stay, Guard sits above them.
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
    <section className="py-16 sm:py-24 px-4 sm:px-6 border-t border-stone-100">
      <div className="max-w-2xl mx-auto text-center">
        <h2 className="text-2xl sm:text-3xl lg:text-4xl font-bold text-stone-900 tracking-tight mb-4">
          Put runtime policy in front of your agents.
        </h2>
        <p className="text-stone-500 mb-8 text-sm sm:text-base">
          Agent Discovery mode runs for 14 days, read-only. See every agent action across your team before you enforce anything.
        </p>
        <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-center gap-3">
          <a
            href="/discovery"
            className="rounded-xl bg-stone-900 text-white px-8 py-4 text-base font-semibold hover:bg-stone-700 transition-colors text-center min-h-[48px] flex items-center justify-center"
          >
            Start Agent Discovery — 14 days free
          </a>
          <a
            href="/book-demo"
            className="rounded-xl border border-stone-200 text-stone-700 px-8 py-4 text-base font-semibold hover:bg-stone-50 transition-colors text-center min-h-[48px] flex items-center justify-center"
          >
            Book a Demo
          </a>
        </div>
      </div>
    </section>
  )
}

/* ─── Footer ──────────────────────────────────────────────────────────── */

function PageFooter() {
  const footerCols = [
    {
      heading: "Product",
      links: [
        ["Guard", "/guard"],
        ["Playbooks", "/playbooks"],
        ["Evidence", "/evidence"],
        ["MCP", "/mcp-gateway"],
      ] as [string, string][],
    },
    {
      heading: "Platform",
      links: [
        ["Agent Discovery", "/docs/discovery"],
        ["Router", "/router"],
        ["Templates", "/docs/templates"],
        ["Registry", "/registry"],
        ["Team OS", "/team-os"],
        ["CLI", "/tools/conduct-cli"],
      ] as [string, string][],
    },
    {
      heading: "Solutions",
      links: [
        ["Engineering Agents", "/solutions/engineering-leaders"],
        ["Security Teams", "/solutions/security-compliance"],
        ["Business Actions", "/solutions/action-governance"],
        ["Financial Services", "/solutions/financial-services"],
        ["Life Sciences", "/solutions/life-sciences"],
        ["Deployment options", "/deployment"],
      ] as [string, string][],
    },
    {
      heading: "Developers",
      links: [
        ["Docs", "/docs"],
        ["CLI", "/tools/conduct-cli"],
        ["Open Source", "/open-source"],
        ["GitHub", "https://github.com/sseshachala/conductai"],
      ] as [string, string][],
    },
    {
      heading: "Company",
      links: [
        ["About", "/about"],
        ["Blog", "/blog"],
        ["Security", "/security"],
        ["Privacy", "/privacy"],
        ["Terms", "/terms"],
      ] as [string, string][],
    },
  ]

  return (
    <footer className="border-t border-stone-100 py-10 px-4 sm:px-6 bg-white">
      <div className="max-w-6xl mx-auto">
        <div className="flex flex-col md:flex-row justify-between gap-8 mb-10">
          <div className="shrink-0">
            <img src="/logo.png" alt="Conduct AI" className="h-8 w-auto mb-3" />
            <p className="text-sm text-stone-400 max-w-xs leading-relaxed">
              Runtime policy for AI agent stacks.
            </p>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-6 sm:gap-8">
            {footerCols.map((col) => (
              <div key={col.heading}>
                <p className="text-xs font-bold uppercase tracking-widest text-stone-400 mb-3">
                  {col.heading}
                </p>
                <ul className="space-y-2">
                  {col.links.map(([label, href]) => (
                    <li key={label}>
                      <a
                        href={href}
                        className="text-sm text-stone-500 hover:text-stone-900 transition-colors"
                      >
                        {label}
                      </a>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </div>
        <div className="border-t border-stone-100 pt-6 flex flex-col sm:flex-row justify-between items-center gap-4 text-xs text-stone-400 text-center sm:text-left">
          <span>
            © {new Date().getFullYear()} Conduct AI. All rights reserved. · Patent pending (US 64/109,502)
          </span>
          <div className="flex items-center gap-4 flex-wrap justify-center">
            <a
              href="https://www.linkedin.com/company/conductai/"
              target="_blank"
              rel="noopener noreferrer"
              className="hover:text-stone-700 transition-colors min-h-[44px] flex items-center"
              aria-label="LinkedIn"
            >
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="w-4 h-4">
                <path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433a2.062 2.062 0 0 1-2.063-2.065 2.064 2.064 0 1 1 2.063 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z" />
              </svg>
            </a>
            <a
              href="https://www.youtube.com/@Conductai"
              target="_blank"
              rel="noopener noreferrer"
              className="hover:text-stone-700 transition-colors min-h-[44px] flex items-center"
              aria-label="YouTube"
            >
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="w-4 h-4">
                <path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z" />
              </svg>
            </a>
            <span className="hidden sm:inline">Envisioned, designed and developed with love from Houston</span>
          </div>
        </div>
      </div>
    </footer>
  )
}
