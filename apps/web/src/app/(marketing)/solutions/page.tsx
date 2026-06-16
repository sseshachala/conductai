"use client"

export default function SolutionsPage() {
  return (
    <div className="min-h-screen bg-white flex flex-col">
      <Nav />
      <main className="flex-1">
        <HeroSection />
        <GuardSection />
        <SecureSection />
        <WorkflowsSection />
        <SDDSection />
        <FinalCTASection />
      </main>
      <PageFooter />
    </div>
  )
}

/* ─── Nav ──────────────────────────────────────────────────────────────── */

function Nav() {
  return (
    <header className="px-6 py-4 flex items-center justify-between max-w-6xl mx-auto w-full sticky top-0 bg-white/95 backdrop-blur-sm z-50 border-b border-stone-100">
      <a href="/"><img src="/logo.png" alt="Conduct AI" className="h-10 w-auto" /></a>
      <nav className="hidden md:flex items-center gap-6">
        <SolutionsDropdown />
        <ToolsDropdown />
        <a href="/partners" className="text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">Partners</a>
        <a href="/docs" className="text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">Docs</a>
        <a href="/blog" className="text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">Blog</a>
      </nav>
      <div className="flex items-center gap-3">
        <a href="mailto:hello@conductai.ai" className="text-sm font-medium text-stone-600 hover:text-stone-900 transition-colors hidden sm:block">Talk to Us</a>
        <a href="/sign-up" className="rounded-lg bg-stone-900 text-white px-4 py-2 text-sm font-semibold hover:bg-stone-700 transition-colors">Start Free</a>
      </div>
    </header>
  )
}

function SolutionsDropdown() {
  return (
    <div className="relative group">
      <a href="/solutions" className="flex items-center gap-1 text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">
        Solutions
        <svg width="12" height="12" viewBox="0 0 12 12" fill="currentColor" className="opacity-40 mt-0.5"><path d="M2 4l4 4 4-4"/></svg>
      </a>
      <div className="absolute left-0 top-full pt-2 hidden group-hover:block z-50 min-w-[220px]">
        <div className="bg-white border border-stone-200 rounded-xl shadow-lg py-2">
          <a href="/solutions#guard" className="flex items-center gap-3 px-4 py-2.5 text-sm text-stone-700 hover:bg-stone-50 transition-colors">
            <span>🛡️</span><div><p className="font-semibold">Conduct Guard</p><p className="text-xs text-stone-400">AI session governance</p></div>
          </a>
          <a href="/solutions#secure" className="flex items-center gap-3 px-4 py-2.5 text-sm text-stone-700 hover:bg-stone-50 transition-colors">
            <span>🔒</span><div><p className="font-semibold">Secure</p><p className="text-xs text-stone-400">Automated security enforcement</p></div>
          </a>
          <a href="/solutions#workflows" className="flex items-center gap-3 px-4 py-2.5 text-sm text-stone-700 hover:bg-stone-50 transition-colors">
            <span>⚡</span><div><p className="font-semibold">Agentic Workflows</p><p className="text-xs text-stone-400">Governed AI automations</p></div>
          </a>
          <a href="/solutions#sdd" className="flex items-center gap-3 px-4 py-2.5 text-sm text-stone-700 hover:bg-stone-50 transition-colors">
            <span>📐</span><div><p className="font-semibold">Spec-Driven Dev</p><p className="text-xs text-stone-400">Intent-first AI coding</p></div>
          </a>
          <div className="border-t border-stone-100 mt-1 pt-1">
            <a href="/solutions" className="flex items-center gap-2 px-4 py-2 text-xs font-semibold text-indigo-600 hover:text-indigo-800 transition-colors">View all solutions →</a>
          </div>
        </div>
      </div>
    </div>
  )
}

