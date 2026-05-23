"use client"

import { useState } from "react"

export default function ComparePage() {
  return (
    <div className="min-h-screen bg-white flex flex-col">

      {/* Nav */}
      <header className="px-6 py-5 flex items-center justify-between max-w-6xl mx-auto w-full border-b border-stone-100">
        <a href="/" className="flex items-center">
          <img src="/logo.png" alt="Conduct AI" className="h-8 w-auto" />
        </a>
        <div className="flex items-center gap-4">
          <a href="/marketplace" className="text-sm text-stone-500 hover:text-stone-900 transition-colors">Marketplace</a>
          <a href="https://narratr.ai/blog/conductai" target="_blank" rel="noopener noreferrer" className="text-sm text-stone-500 hover:text-stone-900 transition-colors">Blog</a>
          <a href="https://github.com/sseshachala/conductai" target="_blank" rel="noopener noreferrer" className="text-sm text-stone-500 hover:text-stone-900 transition-colors">GitHub</a>
          <a href="/sign-in" className="text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">Sign in →</a>
        </div>
      </header>

      {/* Hero */}
      <section className="px-6 py-16 text-center max-w-4xl mx-auto w-full">
        <div className="inline-flex items-center gap-2 bg-stone-100 text-stone-600 text-xs font-medium px-3 py-1.5 rounded-full mb-6">
          Last updated May 2026 · Based on public documentation
        </div>
        <h1 className="text-4xl sm:text-5xl font-bold text-stone-900 leading-tight tracking-tight mb-4">
          AI engineering tools,<br />
          <span className="text-indigo-600">compared honestly.</span>
        </h1>
        <p className="text-lg text-stone-500 max-w-2xl mx-auto leading-relaxed">
          There are excellent tools in this space. Each one makes different trade-offs.
          This page breaks down what each tool actually does, who it is built for, and where
          the differences matter — so you can pick what fits your team.
        </p>
        <p className="mt-4 text-sm text-stone-400 max-w-xl mx-auto">
          We built Conduct. We are clearly not neutral. We have tried to be as fair and accurate as possible —
          if anything here is wrong, <a href="https://github.com/sseshachala/conductai/issues" target="_blank" rel="noopener noreferrer" className="underline hover:text-stone-600">open an issue</a> and we will fix it.
        </p>
      </section>

      {/* Competitor cards */}
      <section className="px-6 pb-16">
        <div className="max-w-6xl mx-auto">
          <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest text-center mb-10">Tools in this comparison</p>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {TOOLS.map(t => (
              <a key={t.id} href={`#${t.id}`}
                className="bg-white rounded-2xl border border-stone-200 p-5 flex flex-col gap-3 hover:border-stone-300 hover:shadow-sm transition-all group">
                <div className="flex items-center justify-between">
                  <span className="text-2xl">{t.emoji}</span>
                  <span className={`text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-full ${t.categoryColor}`}>{t.category}</span>
                </div>
                <div>
                  <p className="font-bold text-stone-900 text-sm group-hover:text-indigo-600 transition-colors">{t.name}</p>
                  <p className="text-xs text-stone-500 mt-0.5">{t.maker}</p>
                </div>
                <p className="text-xs text-stone-500 leading-relaxed">{t.oneLiner}</p>
              </a>
            ))}
          </div>
        </div>
      </section>

      {/* Feature matrix */}
      <section className="px-4 pb-20 bg-stone-50">
        <div className="max-w-6xl mx-auto pt-16">
          <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest text-center mb-3">Feature matrix</p>
          <h2 className="text-2xl font-bold text-stone-900 text-center mb-2">Side-by-side comparison</h2>
          <p className="text-sm text-stone-500 text-center mb-10 max-w-xl mx-auto">
            ✅ = available &nbsp;·&nbsp; 🟡 = partial or limited &nbsp;·&nbsp; ❌ = not available &nbsp;·&nbsp; Based on public documentation as of May 2026.
          </p>
          <FeatureMatrix />
        </div>
      </section>

      {/* Detailed per-tool sections */}
      <section className="px-6 py-20">
        <div className="max-w-4xl mx-auto space-y-16">
          <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest text-center mb-0">In depth</p>
          {TOOLS.map(t => <ToolDetail key={t.id} tool={t} />)}
        </div>
      </section>

      {/* Who should use what */}
      <section className="bg-stone-50 px-6 py-20">
        <div className="max-w-4xl mx-auto">
          <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest text-center mb-3">Decision guide</p>
          <h2 className="text-2xl font-bold text-stone-900 text-center mb-10">Which tool fits your situation?</h2>
          <div className="space-y-4">
            {DECISION_GUIDE.map(d => (
              <div key={d.situation} className="bg-white rounded-2xl border border-stone-200 p-6 flex flex-col sm:flex-row gap-4">
                <div className="shrink-0">
                  <span className="text-2xl">{d.icon}</span>
                </div>
                <div className="flex-1">
                  <p className="font-semibold text-stone-900 mb-1">{d.situation}</p>
                  <p className="text-sm text-stone-500 leading-relaxed mb-3">{d.detail}</p>
                  <div className="flex flex-wrap gap-2">
                    {d.picks.map(p => (
                      <span key={p.name} className={`text-xs font-semibold px-2.5 py-1 rounded-full ${p.highlight ? "bg-indigo-600 text-white" : "bg-stone-100 text-stone-700"}`}>
                        {p.name}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Bottom CTA */}
      <section className="px-6 py-20 text-center">
        <h2 className="text-3xl font-bold text-stone-900 mb-4">Try Conduct free</h2>
        <p className="text-stone-500 mb-8 max-w-md mx-auto text-sm leading-relaxed">
          Sign in with Google, connect a GitHub repo, and install your first playbook from the Marketplace. Running in under 5 minutes.
        </p>
        <a
          href="/sign-in"
          className="inline-flex items-center gap-2 bg-stone-900 hover:bg-stone-700 text-white font-semibold px-7 py-3.5 rounded-xl text-sm transition-colors"
        >
          Get started — it&apos;s free →
        </a>
        <p className="text-xs text-stone-400 mt-4">No credit card · No setup · Sign in with Google</p>
      </section>

      <footer className="border-t border-stone-100 py-8 text-center text-xs text-stone-400 space-y-2">
        <div className="flex items-center justify-center gap-3 flex-wrap">
          <span>© {new Date().getFullYear()} Conduct</span>
          <span>·</span>
          <a href="https://github.com/sseshachala/conductai" target="_blank" rel="noopener noreferrer" className="hover:text-stone-600 transition-colors">GitHub</a>
          <span>·</span>
          <a href="https://narratr.ai/blog/conductai" target="_blank" rel="noopener noreferrer" className="hover:text-stone-600 transition-colors">Blog</a>
          <span>·</span>
          <a href="/privacy" className="hover:text-stone-600 transition-colors">Privacy</a>
          <span>·</span>
          <a href="/terms" className="hover:text-stone-600 transition-colors">Terms</a>
        </div>
        <p className="text-stone-300">Envisioned, designed and developed with 💕 from Houston</p>
      </footer>
    </div>
  )
}

// ── Feature matrix ─────────────────────────────────────────────────────────────

function FeatureMatrix() {
  const [hoveredCol, setHoveredCol] = useState<string | null>(null)
  const toolIds = TOOLS.map(t => t.id)

  return (
    <div className="overflow-x-auto rounded-2xl border border-stone-200 bg-white">
      <table className="w-full text-sm border-collapse">
        <thead>
          <tr className="border-b border-stone-200">
            <th className="text-left px-5 py-4 text-xs font-semibold text-stone-500 uppercase tracking-wider w-52 bg-stone-50">Feature</th>
            {TOOLS.map(t => (
              <th key={t.id}
                onMouseEnter={() => setHoveredCol(t.id)}
                onMouseLeave={() => setHoveredCol(null)}
                className={`px-4 py-4 text-center text-xs font-bold text-stone-900 transition-colors cursor-pointer min-w-[110px] ${t.id === "conduct" ? "bg-indigo-50" : hoveredCol === t.id ? "bg-stone-50" : ""}`}>
                <span className="block text-lg mb-1">{t.emoji}</span>
                {t.shortName}
              </th>
            ))}
          </tr>
        </thead>
        {FEATURE_GROUPS.map((group, gi) => (
          <tbody key={gi}>
            <tr className="bg-stone-50">
              <td colSpan={toolIds.length + 1} className="px-5 py-2.5 text-[10px] font-bold text-stone-400 uppercase tracking-widest">
                {group.label}
              </td>
            </tr>
            {group.features.map((feature, fi) => (
              <tr key={fi} className="border-t border-stone-100 hover:bg-stone-50 transition-colors">
                <td className="px-5 py-3.5">
                  <p className="font-medium text-stone-900 text-xs">{feature.name}</p>
                  {feature.note && <p className="text-[11px] text-stone-400 mt-0.5 leading-snug">{feature.note}</p>}
                </td>
                {toolIds.map(id => (
                  <td key={id}
                    onMouseEnter={() => setHoveredCol(id)}
                    onMouseLeave={() => setHoveredCol(null)}
                    className={`px-4 py-3.5 text-center text-base transition-colors ${id === "conduct" ? "bg-indigo-50" : hoveredCol === id ? "bg-stone-50" : ""}`}>
                    {(feature.values as Record<string, string>)[id]}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        ))}
      </table>
    </div>
  )
}

// ── Tool detail section ────────────────────────────────────────────────────────

function ToolDetail({ tool }: { tool: typeof TOOLS[number] }) {
  return (
    <div id={tool.id} className="scroll-mt-8">
      <div className="flex items-start gap-4 mb-5">
        <span className="text-4xl">{tool.emoji}</span>
        <div>
          <div className="flex items-center gap-2 flex-wrap">
            <h2 className="text-xl font-bold text-stone-900">{tool.name}</h2>
            <span className="text-xs text-stone-400">by {tool.maker}</span>
            <span className={`text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-full ${tool.categoryColor}`}>{tool.category}</span>
          </div>
          <a href={tool.url} target="_blank" rel="noopener noreferrer" className="text-xs text-stone-400 hover:text-indigo-600 transition-colors mt-0.5 block">
            {tool.url} ↗
          </a>
        </div>
      </div>

      <p className="text-stone-600 leading-relaxed mb-6">{tool.description}</p>

      <div className="grid sm:grid-cols-2 gap-4 mb-6">
        <div className="bg-emerald-50 border border-emerald-100 rounded-xl p-4">
          <p className="text-xs font-bold text-emerald-700 uppercase tracking-wider mb-2">Strengths</p>
          <ul className="space-y-1.5">
            {tool.strengths.map(s => (
              <li key={s} className="text-sm text-stone-700 flex items-start gap-2">
                <span className="text-emerald-500 mt-0.5 shrink-0">✓</span>{s}
              </li>
            ))}
          </ul>
        </div>
        <div className="bg-amber-50 border border-amber-100 rounded-xl p-4">
          <p className="text-xs font-bold text-amber-700 uppercase tracking-wider mb-2">Trade-offs</p>
          <ul className="space-y-1.5">
            {tool.tradeoffs.map(t => (
              <li key={t} className="text-sm text-stone-700 flex items-start gap-2">
                <span className="text-amber-500 mt-0.5 shrink-0">–</span>{t}
              </li>
            ))}
          </ul>
        </div>
      </div>

      <div className="bg-stone-50 rounded-xl border border-stone-200 p-4">
        <p className="text-xs font-bold text-stone-500 uppercase tracking-wider mb-1.5">Best for</p>
        <p className="text-sm text-stone-700 leading-relaxed">{tool.bestFor}</p>
      </div>
    </div>
  )
}

// ── Data ───────────────────────────────────────────────────────────────────────

const TOOLS = [
  {
    id: "conduct",
    shortName: "Conduct",
    name: "Conduct AI",
    maker: "Conduct",
    emoji: "🎯",
    category: "Orchestration",
    categoryColor: "bg-indigo-100 text-indigo-700",
    url: "https://conductai.ai",
    oneLiner: "Visual canvas for building AI agent workflows — from copilot to full autopilot — with human-in-the-loop gates and a playbook marketplace.",
    description: "Conduct is an AI agent orchestration platform built for engineering teams. You compose workflows visually on a canvas — trigger blocks, brain (LLM) blocks, tool blocks, logic branches, and approval gates — and the platform executes them. It ships with 9 pre-built playbooks: Autopilot (fix GitHub issues), PR Reviewer, Issue Triage, CI Failure Alert, Incident Responder, Dependency Updater, Release Notes, and more. The key design philosophy is the copilot↔autopilot spectrum: you choose how much automation you want, from \"suggest and wait\" to \"implement, test, and open a PR while you sleep\". Nothing merges without a human approval gate unless you explicitly remove it. Every run is fully audited. MIT licensed.",
    strengths: [
      "Visual canvas — see and edit the entire agent workflow at a glance",
      "Copilot↔autopilot spectrum — tune automation level per workflow",
      "Human-in-the-loop approval gates as first-class blocks",
      "9 pre-built playbooks installable in one click",
      "Full autonomous fix loop: PR review → issue → autopilot → new PR",
      "Per-run cost and audit trail visibility",
      "Multi-model per block — mix Claude, GPT-4, Gemini in one workflow",
      "MIT licensed, config-as-code, no vendor lock-in",
      "Works across verticals — not just SDLC",
    ],
    tradeoffs: [
      "Early-stage product — some rough edges and missing integrations",
      "Requires Modal Labs for production sandbox execution",
      "Smaller community than GitHub Copilot or Amazon Q",
      "No IDE extension — purely web canvas + CLI",
      "Self-hosted option not yet available",
    ],
    bestFor: "Engineering teams (2–15 people) using GitHub + Slack who want full control over what gets automated and how far it goes. Teams that want to see the logic, own the playbook, and add approval gates before anything ships.",
  },
  {
    id: "copilot",
    shortName: "Copilot",
    name: "GitHub Copilot",
    maker: "GitHub / Microsoft",
    emoji: "🐙",
    category: "AI Coding",
    categoryColor: "bg-stone-100 text-stone-700",
    url: "https://github.com/features/copilot",
    oneLiner: "AI pair programmer embedded in your IDE. Code completions, chat, and agentic PR creation via GitHub workflows.",
    description: "GitHub Copilot is the most widely adopted AI coding assistant, with 15M+ users. It works as an IDE extension (VS Code, JetBrains, Neovim) providing inline code completions, multi-file edits, and a chat interface. In 2024–2025 GitHub added agentic capabilities: Copilot can now be assigned GitHub issues, create branches, write code, and open PRs — all triggered from the GitHub web UI. The underlying model has expanded to include GPT-4o and Claude Sonnet. For teams already on GitHub Enterprise, it integrates natively with zero friction.",
    strengths: [
      "Best-in-class IDE integration — completions feel native",
      "15M+ users — widest community, tutorials, and enterprise adoption",
      "Native to GitHub — no new tool to onboard",
      "Workspace context — reads your whole repo for relevant suggestions",
      "Enterprise security and compliance (SOC 2, GDPR)",
      "Agentic issue → PR workflow available in GitHub UI",
    ],
    tradeoffs: [
      "Primarily a suggestion tool — the developer still drives",
      "Agentic workflows are limited and not visually configurable",
      "No approval gates or human-in-the-loop controls",
      "No audit trail for what the AI did across runs",
      "Closed source — cannot customise the review or automation logic",
      "Subscription cost adds up for large teams ($19–39/user/month)",
    ],
    bestFor: "Individual developers and teams who want the best autocomplete and code chat experience inside their IDE, with light agentic capabilities tied to GitHub issues. If the primary use case is writing code faster, Copilot is hard to beat.",
  },
  {
    id: "devin",
    shortName: "Devin",
    name: "Devin",
    maker: "Cognition AI",
    emoji: "🤖",
    category: "Autonomous Agent",
    categoryColor: "bg-purple-100 text-purple-700",
    url: "https://cognition.ai",
    oneLiner: "Fully autonomous AI software engineer. Give it a task; it plans, codes, tests, and deploys end-to-end in its own cloud sandbox.",
    description: "Devin is designed to be a fully autonomous software engineer — not a copilot. You give it a task in natural language and it independently: explores the codebase, creates a plan, writes code across multiple files, runs tests, debugs failures, and opens a pull request. It runs in its own isolated cloud environment with a browser, terminal, and editor. Devin is best described as a \"junior engineer\" you can hand full tasks to. It is the most capable fully-autonomous agent publicly available, and is priced accordingly for teams that need end-to-end task execution without hand-holding.",
    strengths: [
      "Most capable end-to-end autonomous coding agent available",
      "Full environment (browser, terminal, editor) — no constraints",
      "Long-horizon task execution — can work through complex, multi-step problems",
      "Handles real repos, not just toy examples",
      "Communicates progress and asks clarifying questions",
    ],
    tradeoffs: [
      "Expensive — priced for enterprise and power users",
      "Black box — limited visibility into what the agent is doing step-by-step",
      "No visual workflow editor — you describe tasks in natural language only",
      "No playbook marketplace or pre-built agent library",
      "Autonomy without guardrails can be risky on production repos",
      "No multi-agent orchestration or approval gate primitives",
    ],
    bestFor: "Teams with complex, long-horizon engineering tasks where they want to hand off an entire problem and let the agent run. Best suited for greenfield work, prototyping, or well-scoped tickets where full autonomy is safe.",
  },
  {
    id: "linearb",
    shortName: "LinearB",
    name: "LinearB",
    maker: "LinearB",
    emoji: "📊",
    category: "Eng Metrics + AI",
    categoryColor: "bg-blue-100 text-blue-700",
    url: "https://linearb.io",
    oneLiner: "Engineering metrics platform with AI-powered PR automation (gitStream) and DORA/SPACE dashboards for engineering leaders.",
    description: "LinearB combines engineering intelligence (cycle time, deployment frequency, DORA metrics) with PR automation via its gitStream product. gitStream is a YAML-based automation engine that routes PRs, enforces review policies, assigns reviewers, and auto-merges safe changes. LinearB's AI layer adds code review suggestions and automated checks. It is primarily a tool for engineering managers who want visibility into team performance alongside automated PR governance. The metrics dashboards are among the best in the market for understanding eng team health.",
    strengths: [
      "Best-in-class engineering metrics — DORA, SPACE, cycle time, review time",
      "gitStream is a powerful, mature PR automation engine",
      "Executive-friendly dashboards and reporting",
      "Strong workflow automation for review routing and policy enforcement",
      "Integrates with Jira, Linear, GitHub, GitLab, Bitbucket",
    ],
    tradeoffs: [
      "Metrics-first product — AI automation is secondary to analytics",
      "No visual canvas or workflow builder",
      "Limited agentic capabilities — PR automation, not full task execution",
      "No issue-to-PR autopilot loop",
      "Pricing scales with team size and can be expensive at scale",
    ],
    bestFor: "Engineering leaders and managers who need visibility into team performance and want policy-based PR automation. Teams that already care about DORA metrics and want automation to enforce their review process.",
  },
  {
    id: "bito",
    shortName: "Bito AI",
    name: "Bito AI",
    maker: "Bito",
    emoji: "🧩",
    category: "AI Code Review",
    categoryColor: "bg-teal-100 text-teal-700",
    url: "https://bito.ai",
    oneLiner: "AI code review bot with deep codebase awareness, Jira integration, and implementation planning — focused on architectural context.",
    description: "Bito specialises in AI-powered code review with a strong emphasis on codebase context. Unlike tools that look at just the diff, Bito indexes your entire codebase and uses that context when reviewing PRs — catching issues that require understanding of how the changed code interacts with the broader system. It also integrates with Jira to read linked tickets and provide more relevant review comments. Bito offers an IDE plugin for real-time feedback and a CLI for CI integration.",
    strengths: [
      "Deep codebase awareness — reads your full repo, not just the diff",
      "Jira integration — uses linked tickets for review context",
      "IDE plugin for real-time feedback during development",
      "Strong at architectural and cross-file impact analysis",
      "CLI for easy CI/CD integration",
    ],
    tradeoffs: [
      "Review only — no autonomous task execution or autopilot mode",
      "No visual workflow builder or playbook system",
      "No human-in-the-loop approval gates",
      "Smaller community and ecosystem than GitHub Copilot",
      "No Slack-native output or incident response features",
    ],
    bestFor: "Teams that want the most context-aware AI code reviews and are willing to trade breadth of automation for depth of review quality. Particularly strong for larger codebases where cross-file impact matters.",
  },
  {
    id: "amazonq",
    shortName: "Amazon Q",
    name: "Amazon Q Developer",
    maker: "AWS",
    emoji: "☁️",
    category: "AI Coding + Cloud",
    categoryColor: "bg-orange-100 text-orange-700",
    url: "https://aws.amazon.com/q/developer",
    oneLiner: "AWS's AI developer tool — code generation, security scanning, Java upgrades, and CI/CD automation within the AWS ecosystem.",
    description: "Amazon Q Developer is AWS's answer to GitHub Copilot, with a stronger focus on AWS infrastructure and cloud-native development. Beyond code completions, it offers unique features: automated Java version upgrades, security vulnerability scanning, and agentic software development tasks. It integrates deeply with AWS services (CodeCatalyst, CodePipeline, CloudWatch) and is the strongest choice for teams heavily invested in the AWS ecosystem. It is available free on a basic tier and included in AWS Builder ID.",
    strengths: [
      "Deep AWS integration — understands CloudFormation, CDK, Lambda natively",
      "Automated language upgrades (Java 8→17, etc.) — a unique capability",
      "Security scanning built-in — OWASP, CVE detection",
      "Free tier available — accessible to individual developers",
      "Strong CI/CD automation within AWS CodePipeline",
    ],
    tradeoffs: [
      "Best value when deep in AWS — limited value for non-AWS stacks",
      "Primarily a coding assistant — limited orchestration/autopilot",
      "No visual workflow canvas or playbook system",
      "Community and third-party integrations smaller than GitHub Copilot",
      "Less capable outside AWS contexts",
    ],
    bestFor: "Teams running on AWS infrastructure who want AI assistance that understands their cloud stack natively — especially for security, compliance, and infrastructure-as-code work.",
  },
  {
    id: "coderabbit",
    shortName: "CodeRabbit",
    name: "CodeRabbit AI",
    maker: "CodeRabbit",
    emoji: "🐰",
    category: "AI Code Review",
    categoryColor: "bg-pink-100 text-pink-700",
    url: "https://coderabbit.ai",
    oneLiner: "Automated AI PR reviewer that installs as a GitHub/GitLab app and posts detailed, contextual line-by-line review comments.",
    description: "CodeRabbit is a focused, well-executed AI code review product. Install it as a GitHub or GitLab app, and it automatically reviews every PR — posting line-by-line comments, a summary, and a walkthrough of the changes. It supports custom review instructions, learning from dismissals, and integrates with Linear and Jira to read ticket context. The product is beloved for how little setup it requires — install in 60 seconds and it starts reviewing immediately. It has a generous free tier for open source projects.",
    strengths: [
      "Zero-setup — installs as a GitHub app, reviews immediately",
      "Excellent line-by-line review comments with context",
      "Learns from feedback — improves over time per repo",
      "Generous free tier for open source",
      "Supports GitHub, GitLab, Azure DevOps, Bitbucket",
      "Custom review instructions via `.coderabbit.yaml`",
    ],
    tradeoffs: [
      "Review only — no autonomous fix capability or autopilot loop",
      "No human-in-the-loop gates or approval workflows",
      "No visual canvas or workflow customisation beyond config YAML",
      "Does not create fix issues or trigger downstream automation",
      "No incident response, issue triage, or CI failure features",
    ],
    bestFor: "Teams that want instant, zero-config AI code review on every PR without building any automation. Best as a safety net alongside a human review process — not as a replacement for a full automation pipeline.",
  },
  {
    id: "xhawk",
    shortName: "xHawk",
    name: "xHawk AI",
    maker: "xHawk",
    emoji: "🦅",
    category: "Autonomous SDLC",
    categoryColor: "bg-red-100 text-red-700",
    url: "https://xhawk.ai",
    oneLiner: "Autonomous AI agents for the full software development lifecycle — issue to deployment — targeted at enterprise SDLC automation.",
    description: "xHawk focuses on end-to-end SDLC automation: from issue creation through code generation, testing, code review, and deployment. It targets enterprise teams that want to automate the full software delivery pipeline with AI. xHawk is more opinionated about the SDLC process and less flexible for general-purpose agent workflows. Based on public information, it is primarily configured via code/API rather than a visual interface, and is positioned at larger engineering organisations.",
    strengths: [
      "End-to-end SDLC coverage — issue through deploy in one platform",
      "Enterprise-grade — built for larger teams and compliance requirements",
      "Strong focus on software delivery metrics and pipeline automation",
      "Deep integration with enterprise toolchains (Jira, Confluence, etc.)",
    ],
    tradeoffs: [
      "SDLC-only scope — not designed for general-purpose agent workflows",
      "Code-driven configuration — no visual workflow canvas",
      "Less flexible for teams outside the standard enterprise SDLC pattern",
      "Smaller public community and fewer public resources",
      "Pricing and availability less transparent than open-source alternatives",
    ],
    bestFor: "Larger enterprise engineering organisations that want automated end-to-end SDLC pipelines with enterprise toolchain integrations and are comfortable with code-driven configuration over a visual interface.",
  },
]

const FEATURE_GROUPS = [
  {
    label: "Workflow & Automation",
    features: [
      {
        name: "Visual workflow canvas",
        note: "Build and edit agent logic visually",
        values: { conduct: "✅", copilot: "❌", devin: "❌", linearb: "❌", bito: "❌", amazonq: "❌", coderabbit: "❌", xhawk: "❌" },
      },
      {
        name: "Pre-built playbooks / agents",
        note: "Install and run without building from scratch",
        values: { conduct: "✅ 11", copilot: "🟡", devin: "❌", linearb: "🟡", bito: "❌", amazonq: "🟡", coderabbit: "❌", xhawk: "🟡" },
      },
      {
        name: "Custom workflow builder",
        note: "Define your own agent logic",
        values: { conduct: "✅", copilot: "🟡", devin: "❌", linearb: "🟡", bito: "❌", amazonq: "❌", coderabbit: "🟡 YAML", xhawk: "✅" },
      },
      {
        name: "Human-in-the-loop approval gates",
        note: "Pause for human review before proceeding",
        values: { conduct: "✅", copilot: "❌", devin: "❌", linearb: "🟡", bito: "❌", amazonq: "❌", coderabbit: "❌", xhawk: "🟡" },
      },
      {
        name: "Copilot mode (suggestions)",
        note: "AI suggests, human decides",
        values: { conduct: "✅", copilot: "✅", devin: "🟡", linearb: "✅", bito: "✅", amazonq: "✅", coderabbit: "✅", xhawk: "🟡" },
      },
      {
        name: "Autopilot mode (autonomous execution)",
        note: "AI acts end-to-end without prompting",
        values: { conduct: "✅", copilot: "🟡", devin: "✅", linearb: "🟡", bito: "❌", amazonq: "🟡", coderabbit: "❌", xhawk: "✅" },
      },
    ],
  },
  {
    label: "Code Review",
    features: [
      {
        name: "Automated PR review",
        note: "Reviews pull requests and posts comments",
        values: { conduct: "✅", copilot: "🟡", devin: "🟡", linearb: "✅", bito: "✅", amazonq: "🟡", coderabbit: "✅", xhawk: "✅" },
      },
      {
        name: "Line-by-line inline comments",
        values: { conduct: "✅", copilot: "✅", devin: "❌", linearb: "✅", bito: "✅", amazonq: "🟡", coderabbit: "✅", xhawk: "🟡" },
      },
      {
        name: "Deep codebase context (full repo awareness)",
        values: { conduct: "🟡", copilot: "✅", devin: "✅", linearb: "🟡", bito: "✅", amazonq: "✅", coderabbit: "🟡", xhawk: "🟡" },
      },
      {
        name: "Security / vulnerability scanning",
        note: "OWASP Top 10, secret detection, insecure deps",
        values: { conduct: "✅", copilot: "🟡", devin: "🟡", linearb: "❌", bito: "✅", amazonq: "✅", coderabbit: "✅", xhawk: "🟡" },
      },
    ],
  },
  {
    label: "Autonomous Task Execution",
    features: [
      {
        name: "Issue → PR autopilot",
        note: "Label a GitHub issue, get a PR",
        values: { conduct: "✅", copilot: "🟡", devin: "✅", linearb: "❌", bito: "❌", amazonq: "🟡", coderabbit: "❌", xhawk: "✅" },
      },
      {
        name: "Autonomous fix loop",
        note: "Review finds issues → creates fix issue → autopilot re-picks up → new PR → re-review",
        values: { conduct: "✅", copilot: "❌", devin: "❌", linearb: "❌", bito: "❌", amazonq: "❌", coderabbit: "❌", xhawk: "🟡" },
      },
      {
        name: "CI failure diagnosis",
        values: { conduct: "✅", copilot: "🟡", devin: "🟡", linearb: "🟡", bito: "❌", amazonq: "🟡", coderabbit: "❌", xhawk: "✅" },
      },
      {
        name: "Incident response automation",
        values: { conduct: "✅", copilot: "❌", devin: "❌", linearb: "❌", bito: "❌", amazonq: "🟡", coderabbit: "❌", xhawk: "🟡" },
      },
      {
        name: "Automated dependency updates",
        values: { conduct: "✅", copilot: "❌", devin: "🟡", linearb: "❌", bito: "❌", amazonq: "❌", coderabbit: "❌", xhawk: "🟡" },
      },
      {
        name: "Release notes generation",
        values: { conduct: "✅", copilot: "❌", devin: "❌", linearb: "🟡", bito: "❌", amazonq: "❌", coderabbit: "❌", xhawk: "❌" },
      },
      {
        name: "Issue triage & labeling",
        values: { conduct: "✅", copilot: "🟡", devin: "🟡", linearb: "🟡", bito: "❌", amazonq: "❌", coderabbit: "❌", xhawk: "✅" },
      },
    ],
  },
  {
    label: "Observability & Trust",
    features: [
      {
        name: "Full run audit trail",
        note: "Every action logged and replayable",
        values: { conduct: "✅", copilot: "❌", devin: "🟡", linearb: "✅", bito: "❌", amazonq: "🟡", coderabbit: "❌", xhawk: "🟡" },
      },
      {
        name: "Per-run cost transparency",
        values: { conduct: "✅", copilot: "❌", devin: "❌", linearb: "❌", bito: "❌", amazonq: "❌", coderabbit: "❌", xhawk: "❌" },
      },
      {
        name: "Multi-model per block",
        note: "Use different LLMs for different steps",
        values: { conduct: "✅", copilot: "🟡", devin: "❌", linearb: "❌", bito: "❌", amazonq: "❌", coderabbit: "❌", xhawk: "❌" },
      },
      {
        name: "Engineering metrics dashboard",
        note: "DORA, cycle time, deployment freq",
        values: { conduct: "❌", copilot: "❌", devin: "❌", linearb: "✅", bito: "❌", amazonq: "🟡", coderabbit: "❌", xhawk: "🟡" },
      },
    ],
  },
  {
    label: "Integration & Access",
    features: [
      {
        name: "GitHub integration",
        values: { conduct: "✅", copilot: "✅", devin: "✅", linearb: "✅", bito: "✅", amazonq: "✅", coderabbit: "✅", xhawk: "✅" },
      },
      {
        name: "Slack-native output",
        values: { conduct: "✅", copilot: "❌", devin: "❌", linearb: "✅", bito: "❌", amazonq: "❌", coderabbit: "❌", xhawk: "🟡" },
      },
      {
        name: "IDE extension",
        values: { conduct: "❌", copilot: "✅", devin: "✅", linearb: "❌", bito: "✅", amazonq: "✅", coderabbit: "❌", xhawk: "❌" },
      },
      {
        name: "CLI / API",
        values: { conduct: "✅", copilot: "🟡", devin: "✅", linearb: "✅", bito: "✅", amazonq: "✅", coderabbit: "✅", xhawk: "✅" },
      },
      {
        name: "Open source",
        values: { conduct: "✅ MIT", copilot: "❌", devin: "❌", linearb: "❌", bito: "❌", amazonq: "❌", coderabbit: "❌", xhawk: "❌" },
      },
      {
        name: "Free tier",
        values: { conduct: "✅", copilot: "✅", devin: "❌", linearb: "🟡", bito: "✅", amazonq: "✅", coderabbit: "✅", xhawk: "❌" },
      },
      {
        name: "No custom infrastructure required",
        values: { conduct: "✅", copilot: "✅", devin: "✅", linearb: "✅", bito: "✅", amazonq: "✅", coderabbit: "✅", xhawk: "🟡" },
      },
    ],
  },
]

const DECISION_GUIDE = [
  {
    icon: "✍️",
    situation: "I want the best AI autocomplete and code chat in my IDE",
    detail: "This is about productivity while writing code. You want fast, accurate suggestions, multi-file edits, and a chat interface that understands your codebase.",
    picks: [
      { name: "GitHub Copilot", highlight: true },
      { name: "Amazon Q Developer", highlight: false },
      { name: "Bito AI", highlight: false },
    ],
  },
  {
    icon: "🔍",
    situation: "I want automated PR review on every pull request with zero setup",
    detail: "You want an AI reviewer watching every PR. Install it and forget it — no workflow to configure, no canvas to build.",
    picks: [
      { name: "CodeRabbit AI", highlight: true },
      { name: "Bito AI", highlight: false },
      { name: "Conduct AI", highlight: false },
    ],
  },
  {
    icon: "🤖",
    situation: "I want to hand off a complex task and let AI do it fully autonomously",
    detail: "You have a well-scoped ticket and want an AI to handle the entire implementation end-to-end — planning, coding, debugging, and opening a PR.",
    picks: [
      { name: "Devin", highlight: true },
      { name: "Conduct AI (Autopilot)", highlight: false },
      { name: "GitHub Copilot (agentic)", highlight: false },
    ],
  },
  {
    icon: "👁️",
    situation: "I want automation but with human control over what ships",
    detail: "Full autonomy makes you nervous. You want agents doing the work, but a human checkpoint before anything lands in main.",
    picks: [
      { name: "Conduct AI", highlight: true },
      { name: "LinearB (gitStream)", highlight: false },
    ],
  },
  {
    icon: "🔄",
    situation: "I want PR review → auto-fix → re-review to run without me touching it",
    detail: "The full autonomous loop: PR opened, reviewed, critical issues create a fix issue, Autopilot fixes it, new PR opened, reviewed again — hands-free.",
    picks: [
      { name: "Conduct AI", highlight: true },
    ],
  },
  {
    icon: "📊",
    situation: "I'm an engineering manager who wants team performance metrics + PR automation",
    detail: "DORA metrics, cycle time, deployment frequency, and policy-based PR routing all in one place.",
    picks: [
      { name: "LinearB", highlight: true },
      { name: "Conduct AI", highlight: false },
    ],
  },
  {
    icon: "☁️",
    situation: "My stack is heavily AWS and I want AI that understands my infrastructure",
    detail: "CloudFormation, CDK, Lambda, CodePipeline — you need an AI that speaks AWS natively and can handle security scanning and language upgrades.",
    picks: [
      { name: "Amazon Q Developer", highlight: true },
      { name: "GitHub Copilot", highlight: false },
    ],
  },
  {
    icon: "🏢",
    situation: "I'm at a large enterprise and need end-to-end SDLC automation",
    detail: "Enterprise toolchains (Jira, Confluence, ServiceNow), compliance requirements, and a full pipeline from issue creation through deployment.",
    picks: [
      { name: "xHawk AI", highlight: true },
      { name: "Conduct AI", highlight: false },
      { name: "LinearB", highlight: false },
    ],
  },
  {
    icon: "🔓",
    situation: "I want open-source, no vendor lock-in, config-as-code",
    detail: "Workflows as YAML in your repo, MIT licensed, self-hostable direction, and the ability to audit or modify the logic.",
    picks: [
      { name: "Conduct AI", highlight: true },
    ],
  },
]
