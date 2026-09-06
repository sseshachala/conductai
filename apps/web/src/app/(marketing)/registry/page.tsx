import Link from "next/link"
import { PlaybookTile } from "@/components/marketing/facelift/PlaybookTile"
import type { PlaybookCategory, BlockType } from "@/components/marketing/facelift/PlaybookTile"

export const metadata = {
  title: "Registry — Conduct",
  description:
    "39 shipped playbooks for AI agent teams. Code review, security, incident response, CI/CD, and more — each one combining brain, guard, approval, and evidence blocks.",
}

interface PlaybookEntry {
  name: string
  category: PlaybookCategory
  description: string
  blocks: BlockType[]
}

const PLAYBOOKS: PlaybookEntry[] = [
  // Code Review
  { name: "pr-reviewer", category: "code-review", description: "Reviews every pull request with an AI brain block; Guard checks before posting comments.", blocks: ["trigger", "brain", "guard", "output"] },
  { name: "copilot-reviewer", category: "code-review", description: "Runs a structured review pass on Copilot-suggested changes before merge.", blocks: ["trigger", "brain", "guard", "output"] },
  { name: "bulk-pr-reviewer", category: "code-review", description: "Batch-reviews open PRs in a repository overnight.", blocks: ["trigger", "brain", "guard", "output"] },
  { name: "terraform-reviewer", category: "code-review", description: "Static analysis plus Guard policy check on every Terraform plan before apply.", blocks: ["trigger", "brain", "guard", "approval", "output"] },
  // CI/CD
  { name: "release-gating", category: "ci-cd", description: "Holds a release until Guard clears all policy checks and a human approves.", blocks: ["trigger", "brain", "guard", "approval", "output"] },
  { name: "release-readiness", category: "ci-cd", description: "Evaluates tests, coverage, and Guard signal before promoting to production.", blocks: ["trigger", "brain", "guard", "output"] },
  { name: "dependency-updater", category: "ci-cd", description: "Opens PRs for outdated dependencies; Guard blocks known-vulnerable versions.", blocks: ["trigger", "tool", "guard", "output"] },
  { name: "smoke-test", category: "ci-cd", description: "Runs a post-deploy smoke suite; Guard enforces test-pass policy before marking green.", blocks: ["trigger", "tool", "guard", "output"] },
  { name: "multi-env-smoke-test", category: "ci-cd", description: "Fans smoke tests across staging and production in parallel.", blocks: ["trigger", "tool", "guard", "output"] },
  { name: "security-patch-updater", category: "ci-cd", description: "Automatically applies security patches and routes high-severity changes to human approval.", blocks: ["trigger", "tool", "guard", "approval", "output"] },
  // Security
  { name: "security-scanner", category: "security", description: "Scans codebase for secrets, misconfigurations, and known CVEs. Guard blocks on critical findings.", blocks: ["trigger", "tool", "guard", "output"] },
  { name: "security-loop", category: "security", description: "Continuous security loop that re-scans on every commit and opens issues for new findings.", blocks: ["trigger", "tool", "guard", "output"] },
  { name: "security-autopilot-fix", category: "security", description: "Generates and opens fix PRs for security findings; Guard gates the push step.", blocks: ["trigger", "brain", "guard", "approval", "output"] },
  { name: "threat-modeler", category: "security", description: "Runs a threat-modelling pass against architecture docs; produces a findings report.", blocks: ["trigger", "brain", "guard", "output"] },
  { name: "ai-risk-assessment", category: "security", description: "Assesses AI-generated code for risk patterns mapped to the OWASP Agentic Top 10.", blocks: ["trigger", "brain", "guard", "output"] },
  { name: "dependency-audit", category: "security", description: "Audits transitive dependencies for licence conflicts and known vulnerabilities.", blocks: ["trigger", "tool", "guard", "output"] },
  // Incident
  { name: "incident-responder", category: "incident", description: "Triages on-call alerts, collects context, and pages the right owner. Guard checks before any action.", blocks: ["trigger", "brain", "guard", "approval", "output"] },
  { name: "postmortem-drafter", category: "incident", description: "Drafts a structured postmortem from incident timeline and Slack threads.", blocks: ["trigger", "brain", "guard", "output"] },
  { name: "ai-incident-drill", category: "incident", description: "Runs a synthetic incident scenario to test your response runbook.", blocks: ["trigger", "brain", "guard", "output"] },
  // Monitoring
  { name: "network-diagnosis-agent", category: "monitoring", description: "Diagnoses network degradation by correlating logs and metrics across infrastructure.", blocks: ["trigger", "tool", "brain", "guard", "output"] },
  { name: "docs-drift-detector", category: "monitoring", description: "Detects when documentation drifts from code and opens issues for the delta.", blocks: ["trigger", "brain", "guard", "output"] },
  { name: "codebase-guard-monitor", category: "monitoring", description: "Monitors Guard activity across your codebase; surfaces policy-coverage gaps.", blocks: ["trigger", "tool", "guard", "output"] },
  { name: "ai-drift-detector", category: "monitoring", description: "Detects when AI-generated code diverges from established team patterns.", blocks: ["trigger", "brain", "guard", "output"] },
  { name: "ai-output-auditor", category: "monitoring", description: "Audits a sample of AI completions for quality, accuracy, and policy compliance.", blocks: ["trigger", "brain", "guard", "output"] },
  { name: "multi-repo-scanner", category: "monitoring", description: "Scans across all repositories in an organisation for a given pattern or risk.", blocks: ["trigger", "tool", "guard", "output"] },
  // Onboarding
  { name: "acme-onboarding-e2e", category: "onboarding", description: "End-to-end onboarding flow for new workspace members, including Guard policy assignment.", blocks: ["trigger", "brain", "guard", "output"] },
  { name: "self-driving-network-approval-demo", category: "onboarding", description: "Demo playbook: network change requires human approval via Slack before Guard allows.", blocks: ["trigger", "brain", "guard", "approval", "output"] },
  { name: "base-autopilot", category: "onboarding", description: "Reference autopilot skeleton — extend with domain-specific brain and guard blocks.", blocks: ["trigger", "brain", "guard", "output"] },
  { name: "release-notes", category: "onboarding", description: "Generates release notes from merged PRs and posts to Slack.", blocks: ["trigger", "brain", "output"] },
  { name: "ci-notify", category: "onboarding", description: "Posts CI pass/fail status to Slack with Guard-sourced context.", blocks: ["trigger", "tool", "output"] },
  // Issue management
  { name: "issue-triage", category: "code-review", description: "Triages incoming GitHub issues: labels, assignee, and priority suggestions.", blocks: ["trigger", "brain", "guard", "output"] },
  { name: "oss-issue-sweep", category: "code-review", description: "Sweeps open issues on public repos and surfaces stale, duplicate, or blocked ones.", blocks: ["trigger", "brain", "output"] },
  // Testing
  { name: "flaky-test-detective", category: "ci-cd", description: "Identifies and quarantines flaky tests; Guard blocks merges until they are resolved.", blocks: ["trigger", "tool", "brain", "guard", "output"] },
  { name: "bughunter-active-scan", category: "security", description: "Active scan of a deployed service for common vulnerability classes.", blocks: ["trigger", "tool", "guard", "output"] },
  // Autopilot reference
  { name: "autopilot", category: "onboarding", description: "Full autopilot reference — brain-guided loop with Guard on every action and approval gates.", blocks: ["trigger", "brain", "guard", "approval", "output"] },
  { name: "autopilot-approved", category: "onboarding", description: "Autopilot variant where every action requires explicit human approval.", blocks: ["trigger", "brain", "guard", "approval", "output"] },
  { name: "thirdparty-autopilot-fix", category: "security", description: "Autopilot that triages and fixes issues surfaced by third-party security scanners.", blocks: ["trigger", "brain", "guard", "approval", "output"] },
]