function ToolsDropdown() {
  return (
    <div className="relative group">
      <a href="/tools" className="flex items-center gap-1 text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">
        Tools
        <svg width="12" height="12" viewBox="0 0 12 12" fill="currentColor" className="opacity-40 mt-0.5"><path d="M2 4l4 4 4-4"/></svg>
      </a>
      <div className="absolute left-0 top-full pt-2 hidden group-hover:block z-50 min-w-[200px]">
        <div className="bg-white border border-stone-200 rounded-xl shadow-lg py-2">
          <a href="/tools/agent-booster" className="flex items-center gap-3 px-4 py-2.5 text-sm text-stone-700 hover:bg-stone-50 transition-colors">
            <span className="text-indigo-600 font-bold text-base">◈</span><div><p className="font-semibold">Agent Booster</p><p className="text-xs text-stone-400">Cut AI costs 3–15×</p></div>
          </a>
          <a href="/tools/conduct-cli" className="flex items-center gap-3 px-4 py-2.5 text-sm text-stone-700 hover:bg-stone-50 transition-colors">
            <span className="text-violet-600 font-bold text-base">⬡</span><div><p className="font-semibold">Conduct CLI</p><p className="text-xs text-stone-400">Govern from the terminal</p></div>
          </a>
          <a href="/tools/security-loop" className="flex items-center gap-3 px-4 py-2.5 text-sm text-stone-700 hover:bg-stone-50 transition-colors">
            <span className="text-rose-600 font-bold text-base">🔐</span><div><p className="font-semibold">Security Loop</p><p className="text-xs text-stone-400">Automated PR scanning</p></div>
          </a>
        </div>
      </div>
    </div>
  )
}


function HeroSection() {
  return (
    <section className="max-w-5xl mx-auto px-6 pt-20 pb-16 text-center">
      <p className="text-xs font-semibold uppercase tracking-widest text-stone-400 mb-4">Solutions</p>
      <h1 className="text-4xl sm:text-5xl font-black tracking-tight text-stone-900 leading-tight mb-6">
        Not features.<br />
        <span className="bg-gradient-to-r from-indigo-600 to-violet-600 bg-clip-text text-transparent">Outcomes you can point to.</span>
      </h1>
      <p className="text-lg text-stone-500 max-w-2xl mx-auto leading-relaxed mb-8">
        Three solutions built around the problems engineering teams actually face when AI enters the workflow.
        Each one maps to a real pain point, a real outcome, and a real person on your team who feels it.
      </p>
      <div className="flex flex-wrap items-center justify-center gap-4">
        <a href="#guard" className="rounded-lg border border-stone-200 bg-white px-5 py-2.5 text-sm font-semibold text-stone-700 hover:border-indigo-300 hover:text-indigo-600 transition-all">
          🛡️ Conduct Guard
        </a>
        <a href="#secure" className="rounded-lg border border-stone-200 bg-white px-5 py-2.5 text-sm font-semibold text-stone-700 hover:border-emerald-300 hover:text-emerald-700 transition-all">
          🔒 Secure
        </a>
        <a href="#workflows" className="rounded-lg border border-stone-200 bg-white px-5 py-2.5 text-sm font-semibold text-stone-700 hover:border-amber-300 hover:text-amber-700 transition-all">
          ⚡ Agentic Workflows
        </a>
        <a href="#sdd" className="rounded-lg border border-stone-200 bg-white px-5 py-2.5 text-sm font-semibold text-stone-700 hover:border-violet-300 hover:text-violet-700 transition-all">
          📐 Spec-Driven Development
        </a>
      </div>
    </section>
  )
}

/* ─── Guard ────────────────────────────────────────────────────────────── */

