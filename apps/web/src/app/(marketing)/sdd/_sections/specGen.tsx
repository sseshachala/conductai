"use client"

import { apiUrl } from "@/lib/auth/runtime"
import { useState } from "react"
import { MarkdownViewer, type Question, type ScaffoldFile, type ScaffoldStage, type Stage } from "./specGenViewer"

export function SpecGenSection() {
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

  const base = apiUrl() ?? ""

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
        setErrorMsg(body?.detail ?? "Generation failed, please try again.")
        setStage("error")
        return
      }
      const data = await res.json()
      setSpec(data.spec)
      setTimeout(() => setStage("output"), 300)
    } catch {
      clearInterval(iv)
      setErrorMsg("Could not reach the server, check your connection.")
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
          No account needed. Describe what you&apos;re building, get a structured spec in ~20 seconds.
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

            {/* Stage 1. Input */}
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
                  <p className="text-xs text-stone-400">Notion, Confluence, GitHub Epic, agent extracts and normalises</p>
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

            {/* Stage 1b. Asking (loading questions) */}
            {stage === "asking" && (
              <div className="flex flex-col items-center gap-4 py-8">
                <span className="text-2xl animate-spin inline-block text-indigo-400">◈</span>
                <p className="text-sm text-stone-500">Analysing your description…</p>
              </div>
            )}

            {/* Stage 2. Clarify (dynamic questions) */}
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

            {/* Stage 2b. Generating */}
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

            {/* Stage. Error */}
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

            {/* Stage 3. Output */}
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
                      <p className="text-xs text-stone-500">Generates AGENTS.md, DESIGN.md, PLAN.md, SPRINT.md, CLAUDE.md + spec-index.json, free, no login.</p>
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