const CATEGORY_LABELS: Record<PlaybookCategory, string> = {
  "code-review": "Code Review & Issues",
  "ci-cd": "CI / CD & Testing",
  security: "Security",
  incident: "Incident Response",
  monitoring: "Monitoring & Observability",
  onboarding: "Onboarding & Reference",
}

const CATEGORIES: PlaybookCategory[] = ["code-review", "ci-cd", "security", "incident", "monitoring", "onboarding"]

export default function RegistryPage() {
  return (
    <div className="min-h-screen bg-white">
      <main className="max-w-5xl mx-auto px-6">

        {/* Hero */}
        <section className="pt-20 pb-16 text-center">
          <p className="text-xs font-mono font-bold uppercase tracking-widest text-stone-400 mb-4">
            Registry
          </p>
          <h1 className="text-4xl sm:text-5xl font-black tracking-tight text-stone-900 leading-[1.05] mb-6">
            Registry. 39 playbooks shipped.
          </h1>
          <p className="text-lg text-stone-500 max-w-2xl mx-auto leading-relaxed mb-10">
            Each playbook combines a brain block for reasoning, a guard block for policy enforcement,
            approval gates for consequential actions, and hash-chained evidence for every decision.
            The same primitives. Every workflow.
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

        {/* Stats strip */}
        <section className="mb-16 border border-stone-200 rounded-2xl bg-stone-50 grid grid-cols-2 sm:grid-cols-4 divide-y sm:divide-y-0 sm:divide-x divide-stone-200">
          {[
            { n: "39", label: "Shipped playbooks" },
            { n: "15", label: "Compliance packs" },
            { n: "6", label: "BYO gateway adapters" },
            { n: "3", label: "Enforcement surfaces" },
          ].map(({ n, label }) => (
            <div key={label} className="px-6 py-5 text-center">
              <p className="text-2xl font-black text-stone-900 font-mono">{n}</p>
              <p className="text-xs text-stone-400 mt-1">{label}</p>
            </div>
          ))}
        </section>

        {/* Composability explanation */}
        <section className="mb-20">
          <h2 className="text-2xl font-bold text-stone-900 mb-3">What every playbook is made of</h2>
          <p className="text-stone-500 text-sm leading-relaxed mb-8 max-w-2xl">
            Playbooks are not scripts. They are structured compositions of typed blocks. The same block types
            appear across all 39 playbooks — which means policy, approval, and evidence are never bolt-ons.
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {[
              {
                type: "Brain",
                colour: "border-violet-200 bg-violet-50",
                badge: "bg-violet-600 text-white",
                desc: "Reasoning step. Reads context, decides what to do next. One brain per decision boundary.",
              },
              {
                type: "Guard",
                colour: "border-emerald-200 bg-emerald-50",
                badge: "bg-emerald-600 text-white",
                desc: "Policy check. Every action that touches an external system passes through a guard block before it executes.",
              },
              {
                type: "Approval",
                colour: "border-amber-200 bg-amber-50",
                badge: "bg-amber-500 text-white",
                desc: "Human-in-the-loop gate. Pauses the run and routes to Slack or Lens until a human decides.",
              },
              {
                type: "Evidence",
                colour: "border-stone-200 bg-white",
                badge: "bg-stone-700 text-white",
                desc: "Hash-chained receipt for every decision in the run. Replay any action, answer any auditor.",
              },
            ].map(({ type, colour, badge, desc }) => (
              <div key={type} className={`border rounded-xl p-5 ${colour}`}>
                <span className={`inline-block text-[10px] font-mono font-bold uppercase tracking-wider rounded px-2 py-0.5 mb-3 ${badge}`}>
                  {type}
                </span>
                <p className="text-sm text-stone-700 leading-relaxed">{desc}</p>
              </div>
            ))}
          </div>
        </section>

        {/* Category list + tile grid */}
        {CATEGORIES.map((cat) => {
          const tiles = PLAYBOOKS.filter((p) => p.category === cat)
          return (
            <section key={cat} className="mb-16">
              <div className="flex items-baseline gap-3 mb-6">
                <h2 className="text-lg font-bold text-stone-900">{CATEGORY_LABELS[cat]}</h2>
                <span className="text-xs font-mono text-stone-400">{tiles.length} playbooks</span>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                {tiles.map((p) => (
                  <PlaybookTile
                    key={p.name}
                    name={p.name}
                    category={p.category}
                    description={p.description}
                    blocks={p.blocks}
                  />
                ))}
              </div>
            </section>
          )
        })}

        {/* Cross-agent extension + Operations teaser */}
        <section className="mb-20 border border-stone-200 rounded-2xl p-8 bg-stone-50">
          <p className="text-xs font-mono font-bold uppercase tracking-widest text-stone-400 mb-3">
            Cross-agent extension
          </p>
          <h2 className="text-2xl font-bold text-stone-900 mb-3">
            The same playbook runs across any agent surface.
          </h2>
          <p className="text-stone-500 text-sm leading-relaxed max-w-2xl mb-6">
            Install a playbook once. It governs Claude Code, Cursor, Codex, and custom agents through the same
            policy engine. No per-tool configuration. No parallel audit trails.
          </p>
          <div className="border border-stone-200 rounded-xl bg-white px-5 py-4 inline-block mb-6">
            <p className="text-xs font-mono text-stone-400 mb-1 uppercase tracking-widest">Lens</p>
            <p className="text-sm font-mono text-stone-700">
              &ldquo;Ask Lens: &lsquo;which playbooks ran this week?&rsquo;&rdquo;
            </p>
          </div>
          <div className="pt-4 border-t border-stone-200">
            <p className="text-xs font-mono uppercase tracking-widest text-stone-400 mb-2">
              Coming — Design Partner Preview
            </p>
            <p className="text-sm text-stone-500 leading-relaxed max-w-xl">
              Operations will extend the playbook runtime to correlate events across external systems —
              letting Guard decisions account for what happened before this action, not just the action itself.
              Available to design partners first.
            </p>
          </div>
        </section>

        {/* CTA */}
        <section className="mb-20 text-center border-t border-stone-100 pt-16">
          <h2 className="text-2xl font-bold text-stone-900 mb-4">Start with Discovery. Add playbooks as you go.</h2>
          <p className="text-stone-500 text-sm mb-8 max-w-lg mx-auto leading-relaxed">
            Discovery maps what your agents are doing today. Playbooks extend that into governed, repeatable
            automation — with policy at every step.
          </p>
          <div className="flex flex-wrap justify-center gap-3">
            <Link
              href="/sign-up"
              className="inline-block rounded-xl bg-stone-900 text-white px-6 py-3 text-sm font-semibold hover:bg-stone-700 transition-colors"
            >
              Start Discovery — 14 days free
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
