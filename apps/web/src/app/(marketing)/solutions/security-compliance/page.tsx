import Link from "next/link"
import { EvidenceReceipt } from "@/components/marketing/facelift/EvidenceReceipt"
import { CapabilityStatus } from "@/components/marketing/facelift/CapabilityStatus"
import { ThreatModelRow } from "@/components/marketing/facelift/ThreatModelRow"

export const metadata = {
  title: "Security Teams — Enforcement and evidence for AI agents | Conduct",
  description:
    "Guard enforces runtime policy across every AI agent. Every decision is hash-chained. Every compliance question has a signed answer.",
}

export default function SecurityTeamsPage() {
  return (
    <div className="min-h-screen bg-white">
      <main className="max-w-5xl mx-auto px-6">

        {/* Hero */}
        <section className="pt-20 pb-16 text-center">
          <p className="text-xs font-mono font-bold uppercase tracking-widest text-stone-400 mb-4">
            Security Teams
          </p>
          <h1 className="text-4xl sm:text-5xl font-black tracking-tight text-stone-900 leading-[1.05] mb-6">
            Enforcement at runtime. Evidence for every decision.
          </h1>
          <p className="text-lg text-stone-500 max-w-2xl mx-auto leading-relaxed mb-10">
            Guard runs before the action executes — not after. Every allow, approve, and block
            produces a signed receipt. Your compliance team has answers, not logs to correlate.
          </p>
          <div className="flex flex-wrap justify-center gap-3">
            <Link
              href="/sign-up"
              className="inline-block rounded-xl bg-stone-900 text-white px-6 py-3 text-sm font-semibold hover:bg-stone-700 transition-colors"
            >
              Start Discovery — 14 days free
            </Link>
            <Link
              href="/demo"
              className="inline-block rounded-xl border border-stone-200 bg-white text-stone-700 px-6 py-3 text-sm font-semibold hover:bg-stone-50 transition-colors"
            >
              Book a Demo
            </Link>
          </div>
        </section>

        {/* Enforcement */}
        <section className="mb-20">
          <h2 className="text-2xl font-bold text-stone-900 mb-3">Enforcement, not detection.</h2>
          <p className="text-stone-500 text-sm leading-relaxed mb-8 max-w-2xl">
            Guard intercepts every action before it executes and evaluates it against policy. This
            is not a SIEM or a log analyser. Policy runs at the action layer — before money moves,
            before the deployment lands, before the secret is read.
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-sm font-mono">
            {[
              { surface: "CLI hook", agents: "Claude Code · Cursor · Copilot · Codex", status: "SHIPPED" },
              { surface: "HTTP proxy", agents: "Any SDK with configurable base URL", status: "SHIPPED" },
              { surface: "MCP layer", agents: "Any MCP client — Claude Desktop, Cursor, Windsurf, Codex, and more", status: "SHIPPED" },
            ].map(({ surface, agents, status }) => (
              <div key={surface} className="border border-stone-200 rounded-xl bg-white p-5">
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-[10px] font-bold uppercase tracking-wider border border-emerald-200 bg-emerald-50 text-emerald-700 rounded px-1.5 py-0.5">
                    {status}
                  </span>
                </div>
                <p className="text-stone-900 font-bold text-[13px] mb-1">{surface}</p>
                <p className="text-stone-400 text-[11px] leading-relaxed">{agents}</p>
              </div>
            ))}
          </div>
        </section>

        {/* Evidence */}
        <section className="mb-20">
          <h2 className="text-2xl font-bold text-stone-900 mb-3">Signed evidence for every decision.</h2>
          <p className="text-stone-500 text-sm leading-relaxed mb-8 max-w-2xl">
            Every Guard evaluation produces a receipt. The receipt records the agent, action,
            resource, decision, rule that fired, user, and timestamp. Receipts are SHA-256 hash-chained —
            altered entries break verification. No pixel editing required to make your audit trail look right.
          </p>
          <div className="flex justify-center">
            <EvidenceReceipt />
          </div>
        </section>

        {/* Compliance packs */}
        <section className="mb-20">
          <h2 className="text-2xl font-bold text-stone-900 mb-3">15 compliance packs. Shipped.</h2>
          <p className="text-stone-500 text-sm leading-relaxed mb-6 max-w-2xl">
            Each pack is a JSON ruleset mapped to a compliance standard. Install once and Guard
            evaluates every agent action against the pack&apos;s rules automatically.
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 text-xs font-mono">
            {[
              "Conduct base",
              "OWASP Agentic Top 10",
              "SOC 2 CC7.3",
              "HIPAA §164.312",
              "PCI DSS 4.0",
              "EU AI Act",
              "NIST AI RMF",
              "ISO 42001",
              "IRS 1075",
              "Prompt injection",
              "Network operations",
              "Endpoint attacks",
              "Financial services",
              "Life sciences",
              "Support operations",
            ].map((pack) => (
              <div
                key={pack}
                className="border border-stone-200 rounded-lg bg-white px-4 py-2.5 text-stone-700 flex items-center gap-2"
              >
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 shrink-0" />
                {pack}
              </div>
            ))}
          </div>
        </section>

        {/* Deployment */}
        <section className="mb-20">
          <h2 className="text-2xl font-bold text-stone-900 mb-3">Deploy where your controls need to live.</h2>
          <p className="text-stone-500 text-sm leading-relaxed mb-6 max-w-2xl">
            Guard runs in your cloud, on your infrastructure, or as SaaS. Same policy engine,
            same audit trail, regardless of deployment model.
          </p>
          <CapabilityStatus
            showLegend
            items={[
              { name: "SaaS (conductai.ai)", status: "SHIPPED", note: "US-based" },
              { name: "Docker Compose (self-hosted)", status: "SHIPPED" },
              { name: "Kubernetes", status: "PREVIEW", note: "Reference templates" },
              { name: "Air-gapped / on-prem", status: "PLANNED" },
            ]}
          />
        </section>

        {/* Threat model */}
        <section className="mb-20 border border-stone-200 rounded-2xl overflow-hidden">
          <div className="px-6 py-5 bg-stone-50 border-b border-stone-200">
            <h2 className="text-lg font-bold text-stone-900">Guard threat coverage</h2>
            <p className="text-xs text-stone-400 mt-1">
              Honest scope. We publish where Guard stops.
            </p>
          </div>
          <div className="px-6 py-2">
            <ThreatModelRow
              threat="Consequential actions guarded by policy"
              coverage="Protected"
              detail="Refunds, deployments, network changes, secret reads — any action routed through Guard is evaluated before execution."
            />
            <ThreatModelRow
              threat="Audit trail integrity"
              coverage="Protected"
              detail="SHA-256 hash chain on every decision. Altered entries break verification."
            />
            <ThreatModelRow
              threat="Compliance pack coverage (SOC2, HIPAA, PCI DSS, EU AI Act, and 11 more)"
              coverage="Protected"
              detail="15 JSON rulesets evaluated against every agent action automatically."
            />
            <ThreatModelRow
              threat="Pre-call prompt injection"
              coverage="Partial"
              detail="Guard includes a prompt-injection detection pack. Attacks that alter model intent before tool selection are upstream of Guard."
            />
            <ThreatModelRow
              threat="Model-layer attacks (adversarial inputs to the LLM)"
              coverage="Partial"
              detail="Pattern-based detectors. ML-based detection is not implemented."
            />
            <ThreatModelRow
              threat="Actions that bypass Guard enforcement surfaces"
              coverage="Not protected"
              detail="An agent that does not use the hook, proxy, or MCP layer is invisible to Guard."
            />
            <ThreatModelRow
              threat="Cross-agent context correlation"
              coverage="Not protected"
              detail="Guard evaluates each action in isolation. Operations context is planned."
            />
          </div>
        </section>

        {/* CTA */}
        <section className="mb-20 text-center border-t border-stone-100 pt-16">
          <h2 className="text-2xl font-bold text-stone-900 mb-4">
            Runtime enforcement. Signed evidence. Honest scope.
          </h2>
          <div className="flex flex-wrap justify-center gap-3">
            <Link
              href="/sign-up"
              className="inline-block rounded-xl bg-stone-900 text-white px-6 py-3 text-sm font-semibold hover:bg-stone-700 transition-colors"
            >
              Start Discovery — 14 days free
            </Link>
            <Link
              href="/security"
              className="inline-block rounded-xl border border-stone-200 bg-white text-stone-700 px-6 py-3 text-sm font-semibold hover:bg-stone-50 transition-colors"
            >
              View full threat model →
            </Link>
          </div>
        </section>

      </main>
    </div>
  )
}
