"use client"

import { useState } from "react"

/* ─── Use Cases ────────────────────────────────────────────────────────── */

const USE_CASES = [
  {
    title: "Running an agent from the terminal",
    scenario:
      "You want to run the \u201cgithub-pr-review\u201d agent on a new PR without opening the browser.",
    without: {
      label: "Without CLI",
      steps: [
        "Open browser and navigate to Conduct",
        "Find the agent, fill in params, click Run",
        "Wait for the browser to show output",
      ],
      cost: "2 minutes of context-switching",
      color: "text-red-600",
      bg: "bg-red-50 border-red-200",
    },
    with: {
      label: "With conduct-cli",
      steps: [
        "conduct run github-pr-review --pr 142",
        "Agent fires immediately from the terminal",
        "Live output streams to your terminal, done",
      ],
      cost: "8 seconds from idea to result",
      color: "text-emerald-600",
      bg: "bg-emerald-50 border-emerald-200",
    },
    saving: "2 min \u2192 8 sec",
  },
  {
    title: "Enforcing AI policies across the team",
    scenario:
      "Your security lead sets a policy: Claude must not write to production config files.",
    without: {
      label: "Without Guard",
      steps: [
        "Policy lives in a doc no one reads",
        "Violations happen silently in developers\u2019 terminals",
        "No audit trail, no visibility for the team lead",
      ],
      cost: "0 violations caught",
      color: "text-red-600",
      bg: "bg-red-50 border-red-200",
    },
    with: {
      label: "With ConductGuard MCP",
      steps: [
        "Every file-write tool call Claude makes is checked against the policy",
        "Blocked calls are logged with who, what, and when",
        "Manager sees violations in the Guard Insights dashboard",
      ],
      cost: "0 violations slip through",
      color: "text-emerald-600",
      bg: "bg-emerald-50 border-emerald-200",
    },
    saving: "0 violations slip through",
  },
  {
    title: "Switching workspaces",
    scenario:
      "You work across a staging and production workspace. You need to switch contexts and run agents against staging.",
    without: {
      label: "Without CLI",
      steps: [
        "Edit ~/.conduct/config.json manually",
        "Edit ~/.conductguard/config.json manually",
        "Restart MCP server, hope you got both right",
      ],
      cost: "5 manual steps, easy to miss one",
      color: "text-red-600",
      bg: "bg-red-50 border-red-200",
    },
    with: {
      label: "With conduct switch",
      steps: [
        "conduct switch staging",
        "Both configs updated atomically",
        "Guard policies re-synced to the new workspace instantly",
      ],
      cost: "One command, always consistent",
      color: "text-emerald-600",
      bg: "bg-emerald-50 border-emerald-200",
    },
    saving: "5 steps \u2192 1 command",
  },
  {
    title: "Knowing who you are",
    scenario:
      "You forget which workspace your terminal is pointed at before running a destructive agent.",
    without: {
      label: "Without CLI",
      steps: [
        "Check two separate config files",
        "Cross-reference workspace IDs manually",
        "Still not sure if Guard is actually wired",
      ],
      cost: "Uncertainty before every run",
      color: "text-red-600",
      bg: "bg-red-50 border-red-200",
    },
    with: {
      label: "With conduct whoami",
      steps: [
        "conduct whoami",
        "Shows workspace name, server, Guard status (hook wired + policy count)",
        "Booster status included \u2014 full picture in one command",
      ],
      cost: "Instant context, zero doubt",
      color: "text-emerald-600",
      bg: "bg-emerald-50 border-emerald-200",
    },
    saving: "instant context check",
  },
] as const

