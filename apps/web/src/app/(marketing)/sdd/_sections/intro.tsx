/* ─── Hero ─────────────────────────────────────────────────────────────── */

export function HeroSection() {
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

export function ProblemSection() {
  return (
    <section className="bg-stone-50 px-6 py-20">
      <div className="max-w-5xl mx-auto">
        <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest text-center mb-3">The problem</p>
        <h2 className="text-3xl font-bold text-stone-900 text-center mb-4">
          AI coding tools write code.<br />They don&apos;t know <em>why</em>.
        </h2>
        <p className="text-center text-stone-500 text-sm max-w-2xl mx-auto mb-14">
          The faster AI writes, the faster requirements drift. By the time you notice, the code
          doesn&apos;t match the intent, and there&apos;s no audit trail to explain what happened.
        </p>

        <div className="grid sm:grid-cols-3 gap-6">
          {[
            {
              icon: "⇌",
              title: "AI drift",
              desc: "The AI interprets your prompt, not your requirements. Each session it starts fresh, no memory of what FR-001 actually meant last week.",
              border: "border-red-100",
            },
            {
              icon: "∅",
              title: "No traceability",
              desc: "Which lines of code map to which decision? Nobody knows. A refactor breaks something, but nothing links the broken code back to a requirement.",
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

export function PrincipleSection() {
  return (
    <section className="px-6 py-20">
      <div className="max-w-4xl mx-auto">
        <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest text-center mb-3">The principle</p>
        <h2 className="text-3xl font-bold text-stone-900 text-center mb-6">
          SPEC.md is the contract.
        </h2>
        <p className="text-center text-stone-500 text-sm max-w-2xl mx-auto mb-14">
          Every requirement gets a number. Every line of code traces back to one.
          The spec lives in your repo, git-versioned, human-readable, owned by your team.
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

export function WorkflowSection() {
  return (
    <section id="workflow" className="bg-stone-50 px-6 py-20">
      <div className="max-w-5xl mx-auto">
        <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest text-center mb-3">The workflow</p>
        <h2 className="text-3xl font-bold text-stone-900 text-center mb-4">
          From idea to shipped code, with full traceability.
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
              desc: "Reads your SPEC.md and commits 6 files in one push: AGENTS.md, DESIGN.md, PLAN.md, SPRINT.md, CLAUDE.md, and .conduct/spec-index.json, the machine-readable FR index that powers everything downstream.",
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