const guardUseCases = [
  {
    pain: "A developer pasted a production API key into Claude. It reached the model, the log, and the audit trail.",
    what: "Guard's secret-redact policy scans every tool input before it reaches the model. GitHub tokens, AWS keys, Slack tokens, Stripe keys — all detected and blocked. The audit log stores [REDACTED:secret_key], never the raw value.",
    outcome: "The key never reached the model. Redacted from the audit log. Developer received a clear message to use the credential vault instead.",
  },
  {
    pain: "Someone tried to force-push to main at 11pm. The team found out Monday morning — after it had already caused a conflict.",
    what: "Guard's no-force-push policy intercepts the tool call before it executes. The action is blocked. The event is logged with developer identity, timestamp, and the exact command attempted.",
    outcome: "Push never happened. Manager reviewed the blocked event in the audit log Monday morning instead of a production incident.",
  },
  {
    pain: "Finance asked what AI is costing the team this quarter. Engineering leadership had no answer.",
    what: "Guard tracks every AI session across Claude Code, Cursor, Copilot, Claude.ai, and custom MCP surfaces. Spend is aggregated by user, by tool, by project. Per-user budget caps fire a warning before breach.",
    outcome: "Team went from $800/month in untracked AI spend to $310/month with full visibility into who was using what and why.",
  },
  {
    pain: "A new developer joined. Three weeks later, we found out they had no team policies active on their AI tools.",
    what: "conduct guard sync generates a pre-configured hook from your team's live policy set and deploys it to the developer's machine. From their first session, Guard is active — no manual setup, no onboarding step missed.",
    outcome: "New developer had full policy coverage from day one. Confirmed via tool coverage dashboard.",
  },
  {
    pain: "Our compliance audit required logs of all AI tool usage. We had nothing to show.",
    what: "Every tool call is logged with developer identity, AI surface, timestamp, decision (allowed/blocked/warned), and which policy fired. Logs are retained, searchable, and exportable.",
    outcome: "Compliance team received a complete audit trail covering 6 months of AI tool usage across 12 developers. Audit passed.",
  },
  {
    pain: "Developers were including customer data in AI prompts without realizing it — emails, phone numbers, records.",
    what: "Guard's pii-redact policy scans context before it reaches the LLM. Emails, phone numbers, SSNs, credit card numbers, and IPs are replaced with [EMAIL], [PHONE], [CARD] — never sent to the model.",
    outcome: "Customer data stopped reaching the LLM. Zero PII in session logs after policy activation.",
  },
]

function GuardSection() {
  return (
    <section id="guard" className="py-24 px-6 bg-stone-50">
      <div className="max-w-5xl mx-auto">
        <div className="flex items-center gap-3 mb-3">
          <div className="w-10 h-10 rounded-xl bg-indigo-50 flex items-center justify-center text-xl">🛡️</div>
          <p className="text-xs font-bold uppercase tracking-widest text-indigo-600">Conduct Guard</p>
        </div>
        <h2 className="text-3xl sm:text-4xl font-bold text-stone-900 tracking-tight mb-4">
          Every AI session your team runs.<br />Under your policies. Automatically.
        </h2>
        <p className="text-stone-500 leading-relaxed max-w-2xl mb-12">
          ConductGuard is real-time policy enforcement for developer AI sessions — Claude Code, Cursor, Copilot,
          and every MCP-connected surface. Not documentation. Not a review process.
          Enforcement that runs at the same layer as the tools.
        </p>

        <div className="grid md:grid-cols-2 gap-5 mb-12">
          {guardUseCases.map((u, i) => (
            <UseCaseCard key={i} {...u} accentColor="indigo" />
          ))}
        </div>

        <PolicyTable />

        <DualCTA
          platformText="Deploy in 5 minutes. Policies live on every developer's AI session immediately. Free tier covers up to 5 developers."
          solutionsText="We audit your current AI tool usage, design your policy framework, and implement it across your team."
        />
      </div>
    </section>
  )
}

