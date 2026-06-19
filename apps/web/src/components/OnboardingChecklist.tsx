"use client"

import { useEffect, useState } from "react"
import Link from "next/link"

const DISMISS_KEY = "conduct_onboarding_dismissed"

interface Step {
  id: string
  label: string
  detail: string
  cta: string
  href: string
  done: boolean
}

interface Props {
  hasProject: boolean
  getToken: (() => Promise<string | null>) | null
  // P2-5: optional callback to trigger new project modal in-page instead of navigating
  onNewProject?: () => void
}

export default function OnboardingChecklist({ hasProject, getToken, onNewProject }: Props) {
  const [dismissed, setDismissed] = useState(true) // start hidden; reveal after check
  const [hasEnv, setHasEnv] = useState(false)
  const [hasAgent, setHasAgent] = useState(false)
  const [hasRun, setHasRun] = useState(false)
  const [loaded, setLoaded] = useState(false)

  useEffect(() => {
    if (typeof window !== "undefined" && localStorage.getItem(DISMISS_KEY)) return
    setDismissed(false)
  }, [])

  useEffect(() => {
    if (dismissed) return
    async function load() {
      const headers: Record<string, string> = {}
      if (getToken) {
        const token = await getToken()
        if (token) headers["Authorization"] = `Bearer ${token}`
      }
      const base = process.env.NEXT_PUBLIC_API_URL
      const [envRes, wfRes, runRes] = await Promise.allSettled([
        fetch(`${base}/environments`, { headers }),
        fetch(`${base}/workflows`, { headers }),
        fetch(`${base}/runs`, { headers }),
      ])
      if (envRes.status === "fulfilled" && envRes.value.ok) {
        const envs = await envRes.value.json()
        setHasEnv(Array.isArray(envs) && envs.length > 0)
      }
      if (wfRes.status === "fulfilled" && wfRes.value.ok) {
        const wfs = await wfRes.value.json()
        setHasAgent(Array.isArray(wfs) && wfs.length > 0)
      }
      if (runRes.status === "fulfilled" && runRes.value.ok) {
        const runs = await runRes.value.json()
        setHasRun(Array.isArray(runs) && runs.length > 0)
      }
      setLoaded(true)
    }
    load()
  }, [dismissed, getToken])

  function dismiss() {
    localStorage.setItem(DISMISS_KEY, "1")
    setDismissed(true)
  }

  const steps: Step[] = [
    {
      id: "project",
      label: "Create a project",
      detail: "A project groups your agents and credentials. One project per repo or team.",
      cta: "New project",
      href: "/projects",
      done: hasProject,
    },
    {
      id: "env",
      label: "Add an environment",
      detail: "An environment holds your API keys (GitHub, Slack). Create one in Settings → Environments.",
      cta: "Go to Settings",
      href: "/settings",
      done: hasEnv,
    },
    {
      id: "agent",
      label: "Create your first agent",
      detail: "Pick a template — Autopilot is a good start. It pre-wires a GitHub trigger and a Slack approval gate.",
      cta: "Choose template",
      href: "/workflows/new",
      done: hasAgent,
    },
    {
      id: "run",
      label: "Run the agent",
      detail: "Open the agent canvas, assign your environment from the dropdown, then hit ▶ Run.",
      cta: "View agents",
      href: "/workflows",
      done: hasRun,
    },
  ]

  const completedCount = steps.filter(s => s.done).length
  const allDone = completedCount === steps.length

  if (dismissed || !loaded) return null

  return (
    <div className="mb-8 rounded-2xl border border-stone-200 bg-white overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-4 border-b border-stone-100">
        <div>
          <p className="text-sm font-semibold text-stone-900">
            {allDone ? "You're all set 🎉" : "Get started with Conduct"}
          </p>
          <p className="text-xs text-stone-400 mt-0.5">
            {allDone
              ? "All steps complete — your first agent is ready to run."
              : `${completedCount} of ${steps.length} steps done`}
          </p>
        </div>
        <button
          onClick={dismiss}
          className="text-stone-300 hover:text-stone-500 transition-colors text-lg leading-none"
          title="Dismiss"
        >
          ×
        </button>
      </div>

      {/* Progress bar */}
      <div className="h-1 bg-stone-100">
        <div
          className="h-1 bg-stone-900 transition-all duration-500"
          style={{ width: `${(completedCount / steps.length) * 100}%` }}
        />
      </div>

      {/* Steps */}
      <ol className="divide-y divide-stone-100">
        {steps.map((step, i) => (
          <li key={step.id} className={`flex items-start gap-4 px-5 py-4 ${step.done ? "opacity-50" : ""}`}>
            {/* Step indicator */}
            <div className={`mt-0.5 w-5 h-5 rounded-full flex items-center justify-center shrink-0 text-[10px] font-bold ${
              step.done
                ? "bg-stone-900 text-white"
                : "border-2 border-stone-200 text-stone-400"
            }`}>
              {step.done ? "✓" : i + 1}
            </div>

            {/* Text */}
            <div className="flex-1 min-w-0">
              <p className={`text-sm font-medium ${step.done ? "line-through text-stone-400" : "text-stone-900"}`}>
                {step.label}
              </p>
              {!step.done && (
                <p className="text-xs text-stone-400 mt-0.5 leading-relaxed">{step.detail}</p>
              )}
            </div>

            {/* CTA — P2-5: "Create a project" triggers onNewProject modal when on /projects */}
            {!step.done && (
              step.id === "project" && onNewProject ? (
                <button
                  onClick={onNewProject}
                  className="shrink-0 text-xs font-medium text-stone-900 border border-stone-200 hover:bg-stone-50 px-3 py-1.5 rounded-lg transition-colors"
                >
                  {step.cta} →
                </button>
              ) : (
                <Link
                  href={step.href}
                  className="shrink-0 text-xs font-medium text-stone-900 border border-stone-200 hover:bg-stone-50 px-3 py-1.5 rounded-lg transition-colors"
                >
                  {step.cta} →
                </Link>
              )
            )}
          </li>
        ))}
      </ol>

      {allDone && (
        <div className="px-5 py-3 bg-stone-50 flex items-center justify-between">
          <p className="text-xs text-stone-500">Head to your agents and hit ▶ Run to see it work.</p>
          <button onClick={dismiss} className="text-xs font-medium text-stone-700 hover:text-stone-900 transition-colors">
            Dismiss →
          </button>
        </div>
      )}
    </div>
  )
}
