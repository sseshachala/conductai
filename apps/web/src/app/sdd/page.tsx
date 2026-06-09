"use client"

import { useState } from "react"

export default function SDDPage() {
  return (
    <div className="min-h-screen bg-white flex flex-col">
      <Nav />
      <main>
        <HeroSection />
        <ProblemSection />
        <PrincipleSection />
        <WorkflowSection />
        <SpecGenSection />
        <EnforcementSection />
        <SyncSection />
        <WhyNotChatGPTSection />
        <ComparisonSection />
        <FooterCTASection />
      </main>
      <PageFooter />
    </div>
  )
}

/* ─── Nav ──────────────────────────────────────────────────────────────── */

function GitHubIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
      <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0 0 16 8c0-4.42-3.58-8-8-8z" />
    </svg>
  )
}

function Nav() {
  return (
    <header className="px-6 py-5 flex items-center justify-between max-w-6xl mx-auto w-full">
      <div className="flex items-center">
        <a href="/">
          <img src="/logo.png" alt="Conduct AI" className="h-10 w-auto" />
        </a>
      </div>
      <div className="flex items-center gap-4">
        <a href="/blog" className="flex items-center gap-1.5 text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">Blog</a>
        <a href="/marketplace" className="flex items-center gap-1.5 text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">Agent Templates</a>
        <div className="relative group">
          <a href="/tools" className="flex items-center gap-1 text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">
            Tools
            <svg width="12" height="12" viewBox="0 0 12 12" fill="currentColor" className="opacity-50 mt-0.5"><path d="M2 4l4 4 4-4"/></svg>
          </a>
          <div className="absolute left-0 top-full pt-2 hidden group-hover:block z-50">
            <div className="bg-white border border-stone-200 rounded-xl shadow-lg py-1.5 min-w-[160px]">
              <a href="/tools/agent-booster" className="flex items-center gap-2 px-4 py-2 text-sm text-stone-700 hover:bg-stone-50 transition-colors">
                <span className="text-indigo-600 font-bold">◈</span> Agent Booster
              </a>
              <a href="/tools/conduct-cli" className="flex items-center gap-2 px-4 py-2 text-sm text-stone-700 hover:bg-stone-50 transition-colors">
                <span className="text-violet-600 font-bold">⬡</span> Conduct CLI
              </a>
              <a href="/tools/security-loop" className="flex items-center gap-2 px-4 py-2 text-sm text-stone-700 hover:bg-stone-50 transition-colors">
                <span className="text-rose-600 font-bold">🔐</span> Security Loop
              </a>
            </div>
          </div>
        </div>
        <a href="/sdd" className="flex items-center gap-1.5 text-sm font-semibold text-indigo-600 hover:text-indigo-800 transition-colors">SDD</a>
        <a href="/benchmark" className="flex items-center gap-1.5 text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">Benchmark</a>
        <a href="/docs" className="flex items-center gap-1.5 text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">Docs</a>
        <a
          href="https://github.com/sseshachala/conductai"
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-1.5 text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors"
        >
          <GitHubIcon /> GitHub
        </a>
        <a href="/dashboard" className="inline-flex items-center gap-2 rounded-lg bg-stone-900 px-4 py-2 text-sm font-semibold text-white hover:bg-stone-700 transition-colors">
          Sign in →
        </a>
      </div>
    </header>
  )
}

/* ─── Hero ─────────────────────────────────────────────────────────────── */

function HeroSection() {
  return (
    <section className="flex flex-col items-center justify-center px-6 pt-16 pb-24 text-center">
      <div className="inline-flex items-center gap-2 bg-indigo-50 text-indigo-700 border border-indigo-100 text-xs font-semibold px-3 py-1.5 rounded-full mb-8 uppercase tracking-widest">
        Spec-Driven Development · SDD
      </div>

      <h1 className="text-5xl sm:text-6xl font-bold text-stone-900 leading-[1.1] tracking-tight max-w-3xl">
        AI writes code fast.{" "}
        <span className="text-indigo-600">Too fast.</span>
      </h1>

      <p className="mt-6 text-xl text-stone-500 max-w-2xl leading-relaxed">
        Without a spec, AI coding tools drift. Requirements get lost. Nobody can trace
        which code maps to which decision. SDD gives every AI action a&nbsp;<em>why</em> —
        and Conduct enforces it automatically.
      </p>

      <div className="mt-10 flex flex-col sm:flex-row items-center gap-4">
        <a
          href="#try"
          className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-6 py-3 text-sm font-semibold text-white hover:bg-indigo-700 transition-colors"
        >
          Generate your SPEC.md free →
        </a>
        <a
          href="#workflow"
          className="inline-flex items-center gap-2 rounded-xl border border-stone-200 bg-white px-6 py-3 text-sm font-semibold text-stone-700 hover:border-stone-300 hover:shadow-sm transition-all"
        >
          See the full workflow →
        </a>
      </div>

      <p className="mt-5 text-xs text-stone-400">No account needed to generate a spec.</p>
    </section>
  )
}

/* ─── Problem ──────────────────────────────────────────────────────────── */