function PolicyTable() {
  const policies = [
    ["no-rm-rf", "Recursive deletes", "Block"],
    ["no-force-push", "Force pushes to any branch", "Block"],
    ["no-drop-table", "DROP TABLE in any tool", "Block"],
    ["secret-redact", "API keys, tokens, passwords", "Block + redact from log"],
    ["pii-redact", "Email, phone, SSN, card, IP", "Redact before LLM"],
    ["sql-injection", "String-formatted SQL queries", "Warn"],
    ["cmd-injection", "Unsafe shell execution patterns", "Warn"],
    ["weak-hash-md5", "MD5 for security-sensitive use", "Warn"],
    ["warn-large-context", ">50K token single calls", "Warn"],
  ]
  return (
    <div className="mb-10">
      <p className="text-sm font-bold text-stone-700 mb-4">Built-in policy library — ready to enable on day one:</p>
      <div className="rounded-xl border border-stone-200 overflow-hidden bg-white">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-stone-100 bg-stone-50">
              <th className="px-4 py-3 text-left text-xs font-bold text-stone-400 uppercase tracking-wider">Policy</th>
              <th className="px-4 py-3 text-left text-xs font-bold text-stone-400 uppercase tracking-wider">What it catches</th>
              <th className="px-4 py-3 text-left text-xs font-bold text-stone-400 uppercase tracking-wider">Action</th>
            </tr>
          </thead>
          <tbody>
            {policies.map(([rule, desc, action], i) => (
              <tr key={rule} className={i < policies.length - 1 ? "border-b border-stone-50" : ""}>
                <td className="px-4 py-3 font-mono text-xs text-stone-600">{rule}</td>
                <td className="px-4 py-3 text-stone-500">{desc}</td>
                <td className="px-4 py-3">
                  <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-semibold ${
                    action.startsWith("Block") ? "bg-red-50 text-red-600" :
                    action.startsWith("Warn") ? "bg-amber-50 text-amber-700" :
                    "bg-stone-100 text-stone-600"
                  }`}>{action}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-stone-400 mt-2">+ Custom policies: any tool, any regex pattern, any action.</p>
    </div>
  )
}

/* ─── Secure ───────────────────────────────────────────────────────────── */

const secureUseCases = [
  {
    pain: "PR opened Friday. Security reviewer won't look at it until Monday. High-severity vulnerability sat open all weekend.",
    what: "Security scanning runs automatically on every PR trigger. BugHunter analyzes the diff, fetches the relevant files, and surfaces findings — file, line, severity, remediation — before any human reviewer opens the tab.",
    outcome: "Critical vulnerability caught 45 minutes after PR opened. Reviewer found a fix suggestion waiting, not a problem to diagnose.",
  },
  {
    pain: "A hardcoded password sat in the codebase for 14 months. Nobody caught it across three security reviews.",
    what: "Security policies run on every scan — not just new code. Hardcoded credentials, weak hashing, unsafe eval patterns, SQL injection risks — all flagged with location and context. Findings appear in /secure/activity with severity and line number.",
    outcome: "14-month-old credential found in first scan. Rotated within the hour. Added to Guard's block list going forward.",
  },
  {
    pain: "A dependency update PR came in. Nobody checked whether the new version had known CVEs.",
    what: "Security scanning runs on dependency changes. Known CVEs in updated packages are flagged at PR time — before merge, before deploy, before the vulnerability is live in production.",
    outcome: "CVE in updated package caught at PR review. Dependency pinned to safe version. Never reached staging.",
  },
  {
    pain: "Our security review process was a bottleneck. Developers started splitting PRs into small pieces to avoid triggering it.",
    what: "Security enforcement runs automatically on every PR — no human in the loop for common vulnerability classes. Human review focuses on findings Conduct surfaces, not on scanning. The bottleneck disappears.",
    outcome: "Security review time dropped from 2-day average to same-day. Developers stopped splitting PRs. Coverage went up, not down.",
  },
]

function SecureSection() {
  return (
    <section id="secure" className="py-24 px-6 bg-white">
      <div className="max-w-5xl mx-auto">
        <div className="flex items-center gap-3 mb-3">
          <div className="w-10 h-10 rounded-xl bg-emerald-50 flex items-center justify-center text-xl">🔒</div>
          <p className="text-xs font-bold uppercase tracking-widest text-emerald-600">Secure</p>
        </div>
        <h2 className="text-3xl sm:text-4xl font-bold text-stone-900 tracking-tight mb-4">
          Security policies that enforce themselves.<br />On every PR. On every commit. Automatically.
        </h2>
        <p className="text-stone-500 leading-relaxed max-w-2xl mb-12">
          Conduct runs security scanning as a continuous governance layer — not a gate your team works around,
          but a policy that runs inside your workflow, catching vulnerabilities before they reach production.
        </p>

        <div className="grid md:grid-cols-2 gap-5 mb-10">
          {secureUseCases.map((u, i) => (
            <UseCaseCard key={i} {...u} accentColor="emerald" />
          ))}
        </div>

        <DualCTA
          platformText="Connect your repo. Enable security policies. Scanning runs on every PR automatically. Free tier covers one repo."
          solutionsText="We assess your codebase, define your security policy library, and configure continuous enforcement across your repositories."
        />
      </div>
    </section>
  )
}

/* ─── Workflows ────────────────────────────────────────────────────────── */

const workflowUseCases = [
  {
    pain: "A GitHub issue was filed at 2am. The fix needed to ship before the US market opened. Nobody was on call.",
    what: "The autopilot-fix workflow triggers on issue label. It fetches the issue, searches the codebase, plans the fix, writes the patch, runs lint, pushes a branch, and opens a PR — all under Guard policy enforcement. No human in the loop.",
    outcome: "PR open by 9am. Engineer woke up to a fix waiting for review, not a problem to solve.",
  },
  {
    pain: "The team spent 3 hours a week triaging and labeling GitHub issues. Important issues got delayed. Easy ones got missed.",
    what: "The issue-triage workflow triggers on every new issue. A Brain block reads the title, body, and recent context, classifies the issue, applies the right labels, and posts a structured comment. Edge cases get flagged for human review.",
    outcome: "Zero manual triage hours. Edge case rate under 8%. Team routes issues faster than before with less attention on each one.",
  },
  {
    pain: "On-call engineers had no context when an alert fired. Context gathering took 20 minutes before they could start fixing.",
    what: "The incident-responder workflow triggers on alert. It fetches recent deployments, correlates error logs, identifies the affected service, pulls the relevant runbook section, and posts a structured summary to Slack — before the engineer finishes reading the alert.",
    outcome: "Engineer had full incident context in Slack before opening a terminal. Mean time to resolution dropped 40%.",
  },
  {
    pain: "Every new repo needs the same setup — branch protection, CI config, README, security scanning. Someone always misses a step.",
    what: "The repo-bootstrap workflow triggers on repository creation. Within minutes: branch protection configured, CI workflow committed, README scaffolded, Guard policies synced, security scanning enabled, first issue filed with the team's standard checklist.",
    outcome: "Every repo starts identical. No checklist. No missed step. No one has to remember.",
  },
]

function WorkflowsSection() {
  return (
    <section id="workflows" className="py-24 px-6 bg-stone-50">
      <div className="max-w-5xl mx-auto">
        <div className="flex items-center gap-3 mb-3">
          <div className="w-10 h-10 rounded-xl bg-amber-50 flex items-center justify-center text-xl">⚡</div>
          <p className="text-xs font-bold uppercase tracking-widest text-amber-700">Agentic Workflows</p>
        </div>
        <h2 className="text-3xl sm:text-4xl font-bold text-stone-900 tracking-tight mb-4">
          The engineering work your team does manually every week.<br />Now it runs itself.
        </h2>
        <p className="text-stone-500 leading-relaxed max-w-2xl mb-12">
          Conduct Workflows are AI agents built as YAML playbooks — triggered by the events that matter,
          governed by your Guard and security policies, and fully auditable from first block to last.
        </p>

        <div className="grid md:grid-cols-2 gap-5 mb-10">
          {workflowUseCases.map((u, i) => (
            <UseCaseCard key={i} {...u} accentColor="amber" />
          ))}
        </div>

        <div className="bg-white rounded-2xl border border-stone-200 p-6 mb-10">
          <p className="text-sm font-bold text-stone-700 mb-4">Three ways to build and run workflows:</p>
          <div className="grid md:grid-cols-3 gap-4">
            {[
              { title: "Install from marketplace", desc: "22+ production-ready playbooks covering GitHub, Slack, CI/CD, incident response, and more. Install, configure, run." },
              { title: "Build on the canvas", desc: "Visual workflow editor. Drag blocks, wire connections, set conditions. Export as YAML. Version-controlled like any other code." },
              { title: "Write YAML directly", desc: "Full DSL with Brain, Tool, Logic, Approval, Memory, and MCP blocks. Composable. Reviewable. Runs from CLI or any trigger." },
            ].map(m => (
              <div key={m.title} className="p-4 rounded-xl bg-stone-50 border border-stone-100">
                <p className="text-sm font-bold text-stone-800 mb-1">{m.title}</p>
                <p className="text-sm text-stone-500 leading-relaxed">{m.desc}</p>
              </div>
            ))}
          </div>
          <p className="text-xs text-stone-400 mt-4">Every workflow run inherits Guard and security policies automatically. No extra configuration.</p>
        </div>

        <DualCTA
          platformText="Install a playbook from the marketplace. Connect your GitHub, Slack, or cloud integration. First workflow live in under an hour."
          solutionsText="We map your engineering processes, build custom playbooks for your stack, configure triggers, and hand off production-ready automations."
        />
      </div>
    </section>
  )
}

/* ─── Shared Components ────────────────────────────────────────────────── */

type AccentColor = "indigo" | "emerald" | "amber" | "violet"

function UseCaseCard({ pain, what, outcome, accentColor }: {
  pain: string
  what: string
  outcome: string
  accentColor: AccentColor
}) {
  const outcomeColors: Record<AccentColor, string> = {
    indigo: "text-indigo-700 bg-indigo-50 border-indigo-100",
    emerald: "text-emerald-700 bg-emerald-50 border-emerald-100",
    amber: "text-amber-700 bg-amber-50 border-amber-100",
    violet: "text-violet-700 bg-violet-50 border-violet-100",
  }
  return (
    <div className="bg-white rounded-2xl border border-stone-200 p-5 flex flex-col gap-3 hover:border-stone-300 hover:shadow-sm transition-all">
      <div className="flex items-start gap-2">
        <span className="text-stone-400 font-bold text-sm flex-shrink-0 mt-0.5">⚠</span>
        <p className="text-sm font-semibold text-stone-700 leading-relaxed">{pain}</p>
      </div>
      <p className="text-sm text-stone-500 leading-relaxed border-t border-stone-50 pt-3">{what}</p>
      <div className={`rounded-lg border px-3 py-2.5 text-sm font-medium leading-relaxed ${outcomeColors[accentColor]}`}>
        ✓ {outcome}
      </div>
    </div>
  )
}

function DualCTA({ platformText, solutionsText }: { platformText: string; solutionsText: string }) {
  return (
    <div className="grid md:grid-cols-2 gap-4">
      <div className="rounded-xl bg-indigo-50 border border-indigo-100 p-5">
        <p className="text-xs font-bold uppercase tracking-widest text-indigo-600 mb-2">Use the Platform</p>
        <p className="text-sm text-stone-600 leading-relaxed mb-4">{platformText}</p>
        <a href="/sign-up" className="inline-flex rounded-lg bg-stone-900 text-white px-4 py-2 text-sm font-semibold hover:bg-stone-700 transition-colors">
          Start Free →
        </a>
      </div>
      <div className="rounded-xl bg-stone-900 border border-stone-800 p-5">
        <p className="text-xs font-bold uppercase tracking-widest text-stone-400 mb-2">Work With Us</p>
        <p className="text-sm text-stone-400 leading-relaxed mb-4">{solutionsText}</p>
        <a href="mailto:hello@conductai.ai" className="inline-flex rounded-lg border border-white/20 text-white px-4 py-2 text-sm font-semibold hover:bg-white/10 transition-colors">
          Talk to Us →
        </a>
      </div>
    </div>
  )
}

/* ─── SDD ──────────────────────────────────────────────────────────────── */

const sddUseCases = [
  {
    pain: "AI wrote the feature in 20 minutes. Nobody can explain why it works the way it does — or trace it back to any requirement.",
    what: "SDD attaches a spec to every AI action before code is written. The spec defines the why — the requirement, the constraint, the decision. Conduct enforces that code maps to spec, not just to the prompt.",
    outcome: "Every function traceable to a decision. Every PR reviewable against the original requirement. No more AI-generated mystery code.",
  },
  {
    pain: "Requirements get agreed on in Slack, drift in JIRA, and disappear by the time the PR is opened. Nobody knows what was actually asked for.",
    what: "SDD keeps the spec as the source of truth. When the requirement changes, the spec changes — and Conduct flags the delta between spec and implementation automatically.",
    outcome: "Requirements visible at the code layer. Drift caught before merge, not after deployment.",
  },
  {
    pain: "We onboarded a new developer. They spent three days reading old PRs trying to understand why the codebase is shaped the way it is.",
    what: "SDD attaches decision context to the codebase itself, not to Slack threads that age out. New developers read the spec, understand the intent, and contribute without archaeology.",
    outcome: "Onboarding time cut from days to hours. Context lives with the code — not in someone's memory.",
  },
  {
    pain: "An AI agent rewrote a module. It passed all the tests. It also removed a constraint that existed for a compliance reason nobody commented.",
    what: "SDD encodes constraints as part of the spec, not as tribal knowledge. Conduct checks AI-generated changes against the spec — flagging when code satisfies the tests but violates the original intent.",
    outcome: "Compliance constraint preserved. Agent output reviewed against spec before merge. Audit trail intact.",
  },
]

function SDDSection() {
  return (
    <section id="sdd" className="py-24 px-6 bg-white">
      <div className="max-w-5xl mx-auto">
        <div className="flex items-center gap-3 mb-3">
          <div className="w-10 h-10 rounded-xl bg-violet-50 flex items-center justify-center text-xl">📐</div>
          <p className="text-xs font-bold uppercase tracking-widest text-violet-600">Spec-Driven Development</p>
        </div>
        <h2 className="text-3xl sm:text-4xl font-bold text-stone-900 tracking-tight mb-4">
          AI writes code fast.<br />
          <span className="text-violet-600">SDD gives every action a why.</span>
        </h2>
        <p className="text-stone-500 leading-relaxed max-w-2xl mb-12">
          Without a spec, AI coding tools drift. Requirements get lost. Nobody can trace which code maps
          to which decision. SDD attaches intent to every AI action — and Conduct enforces it automatically.
        </p>

        <div className="grid md:grid-cols-2 gap-5 mb-10">
          {sddUseCases.map((u, i) => (
            <UseCaseCard key={i} {...u} accentColor="violet" />
          ))}
        </div>

        <DualCTA
          platformText="Connect your repo and start attaching specs to AI actions today. Works with Claude Code, Cursor, and any MCP-connected tool."
          solutionsText="We implement SDD across your engineering team — spec templates, enforcement rules, and workflow integration tailored to how you already work."
        />
      </div>
    </section>
  )
}

/* ─── Final CTA ────────────────────────────────────────────────────────── */

function FinalCTASection() {
  return (
    <section className="py-24 px-6 bg-gradient-to-br from-indigo-600 to-violet-600">
      <div className="max-w-3xl mx-auto text-center">
        <h2 className="text-3xl sm:text-4xl font-black text-white tracking-tight leading-tight mb-4">
          Platform or partnership.<br />Either way — your AI layer gets governed.
        </h2>
        <p className="text-indigo-200 text-lg leading-relaxed mb-10 max-w-xl mx-auto">
          Start free and self-serve, or talk to us about a scoped engagement.
          Both paths lead to the same place: AI your team can actually trust.
        </p>
        <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
          <a href="/sign-up" className="rounded-xl bg-white text-indigo-600 px-7 py-3.5 text-base font-bold hover:bg-indigo-50 transition-colors w-full sm:w-auto text-center">
            Start Free — No Credit Card
          </a>
          <a href="mailto:hello@conductai.ai" className="rounded-xl border border-white/40 text-white px-7 py-3.5 text-base font-semibold hover:bg-white/10 transition-colors w-full sm:w-auto text-center">
            Book a Discovery Call
          </a>
        </div>
      </div>
    </section>
  )
}

/* ─── Footer ───────────────────────────────────────────────────────────── */

function PageFooter() {
  return (
    <footer className="border-t border-stone-100 py-8 px-6 bg-white">
      <div className="max-w-5xl mx-auto flex flex-col sm:flex-row justify-between items-center gap-4 text-xs text-stone-400">
        <div className="flex items-center gap-4 flex-wrap justify-center">
          <span>© {new Date().getFullYear()} Conduct AI</span>
          <a href="/" className="hover:text-stone-600 transition-colors">Home</a>
          <a href="/partners" className="hover:text-stone-600 transition-colors">Partners</a>
          <a href="/docs" className="hover:text-stone-600 transition-colors">Docs</a>
          <a href="/privacy" className="hover:text-stone-600 transition-colors">Privacy</a>
          <a href="/terms" className="hover:text-stone-600 transition-colors">Terms</a>
        </div>
        <span className="text-stone-300">Envisioned, designed and developed with love from Houston</span>
      </div>
    </footer>
  )
}