export function UseCasesSection() {
  const [active, setActive] = useState<number>(0)
  const uc = USE_CASES[active]

  return (
    <section className="px-6 py-20">
      <div className="max-w-5xl mx-auto">
        <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest text-center mb-3">
          Example use cases
        </p>
        <h2 className="text-3xl font-bold text-stone-900 text-center mb-4">
          See the difference on real tasks.
        </h2>
        <p className="text-center text-stone-500 text-sm max-w-xl mx-auto mb-10">
          These are actual patterns from everyday development workflows &mdash; not synthetic
          demos.
        </p>

        {/* Tab selector */}
        <div className="flex flex-wrap gap-2 justify-center mb-10">
          {USE_CASES.map((u, i) => (
            <button
              key={i}
              onClick={() => setActive(i)}
              className={`rounded-full px-4 py-2 text-xs font-semibold transition-all border ${
                active === i
                  ? "bg-indigo-600 text-white border-indigo-600"
                  : "bg-white text-stone-600 border-stone-200 hover:border-stone-300"
              }`}
            >
              {u.title}
            </button>
          ))}
        </div>

        {/* Active case */}
        <div className="rounded-2xl border border-stone-200 bg-white overflow-hidden">
          {/* Header */}
          <div className="px-8 py-6 border-b border-stone-100 flex items-start justify-between gap-4">
            <div>
              <p className="text-lg font-bold text-stone-900 mb-1">{uc.title}</p>
              <p className="text-sm text-stone-500">{uc.scenario}</p>
            </div>
            <div className="shrink-0 text-right">
              <p className="text-base font-black text-indigo-600 whitespace-nowrap">{uc.saving}</p>
              <p className="text-xs text-stone-400 mt-0.5">time saved</p>
            </div>
          </div>

          {/* Comparison */}
          <div className="grid sm:grid-cols-2 divide-y sm:divide-y-0 sm:divide-x divide-stone-100">
            {[uc.without, uc.with].map((side) => (
              <div key={side.label} className="px-8 py-7 flex flex-col gap-4">
                <p
                  className={`text-xs font-bold uppercase tracking-widest ${side.color}`}
                >
                  {side.label}
                </p>
                <ul className="space-y-2.5">
                  {side.steps.map((step, i) => (
                    <li
                      key={i}
                      className="flex items-start gap-2.5 text-sm text-stone-600"
                    >
                      <span
                        className={`mt-0.5 w-4 h-4 rounded-full border flex items-center justify-center shrink-0 text-[10px] font-bold ${side.bg} ${side.color}`}
                      >
                        {side === uc.with ? "✓" : "✕"}
                      </span>
                      {step}
                    </li>
                  ))}
                </ul>
                <div className="mt-auto pt-4 border-t border-stone-100">
                  <p className={`text-sm font-semibold ${side.color}`}>{side.cost}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  )
}

/* ─── Guard Insights Callout ───────────────────────────────────────────── */

export function GuardInsightsCallout() {
  return (
    <section className="bg-stone-900 px-6 py-20">
      <div className="max-w-3xl mx-auto">
        <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest text-center mb-3">
          Guard Insights
        </p>
        <h2 className="text-3xl font-bold text-white text-center mb-8">
          See what every developer&apos;s AI is doing.
        </h2>

        <div className="flex flex-col gap-3 mb-10">
          {[
            "Every blocked tool call logged with who, what, and when",
            "Coverage table: which developers have Guard wired",
            "Events feed: real-time stream of policy enforcement",
            "OWASP Agentic Top 10 mapping via conduct verify — use in CI with --strict",
            "Advisory mode: log-all, block-nothing governance for gradual rollouts",
            "Hash-chain audit log: tamper-evident, cryptographically linked events",
          ].map((point) => (
            <div
              key={point}
              className="rounded-2xl border border-stone-700 bg-stone-800 px-6 py-4 flex items-start gap-3"
            >
              <span className="mt-0.5 w-4 h-4 rounded-full bg-indigo-900 border border-indigo-600 text-indigo-400 flex items-center justify-center shrink-0 text-[10px] font-bold">
                ✓
              </span>
              <p className="text-sm text-stone-300 leading-relaxed">{point}</p>
            </div>
          ))}
        </div>

        <div className="text-center">
          <a
            href="/guard"
            className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-6 py-3 text-sm font-semibold text-white hover:bg-indigo-700 transition-colors"
          >
            Open Guard Insights &rarr;
          </a>
        </div>
      </div>
    </section>
  )
}