function ProblemSection() {
  return (
    <section className="bg-stone-50 px-6 py-20">
      <div className="max-w-5xl mx-auto">
        <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest text-center mb-3">The problem</p>
        <h2 className="text-3xl font-bold text-stone-900 text-center mb-4">
          AI coding tools write code.<br />They don&apos;t know <em>why</em>.
        </h2>
        <p className="text-center text-stone-500 text-sm max-w-2xl mx-auto mb-14">
          The faster AI writes, the faster requirements drift. By the time you notice, the code
          doesn&apos;t match the intent — and there&apos;s no audit trail to explain what happened.
        </p>

        <div className="grid sm:grid-cols-3 gap-6">
          {[
            {
              icon: "⇌",
              title: "AI drift",
              desc: "The AI interprets your prompt, not your requirements. Each session it starts fresh — no memory of what FR-001 actually meant last week.",
              border: "border-red-100",
            },
            {
              icon: "∅",
              title: "No traceability",
              desc: "Which lines of code map to which decision? Nobody knows. A refactor breaks something — but nothing links the broken code back to a requirement.",
              border: "border-amber-100",
            },
            {
              icon: "⚠",
              title: "Compliance gap",
              desc: "SOC 2, ISO 27001, and internal audits ask: how do you know your software does what it's supposed to? You can't answer that without a spec.",
              border: "border-orange-100",
            },
          ].map(card => (
            <div key={card.title} className={`rounded-2xl border ${card.border} bg-white px-7 py-7 flex flex-col gap-4`}>
              <span className="text-3xl font-black text-stone-300">{card.icon}</span>
              <div>
                <h3 className="text-base font-semibold text-stone-900 mb-2">{card.title}</h3>
                <p className="text-sm text-stone-500 leading-relaxed">{card.desc}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

/* ─── Principle ────────────────────────────────────────────────────────── */

function PrincipleSection() {
  return (
    <section className="px-6 py-20">
      <div className="max-w-4xl mx-auto">
        <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest text-center mb-3">The principle</p>
        <h2 className="text-3xl font-bold text-stone-900 text-center mb-6">
          SPEC.md is the contract.
        </h2>
        <p className="text-center text-stone-500 text-sm max-w-2xl mx-auto mb-14">
          Every requirement gets a number. Every line of code traces back to one.
          The spec lives in your repo — git-versioned, human-readable, owned by your team.
          Conduct never owns your spec. It just enforces it.
        </p>

        <div className="rounded-2xl border border-stone-200 bg-stone-950 overflow-hidden">
          <div className="px-6 py-3 bg-stone-900 border-b border-stone-800 flex items-center gap-2">
            <span className="w-3 h-3 rounded-full bg-red-500 opacity-70" />
            <span className="w-3 h-3 rounded-full bg-amber-500 opacity-70" />
            <span className="w-3 h-3 rounded-full bg-emerald-500 opacity-70" />
            <span className="ml-3 text-xs text-stone-500 font-mono">SPEC.md</span>
          </div>
          <div className="px-8 py-6 font-mono text-sm leading-loose">
            <p className="text-stone-400"># Project Spec · v1.0</p>
            <p className="text-stone-600 mt-3">## Functional Requirements</p>
            <p className="mt-2"><span className="text-indigo-400 font-semibold">FR-001</span> <span className="text-white">User can log in with SSO</span></p>
            <p className="text-stone-500 text-xs ml-6">Acceptance: SSO flow completes in &lt;3s · session expires after 8h</p>
            <p className="mt-2"><span className="text-indigo-400 font-semibold">FR-002</span> <span className="text-white">Session expires after 8 hours of inactivity</span></p>
            <p className="text-stone-500 text-xs ml-6">Acceptance: idle session redirects to login · active session unaffected</p>
            <p className="mt-2"><span className="text-indigo-400 font-semibold">FR-003</span> <span className="text-white">Admin can revoke any active session</span></p>
            <p className="text-stone-500 text-xs ml-6">Acceptance: revoked session logs out within 60s · audit log records action</p>
            <p className="mt-4 text-stone-600">## Non-Functional Requirements</p>
            <p className="mt-2"><span className="text-violet-400 font-semibold">NFR-001</span> <span className="text-white">API response time &lt;200ms at p99</span></p>
            <p className="mt-2 text-stone-600">...</p>
          </div>
        </div>

        <div className="mt-8 grid sm:grid-cols-3 gap-4 text-center">
          {[
            { label: "Atomic", desc: "One behaviour per requirement" },
            { label: "Testable", desc: "Clear pass/fail acceptance criteria" },
            { label: "Traceable", desc: "PR can reference it unambiguously" },
          ].map(({ label, desc }) => (
            <div key={label} className="rounded-xl border border-indigo-100 bg-indigo-50 px-5 py-4">
              <p className="text-sm font-semibold text-indigo-800 mb-1">{label}</p>
              <p className="text-xs text-indigo-600">{desc}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

/* ─── Workflow ─────────────────────────────────────────────────────────── */

function WorkflowSection() {
  return (
    <section id="workflow" className="bg-stone-50 px-6 py-20">
      <div className="max-w-5xl mx-auto">
        <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest text-center mb-3">The workflow</p>
        <h2 className="text-3xl font-bold text-stone-900 text-center mb-4">
          From idea to shipped code — with full traceability.
        </h2>
        <p className="text-center text-stone-500 text-sm max-w-2xl mx-auto mb-14">
          Six playbooks. One continuous workflow. Each step feeds the next.
        </p>

        <div className="flex flex-col gap-3">
          {[
            {
              phase: "0",
              name: "sdd-spec-gen",
              label: "Free · No login",
              title: "Describe → SPEC.md",
              desc: "Paste a description, Notion doc, Confluence page, or GitHub Epic. The agent asks 2–3 targeted questions to fill gaps, then writes a structured SPEC.md with numbered, testable FR-xxx requirements.",
              color: "border-indigo-300 bg-indigo-50",
              badge: "bg-indigo-100 text-indigo-700",
              icon: "◈",
              iconColor: "text-indigo-600",
            },
            {
              phase: "1",
              name: "sdd-bootstrap",
              label: "Requires account",
              title: "SPEC.md → Full repo scaffold",
              desc: "Reads your SPEC.md and commits 6 files in one push: AGENTS.md, DESIGN.md, PLAN.md, SPRINT.md, CLAUDE.md, and .conduct/spec-index.json — the machine-readable FR index that powers everything downstream.",
              color: "border-violet-300 bg-violet-50",
              badge: "bg-violet-100 text-violet-700",
              icon: "⬡",
              iconColor: "text-violet-600",
            },
            {
              phase: "2",
              name: "sdd-feature",
              label: "Per feature",
              title: "FR → failing tests → code → PR",
              desc: "For each feature: reads the relevant FRs, writes failing tests first, writes code that makes them pass, runs a spec gate (every changed line must trace to a FR), then opens a PR with a spec compliance summary.",
              color: "border-emerald-300 bg-emerald-50",
              badge: "bg-emerald-100 text-emerald-700",
              icon: "⟁",
              iconColor: "text-emerald-600",
            },
            {
              phase: "3",
              name: "sdd-spec-to-issues",
              label: "GitHub · Jira · Linear",
              title: "FR list → Epics + Stories",
              desc: "Pushes every FR as a Story under the right Epic into your tracker. FR numbers become the connective tissue: the same number appears in SPEC.md, the Jira ticket, the test comment, the commit, and the PR title.",
              color: "border-amber-300 bg-amber-50",
              badge: "bg-amber-100 text-amber-700",
              icon: "◎",
              iconColor: "text-amber-600",
            },
            {
              phase: "4",
              name: "sdd-spec-index",
              label: "On every push",
              title: "Keep spec-index.json in sync",
              desc: "Runs automatically on every push. Regenerates the machine-readable FR index when SPEC.md changes. Keeps tracker issue URLs, status, and file mappings current without manual intervention.",
              color: "border-teal-300 bg-teal-50",
              badge: "bg-teal-100 text-teal-700",
              icon: "⊙",
              iconColor: "text-teal-600",
            },
            {
              phase: "5",
              name: "sdd-drift-check",
              label: "Weekly",
              title: "Surface untraced code + unimplemented FRs",
              desc: "Weekly scan: finds source files with no FR reference and FRs with no code yet. Surfaces both as a Slack report. The spec and the codebase stay honest.",
              color: "border-rose-300 bg-rose-50",
              badge: "bg-rose-100 text-rose-700",
              icon: "≋",
              iconColor: "text-rose-600",
            },
          ].map((step, idx, arr) => (
            <div key={step.phase}>
              <div className={`rounded-2xl border ${step.color} px-7 py-6 flex items-start gap-6`}>
                <div className="shrink-0 flex flex-col items-center gap-2">
                  <span className={`text-2xl font-black ${step.iconColor}`}>{step.icon}</span>
                  {idx < arr.length - 1 && <div className="w-px h-8 bg-stone-200" />}
                </div>
                <div className="flex-1">
                  <div className="flex items-center gap-3 mb-2 flex-wrap">
                    <code className="font-mono text-sm font-semibold text-stone-800">{step.name}</code>
                    <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${step.badge}`}>{step.label}</span>
                  </div>
                  <p className="text-base font-semibold text-stone-900 mb-1">{step.title}</p>
                  <p className="text-sm text-stone-500 leading-relaxed">{step.desc}</p>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

/* ─── sdd-spec-gen free tool ───────────────────────────────────────────── */

type Stage = "input" | "asking" | "clarify" | "generating" | "output" | "error"
type Question = { key: string; question: string }
type ScaffoldFile = { name: string; content: string }
type ScaffoldStage = "idle" | "generating" | "done"

function renderInline(text: string): React.ReactNode[] {
  const parts = text.split(/(\*\*[^*]+\*\*|_[^_]+_|`[^`]+`)/g)
  return parts.map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**")) return <strong key={i}>{part.slice(2, -2)}</strong>
    if (part.startsWith("_") && part.endsWith("_")) return <em key={i} className="text-stone-500 not-italic">{part.slice(1, -1)}</em>
    if (part.startsWith("`") && part.endsWith("`")) return <code key={i} className="bg-stone-100 px-1 rounded text-xs font-mono text-indigo-700">{part.slice(1, -1)}</code>
    return part
  })
}

function MarkdownViewer({ content, name }: { content: string; name: string }) {
  if (name === "spec-index.json") {
    return <pre className="px-5 py-5 text-xs font-mono text-stone-600 leading-relaxed whitespace-pre-wrap max-h-[420px] overflow-y-auto">{content}</pre>
  }
  const lines = content.split("\n")
  return (
    <div className="px-6 py-5 max-h-[420px] overflow-y-auto space-y-1">
      {lines.map((line, i) => {
        if (line.startsWith("# ")) return <h1 key={i} className="text-lg font-bold text-stone-900 mt-2 mb-1 first:mt-0">{renderInline(line.slice(2))}</h1>
        if (line.startsWith("## ")) return <h2 key={i} className="text-sm font-bold text-stone-800 mt-5 mb-1 pb-1 border-b border-stone-100">{renderInline(line.slice(3))}</h2>
        if (line.startsWith("### ")) return <h3 key={i} className="text-sm font-semibold text-stone-700 mt-3 mb-0.5">{renderInline(line.slice(4))}</h3>
        if (line.startsWith("---")) return <hr key={i} className="border-stone-200 my-3" />
        if (line.startsWith("- ") || line.startsWith("* ")) return (
          <div key={i} className="flex gap-2 text-xs text-stone-600 leading-relaxed">
            <span className="text-stone-300 shrink-0 mt-0.5">•</span>
            <span>{renderInline(line.slice(2))}</span>
          </div>
        )
        if (line.startsWith("❓")) return (
          <div key={i} className="bg-amber-50 border border-amber-100 rounded-lg px-3 py-2 text-xs text-amber-800 my-1">{renderInline(line)}</div>
        )
        if (/^\*\*FR-\d+\*\*/.test(line)) return (
          <div key={i} className="mt-3 mb-0.5 text-xs font-bold text-indigo-700">{renderInline(line)}</div>
        )
        if (/^\*\*NFR-\d+\*\*/.test(line)) return (
          <div key={i} className="mt-3 mb-0.5 text-xs font-bold text-violet-700">{renderInline(line)}</div>
        )
        if (line.startsWith("_Acceptance")) return (
          <div key={i} className="ml-4 text-xs text-emerald-700 border-l-2 border-emerald-200 pl-3 py-0.5 italic">{renderInline(line)}</div>
        )
        if (line.trim() === "") return <div key={i} className="h-1.5" />
        return <p key={i} className="text-xs text-stone-600 leading-relaxed">{renderInline(line)}</p>
      })}
    </div>
  )
}

function SpecGenSection() {
  const [stage, setStage] = useState<Stage>("input")
  const [description, setDescription] = useState("")
  const [sourceUrl, setSourceUrl] = useState("")
  const [questions, setQuestions] = useState<Question[]>([])
  const [answers, setAnswers] = useState<Record<string, string>>({})
  const [generatingStep, setGeneratingStep] = useState(0)
  const [trailOpen, setTrailOpen] = useState(false)
  const [spec, setSpec] = useState("")
  const [errorMsg, setErrorMsg] = useState("")
  const [scaffoldFiles, setScaffoldFiles] = useState<ScaffoldFile[]>([])
  const [scaffoldStage, setScaffoldStage] = useState<ScaffoldStage>("idle")
  const [scaffoldStep, setScaffoldStep] = useState("")
  const [activeTab, setActiveTab] = useState("SPEC.md")
  const [copiedTab, setCopiedTab] = useState("")

  const base = process.env.NEXT_PUBLIC_API_URL ?? ""

  const GENERATING_STEPS = [
    "Reading description",
    "Extracting functional areas",
    "Writing FR-xxx requirements",
    "Checking quality rules",
    "Finalising SPEC.md",
  ]

  async function handleAnalyse() {
    if (!description.trim()) return
    setStage("asking")
    try {
      const res = await fetch(`${base}/sdd/questions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ description }),
      })
      if (res.ok) {
        const data = await res.json()
        setQuestions(data.questions ?? [])
        const init: Record<string, string> = {}
        for (const q of (data.questions ?? [])) init[q.key] = ""
        setAnswers(init)
      } else {
        // Fall back to generic questions
        const fallback = [
          { key: "users", question: "Who are the primary users? What's their main goal?" },
          { key: "out_of_scope", question: "What's explicitly out of scope for this version?" },
          { key: "constraints", question: "Any hard constraints? (tech stack, compliance, timeline)" },
        ]
        setQuestions(fallback)
        setAnswers({ users: "", out_of_scope: "", constraints: "" })
      }
    } catch {
      const fallback = [
        { key: "users", question: "Who are the primary users? What's their main goal?" },
        { key: "out_of_scope", question: "What's explicitly out of scope for this version?" },
        { key: "constraints", question: "Any hard constraints? (tech stack, compliance, timeline)" },
      ]
      setQuestions(fallback)
      setAnswers({ users: "", out_of_scope: "", constraints: "" })
    }
    setStage("clarify")
  }

  async function handleGenerate() {
    setStage("generating")
    setGeneratingStep(0)
    setErrorMsg("")

    // Animate steps while API call runs
    let step = 0
    const iv = setInterval(() => {
      step = Math.min(step + 1, GENERATING_STEPS.length - 1)
      setGeneratingStep(step)
    }, 800)

    try {
      const res = await fetch(`${base}/sdd/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          description,
          source_url: sourceUrl || null,
          answers,
        }),
      })
      clearInterval(iv)
      setGeneratingStep(GENERATING_STEPS.length)

      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        setErrorMsg(body?.detail ?? "Generation failed — please try again.")
        setStage("error")
        return
      }
      const data = await res.json()
      setSpec(data.spec)
      setTimeout(() => setStage("output"), 300)
    } catch {
      clearInterval(iv)
      setErrorMsg("Could not reach the server — check your connection.")
      setStage("error")
    }
  }

  const SCAFFOLD_FILES = ["spec-index.json", "AGENTS.md", "DESIGN.md", "PLAN.md", "SPRINT.md", "CLAUDE.md"]

  async function handleScaffold() {
    setScaffoldStage("generating")
    setScaffoldFiles([])
    setScaffoldStep("spec-index.json")

    try {
      const res = await fetch(`${base}/sdd/scaffold/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ spec }),
      })
      if (!res.ok || !res.body) { setScaffoldStage("idle"); return }

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buf = ""

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buf += decoder.decode(value, { stream: true })
        const lines = buf.split("\n")
        buf = lines.pop() ?? ""
        for (const line of lines) {
          if (!line.trim()) continue
          try {
            const file = JSON.parse(line) as ScaffoldFile
            setScaffoldFiles(prev => [...prev, file])
            setScaffoldStep(file.name)
            setActiveTab(file.name)
          } catch { /* malformed line */ }
        }
      }
      setScaffoldStage("done")
    } catch {
      setScaffoldStage("idle")
    }
  }

  function downloadFile(name: string, content: string) {
    const blob = new Blob([content], { type: name.endsWith(".json") ? "application/json" : "text/markdown" })
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url; a.download = name; a.click()
    URL.revokeObjectURL(url)
  }

  function copyFile(name: string, content: string) {
    navigator.clipboard.writeText(content).then(() => {
      setCopiedTab(name)
      setTimeout(() => setCopiedTab(""), 2000)
    })
  }

  const allFiles: ScaffoldFile[] = [{ name: "SPEC.md", content: spec }, ...scaffoldFiles]
  const activeFile = allFiles.find(f => f.name === activeTab) ?? allFiles[0]
  const frCount = (spec.match(/\*\*FR-\d+\*\*/g) ?? []).length
  const openQCount = (spec.match(/❓/g) ?? []).length

  return (
    <section id="try" className="px-6 py-20">
      <div className="max-w-2xl mx-auto">
        <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest text-center mb-3">Try it free</p>
        <h2 className="text-3xl font-bold text-stone-900 text-center mb-3">
          Generate your SPEC.md.
        </h2>
        <p className="text-center text-stone-500 text-sm mb-10">
          No account needed. Describe what you&apos;re building — get a structured spec in ~20 seconds.
        </p>

        <div className="rounded-2xl border border-stone-200 bg-white overflow-hidden shadow-sm">

          {/* Stage indicator */}
          <div className="px-6 py-3 bg-stone-50 border-b border-stone-100 flex items-center gap-3">
            {(["input", "clarify", "output"] as const).map((s, i) => (
              <div key={s} className="flex items-center gap-2">
                <div className={`w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold transition-colors ${
                  stage === s || (stage === "asking" && s === "input") || (stage === "generating" && s === "clarify") || (stage === "output" && i < 2)
                    ? "bg-indigo-600 text-white"
                    : "bg-stone-200 text-stone-400"
                }`}>{i + 1}</div>
                <span className="text-xs text-stone-500 hidden sm:block">
                  {["Describe", "Clarify", "Download"][i]}
                </span>
                {i < 2 && <span className="text-stone-300 text-xs">→</span>}
              </div>
            ))}
          </div>

          <div className="px-7 py-7">

            {/* Stage 1 — Input */}
            {stage === "input" && (
              <div className="flex flex-col gap-5">
                <div className="flex flex-col gap-2">
                  <label className="text-sm font-semibold text-stone-700">What are you building?</label>
                  <textarea
                    value={description}
                    onChange={e => setDescription(e.target.value)}
                    rows={5}
                    placeholder="e.g. A SaaS tool that helps product managers capture feature requests from Slack and route them into Jira tickets automatically. The PM connects their Slack workspace, configures which channels to monitor, and reviews captured requests before they become tickets."
                    className="w-full rounded-xl border border-stone-200 bg-stone-50 px-4 py-3 text-sm text-stone-800 placeholder:text-stone-400 focus:outline-none focus:ring-2 focus:ring-indigo-300 resize-none leading-relaxed"
                  />
                </div>
                <div className="flex flex-col gap-2">
                  <label className="text-sm font-medium text-stone-500">Or paste a doc URL <span className="text-stone-400">(optional)</span></label>
                  <input
                    type="url"
                    value={sourceUrl}
                    onChange={e => setSourceUrl(e.target.value)}
                    placeholder="https://notion.so/... or Confluence, GitHub Epic"
                    className="w-full rounded-xl border border-stone-200 bg-stone-50 px-4 py-2.5 text-sm text-stone-800 placeholder:text-stone-400 focus:outline-none focus:ring-2 focus:ring-indigo-300"
                  />
                  <p className="text-xs text-stone-400">Notion, Confluence, GitHub Epic — agent extracts and normalises</p>
                </div>
                <button
                  onClick={handleAnalyse}
                  disabled={!description.trim()}
                  className="self-end inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-6 py-2.5 text-sm font-semibold text-white hover:bg-indigo-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                >
                  Analyse →
                </button>
              </div>
            )}

            {/* Stage 1b — Asking (loading questions) */}
            {stage === "asking" && (
              <div className="flex flex-col items-center gap-4 py-8">
                <span className="text-2xl animate-spin inline-block text-indigo-400">◈</span>
                <p className="text-sm text-stone-500">Analysing your description…</p>
              </div>
            )}

            {/* Stage 2 — Clarify (dynamic questions) */}
            {stage === "clarify" && (
              <div className="flex flex-col gap-6">
                <div className="rounded-xl bg-indigo-50 border border-indigo-100 px-5 py-4">
                  <p className="text-sm text-indigo-700 leading-relaxed">
                    Based on your description, I have a few targeted questions before writing
                    atomic, testable requirements.
                  </p>
                </div>

                {questions.map(({ key, question }, i) => (
                  <div key={key} className="flex flex-col gap-2">
                    <label className="text-sm font-semibold text-stone-700">{i + 1}. {question}</label>
                    <textarea
                      rows={2}
                      value={answers[key] ?? ""}
                      onChange={e => setAnswers(a => ({ ...a, [key]: e.target.value }))}
                      className="w-full rounded-xl border border-stone-200 bg-stone-50 px-4 py-3 text-sm text-stone-800 placeholder:text-stone-400 focus:outline-none focus:ring-2 focus:ring-indigo-300 resize-none leading-relaxed"
                    />
                  </div>
                ))}

                <div className="flex items-center justify-between pt-2">
                  <button onClick={() => setStage("input")} className="text-sm text-stone-400 hover:text-stone-600 transition-colors">← Back</button>
                  <div className="flex items-center gap-3">
                    <span className="text-xs text-stone-400">~20 seconds</span>
                    <button
                      onClick={handleGenerate}
                      className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-6 py-2.5 text-sm font-semibold text-white hover:bg-indigo-700 transition-colors"
                    >
                      Generate SPEC →
                    </button>
                  </div>
                </div>
              </div>
            )}

            {/* Stage 2b — Generating */}
            {stage === "generating" && (
              <div className="flex flex-col items-center gap-6 py-6">
                <div className="w-10 h-10 rounded-full bg-indigo-100 flex items-center justify-center">
                  <span className="text-xl text-indigo-600 animate-spin inline-block">◈</span>
                </div>
                <div className="flex flex-col gap-2 w-full max-w-xs">
                  {GENERATING_STEPS.map((step, i) => (
                    <div key={step} className="flex items-center gap-3">
                      <span className={`w-4 h-4 rounded-full flex items-center justify-center text-[10px] shrink-0 transition-colors ${
                        i < generatingStep ? "bg-emerald-500 text-white" : i === generatingStep ? "bg-indigo-200 text-indigo-600" : "bg-stone-100 text-stone-400"
                      }`}>
                        {i < generatingStep ? "✓" : "◌"}
                      </span>
                      <span className={`text-sm transition-colors ${i < generatingStep ? "text-stone-500" : i === generatingStep ? "text-stone-800 font-medium" : "text-stone-400"}`}>
                        {step}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Stage — Error */}
            {stage === "error" && (
              <div className="flex flex-col gap-4">
                <div className="rounded-xl bg-red-50 border border-red-200 px-5 py-4">
                  <p className="text-sm font-semibold text-red-700 mb-1">Generation failed</p>
                  <p className="text-sm text-red-600">{errorMsg}</p>
                </div>
                <div className="flex items-center gap-3">
                  <button onClick={() => setStage("clarify")} className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-indigo-700 transition-colors">
                    Try again →
                  </button>
                  <button onClick={() => setStage("input")} className="text-sm text-stone-400 hover:text-stone-600 transition-colors">← Start over</button>
                </div>
              </div>
            )}

            {/* Stage 3 — Output */}
            {stage === "output" && (
              <div className="flex flex-col gap-4">

                {/* Status bar */}
                <div className="flex items-center gap-3 flex-wrap">
                  <div className="flex items-center gap-2 bg-emerald-50 border border-emerald-200 rounded-full px-3 py-1">
                    <span className="w-2 h-2 rounded-full bg-emerald-500" />
                    <span className="text-xs font-semibold text-emerald-700">
                      {scaffoldStage === "done" ? `${allFiles.length} files ready` : "SPEC.md ready"}
                    </span>
                  </div>
                  <span className="text-xs text-stone-400">
                    {frCount > 0 ? `${frCount} FRs` : ""}
                    {openQCount > 0 ? ` · ${openQCount} open questions` : ""}
                  </span>
                  <button
                    onClick={() => { setStage("input"); setDescription(""); setSourceUrl(""); setAnswers({}); setQuestions([]); setSpec(""); setScaffoldFiles([]); setScaffoldStage("idle"); setActiveTab("SPEC.md"); setTrailOpen(false) }}
                    className="text-xs text-stone-400 hover:text-stone-600 transition-colors ml-auto"
                  >
                    Start over
                  </button>
                </div>

                {/* Tab pills */}
                <div className="flex items-center gap-1.5 flex-wrap">
                  {allFiles.map(f => (
                    <button
                      key={f.name}
                      onClick={() => setActiveTab(f.name)}
                      className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors ${
                        activeTab === f.name
                          ? "bg-indigo-600 text-white"
                          : "bg-stone-100 text-stone-500 hover:bg-stone-200"
                      }`}
                    >
                      {f.name}
                    </button>
                  ))}
                  {scaffoldStage === "idle" && SCAFFOLD_FILES.map(n => (
                    <span key={n} className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-stone-50 text-stone-300 border border-dashed border-stone-200">{n}</span>
                  ))}
                </div>

                {/* File viewer */}
                <div className="rounded-xl border border-stone-200 bg-white overflow-hidden">
                  <div className="px-4 py-2.5 bg-stone-50 border-b border-stone-100 flex items-center justify-between">
                    <span className="font-mono text-xs text-stone-500">{activeFile?.name}</span>
                    <div className="flex items-center gap-3">
                      <button onClick={() => copyFile(activeFile.name, activeFile.content)} className="text-xs text-stone-400 hover:text-stone-700 transition-colors">
                        {copiedTab === activeFile?.name ? "Copied ✓" : "Copy"}
                      </button>
                      <button onClick={() => downloadFile(activeFile.name, activeFile.content)} className="text-xs text-indigo-500 hover:text-indigo-700 font-semibold transition-colors">
                        Download
                      </button>
                    </div>
                  </div>
                  {activeFile && <MarkdownViewer content={activeFile.content} name={activeFile.name} />}
                </div>

                {/* Scaffold CTA or generating */}
                {scaffoldStage === "idle" && (
                  <div className="rounded-xl border border-indigo-100 bg-indigo-50 px-5 py-4 flex items-center justify-between gap-4">
                    <div>
                      <p className="text-sm font-semibold text-stone-900 mb-0.5">Scaffold your repo from this spec</p>
                      <p className="text-xs text-stone-500">Generates AGENTS.md, DESIGN.md, PLAN.md, SPRINT.md, CLAUDE.md + spec-index.json — free, no login.</p>
                    </div>
                    <button
                      onClick={handleScaffold}
                      className="shrink-0 inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-indigo-700 transition-colors"
                    >
                      Scaffold this →
                    </button>
                  </div>
                )}

                {scaffoldStage === "generating" && (
                  <div className="rounded-xl border border-stone-100 bg-stone-50 px-5 py-4 flex items-center gap-4">
                    <span className="text-indigo-400 animate-spin text-lg shrink-0">◈</span>
                    <div>
                      <p className="text-xs font-semibold text-stone-700">Generating scaffold files…</p>
                      <p className="text-xs text-stone-400 font-mono mt-0.5">{scaffoldStep}</p>
                    </div>
                  </div>
                )}

                {/* Generation trail */}
                <details open={trailOpen} onToggle={e => setTrailOpen((e.target as HTMLDetailsElement).open)}
                  className="rounded-xl border border-stone-100 overflow-hidden">
                  <summary className="px-5 py-3 text-xs font-semibold text-stone-400 cursor-pointer select-none hover:text-stone-600 transition-colors list-none flex items-center justify-between bg-stone-50">
                    <span>How this was generated</span>
                    <span className="text-stone-300">{trailOpen ? "▲" : "▼"}</span>
                  </summary>
                  {trailOpen && (
                    <div className="px-5 pb-5 flex flex-col gap-4 border-t border-stone-100 pt-4 bg-stone-50">
                      <div>
                        <p className="text-[10px] font-bold text-stone-400 uppercase tracking-widest mb-1.5">Description</p>
                        <p className="text-xs text-stone-600 leading-relaxed whitespace-pre-wrap">{description}</p>
                      </div>
                      {questions.length > 0 && (
                        <div>
                          <p className="text-[10px] font-bold text-stone-400 uppercase tracking-widest mb-2">Questions asked</p>
                          <div className="flex flex-col gap-3">
                            {questions.map(({ key, question }) => (
                              <div key={key}>
                                <p className="text-xs font-medium text-stone-600 mb-0.5">{question}</p>
                                <p className="text-xs text-stone-400 italic">{answers[key] ? `"${answers[key]}"` : "(not answered)"}</p>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                      <div>
                        <p className="text-[10px] font-bold text-stone-400 uppercase tracking-widest mb-1.5">Model</p>
                        <p className="text-xs text-stone-500 font-mono">claude-sonnet-4-6</p>
                      </div>
                    </div>
                  )}
                </details>

              </div>
            )}
          </div>
        </div>
      </div>
    </section>
  )
}

/* ─── Enforcement ──────────────────────────────────────────────────────── */

function EnforcementSection() {
  return (
    <section className="bg-stone-900 px-6 py-20">
      <div className="max-w-4xl mx-auto">
        <p className="text-xs font-semibold text-stone-500 uppercase tracking-widest text-center mb-3">The moat</p>
        <h2 className="text-3xl font-bold text-white text-center mb-6">
          The only platform where AI can&apos;t ship<br />code that isn&apos;t in the spec.
        </h2>
        <p className="text-center text-stone-400 text-sm max-w-2xl mx-auto mb-14">
          Notion stores requirements. Jira tracks tickets. Linear manages sprints.
          None of them prevent AI from writing code with no requirement behind it.
          Conduct does — at the git hook level.
        </p>

        <div className="grid sm:grid-cols-2 gap-5 mb-8">
          <div className="rounded-2xl border border-stone-700 bg-stone-800 px-7 py-6">
            <p className="text-xs font-bold text-stone-500 uppercase tracking-widest mb-4">Without Conduct</p>
            <div className="rounded-xl bg-stone-950 px-5 py-4 font-mono text-xs space-y-2">
              <p className="text-stone-500"># git push — no checks</p>
              <p className="text-stone-400">modified: src/auth/session.ts</p>
              <p className="text-stone-400">modified: src/auth/sso.ts</p>
              <p className="text-emerald-400">✓ pushed to main</p>
              <p className="text-stone-600 mt-3"># No one knows which requirement</p>
              <p className="text-stone-600"># these files implement</p>
            </div>
          </div>
          <div className="rounded-2xl border border-indigo-500 bg-stone-800 px-7 py-6">
            <p className="text-xs font-bold text-indigo-400 uppercase tracking-widest mb-4">With Conduct SDD</p>
            <div className="rounded-xl bg-stone-950 px-5 py-4 font-mono text-xs space-y-2">
              <p className="text-stone-500"># git push — hook runs</p>
              <p className="text-stone-400">modified: src/auth/session.ts</p>
              <p className="text-red-400">✗ no FR reference found</p>
              <p className="text-amber-400">  hint: add [FR-002] to commit msg</p>
              <p className="text-stone-600 mt-2"># Add FR reference, push again</p>
              <p className="text-stone-400">modified: src/auth/session.ts</p>
              <p className="text-emerald-400">✓ FR-002 · FR-003 verified</p>
              <p className="text-emerald-400">✓ pushed to main</p>
            </div>
          </div>
        </div>

        <div className="rounded-2xl border border-stone-600 bg-stone-800 px-8 py-6 text-center">
          <p className="text-stone-300 text-sm leading-relaxed">
            The pre-merge hook lives in <code className="font-mono text-indigo-400 bg-stone-900 px-1.5 py-0.5 rounded">.conduct/hooks/pre-merge</code> — git-native, no external service required to enforce. If a team leaves Conduct, their spec and traceability data stay in the repo.
          </p>
        </div>
      </div>
    </section>
  )
}

/* ─── Sync ─────────────────────────────────────────────────────────────── */

function SyncSection() {
  return (
    <section className="px-6 py-20">
      <div className="max-w-5xl mx-auto">
        <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest text-center mb-3">Tracker sync</p>
        <h2 className="text-3xl font-bold text-stone-900 text-center mb-4">
          FR numbers connect everything.
        </h2>
        <p className="text-center text-stone-500 text-sm max-w-2xl mx-auto mb-14">
          One number traces a requirement from SPEC.md through Jira, the test file, the commit,
          and the PR. Sync with GitHub, Jira, or Linear — bidirectionally.
        </p>

        <div className="rounded-2xl border border-stone-200 bg-stone-950 overflow-hidden mb-8">
          <div className="px-6 py-3 bg-stone-900 border-b border-stone-800">
            <span className="font-mono text-xs text-stone-500">FR-001 traces through your entire stack</span>
          </div>
          <div className="px-8 py-6 grid sm:grid-cols-2 gap-8 font-mono text-xs">
            <div className="flex flex-col gap-3">
              {[
                { label: "SPEC.md", value: "FR-001  User can log in with SSO", color: "text-indigo-400" },
                { label: "Jira / Linear / GH", value: "[FR-001] User can log in with SSO", color: "text-violet-400" },
                { label: "Test file", value: "# FR-001\ndef test_sso_login():", color: "text-emerald-400" },
              ].map(({ label, value, color }) => (
                <div key={label}>
                  <p className="text-stone-600 mb-1"># {label}</p>
                  <p className={color}>{value}</p>
                </div>
              ))}
            </div>
            <div className="flex flex-col gap-3">
              {[
                { label: "Git commit", value: 'feat(auth): SSO login [FR-001]', color: "text-amber-400" },
                { label: "PR title", value: "feat(auth): SSO [FR-001] closes #42", color: "text-teal-400" },
                { label: "SPRINT.md", value: "FR-001 → done (merged Jun 8)", color: "text-rose-400" },
              ].map(({ label, value, color }) => (
                <div key={label}>
                  <p className="text-stone-600 mb-1"># {label}</p>
                  <p className={color}>{value}</p>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="grid sm:grid-cols-3 gap-5">
          {[
            { tracker: "GitHub Issues", phase: "Available now", color: "bg-emerald-50 border-emerald-200 text-emerald-700" },
            { tracker: "Jira", phase: "Phase 2", color: "bg-amber-50 border-amber-200 text-amber-700" },
            { tracker: "Linear", phase: "Phase 2", color: "bg-amber-50 border-amber-200 text-amber-700" },
          ].map(({ tracker, phase, color }) => (
            <div key={tracker} className="rounded-xl border border-stone-200 bg-white px-5 py-4 flex items-center justify-between">
              <span className="text-sm font-semibold text-stone-800">{tracker}</span>
              <span className={`text-[10px] font-semibold px-2.5 py-1 rounded-full border ${color}`}>{phase}</span>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

/* ─── Comparison ───────────────────────────────────────────────────────── */

function WhyNotChatGPTSection() {
  return (
    <section className="px-6 py-20">
      <div className="max-w-4xl mx-auto">
        <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest text-center mb-3">Common question</p>
        <h2 className="text-3xl font-bold text-stone-900 text-center mb-4">
          Why not just ask Claude or ChatGPT?
        </h2>
        <p className="text-stone-500 text-center max-w-xl mx-auto mb-14 leading-relaxed">
          You can. But you get a markdown blob in a chat window.
        </p>

        <div className="grid sm:grid-cols-2 gap-6 mb-12">
          <div className="rounded-2xl border border-stone-200 p-7">
            <p className="text-xs font-bold text-stone-400 uppercase tracking-widest mb-4">Claude / ChatGPT</p>
            <ul className="space-y-3">
              {[
                "Spec lives in a chat thread",
                "No FR numbers — just prose",
                "Nothing enforced at commit time",
                "Disconnected from your repo and tickets",
                "Agents ignore it the next day",
              ].map(item => (
                <li key={item} className="flex items-start gap-2.5 text-sm text-stone-500">
                  <span className="mt-0.5 text-stone-300">✕</span>
                  {item}
                </li>
              ))}
            </ul>
          </div>

          <div className="rounded-2xl border border-indigo-100 bg-indigo-50/40 p-7">
            <p className="text-xs font-bold text-indigo-500 uppercase tracking-widest mb-4">Conduct SDD</p>
            <ul className="space-y-3">
              {[
                "SPEC.md committed to git — versioned forever",
                "FR-xxx numbers in every commit, PR, and test",
                "Pre-commit hook blocks unlinked code",
                "One command syncs FRs to Jira / Linear / GitHub",
                "AGENTS.md makes every AI agent spec-aware",
              ].map(item => (
                <li key={item} className="flex items-start gap-2.5 text-sm text-stone-700">
                  <span className="mt-0.5 text-indigo-500">✓</span>
                  {item}
                </li>
              ))}
            </ul>
          </div>
        </div>

        <p className="text-center text-stone-500 text-sm font-medium">
          Chat → markdown.&nbsp;&nbsp;Conduct → enforced architecture.
        </p>
      </div>
    </section>
  )
}

function ComparisonSection() {
  return (
    <section className="bg-stone-50 px-6 py-20">
      <div className="max-w-4xl mx-auto">
        <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest text-center mb-3">Why not just use Notion?</p>
        <h2 className="text-3xl font-bold text-stone-900 text-center mb-12">
          Storing requirements isn&apos;t enforcing them.
        </h2>

        <div className="rounded-2xl overflow-hidden border border-stone-200">
          <div className="grid grid-cols-3 bg-stone-100 px-6 py-3 border-b border-stone-200">
            <p className="text-xs font-bold text-stone-400 uppercase tracking-widest"></p>
            <p className="text-xs font-bold text-stone-400 uppercase tracking-widest text-center">Notion / Confluence / Jira</p>
            <p className="text-xs font-bold text-indigo-600 uppercase tracking-widest text-center">Conduct SDD</p>
          </div>
          {[
            ["Write structured requirements", "Manual", "Generated + quality-checked"],
            ["Requirements in version control", "No", "Yes — SPEC.md in git"],
            ["FR numbers in code", "Convention only", "Enforced by hook"],
            ["Block PR with no spec reference", "No", "Yes"],
            ["Sync FRs to Jira / Linear", "Manual copy-paste", "Automated bidirectional"],
            ["Detect spec drift weekly", "No", "Yes — sdd-drift-check"],
            ["AI agents respect requirements", "No", "Yes — AGENTS.md + gate"],
          ].map(([feature, them, us], i) => (
            <div key={feature} className={`grid grid-cols-3 px-6 py-4 ${i % 2 === 0 ? "bg-white" : "bg-stone-50"} border-b border-stone-100 last:border-0`}>
              <p className="text-sm text-stone-700 font-medium">{feature}</p>
              <p className="text-sm text-stone-400 text-center">{them}</p>
              <p className="text-sm text-indigo-700 font-semibold text-center">{us}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

/* ─── Footer CTA ───────────────────────────────────────────────────────── */

function FooterCTASection() {
  return (
    <section className="px-6 py-20 text-center">
      <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-4">Get started</p>
      <h2 className="text-3xl font-bold text-stone-900 mb-4">
        Start with a spec. Ship with confidence.
      </h2>
      <p className="text-stone-500 mb-8 max-w-lg mx-auto leading-relaxed">
        Generate your SPEC.md free — no account needed. Then run the full SDD workflow
        inside Conduct to scaffold, enforce, and ship spec-compliant code.
      </p>
      <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
        <a
          href="#try"
          className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-6 py-3 text-sm font-semibold text-white hover:bg-indigo-700 transition-colors"
        >
          Generate SPEC.md free →
        </a>
        <a
          href="/dashboard"
          className="inline-flex items-center gap-2 rounded-xl border border-stone-200 bg-white px-6 py-3 text-sm font-semibold text-stone-700 hover:border-stone-300 hover:shadow-sm transition-all"
        >
          Sign in to Conduct →
        </a>
        <a
          href="/marketplace"
          className="inline-flex items-center gap-2 rounded-xl border border-stone-200 bg-white px-6 py-3 text-sm font-semibold text-stone-700 hover:border-stone-300 hover:shadow-sm transition-all"
        >
          Browse playbooks →
        </a>
      </div>
    </section>
  )
}

/* ─── Page footer ──────────────────────────────────────────────────────── */

function PageFooter() {
  return (
    <footer className="border-t border-stone-100 py-8 text-center text-xs text-stone-400 space-y-2">
      <div className="flex items-center justify-center gap-3 flex-wrap">
        <span>© {new Date().getFullYear()} Conduct</span>
        <span>·</span>
        <a href="https://github.com/sseshachala/conductai" target="_blank" rel="noopener noreferrer" className="hover:text-stone-600 transition-colors">GitHub</a>
        <span>·</span>
        <a href="/" className="hover:text-stone-600 transition-colors">Conduct AI</a>
        <span>·</span>
        <a href="/marketplace" className="hover:text-stone-600 transition-colors">Agent Templates</a>
        <span>·</span>
        <a href="/tools" className="hover:text-stone-600 transition-colors">Tools</a>
        <span>·</span>
        <a href="/docs" className="hover:text-stone-600 transition-colors">Docs</a>
        <span>·</span>
        <a href="/about" className="hover:text-stone-600 transition-colors">About</a>
        <span>·</span>
        <a href="/privacy" className="hover:text-stone-600 transition-colors">Privacy</a>
        <span>·</span>
        <a href="/terms" className="hover:text-stone-600 transition-colors">Terms</a>
      </div>
      <p className="text-stone-300">Envisioned, designed and developed with love from Houston</p>
    </footer>
  )
}
