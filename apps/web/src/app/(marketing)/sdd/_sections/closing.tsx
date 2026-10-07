/* ─── Enforcement ──────────────────────────────────────────────────────── */

export function EnforcementSection() {
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
          Conduct does, at the git hook level.
        </p>

        <div className="grid sm:grid-cols-2 gap-5 mb-8">
          <div className="rounded-2xl border border-stone-700 bg-stone-800 px-7 py-6">
            <p className="text-xs font-bold text-stone-500 uppercase tracking-widest mb-4">Without Conduct</p>
            <div className="rounded-xl bg-stone-950 px-5 py-4 font-mono text-xs space-y-2">
              <p className="text-stone-500"># git push, no checks</p>
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
              <p className="text-stone-500"># git push, hook runs</p>
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
            The pre-merge hook lives in <code className="font-mono text-indigo-400 bg-stone-900 px-1.5 py-0.5 rounded">.conduct/hooks/pre-merge</code>, git-native, no external service required to enforce. If a team leaves Conduct, their spec and traceability data stay in the repo.
          </p>
        </div>
      </div>
    </section>
  )
}

/* ─── Sync ─────────────────────────────────────────────────────────────── */

export function SyncSection() {
  return (
    <section className="px-6 py-20">
      <div className="max-w-5xl mx-auto">
        <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest text-center mb-3">Tracker sync</p>
        <h2 className="text-3xl font-bold text-stone-900 text-center mb-4">
          FR numbers connect everything.
        </h2>
        <p className="text-center text-stone-500 text-sm max-w-2xl mx-auto mb-14">
          One number traces a requirement from SPEC.md through Jira, the test file, the commit,
          and the PR. Sync with GitHub, Jira, or Linear, bidirectionally.
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

export function WhyNotChatGPTSection() {
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
                "No FR numbers, just prose",
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
                "SPEC.md committed to git, versioned forever",
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

export function ComparisonSection() {
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
            ["Requirements in version control", "No", "Yes. SPEC.md in git"],
            ["FR numbers in code", "Convention only", "Enforced by hook"],
            ["Block PR with no spec reference", "No", "Yes"],
            ["Sync FRs to Jira / Linear", "Manual copy-paste", "Automated bidirectional"],
            ["Detect spec drift weekly", "No", "Yes, sdd-drift-check"],
            ["AI agents respect requirements", "No", "Yes. AGENTS.md + gate"],
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

export function FooterCTASection() {
  return (
    <section className="px-6 py-20 text-center">
      <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-4">Get started</p>
      <h2 className="text-3xl font-bold text-stone-900 mb-4">
        Start with a spec. Ship with confidence.
      </h2>
      <p className="text-stone-500 mb-8 max-w-lg mx-auto leading-relaxed">
        Generate your SPEC.md free, no account needed. Then run the full SDD workflow
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
          href="/packs"
          className="inline-flex items-center gap-2 rounded-xl border border-stone-200 bg-white px-6 py-3 text-sm font-semibold text-stone-700 hover:border-stone-300 hover:shadow-sm transition-all"
        >
          Browse playbooks →
        </a>
      </div>
    </section>
  )
}

/* ─── Page footer ──────────────────────────────────────────────────────── */


export function TeamOSBridge() {
  return (
    <section className="bg-stone-50 border-t border-stone-100 py-12 px-6">
      <div className="max-w-4xl mx-auto flex flex-col sm:flex-row items-center gap-6 rounded-2xl border border-stone-200 bg-white p-8">
        <div className="text-3xl shrink-0">📄</div>
        <div className="flex-1 text-center sm:text-left">
          <p className="text-xs font-bold uppercase tracking-widest text-stone-400 mb-1">Before you spec</p>
          <h3 className="font-bold text-stone-900 text-lg mb-1">Set the quality bar with Team OS</h3>
          <p className="text-sm text-stone-500 leading-relaxed">
            SDD gives every agent a <em>why</em>. Team OS gives every agent your <em>standards</em> — the auth patterns, security rules, and review checklist agents check before declaring work done.
          </p>
        </div>
        <a href="/team-os" className="shrink-0 rounded-xl border border-stone-200 bg-white px-5 py-2.5 text-sm font-semibold text-stone-700 hover:border-stone-400 hover:shadow-sm transition-all whitespace-nowrap">
          Get Team OS →
        </a>
      </div>
    </section>
  )
}
