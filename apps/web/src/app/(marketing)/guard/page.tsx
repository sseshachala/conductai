import Link from "next/link"
import { DecisionCard } from "@/components/marketing/facelift/DecisionCard"
import { PolicySnippet } from "@/components/marketing/facelift/PolicySnippet"
import { EvidenceReceipt } from "@/components/marketing/facelift/EvidenceReceipt"
import { AgentSurfaceStrip } from "@/components/marketing/facelift/AgentSurfaceStrip"
import { ThreatModelRow } from "@/components/marketing/facelift/ThreatModelRow"
import { ActivityRow } from "@/components/marketing/facelift/ActivityRow"

export const metadata = {
  title: "Guard — Runtime policy for every AI agent | Conduct",
  description:
    "ConductGuard enforces runtime policy across AI agents, model gateways, and MCP tools — before consequential actions execute. Allow. Approve. Block. Prove.",
}

export default function GuardPage() {
  return (
    <div className="min-h-screen bg-white">
      <main className="max-w-5xl mx-auto px-6">

        {/* Hero — Figma frame 11 */}
        <section className="pt-20 pb-16 grid grid-cols-1 lg:grid-cols-2 gap-10 items-center">
          <div>
            <p className="text-xs font-mono font-bold uppercase tracking-widest text-stone-400 mb-4">
              Guard
            </p>
            <h1 className="text-4xl sm:text-5xl font-black tracking-tight text-stone-900 leading-[1.05] mb-6">
              Runtime policy for every AI agent.
            </h1>
            <p className="text-lg text-stone-500 leading-relaxed mb-4">
              Conduct Guard enforces runtime policy across any MCP-compatible AI agent, model gateway, and MCP
              tool — before consequential actions execute.
            </p>
            <p className="text-sm font-mono font-bold text-stone-700 tracking-wider mb-3">
              Allow. Approve. Block. Prove.
            </p>
            <p className="text-sm sm:text-base font-semibold text-stone-700 mb-10">
              Install in 10 minutes. Evidence for the CISO from day one.
            </p>
            <div className="flex flex-wrap gap-3">
              <Link
                href="/sign-up"
                className="inline-block rounded-xl bg-stone-900 text-white px-6 py-3 text-sm font-semibold hover:bg-stone-700 transition-colors"
              >
                Start Agent Discovery — 14 days free
              </Link>
              <Link
                href="/demo"
                className="inline-block rounded-xl border border-stone-200 bg-white text-stone-700 px-6 py-3 text-sm font-semibold hover:bg-stone-50 transition-colors"
              >
                Book a Demo
              </Link>
            </div>
          </div>
          <div className="lg:pl-4">
            <DecisionCard
              agent="claude-code / deploy-agent"
              action="deploy_production"
              resource="payments-api"
              policy="production-change-v4"
              decision="APPROVE"
              reason="Production deployment outside approved change window"
              showButtons
            />
          </div>
        </section>

        {/* One policy across surfaces */}
        <section className="mb-20">
          <h2 className="text-2xl font-bold text-stone-900 mb-3">
            One policy across your AI agent stack.
          </h2>
          <p className="text-stone-500 text-sm leading-relaxed mb-8 max-w-2xl">
            Write the rule once. Guard applies it wherever your agents work — through the CLI hook,
            the HTTP proxy, and the MCP layer. No separate configuration per tool.
          </p>
          <AgentSurfaceStrip />
        </section>

        {/* Allow / Approve / Block trio */}
        <section className="mb-20">
          <h2 className="text-2xl font-bold text-stone-900 mb-3">Three decisions. One engine.</h2>
          <p className="text-stone-500 text-sm leading-relaxed mb-8 max-w-2xl">
            Guard evaluates every action before it executes and returns one of three decisions.
            The decision, the rule that fired, and the reason are all recorded.
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-6">
            <DecisionCard
              agent="claude-code / deploy-agent"
              action="run_unit_tests"
              resource="orders-db"
              policy="production-change-v4"
              decision="ALLOW"
              reason="Action within policy limits"
            />
            <DecisionCard
              agent="claude-code / deploy-agent"
              action="deploy_production"
              resource="payments-api"
              policy="production-change-v4"
              decision="APPROVE"
              reason="Production deployment outside approved change window"
              showButtons
            />
            <DecisionCard
              agent="cursor-agent-17"
              action="update_terraform"
              resource="prod-vpc"
              policy="no-production-network-change"
              decision="BLOCK"
              reason="Production network modifications require approved change record."
            />
          </div>
        </section>

        {/* Policy + Consequential actions — Figma frame 11 */}
        <section className="mb-20">
          <h2 className="text-2xl font-bold text-stone-900 mb-3">Policy that can be inspected.</h2>
          <p className="text-stone-500 text-sm leading-relaxed mb-8 max-w-2xl">
            Policies are YAML files checked into your repository. No black-box rule engine. Any engineer
            can read, modify, and audit the rules that govern your agents.
          </p>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 items-start">
            <PolicySnippet language="yaml" />
            <div>
              <p className="text-xs font-mono font-bold uppercase tracking-widest text-stone-400 mb-3">
                Consequential actions
              </p>
              <div className="space-y-2.5">
                <ActivityRow
                  decision="BLOCK"
                  action="process_refund"
                  actor="over $500 limit"
                  timestamp="C-8911"
                />
                <ActivityRow
                  decision="APPROVE"
                  action="deploy_production"
                  actor="routes to Slack"
                  timestamp="payments-api"
                />
                <ActivityRow
                  decision="BLOCK"
                  action="read_env"
                  actor="secret access denied"
                  timestamp="prod"
                />
              </div>
              <p className="text-xs text-stone-400 mt-4 leading-relaxed max-w-md">
                Guard was built for actions that cannot be undone. Refunds, production deployments,
                secret reads, network changes — a policy decision before they execute, not after.
              </p>
            </div>
          </div>
          <div className="mt-8 border border-stone-200 rounded-xl bg-stone-50 px-5 py-4 inline-block">
            <p className="text-xs font-mono text-stone-400 mb-1 uppercase tracking-widest">Lens</p>
            <p className="text-sm font-mono text-stone-700">
              &ldquo;Ask Lens: &lsquo;what did Guard block last week?&rsquo;&rdquo;
            </p>
          </div>
        </section>

        {/* Evidence */}
        <section className="mb-20">
          <h2 className="text-2xl font-bold text-stone-900 mb-3">Every decision leaves a receipt.</h2>
          <p className="text-stone-500 text-sm leading-relaxed mb-8 max-w-2xl">
            Guard records the agent, action, resource, decision, rule, reason, and user for every evaluation.
            The receipt is hash-chained — altered entries break the chain.
          </p>
          <div className="flex justify-center">
            <EvidenceReceipt />
          </div>
        </section>

        {/* Deployment — Figma frame 11: dark section with 4 tiles */}
        <section className="mb-20 -mx-6 sm:-mx-10 lg:-mx-20 px-6 sm:px-10 lg:px-20 py-14 bg-stone-950 rounded-3xl">
          <h2 className="text-2xl font-bold text-white mb-3">Deploy Guard where your controls need to live.</h2>
          <p className="text-stone-400 text-sm leading-relaxed mb-8 max-w-2xl">
            Same policy engine, same CLI, same audit trail — regardless of where Guard runs.
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {[
              { name: "SaaS", status: "SHIPPED", note: "conductai.ai · US-based" },
              { name: "Docker", status: "SHIPPED", note: "Self-hosted Compose" },
              { name: "Kubernetes", status: "PREVIEW", note: "Reference templates" },
              { name: "Air-gapped", status: "PLANNED", note: "On-prem, no external calls" },
            ].map(({ name, status, note }) => (
              <div key={name} className="border border-stone-800 rounded-2xl bg-stone-900 p-5">
                <p className="text-white text-lg font-semibold mb-1">{name}</p>
                <p className={`text-[10px] font-mono uppercase tracking-widest mb-3 ${
                  status === "SHIPPED" ? "text-emerald-400" : status === "PREVIEW" ? "text-amber-400" : "text-stone-500"
                }`}>
                  {status}
                </p>
                <p className="text-stone-400 text-xs leading-relaxed">{note}</p>
              </div>
            ))}
          </div>
        </section>

        {/* What Guard does NOT protect */}
        <section className="mb-20 border border-stone-200 rounded-2xl overflow-hidden">
          <div className="px-6 py-5 bg-stone-50 border-b border-stone-200">
            <h2 className="text-lg font-bold text-stone-900">One policy where your stack isn&apos;t one vendor&apos;s.</h2>
            <p className="text-xs text-stone-400 mt-1">
              Native platform controls stay in place. Guard applies one policy and evidence model <em>across</em> the mix of agent tools your team actually runs. Here&apos;s the scope Guard owns — and what we intentionally leave to the tools and data layers you already have.
            </p>
          </div>
          <div className="px-6 py-2">
            <ThreatModelRow
              threat="Actions that bypass the hook, proxy, or MCP layer"
              coverage="Not protected"
              detail="Guard only evaluates actions routed through its enforcement surfaces. An agent that does not use the hook, proxy, or MCP layer is invisible to Guard."
            />
            <ThreatModelRow
              threat="Pre-call prompt injection (before Guard sees the prompt)"
              coverage="Partial"
              detail="Guard evaluates the tool call after the model has decided to call it. Injection attacks that alter the model intent before tool selection are upstream of Guard."
            />
            <ThreatModelRow
              threat="Consequential actions guarded by policy"
              coverage="Protected"
              detail="Refunds, deployments, network changes, secret reads — any action routed through Guard is evaluated before execution."
            />
            <ThreatModelRow
              threat="Cross-agent correlation (Operations context)"
              coverage="Not protected"
              detail="Guard evaluates each action in isolation. Context from prior actions by other agents is not yet available. This is the Operations gap — planned."
            />
            <ThreatModelRow
              threat="Audit trail integrity"
              coverage="Protected"
              detail="SHA-256 hash chain on every decision. Altered entries break verification."
            />
            <ThreatModelRow
              threat="Model-layer attacks (adversarial inputs to the LLM itself)"
              coverage="Partial"
              detail="Guard includes a prompt-injection detection pack and pattern-based detectors. ML-based detection is not implemented."
            />
          </div>
        </section>

        {/* CTA */}
        <section className="mb-20 text-center border-t border-stone-100 pt-16">
          <h2 className="text-2xl font-bold text-stone-900 mb-4">Put runtime policy in front of your agents.</h2>
          <div className="flex flex-wrap justify-center gap-3">
            <Link
              href="/sign-up"
              className="inline-block rounded-xl bg-stone-900 text-white px-6 py-3 text-sm font-semibold hover:bg-stone-700 transition-colors"
            >
              Start Agent Discovery — 14 days free
            </Link>
            <a
              href="https://github.com/sseshachala/conductai"
              className="inline-block rounded-xl border border-stone-200 bg-white text-stone-700 px-6 py-3 text-sm font-semibold hover:bg-stone-50 transition-colors"
            >
              View the open-source runtime →
            </a>
          </div>
        </section>

      </main>
    </div>
  )
}
