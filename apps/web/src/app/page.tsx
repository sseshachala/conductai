"use client"

import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import { useAuth, SignInButton } from "@clerk/nextjs"
import BlogSection from "@/components/BlogSection"
import BlogErrorBoundary from "@/components/BlogErrorBoundary"

export default function Home() {
  return <LandingPage />
}

function LandingPage() {
  const clerkEnabled = !!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY
  if (clerkEnabled) return <LandingPageWithAuth />
  return <LandingPageContent isSignedIn={false} isLoaded={true} />
}

function LandingPageWithAuth() {
  const { isSignedIn, isLoaded } = useAuth()
  return <LandingPageContent isSignedIn={!!isSignedIn} isLoaded={isLoaded} />
}

function LandingPageContent({ isSignedIn, isLoaded }: { isSignedIn: boolean; isLoaded: boolean }) {
  const router = useRouter()
  const clerkEnabled = !!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY

  // Single source of truth for the playbook count — fetched from the same
  // endpoint the Marketplace uses, so marketing copy never drifts from the
  // registry. Falls back to the default if the API is unreachable.
  const [playbookCount, setPlaybookCount] = useState(18)
  useEffect(() => {
    fetch(`${process.env.NEXT_PUBLIC_API_URL}/workflows/playbooks`)
      .then(r => (r.ok ? r.json() : []))
      .then((pbs: unknown[]) => {
        if (Array.isArray(pbs) && pbs.length > 0) setPlaybookCount(pbs.length)
      })
      .catch(() => {})
  }, [])

  return (
    <div className="min-h-screen bg-white flex flex-col">

      {/* Nav */}
      <header className="px-6 py-5 flex items-center justify-between max-w-6xl mx-auto w-full">
        <div className="flex items-center">
          <img src="/logo.png" alt="Conduct AI" className="h-10 w-auto" />
        </div>
        <div className="flex items-center gap-4">
          <a
            href="/marketplace"
            className="flex items-center gap-1.5 text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors"
          >
            Playbooks
          </a>
          <a
            href="/tools"
            className="flex items-center gap-1.5 text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors"
          >
            Tools
          </a>
          <a
            href="/benchmark"
            className="flex items-center gap-1.5 text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors"
          >
            Benchmark
          </a>
          <a
            href="/eval"
            className="flex items-center gap-1.5 text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors"
          >
            Quality
          </a>
          <a
            href="/compare"
            className="flex items-center gap-1.5 text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors"
          >
            Compare
          </a>
          <a
            href="/docs"
            className="flex items-center gap-1.5 text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors"
          >
            Docs
          </a>
          <a
            href="https://narratr.ai/blog/conductai"
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1.5 text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors"
          >
            Blog
          </a>
          <a
            href="https://github.com/sseshachala/conductai/discussions/new?category=ideas"
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1.5 text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors"
          >
            💡 Request an idea
          </a>
          <a
            href="https://github.com/sseshachala/conductai"
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1.5 text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors"
          >
            <GitHubIcon />
            Star on GitHub
          </a>
          {isLoaded && (
            isSignedIn ? (
              <button
                onClick={() => router.push("/dashboard")}
                className="text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors"
              >
                Open app →
              </button>
            ) : clerkEnabled ? (
              <SignInButton mode="modal">
                <button className="text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">
                  Sign in →
                </button>
              </SignInButton>
            ) : null
          )}
        </div>
      </header>

      {/* Hero */}
      <section className="flex-1 flex flex-col items-center justify-center px-6 pt-16 pb-24 text-center">
        <div className="inline-flex items-center gap-2 bg-stone-100 text-stone-600 text-xs font-medium px-3 py-1.5 rounded-full mb-8">
          <span className="w-1.5 h-1.5 rounded-full bg-green-500 inline-block" />
          Now in early access — sign in to try it free
        </div>

        <h1 className="text-5xl sm:text-6xl font-bold text-stone-900 leading-[1.1] tracking-tight max-w-3xl">
          AI agents for the work<br />
          <span className="text-indigo-600">around code.</span>
        </h1>

        <p className="mt-6 text-xl text-stone-500 max-w-2xl leading-relaxed">
          Conduct turns tickets, PRs, alerts, and incidents into auditable AI agent workflows.
          Install a playbook, connect your tools, and let agents triage, review, patch, and
          notify with human approval before anything ships.
        </p>

        <div className="mt-10 flex flex-col sm:flex-row items-center gap-4">
          {isLoaded && (
            isSignedIn ? (
              <button
                onClick={() => router.push("/dashboard")}
                className="inline-flex items-center gap-2 bg-stone-900 hover:bg-stone-700 text-white font-semibold px-7 py-3.5 rounded-xl text-sm transition-colors shadow-sm"
              >
                Open app →
              </button>
            ) : clerkEnabled ? (
              <SignInButton mode="modal">
                <button className="inline-flex items-center gap-3 bg-stone-900 hover:bg-stone-700 text-white font-semibold px-7 py-3.5 rounded-xl text-sm transition-colors shadow-sm">
                  Sign in — it&apos;s free
                </button>
              </SignInButton>
            ) : null
          )}
          {isLoaded && !isSignedIn && clerkEnabled && (
            <p className="text-xs text-stone-400">No credit card · Connect your existing tools · Sign in with Google, GitHub, or Microsoft</p>
          )}
        </div>

        {/* Post-sign-in next steps — only shown when signed in */}
        {isLoaded && isSignedIn && (
          <div className="mt-8 bg-stone-50 border border-stone-200 rounded-2xl px-6 py-5 max-w-md w-full text-left">
            <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-3">Get started in 3 steps</p>
            <ol className="space-y-2.5">
              {[
                { n: "1", text: "Create a project and connect your GitHub repo" },
                { n: "2", text: "Browse the Playbook Marketplace and install an agent in one click" },
                { n: "3", text: "Add your credentials in Settings → Environments, then hit Run" },
              ].map(({ n, text }) => (
                <li key={n} className="flex items-start gap-3 text-sm text-stone-600">
                  <span className="w-5 h-5 rounded-full bg-stone-900 text-white text-[10px] font-bold flex items-center justify-center shrink-0 mt-0.5">{n}</span>
                  {text}
                </li>
              ))}
            </ol>
            <button
              onClick={() => router.push("/dashboard")}
              className="mt-4 text-sm font-medium text-stone-900 hover:text-stone-600 transition-colors"
            >
              Go to Projects →
            </button>
          </div>
        )}
      </section>

      {/* Audience */}
      <section className="px-6 py-14">
        <div className="max-w-4xl mx-auto">
          <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest text-center mb-2">Built for</p>
          <p className="text-center text-stone-500 text-sm mb-8">From solo builders to growing engineering teams.</p>
          <div className="grid sm:grid-cols-4 gap-4">
            {[
              {
                icon: "⚡",
                label: "Solo builders",
                tag: "Solo",
                desc: "Turn repeated engineering chores into reusable playbooks without building agent infrastructure.",
                accent: "from-amber-50 to-orange-50 border-amber-200",
                iconBg: "bg-amber-100 text-amber-600",
              },
              {
                icon: "🚀",
                label: "Teams of 2–5",
                tag: "Early-stage",
                desc: "Every engineer counts. Let agents pick up tickets, review PRs, and triage issues overnight.",
                accent: "from-violet-50 to-indigo-50 border-violet-200",
                iconBg: "bg-violet-100 text-violet-600",
              },
              {
                icon: "🔥",
                label: "Teams of 5–10",
                tag: "Growing",
                desc: "Drowning in issues and incident triage? Agents run 24/7 so your team can focus on features.",
                accent: "from-blue-50 to-sky-50 border-blue-200",
                iconBg: "bg-blue-100 text-blue-600",
              },
              {
                icon: "🏗️",
                label: "Teams of 10–15",
                tag: "Scaling",
                desc: "Consistent process across the team without adding headcount. Every workflow audited and gated.",
                accent: "from-emerald-50 to-teal-50 border-emerald-200",
                iconBg: "bg-emerald-100 text-emerald-600",
              },
            ].map(({ icon, label, tag, desc, accent, iconBg }) => (
              <div key={label} className={`rounded-2xl border bg-gradient-to-br ${accent} px-5 py-5 flex flex-col gap-3`}>
                <div className="flex items-center justify-between">
                  <span className={`w-9 h-9 rounded-xl flex items-center justify-center text-lg ${iconBg}`}>{icon}</span>
                  <span className="text-[10px] font-semibold text-stone-400 uppercase tracking-wider">{tag}</span>
                </div>
                <div>
                  <p className="text-sm font-bold text-stone-900 mb-1">{label}</p>
                  <p className="text-xs text-stone-500 leading-relaxed">{desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Trust strip */}
      <div className="border-y border-stone-100 bg-stone-50 py-4 px-6">
        <div className="max-w-4xl mx-auto flex flex-wrap items-center justify-center gap-6 text-xs font-medium text-stone-500">
          <span className="flex items-center gap-1.5"><span className="w-1.5 h-1.5 rounded-full bg-emerald-400 inline-block"/>{playbookCount} ready-made agents</span>
          <span className="flex items-center gap-1.5"><span className="w-1.5 h-1.5 rounded-full bg-emerald-400 inline-block"/>Verified playbooks</span>
          <span className="flex items-center gap-1.5"><span className="w-1.5 h-1.5 rounded-full bg-emerald-400 inline-block"/>Human approval on every merge</span>
          <span className="flex items-center gap-1.5"><span className="w-1.5 h-1.5 rounded-full bg-emerald-400 inline-block"/>RBAC — admin, editor, viewer</span>
          <span className="flex items-center gap-1.5"><span className="w-1.5 h-1.5 rounded-full bg-emerald-400 inline-block"/>Auto model routing — Haiku to Opus</span>
          <span className="flex items-center gap-1.5"><span className="w-1.5 h-1.5 rounded-full bg-emerald-400 inline-block"/>Hard cap enforcement per developer</span>
          <span className="flex items-center gap-1.5"><span className="w-1.5 h-1.5 rounded-full bg-emerald-400 inline-block"/>MIT licensed</span>
        </div>
      </div>

      {/* Autonomous execution. Human control. */}
      <section className="px-6 py-14">
        <div className="max-w-3xl mx-auto rounded-2xl bg-stone-900 px-10 py-10 flex flex-col sm:flex-row items-center justify-between gap-6">
          <div>
            <p className="text-white text-xl font-bold mb-2">Autonomous execution. Human control.</p>
            <p className="text-stone-400 text-sm leading-relaxed max-w-md">
              Conduct agents act — they write code, open PRs, post to Slack — but nothing merges without your explicit approval. The agent does the work. You stay in charge.
            </p>
            <p className="text-stone-500 text-xs leading-relaxed max-w-md mt-3">
              Your team lead sets spending limits, blocked actions, and approved tools in ConductGuard — one policy for the whole team, automatically applied to every workflow and every developer&apos;s environment.
            </p>
          </div>
          <div className="flex flex-col gap-2 shrink-0 text-sm">
            <div className="flex items-center gap-2 text-stone-300"><span className="text-emerald-400">✓</span> Executes tasks, not suggestions</div>
            <div className="flex items-center gap-2 text-stone-300"><span className="text-emerald-400">✓</span> Pauses for human approval</div>
            <div className="flex items-center gap-2 text-stone-300"><span className="text-emerald-400">✓</span> Full audit trail, every run</div>
            <div className="flex items-center gap-2 text-stone-300"><span className="text-emerald-400">✓</span> Team policies enforced via Guard</div>
          </div>
        </div>
      </section>

      {/* Templates */}
      <section className="px-6 py-20">
        <div className="max-w-6xl mx-auto">
          <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest text-center mb-3">Playbook Marketplace</p>
          <h2 className="text-3xl font-bold text-stone-900 text-center mb-4">
            One click to install.<br />Running in minutes.
          </h2>
          <p className="text-center text-stone-500 text-sm max-w-xl mx-auto mb-12">
            {playbookCount} pre-built agent playbooks across 10 categories — browse, install, configure your credentials, and run. Already installed playbooks are tracked so you never duplicate. No blank canvas required.
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5 mb-8">
            {TEMPLATES.map(t => (
              <div key={t.name} className="bg-white rounded-2xl border border-stone-200 p-6 flex flex-col gap-3">
                <div className="flex items-start justify-between gap-2">
                  <span className="text-2xl">{t.icon}</span>
                  <span className="text-[10px] font-semibold uppercase tracking-wide text-stone-400 bg-stone-100 px-2 py-0.5 rounded-full mt-1">{t.trigger}</span>
                </div>
                <div>
                  <p className="font-semibold text-stone-900 mb-1">{t.name}</p>
                  <p className="text-sm text-stone-500 leading-relaxed">{t.what}</p>
                </div>
                <div className="mt-auto pt-3 border-t border-stone-100">
                  <p className="text-xs text-stone-400 italic leading-relaxed">{t.scenario}</p>
                </div>
              </div>
            ))}
          </div>
          <div className="text-center">
            <a
              href="/marketplace"
              className="inline-flex items-center gap-2 rounded-xl border border-stone-200 bg-white px-6 py-3 text-sm font-medium text-stone-700 hover:border-stone-300 hover:shadow-sm transition-all"
            >
              📦 Browse all {playbookCount} playbooks in the Marketplace →
            </a>
          </div>
        </div>
      </section>

      {/* 3-step setup */}
      <section className="bg-stone-50 px-6 py-20">
        <div className="max-w-4xl mx-auto">
          <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest text-center mb-3">Setup in minutes</p>
          <h2 className="text-2xl font-bold text-stone-900 text-center mb-12">Live on day one.</h2>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-6">
            {[
              { step: "1", icon: "🔗", title: "Connect your repo", body: "Link GitHub, GitLab, or Bitbucket. Add Slack, Linear, and your API keys. No migration, no new tooling — Conduct wraps around what you already use." },
              { step: "2", icon: "📦", title: "Install from the Marketplace", body: `Browse ${playbookCount} pre-built playbooks, click Install — canvas is pre-wired. Add credentials and the agent is ready to run.` },
              { step: "3", icon: "✅", title: "Get output in Slack", body: "PRs, diagnoses, triage comments, changelogs — delivered to Slack. Approve or reject with one click." },
            ].map(s => (
              <div key={s.step} className="bg-white rounded-2xl border border-stone-200 p-6 text-center">
                <div className="text-3xl mb-3">{s.icon}</div>
                <div className="text-xs font-bold text-stone-400 uppercase tracking-widest mb-2">Step {s.step}</div>
                <p className="font-semibold text-stone-900 mb-2">{s.title}</p>
                <p className="text-sm text-stone-500 leading-relaxed">{s.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Social proof */}
      <section className="px-6 py-16">
        <div className="max-w-3xl mx-auto">
          <div className="rounded-2xl border border-stone-200 bg-white p-8">
            <p className="text-stone-700 text-lg leading-relaxed mb-5">
              &ldquo;Labeled a bug at 5pm on a Friday. PR was open by 5:02pm, tests green, ready to review Monday morning. That&apos;s the thing — it just works while we&apos;re not watching.&rdquo;
            </p>
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-full bg-indigo-100 flex items-center justify-center text-indigo-700 text-xs font-bold">E</div>
              <div>
                <p className="text-sm font-semibold text-stone-900">Engineering Lead</p>
                <p className="text-xs text-stone-400">Series B startup, 35-person eng team</p>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Copilot / AI coding tools orchestration */}
      <section className="bg-stone-900 px-6 py-20">
        <div className="max-w-4xl mx-auto text-center">
          <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-4">Works with GitHub Copilot · Cursor · Claude Code</p>
          <h2 className="text-3xl font-bold text-white mb-4">
            You have AI that writes code.<br />Conduct turns the surrounding work into a workflow.
          </h2>
          <p className="text-stone-400 text-sm max-w-2xl mx-auto mb-10 leading-relaxed">
            Every engineering team now has an AI writing code. Conduct gives teams governed automations for the work around it:
            catch AI-generated PRs, review the diff, gate on human approval, and post structured findings to Slack before a single
            line hits main.
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-left mb-10">
            {[
              { icon: "🔍", title: "Catch AI PRs automatically", body: "Trigger fires when Copilot, Cursor, or any bot opens a PR. Human PRs are skipped silently." },
              { icon: "🧠", title: "Review with extra scrutiny", body: "Checks for hallucinated APIs, missing tests, security issues, and over-engineering — things humans miss in AI diffs." },
              { icon: "✋", title: "Gate before merge", body: "Human approval required before the PR can land. One-click Approve or Reject in Slack." },
            ].map(c => (
              <div key={c.title} className="bg-stone-800 rounded-2xl p-5">
                <span className="text-2xl block mb-3">{c.icon}</span>
                <p className="text-white font-semibold text-sm mb-1">{c.title}</p>
                <p className="text-stone-400 text-xs leading-relaxed">{c.body}</p>
              </div>
            ))}
          </div>
          <a
            href="/marketplace"
            className="inline-flex items-center gap-2 rounded-xl bg-white text-stone-900 px-6 py-3 text-sm font-semibold hover:bg-stone-100 transition-colors"
          >
            Install Copilot / AI PR Reviewer →
          </a>
        </div>
      </section>

      {/* Why Conduct — the moat */}
      <section className="px-6 py-20">
        <div className="max-w-5xl mx-auto">
          <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest text-center mb-3">Why Conduct</p>
          <h2 className="text-3xl font-bold text-stone-900 text-center mb-12">
            Not just another AI tool.<br />An AI teammate you can trust.
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
            {WHY_DELEGATOR(playbookCount).map(f => (
              <div key={f.title} className="bg-white rounded-2xl border border-stone-200 p-6">
                <div className="text-2xl mb-3">{f.icon}</div>
                <p className="font-semibold text-stone-900 mb-1.5">{f.title}</p>
                <p className="text-sm text-stone-500 leading-relaxed">{f.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Memory — agents that learn */}
      <section className="px-6 py-20 bg-amber-50">
        <div className="max-w-5xl mx-auto">
          <p className="text-xs font-semibold text-amber-600 uppercase tracking-widest text-center mb-3">Agent Memory</p>
          <h2 className="text-3xl font-bold text-stone-900 text-center mb-4">
            Agents that get better<br />with every run.
          </h2>
          <p className="text-center text-stone-500 text-sm max-w-2xl mx-auto mb-12 leading-relaxed">
            Most AI tools start from scratch every time. Conduct agents remember. Before each run, the agent
            recalls what it learned last time on that repo. After the run, it records the outcome for next time.
            The 10th PR on your codebase is noticeably smarter than the first.
          </p>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-5 mb-12">
            {[
              {
                icon: "🧠",
                title: "Recall before acting",
                body: "Before the brain block runs, a Memory read block retrieves the most relevant past summaries using vector similarity search — not just recent history, but the most applicable context for this specific task.",
              },
              {
                icon: "📝",
                title: "Record every outcome",
                body: "After the run completes, a Memory write block stores a summary of what was done: the approach taken, the files changed, what worked. That becomes context for future runs on the same repo.",
              },
              {
                icon: "🔒",
                title: "Scoped and isolated",
                body: "Each playbook builds its own knowledge store. Autopilot Quick and Autopilot Full on the same repo never share memories — each agent specialises independently. Repo scope or workspace scope — your choice.",
              },
            ].map(({ icon, title, body }) => (
              <div key={title} className="bg-white rounded-2xl border border-amber-200 p-6 flex flex-col gap-3">
                <span className="text-2xl">{icon}</span>
                <div>
                  <p className="font-semibold text-stone-900 mb-1.5">{title}</p>
                  <p className="text-xs text-stone-500 leading-relaxed">{body}</p>
                </div>
              </div>
            ))}
          </div>

          <div className="bg-white rounded-2xl border border-amber-200 overflow-hidden mb-8">
            <div className="px-6 py-4 border-b border-amber-100">
              <p className="text-xs font-semibold text-stone-500 uppercase tracking-wider">Two memory scopes — one decision</p>
            </div>
            <div className="grid sm:grid-cols-2 divide-y sm:divide-y-0 sm:divide-x divide-amber-100">
              <div className="px-6 py-5">
                <p className="font-semibold text-stone-900 mb-1.5 text-sm">Repo scope</p>
                <p className="text-xs text-stone-500 leading-relaxed mb-3">
                  Memories are isolated per repository. The agent learns the conventions, file layout,
                  and bug patterns of <em>that specific codebase</em>. Installing the same playbook on
                  5 repos gives you 5 independent experts.
                </p>
                <div className="bg-stone-50 rounded-lg px-3 py-2 text-xs font-mono text-stone-600">
                  key: {"{{_trigger.repo_full_name}}"}
                </div>
              </div>
              <div className="px-6 py-5">
                <p className="font-semibold text-stone-900 mb-1.5 text-sm">Workspace scope</p>
                <p className="text-xs text-stone-500 leading-relaxed mb-3">
                  Memories are shared across all repos in the workspace for this playbook.
                  What the agent learns fixing a bug in <code className="font-mono text-[11px] bg-stone-100 px-1 rounded">acme/api</code> informs
                  how it approaches <code className="font-mono text-[11px] bg-stone-100 px-1 rounded">acme/frontend</code>.
                  Team conventions, not repo conventions.
                </p>
                <div className="bg-stone-50 rounded-lg px-3 py-2 text-xs font-mono text-stone-600">
                  key: &quot;workspace&quot;
                </div>
              </div>
            </div>
          </div>

          <p className="text-center text-xs text-stone-400">
            Powered by vector similarity search (OpenAI <code className="font-mono bg-stone-100 px-1 rounded">text-embedding-3-small</code>).
            Falls back to recency-based retrieval when no embedding key is configured — memory still works.{" "}
            <a href="/docs#memory-block" className="text-amber-600 hover:underline">Full docs →</a>
          </p>
        </div>
      </section>

      {/* Guard — workflow governance */}
      <section className="bg-stone-900 px-6 py-20">
        <div className="max-w-4xl mx-auto text-center">
          <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-3">How it all fits together</p>
          <h2 className="text-3xl font-bold text-white mb-4">
            Every AI workflow runs within rules<br />your team sets.
          </h2>
          <p className="text-stone-400 text-sm max-w-xl mx-auto mb-12">
            Every time Conduct runs a playbook — PR review, issue triage, incident response — it checks
            the policies your team lead configured in Guard. Spending limits, blocked actions, approved tools.
            Set once. Applied automatically to every run.
          </p>

          <div className="flex flex-col gap-2 text-left mb-4 max-w-2xl mx-auto">
            <div className="rounded-xl border border-red-400 bg-red-950 px-6 py-4 flex items-center gap-4">
              <span className="text-xl">🛡️</span>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold text-white">ConductGuard — governs every workflow run</p>
                <p className="text-xs text-red-300 mt-0.5">Spending limits · blocked actions · audit log — one policy, applied to every playbook automatically</p>
              </div>
              <span className="shrink-0 text-xs font-semibold text-red-300 bg-red-900 border border-red-700 px-2 py-0.5 rounded-full">Rules layer</span>
            </div>
          </div>

          <div className="flex items-center gap-3 mb-4 max-w-2xl mx-auto px-2">
            <div className="flex-1 border-t border-stone-700" />
            <p className="text-xs text-stone-500 whitespace-nowrap">every playbook run checks these rules</p>
            <div className="flex-1 border-t border-stone-700" />
          </div>

          <div className="flex flex-col gap-2 text-left max-w-2xl mx-auto mb-10">
            {[
              { icon: "⚡", title: "Autopilot workflows", body: "Issue labeled → AI implements fix → PR opened — guarded by your spending limit and action policies" },
              { icon: "🔍", title: "PR review workflows", body: "PR opened → AI reviews the diff → posts findings — within your approved model budget" },
              { icon: "🔥", title: "Incident response workflows", body: "Alert fires → AI diagnoses root cause → posts to Slack — every action audit logged" },
              { icon: "🔒", title: "Security & compliance workflows", body: "Dependency alerts, CVE scans, Terraform reviews — all governed by the same policy your team lead set" },
            ].map(({ icon, title, body }) => (
              <div key={title} className="rounded-xl border border-stone-600 bg-stone-800 px-5 py-3 flex items-center gap-3">
                <span className="text-lg shrink-0">{icon}</span>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold text-white">{title}</p>
                  <p className="text-xs text-stone-400">{body}</p>
                </div>
              </div>
            ))}
          </div>

          <a href="/dashboard" className="inline-flex items-center gap-2 rounded-xl border border-stone-600 px-6 py-3 text-sm font-semibold text-stone-300 hover:border-stone-400 hover:text-white transition-colors">
            Set up Guard →
          </a>
        </div>
      </section>

      {/* Guard onboarding — who does what */}
      <section className="px-6 py-20 bg-stone-50">
        <div className="max-w-5xl mx-auto">
          <div className="text-center mb-14">
            <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-3">Getting started with Guard</p>
            <h2 className="text-3xl font-bold text-stone-900 mb-4">
              Three steps. Three minutes.<br />Your whole team, in sync.
            </h2>
            <p className="text-stone-500 text-sm max-w-xl mx-auto leading-relaxed">
              One person sets the rules. Everyone else joins with a single command.
              Every AI workflow on your team runs within those rules automatically.
            </p>
          </div>

          <div className="grid sm:grid-cols-3 gap-6 mb-10">

            <div className="bg-white rounded-2xl border border-stone-200 p-7 flex flex-col gap-4">
              <div className="flex items-center justify-between mb-1">
                <span className="inline-flex items-center gap-1.5 text-[10px] font-bold text-red-700 bg-red-50 border border-red-100 px-2.5 py-1 rounded-full uppercase tracking-widest">Team lead</span>
                <span className="text-xs font-bold text-stone-300">Step 1</span>
              </div>
              <div>
                <p className="text-lg font-bold text-stone-900 mb-2">Set the policies</p>
                <p className="text-sm text-stone-500 leading-relaxed">
                  Log into Conduct, open Guard, and configure your team&apos;s rules —
                  daily spend limit, approved AI tools, blocked actions.
                  Takes about five minutes. Only needs to happen once.
                </p>
              </div>
              <ul className="space-y-1.5 mt-auto">
                {[
                  "Set daily spend limit per developer",
                  "Choose approved AI tools for the team",
                  "Block risky actions across all workflows",
                  "Invite team members by email",
                ].map(item => (
                  <li key={item} className="flex items-start gap-2 text-xs text-stone-500">
                    <span className="text-red-400 mt-0.5 shrink-0">✓</span>
                    {item}
                  </li>
                ))}
              </ul>
              <div className="mt-4 pt-4 border-t border-stone-100">
                <a href="/dashboard" className="inline-flex items-center gap-1.5 text-xs font-semibold text-red-700 hover:text-red-900 transition-colors">
                  Open Conduct → Guard →
                </a>
              </div>
            </div>

            <div className="bg-white rounded-2xl border border-stone-200 p-7 flex flex-col gap-4">
              <div className="flex items-center justify-between mb-1">
                <span className="inline-flex items-center gap-1.5 text-[10px] font-bold text-indigo-700 bg-indigo-50 border border-indigo-100 px-2.5 py-1 rounded-full uppercase tracking-widest">Developer</span>
                <span className="text-xs font-bold text-stone-300">Step 2</span>
              </div>
              <div>
                <p className="text-lg font-bold text-stone-900 mb-2">Join and pull policies</p>
                <p className="text-sm text-stone-500 leading-relaxed">
                  Accept the invite, run one command. Conduct downloads your team&apos;s
                  Guard policies and applies them to your local environment automatically.
                  Nothing to configure manually.
                </p>
              </div>
              <div className="mt-auto bg-stone-950 rounded-xl px-4 py-3 font-mono text-xs">
                <p className="text-stone-500 mb-1"># One command to join</p>
                <p className="text-emerald-400">conduct guard join</p>
                <p className="text-stone-500 mt-2 mb-1"># Policies pulled automatically</p>
                <p className="text-white">✓ spend limit applied</p>
                <p className="text-white">✓ approved tools configured</p>
                <p className="text-white">✓ blocked actions enforced</p>
              </div>
            </div>

            <div className="bg-white rounded-2xl border border-stone-200 p-7 flex flex-col gap-4">
              <div className="flex items-center justify-between mb-1">
                <span className="inline-flex items-center gap-1.5 text-[10px] font-bold text-violet-700 bg-violet-50 border border-violet-100 px-2.5 py-1 rounded-full uppercase tracking-widest">MCP server</span>
                <span className="text-xs font-bold text-stone-300">Step 3</span>
              </div>
              <div>
                <p className="text-lg font-bold text-stone-900 mb-2">Guard in your AI coding tools</p>
                <p className="text-sm text-stone-500 leading-relaxed">
                  The <code className="font-mono text-xs bg-stone-100 px-1 rounded">conductguard-mcp</code> MCP server connects
                  Guard to Claude Code, Cursor, and any MCP-compatible editor.
                  Policies are enforced where AI actually runs — not just in hosted workflows.
                </p>
              </div>
              <div className="mt-auto bg-stone-950 rounded-xl px-4 py-3 font-mono text-xs">
                <p className="text-stone-500 mb-1"># MCP server — add to your editor config</p>
                <p className="text-emerald-400">conductguard-mcp \</p>
                <p className="text-emerald-400 pl-4">--team &lt;team-id&gt; \</p>
                <p className="text-emerald-400 pl-4">--token &lt;member-token&gt;</p>
                <p className="text-stone-500 mt-2 mb-1"># Three tools exposed to the AI</p>
                <p className="text-white">guard_status  guard_check  guard_sync</p>
              </div>
              <div className="mt-4 pt-4 border-t border-stone-100">
                <a href="/docs#guard" className="inline-flex items-center gap-1.5 text-xs font-semibold text-violet-700 hover:text-violet-900 transition-colors">
                  MCP setup docs →
                </a>
              </div>
            </div>

          </div>

          <div className="rounded-2xl border border-indigo-100 bg-indigo-50 px-8 py-6 flex flex-col sm:flex-row items-center gap-6">
            <div className="text-3xl shrink-0">🔄</div>
            <div className="flex-1">
              <p className="font-semibold text-stone-900 mb-1">Change a rule once. It updates everywhere.</p>
              <p className="text-sm text-stone-500 leading-relaxed">
                When the team lead lowers the spend limit or adds a new blocked action,
                every developer gets the update the next time they sync — no Slack messages,
                no manual steps, no one left on an old policy.
              </p>
            </div>
            <a href="/tools" className="shrink-0 inline-flex items-center gap-2 rounded-xl border border-indigo-200 bg-white px-5 py-2.5 text-sm font-semibold text-indigo-700 hover:border-indigo-300 transition-colors">
              See the tools →
            </a>
          </div>
        </div>
      </section>

      {/* Guard spend controls + hard cap */}
      <section className="px-6 py-20 bg-white">
        <div className="max-w-5xl mx-auto">
          <p className="text-xs font-semibold text-red-500 uppercase tracking-widest text-center mb-3">ConductGuard — Spend Controls</p>
          <h2 className="text-3xl font-bold text-stone-900 text-center mb-4">
            Know exactly what your team<br />spends on AI. Hard-stop when they hit the cap.
          </h2>
          <p className="text-center text-stone-500 text-sm max-w-2xl mx-auto mb-12 leading-relaxed">
            Guard tracks every token and dollar spent by every developer, across every AI tool.
            Set a monthly hard cap — when a developer hits it, their next AI call is blocked at the source before it reaches the model. No surprises on the bill.
          </p>

          <div className="grid sm:grid-cols-3 gap-5 mb-10">
            {[
              {
                icon: "💸",
                title: "Real-time spend tracking",
                body: "Every Claude Code call, every Cursor completion, every Conduct workflow run — all tracked per developer, per tool, per month. Dashboard shows spend vs. budget at a glance.",
                badge: "Per developer",
              },
              {
                icon: "🚫",
                title: "Hard cap enforcement",
                body: "When a developer hits their monthly budget, the PreToolUse hook blocks the next AI call before it reaches the model — not just a warning, a hard stop. The cap resets on the 1st.",
                badge: "Hard stop",
              },
              {
                icon: "📣",
                title: "Slack alerts on policy hit",
                body: "When a policy blocks an action or a budget threshold is crossed, Guard posts to your configured Slack channel immediately — not after the fact, in real time.",
                badge: "Instant notify",
              },
            ].map(({ icon, title, body, badge }) => (
              <div key={title} className="bg-white rounded-2xl border border-stone-200 p-6 flex flex-col gap-3">
                <div className="flex items-start justify-between">
                  <span className="text-2xl">{icon}</span>
                  <span className="text-[10px] font-bold uppercase tracking-wider bg-red-50 text-red-700 border border-red-100 px-2 py-0.5 rounded-full">{badge}</span>
                </div>
                <div>
                  <p className="font-semibold text-stone-900 mb-1.5">{title}</p>
                  <p className="text-xs text-stone-500 leading-relaxed">{body}</p>
                </div>
              </div>
            ))}
          </div>

          <div className="rounded-2xl bg-stone-900 px-8 py-6 flex flex-col sm:flex-row items-center gap-6">
            <div className="text-3xl shrink-0">🛡️</div>
            <div className="flex-1">
              <p className="text-white font-semibold mb-1">The hook runs before every AI tool call.</p>
              <p className="text-stone-400 text-sm leading-relaxed">
                <code className="font-mono text-xs bg-stone-800 px-1 rounded">conduct guard join</code> installs a PreToolUse hook that runs locally every time
                your AI coding tool is about to make a call. It checks the team&apos;s hard cap, blocks if hit, and records spend.
                Works with Claude Code, Cursor, and any tool that supports hooks.
              </p>
            </div>
            <a href="/docs#guard-hook" className="shrink-0 inline-flex items-center gap-2 rounded-xl border border-stone-600 px-5 py-2.5 text-sm font-semibold text-stone-300 hover:border-stone-400 hover:text-white transition-colors">
              Hook docs →
            </a>
          </div>
        </div>
      </section>

      {/* Credential Vault Security */}
      <section className="bg-stone-50 px-6 py-20">
        <div className="max-w-5xl mx-auto">
          <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest text-center mb-3">Credential Vault</p>
          <h2 className="text-3xl font-bold text-stone-900 text-center mb-4">
            Your keys. Locked down. Always.
          </h2>
          <p className="text-center text-stone-500 text-sm max-w-xl mx-auto mb-12">
            Conduct AI agents need your GitHub token and Slack token to act on your behalf. Here is exactly how we protect them.
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-5 mb-8">
            {VAULT_SECURITY.map(v => (
              <div key={v.title} className="bg-white rounded-2xl border border-stone-200 p-6 flex flex-col gap-3">
                <div className="text-2xl">{v.icon}</div>
                <div>
                  <p className="font-semibold text-stone-900 mb-1">{v.title}</p>
                  <p className="text-xs text-stone-500 leading-relaxed">{v.body}</p>
                </div>
                <div className="mt-auto">
                  <span className="inline-block text-[10px] font-semibold uppercase tracking-wide bg-emerald-50 text-emerald-700 border border-emerald-200 px-2 py-0.5 rounded-full">{v.badge}</span>
                </div>
              </div>
            ))}
          </div>
          <p className="text-center text-xs text-stone-400">
                  Credentials are decrypted only at runtime, scoped to the workspace environment, and never written to logs.
          </p>
        </div>
      </section>

      {/* Integrations */}
      <section className="bg-white px-6 py-16">
        <div className="max-w-3xl mx-auto text-center">
          <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-8">Works with your existing stack</p>
          <div className="flex flex-wrap justify-center gap-3">
            {INTEGRATIONS.map(i => (
              <span key={i.name} className="inline-flex items-center gap-2 bg-white border border-stone-200 text-stone-600 text-sm font-medium px-4 py-2 rounded-lg hover:border-stone-300 hover:shadow-sm transition-all">
                <svg viewBox="0 0 24 24" className="w-4 h-4 shrink-0" style={{ fill: i.color }} aria-hidden="true">
                  <path d={i.svg} />
                </svg>
                {i.name}
              </span>
            ))}
          </div>
        </div>
      </section>

      {/* Bottom CTA */}
      <section className="px-6 py-20 text-center">
        <h2 className="text-3xl font-bold text-stone-900 mb-4">
          {isLoaded && isSignedIn ? "Ready to conduct?" : "Try it in 30 seconds"}
        </h2>
        <p className="text-stone-500 mb-8 max-w-md mx-auto">
          {isLoaded && isSignedIn
            ? "Head to your projects and connect your first repo."
            : "Sign in, connect your GitHub repo, and let Conduct pick up its first ticket."}
        </p>
        {isLoaded && (
          isSignedIn ? (
            <button
              onClick={() => router.push("/dashboard")}
              className="inline-flex items-center gap-2 bg-stone-900 hover:bg-stone-700 text-white font-semibold px-7 py-3.5 rounded-xl text-sm transition-colors"
            >
              Open app →
            </button>
          ) : clerkEnabled ? (
            <>
              <SignInButton mode="modal">
                <button className="inline-flex items-center gap-2 bg-stone-900 hover:bg-stone-700 text-white font-semibold px-7 py-3.5 rounded-xl text-sm transition-colors">
                  Get started — it&apos;s free
                </button>
              </SignInButton>
              <p className="text-xs text-stone-400 mt-4">No credit card · Instant access · Google, GitHub, or Microsoft</p>
            </>
          ) : null
        )}
      </section>

      {/* Blog */}
      <BlogErrorBoundary>
        <BlogSection />
      </BlogErrorBoundary>

      {/* CLI section */}
      <section className="border-t border-stone-100 py-16 px-6">
        <div className="mx-auto max-w-3xl">
          <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-3">CLI & CI</p>
          <h2 className="text-2xl font-bold text-stone-900 mb-3">Run agents from your terminal</h2>
          <p className="text-stone-500 mb-8 text-sm leading-relaxed">
            The <code className="bg-stone-100 px-1.5 py-0.5 rounded text-stone-700 font-mono text-xs">conduct</code> CLI
            lets you trigger any agent from your terminal, a GitHub Action, or a CI pipeline — no browser required.
          </p>
          <div className="grid md:grid-cols-2 gap-4">
            <div className="rounded-xl bg-stone-950 p-5 font-mono text-sm">
              <p className="text-stone-500 text-xs mb-3"># Install &amp; authenticate</p>
              <p className="text-emerald-400">pip install conduct-cli</p>
              <p className="text-white mt-2">conduct login</p>
              <p className="text-stone-500 text-xs mt-4 mb-3"># Manage environments &amp; credentials</p>
              <p className="text-white">conduct environments</p>
              <p className="text-white">conduct create environment Staging</p>
              <p className="text-white">conduct set credential \</p>
              <p className="text-white pl-4">--environment Staging \</p>
              <p className="text-white pl-4">--key GITHUB_TOKEN --value ghp_xxx</p>
            </div>
            <div className="rounded-xl bg-stone-950 p-5 font-mono text-sm">
              <p className="text-stone-500 text-xs mb-3"># Run &amp; monitor agents</p>
              <p className="text-white">conduct agents</p>
              <p className="text-white mt-2">conduct test "PR Reviewer" \</p>
              <p className="text-white pl-4">--pr 142</p>
              <p className="text-stone-500 text-xs mt-4 mb-3"># Assign environment to agent</p>
              <p className="text-white">conduct set environment \</p>
              <p className="text-white pl-4">--agent "PR Reviewer" \</p>
              <p className="text-white pl-4">--environment Production</p>
            </div>
          </div>
        </div>
      </section>

      {/* Quality + Benchmark */}
      <section className="border-t border-stone-100 py-20 px-6 bg-stone-50">
        <div className="max-w-5xl mx-auto">
          <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest text-center mb-3">Transparency by default</p>
          <h2 className="text-3xl font-bold text-stone-900 text-center mb-4">
            We grade our own agents.<br />In public.
          </h2>
          <p className="text-center text-stone-500 text-sm max-w-2xl mx-auto mb-14">
            Most AI tools ship a demo and call it a product. We score every playbook against 13 structural criteria and an LLM judge in controlled eval runs — then publish the results. No cherry-picking. No hiding the Bs.
          </p>

          {/* Two product cards */}
          <div className="grid sm:grid-cols-2 gap-6 mb-12">

            {/* Quality card */}
            <div className="rounded-2xl border border-stone-200 bg-white px-7 py-7 flex flex-col gap-5">
              <div className="flex items-start justify-between">
                <div>
                  <span className="inline-flex items-center gap-1.5 text-[10px] font-semibold text-violet-700 bg-violet-50 border border-violet-100 rounded-full px-2.5 py-0.5 uppercase tracking-widest mb-2">
                    Controlled scoring
                  </span>
                  <h3 className="text-lg font-bold text-stone-900">Quality</h3>
                  <p className="text-xs text-stone-400 mt-0.5">Per-playbook grades from controlled eval runs</p>
                </div>
                <span className="text-3xl font-black text-violet-100 select-none">◈</span>
              </div>
              <div className="space-y-2.5 text-xs text-stone-500">
                {[
                  "Grade A–F per playbook based on 13 structural criteria",
                  "Execution samples scored by Claude Haiku as judge",
                  "Failing criteria listed inline — know exactly what's wrong",
                  "Published scores update after reviewed evaluation runs",
                ].map(t => (
                  <div key={t} className="flex items-start gap-2">
                    <span className="text-violet-400 mt-0.5">✓</span>
                    <span>{t}</span>
                  </div>
                ))}
              </div>
              <div className="mt-auto pt-4 border-t border-stone-100 flex items-center justify-between">
                <span className="text-[10px] text-stone-400">conductai.ai/eval</span>
                <a
                  href="/eval"
                  className="inline-flex items-center gap-1.5 text-xs font-medium text-violet-700 hover:text-violet-900 transition-colors"
                >
                  View Quality →
                </a>
              </div>
            </div>

            {/* Benchmark card */}
            <div className="rounded-2xl border border-indigo-100 bg-gradient-to-br from-indigo-50 to-white px-7 py-7 flex flex-col gap-5">
              <div className="flex items-start justify-between">
                <div>
                  <span className="inline-flex items-center gap-1.5 text-[10px] font-semibold text-indigo-700 bg-indigo-50 border border-indigo-100 rounded-full px-2.5 py-0.5 uppercase tracking-widest mb-2">
                    Public leaderboard
                  </span>
                  <h3 className="text-lg font-bold text-stone-900">Benchmark</h3>
                  <p className="text-xs text-stone-400 mt-0.5">Frozen edition scores — no sign-in required</p>
                </div>
                <span className="text-3xl font-black text-indigo-100 select-none">▲</span>
              </div>
              <div className="space-y-2.5 text-xs text-stone-500">
                {[
                  "All 19 playbooks scored across Haiku, Sonnet, and Opus",
                  "Edition 001: 92.9% average — 10 Grade A, 9 Grade B",
                  "Structural (100 pts) + quality judge (70 pts) = 170 pts max",
                  "Share any playbook deep-dive with a single link",
                ].map(t => (
                  <div key={t} className="flex items-start gap-2">
                    <span className="text-indigo-400 mt-0.5">✓</span>
                    <span>{t}</span>
                  </div>
                ))}
              </div>
              <div className="mt-auto pt-4 border-t border-indigo-100 flex items-center justify-between">
                <span className="text-[10px] text-stone-400">conductai.ai/benchmark</span>
                <a
                  href="/benchmark"
                  className="inline-flex items-center gap-1.5 text-xs font-medium text-indigo-700 hover:text-indigo-900 transition-colors"
                >
                  View Benchmark →
                </a>
              </div>
            </div>

          </div>

          {/* Stats row */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {[
              { value: "92.9%", label: "avg score, Edition 001", accent: "text-emerald-700" },
              { value: "10 / 19", label: "Grade A playbooks",     accent: "text-indigo-700" },
              { value: "3 models", label: "Haiku · Sonnet · Opus", accent: "text-violet-700" },
              { value: "170 pts", label: "max score per playbook", accent: "text-stone-700"  },
            ].map(({ value, label, accent }) => (
              <div key={label} className="rounded-xl border border-stone-200 bg-white px-5 py-4 text-center">
                <p className={`text-2xl font-black ${accent}`}>{value}</p>
                <p className="text-[11px] text-stone-400 mt-1">{label}</p>
              </div>
            ))}
          </div>

        </div>
      </section>

      {/* Observability + Audit */}
      <section className="border-t border-stone-100 px-6 py-20">
        <div className="max-w-5xl mx-auto">
          <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest text-center mb-3">Observability</p>
          <h2 className="text-3xl font-bold text-stone-900 text-center mb-4">
            Three audit layers.<br />Every action accounted for.
          </h2>
          <p className="text-center text-stone-500 text-sm max-w-2xl mx-auto mb-12 leading-relaxed">
            Most AI tools give you a chat history. Conduct gives you an immutable audit trail across three lenses —
            workflow execution, workspace events, and developer AI tool governance — so you can always answer
            &ldquo;what did the agent do, who approved it, and what did it cost?&rdquo;
          </p>

          <div className="grid sm:grid-cols-3 gap-5 mb-10">
            {[
              {
                icon: "🔁",
                label: "Run trace",
                tag: "Per workflow run",
                accent: "from-indigo-50 to-white border-indigo-200",
                iconBg: "bg-indigo-100 text-indigo-600",
                tagColor: "text-indigo-600",
                points: [
                  "Every block: started → completed → failed",
                  "Every LLM call and tool call inline",
                  "Guard policy check result in the trace",
                  "Live via Server-Sent Events while running",
                  "Immutable — append-only, never deleted",
                ],
                link: "/runs",
                linkLabel: "View Runs →",
              },
              {
                icon: "🏢",
                label: "Workspace audit",
                tag: "Platform events",
                accent: "from-violet-50 to-white border-violet-200",
                iconBg: "bg-violet-100 text-violet-600",
                tagColor: "text-violet-600",
                points: [
                  "Credential added, rotated, or removed",
                  "Agent installed or deleted",
                  "Member invited or role changed",
                  "Environment created or reassigned",
                  "Scoped to workspace — cross-workspace blind",
                ],
                link: "/audit",
                linkLabel: "View Audit Log →",
              },
              {
                icon: "🛡️",
                label: "Guard audit",
                tag: "Developer AI governance",
                accent: "from-red-50 to-white border-red-200",
                iconBg: "bg-red-100 text-red-600",
                tagColor: "text-red-600",
                points: [
                  "Every Claude Code, Cursor, and AI tool call",
                  "Decision: allowed / blocked / warned",
                  "Which policy rule triggered and why",
                  "Tokens and cost per call, per developer",
                  "Slack alert posted in real time on block",
                ],
                link: "/guard/audit",
                linkLabel: "View Guard Audit →",
              },
            ].map(({ icon, label, tag, accent, iconBg, tagColor, points, link, linkLabel }) => (
              <div key={label} className={`rounded-2xl border bg-gradient-to-br ${accent} p-6 flex flex-col gap-4`}>
                <div className="flex items-center justify-between">
                  <span className={`w-10 h-10 rounded-xl flex items-center justify-center text-xl ${iconBg}`}>{icon}</span>
                  <span className={`text-[10px] font-semibold uppercase tracking-wider ${tagColor}`}>{tag}</span>
                </div>
                <p className="font-bold text-stone-900">{label}</p>
                <ul className="space-y-1.5 flex-1">
                  {points.map(p => (
                    <li key={p} className="flex items-start gap-2 text-xs text-stone-500">
                      <span className="text-stone-300 mt-0.5 shrink-0">·</span>
                      {p}
                    </li>
                  ))}
                </ul>
                <div className="pt-3 border-t border-stone-200">
                  <a href={link} className="text-xs font-semibold text-stone-600 hover:text-stone-900 transition-colors">{linkLabel}</a>
                </div>
              </div>
            ))}
          </div>

          <div className="rounded-2xl bg-stone-50 border border-stone-200 px-8 py-5 flex flex-col sm:flex-row items-center gap-5">
            <div className="text-2xl shrink-0">🔗</div>
            <div className="flex-1">
              <p className="font-semibold text-stone-900 mb-1 text-sm">Guard and workflow runs share a link, not a table.</p>
              <p className="text-xs text-stone-500 leading-relaxed">
                When a Guard block fires inside a workflow, the policy decision appears inline in the run trace
                as a <code className="font-mono bg-stone-100 px-1 rounded">guard_check</code> event — rules evaluated, verdict, warnings — alongside the other block events.
                The same event is also written to the Guard audit log with full token and cost context.
                Two lenses on the same moment.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* FAQ */}
      <section className="border-t border-stone-100 py-16 px-6">
        <div className="mx-auto max-w-3xl">
          <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-3">FAQ</p>
          <h2 className="text-2xl font-bold text-stone-900 mb-8">Common questions</h2>
          <div className="space-y-6">
            {FAQ(playbookCount).map(({ q, a }) => (
              <div key={q} className="border-b border-stone-100 pb-6 last:border-0">
                <p className="font-semibold text-stone-900 mb-2">{q}</p>
                <p className="text-sm text-stone-500 leading-relaxed">{a}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <footer className="border-t border-stone-100 py-8 text-center text-xs text-stone-400 space-y-2">
        <div className="flex items-center justify-center gap-3 flex-wrap">
          <span>© {new Date().getFullYear()} Conduct</span>
          <span>·</span>
          <a href="https://github.com/sseshachala/conductai" target="_blank" rel="noopener noreferrer" className="hover:text-stone-600 transition-colors">GitHub</a>
          <span>·</span>
          <span>MIT licensed</span>
          <span>·</span>
          <a href="https://github.com/sseshachala/conductai/discussions/new?category=ideas" target="_blank" rel="noopener noreferrer" className="hover:text-stone-600 transition-colors">💡 Request an idea</a>
          <span>·</span>
          <a href="/tools" className="hover:text-stone-600 transition-colors">Tools</a>
          <span>·</span>
          <a href="/compare" className="hover:text-stone-600 transition-colors">Compare</a>
          <span>·</span>
          <a href="/docs" className="hover:text-stone-600 transition-colors">Docs</a>
          <span>·</span>
          <a href="https://narratr.ai/blog/conductai" target="_blank" rel="noopener noreferrer" className="hover:text-stone-600 transition-colors">Blog</a>
          <span>·</span>
          <a href="/privacy" className="hover:text-stone-600 transition-colors">Privacy</a>
          <span>·</span>
          <a href="/terms" className="hover:text-stone-600 transition-colors">Terms</a>
        </div>
        <p className="text-stone-300">Envisioned, designed and developed with 💕 from Houston</p>
      </footer>

      {/* FAQ JSON-LD structured data */}
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify({
          "@context": "https://schema.org",
          "@type": "FAQPage",
          "mainEntity": FAQ(playbookCount).map(({ q, a }) => ({
            "@type": "Question",
            "name": q,
            "acceptedAnswer": { "@type": "Answer", "text": a },
          })),
        }) }}
      />
    </div>
  )
}

const TEMPLATES = [
  {
    icon: "⚡",
    name: "Autopilot Quick",
    trigger: "GitHub issue",
    what: "Issue labeled → AI implements the fix → opens a PR immediately. No test step — CI runs tests on the PR.",
    scenario: "Team labels a bug \"autopilot ready\" at 5pm. PR is open and ready for review by 5:02pm.",
  },
  {
    icon: "🧪",
    name: "Autopilot + Tests",
    trigger: "GitHub issue",
    what: "Issue labeled → AI implements the fix → runs your test suite → opens PR only if tests pass.",
    scenario: "Issue filed on Friday. By Monday morning a green PR is waiting — tests already passed.",
  },
  {
    icon: "✅",
    name: "Autopilot + Approval",
    trigger: "GitHub issue",
    what: "Issue labeled → implement → run tests → human approves in Slack → PR opened. Nothing ships without a gate.",
    scenario: "Junior dev labels an issue. Senior reviews the AI's implementation in Slack before any PR is created.",
  },
  {
    icon: "🔍",
    name: "PR Reviewer",
    trigger: "PR opened",
    what: "Any PR opened (by a human or Autopilot) → AI reviews the diff for bugs, security issues, and style → posts a review comment.",
    scenario: "Autopilot opens a PR at 2am. By the time a human reads it in the morning, it already has an AI code review flagging a missing null check.",
  },
  {
    icon: "🚨",
    name: "CI Failure Alert",
    trigger: "CI webhook",
    what: "Build fails → AI reads the failed step and error → diagnoses root cause → posts structured Slack alert with a suggested fix.",
    scenario: "GitHub Actions workflow fails at 3am. On-call wakes up to a Slack message: \"Likely cause: missing env var STRIPE_KEY in staging. Fix: add to Render env config.\"",
  },
  {
    icon: "🔥",
    name: "Incident Responder",
    trigger: "PagerDuty / OpsGenie",
    what: "Alert fires → AI fetches recent commits and deploys → correlates timing → posts root cause hypothesis to #incidents within 60 seconds.",
    scenario: "payment-service latency spikes. Before the on-call opens their laptop, Slack already says: \"Deploy 3 minutes before spike touched checkout.py — suspect commit a3f92b1 by @alice.\"",
  },
  {
    icon: "📦",
    name: "Dependency Updater",
    trigger: "Weekly cron",
    what: "Cron fires every Monday → AI scans for outdated patch/minor deps → bumps versions → opens a single clean PR. Never bumps major versions.",
    scenario: "Team was 4 months behind on npm patches. Now a single PR lands every Monday. Merge in 30 seconds when CI is green.",
  },
  {
    icon: "🏷️",
    name: "Issue Triage",
    trigger: "GitHub issue",
    what: "New issue opened → AI classifies type and priority → adds labels → posts a clarifying comment if the issue is vague or missing reproduction steps.",
    scenario: "Issue filed at 11pm with just a title. By morning it has a bug/P2 label and a comment asking for reproduction steps — before any human touched it.",
  },
  {
    icon: "📋",
    name: "Release Notes",
    trigger: "Git tag pushed",
    what: "Tag pushed → AI reads every merged PR since the last tag → groups by feature/fix/maintenance → writes CHANGELOG entry → posts summary to Slack.",
    scenario: "Engineer pushes v1.4.0 tag. #releases gets a Slack message listing 12 PRs shipped, grouped by type. CHANGELOG.md updated automatically.",
  },
  {
    icon: "🔒",
    name: "Security Scanner",
    trigger: "PR opened",
    what: "PR opened → AI scans the diff for OWASP Top 10 vulnerabilities, hardcoded secrets, injection flaws, and insecure dependencies → posts a structured security report as a review comment.",
    scenario: "Dev opens a PR at midnight. By morning it has a security review flagging a hardcoded API key and a missing auth check — before any human looked at it.",
  },
  {
    icon: "🤖",
    name: "Copilot / AI PR Reviewer",
    trigger: "PR opened",
    what: "PR opened by Copilot, Cursor, or Claude Code → AI reviews the diff with extra scrutiny for hallucinated APIs, missing tests, and over-engineering → human approves in Slack before merge.",
    scenario: "Cursor opens a PR fixing a bug. AI flags a hallucinated method that doesn't exist in the codebase. Human reviews and rejects before it ever hits CI.",
  },
  {
    icon: "🛡️",
    name: "Security Patch Updater",
    trigger: "Dependabot alert",
    what: "Dependabot alert fires → AI confirms the vulnerable package is present → applies the patched version → runs tests → opens a PR with full CVE reference. No waiting for the weekly cron.",
    scenario: "A critical CVE lands at 2am. By the time the team wakes up, a PR with the patch is already open, tests ran, and #security has a notification with the CVE number and severity.",
  },
  {
    icon: "🔬",
    name: "Flaky Test Detective",
    trigger: "CI webhook",
    what: "CI run has repeated failures → AI identifies which tests are flaky, traces the offending commit, and posts a fix recommendation to Slack.",
    scenario: "A test fails 1-in-5 runs and everyone keeps hitting retry. Conduct names the flaky test, points at the commit that introduced it, and suggests the fix — no more guessing.",
  },
  {
    icon: "✅",
    name: "Release Readiness Reviewer",
    trigger: "Release branch cut",
    what: "Release branch created → AI checks open blockers, failed CI, pending reviews, and unresolved incidents → posts a go/no-go summary before you ship.",
    scenario: "Release manager cuts release/2.0 on Friday. Within a minute Slack has a go/no-go: 2 open blockers, 1 failing check, 3 PRs still awaiting review — decision made in seconds.",
  },
  {
    icon: "📋",
    name: "Postmortem Drafter",
    trigger: "Incident resolved",
    what: "Incident closed → AI reads the timeline, alerts, and commits → drafts a structured postmortem with root cause and action items, ready for human edit.",
    scenario: "An outage resolves at midnight. By morning a draft postmortem is waiting — timeline reconstructed, root cause hypothesized, action items listed. The team edits instead of starting from a blank page.",
  },
  {
    icon: "📖",
    name: "Docs Drift Detector",
    trigger: "PR merged",
    what: "PR merged → AI checks whether related docs, README, or runbooks went stale → opens a follow-up docs PR or files an issue.",
    scenario: "An engineer renames an env var and merges. Conduct notices the README still references the old name and opens a one-line docs PR before anyone is paged about a broken setup guide.",
  },
  {
    icon: "🏗️",
    name: "Terraform Plan Reviewer",
    trigger: "Terraform PR opened",
    what: "Terraform plan PR opened → AI reviews for security misconfigs, cost anomalies, and drift from approved patterns → posts structured findings as a review.",
    scenario: "A PR opens a public S3 bucket and bumps an instance to a $2k/mo type. Conduct flags both on the diff before a human reviewer even reads it.",
  },
  {
    icon: "🏓",
    name: "Smoke Test",
    trigger: "Manual / CI",
    what: "Minimal one-step pipeline ping → fires a Brain block and returns ok. Use it for CI gating and worker health checks — completes in under 30s.",
    scenario: "You just deployed the worker and want to know it can actually run an agent. Trigger Smoke Test — green in under 30 seconds, no real repo or credentials required.",
  },
]


const WHY_DELEGATOR = (count: number) => [
  {
    icon: "🔒",
    title: "Human approval on every merge",
    body: "Approval gates are first-class blocks, not an afterthought. Add a Slack checkpoint before high-risk actions so agents can do the work while people keep control.",
  },
  {
    icon: "📂",
    title: "Open source, config-as-code",
    body: "MIT licensed. The workflow lives as YAML your team can read, diff, review in PRs, and version-control like any other engineering config. No black box.",
  },
  {
    icon: "🏠",
    title: "Workspace-scoped execution",
    body: "Agent execution uses the runtime configured for that workspace, such as Modal or SSH. Credentials are injected only for the run and never shared across workspaces.",
  },
  {
    icon: "🔍",
    title: "Full audit trail, zero surprises",
    body: "Every action is event-sourced — what the AI read, what it wrote, what it ran, how long it took, what it cost. Debug any run by scrubbing through the trace.",
  },
  {
    icon: "⚡",
    title: "Playbook Marketplace — one click to install",
    body: `${count} pre-built agents in the Marketplace: Autopilot, PR Reviewer, Security Scanner, Security Patch Updater, Issue Triage, Flaky Test Detective, Release Readiness, Release Notes, CI Failure Alert, Incident Responder, Postmortem Drafter, Dependency Updater, Docs Drift Detector, Terraform Reviewer, and more. Install, configure credentials, run. Already-installed playbooks are tracked so you never duplicate.`,
  },
  {
    icon: "🧩",
    title: "GitHub, GitLab, or Bitbucket — your choice",
    body: "Connect the git provider your team already uses. Webhook registration, signature verification, repo selection, and branch targeting are handled through the same playbook model across GitHub, GitLab, and Bitbucket.",
  },
  {
    icon: "👥",
    title: "Teams, projects, and role-based access",
    body: "Organize agents into projects. Invite teammates as admin, editor, or viewer — each with enforced permissions at the API level. Environments and credentials are workspace-scoped, so staging and production never cross-contaminate.",
  },
  {
    icon: "💾",
    title: "Agents that learn — built-in memory",
    body: "Every agent can recall what it did last time on your repo and record what it does this time. Powered by vector similarity search — the most relevant past context surfaces automatically, not just the most recent. Repo scope or workspace scope. Gets smarter with every run.",
  },
  {
    icon: "🧠",
    title: "Auto model routing — best model for the job",
    body: "Set your optimization goal — Quality, Balanced, Speed, or Cost — and Conduct routes each agent step to the right model automatically. Security scans get Opus. Issue triage gets Haiku. Code review gets Sonnet. You see exactly which model ran and why, in the run trace.",
  },
  {
    icon: "🔐",
    title: "AES-256-GCM credential vault",
    body: "Every API key and token is encrypted at rest with AES-256-GCM + HKDF-SHA256 key derivation. Credentials are decrypted only at runtime, never logged, and never shared across workspaces.",
  },
]

const VAULT_SECURITY = [
  {
    icon: "🔐",
    title: "AES-256-GCM encryption at rest",
    body: "Every credential is encrypted with AES-256-GCM before it touches the database. The encryption key is derived via HKDF-SHA256 — a separate environment secret, never stored alongside your data.",
    badge: "Encrypted at rest",
  },
  {
    icon: "🚫",
    title: "Never logged, never exposed",
    body: "Decrypted tokens are passed to the runtime only when needed. They are never written to logs, run traces, or any persistent store. The API returns only field names — never values.",
    badge: "Zero token logging",
  },
  {
    icon: "⏱️",
    title: "Runtime-only, workspace-scoped",
    body: "Credentials are decrypted only when a run needs them and are scoped to the workspace and environment assigned to that workflow. Removing a credential immediately locks agents that depend on it.",
    badge: "Runtime only",
  },
  {
    icon: "🛡️",
    title: "Fail-fast in production",
    body: "The API refuses to start if a default or weak encryption key is detected in production. You cannot accidentally ship an unprotected vault.",
    badge: "Startup guard",
  },
  {
    icon: "🔑",
    title: "You own your keys — including the LLM key",
    body: "Bring your own Anthropic key and it takes precedence over the platform key — your spend, your rate limits, your control. GitHub, Slack, Modal, and any other token can be rotated at any time. Removing a credential immediately locks all agents that depend on it.",
    badge: "BYO keys",
  },
  {
    icon: "📋",
    title: "Standardized environment names",
    body: "Industry-standard names like GITHUB_TOKEN, SLACK_BOT_TOKEN, ANTHROPIC_API_KEY, and MODAL_TOKEN_ID map cleanly to integrations, so teams can configure environments without learning a new credential model.",
    badge: "Standard envs",
  },
  {
    icon: "🏠",
    title: "Workspace runtime isolation",
    body: "Sandbox-backed runs use the runtime configured for that workspace. Conduct keeps credentials workspace-scoped and avoids cross-workspace sharing.",
    badge: "Workspace scoped",
  },
]

const INTEGRATIONS: { name: string; color: string; svg: string }[] = [
  {
    name: "GitHub",
    color: "#181717",
    svg: "M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12",
  },
  {
    name: "GitLab",
    color: "#FC6D26",
    svg: "M23.955 13.587l-1.342-4.135-2.664-8.189a.455.455 0 00-.867 0L16.418 9.45H7.582L4.918 1.263a.455.455 0 00-.867 0L1.386 9.45.044 13.587a.924.924 0 00.331 1.023L12 23.054l11.625-8.443a.924.924 0 00.33-1.024",
  },
  {
    name: "Bitbucket",
    color: "#0052CC",
    svg: "M.778 1.213a.768.768 0 00-.768.892l3.263 19.81c.084.5.515.868 1.022.873H19.95a.772.772 0 00.77-.646l3.27-20.03a.768.768 0 00-.768-.891L.778 1.213zM14.52 15.53H9.522L8.17 8.466h7.561l-1.211 7.064z",
  },
  {
    name: "Slack",
    color: "#4A154B",
    svg: "M5.042 15.165a2.528 2.528 0 01-2.52 2.523A2.528 2.528 0 010 15.165a2.527 2.527 0 012.522-2.52h2.52v2.52zM6.313 15.165a2.527 2.527 0 012.521-2.52 2.527 2.527 0 012.521 2.52v6.313A2.528 2.528 0 018.834 24a2.528 2.528 0 01-2.521-2.522v-6.313zM8.834 5.042a2.528 2.528 0 01-2.521-2.52A2.528 2.528 0 018.834 0a2.527 2.527 0 012.521 2.522v2.52H8.834zM8.834 6.313a2.527 2.527 0 012.521 2.521 2.527 2.527 0 01-2.521 2.521H2.522A2.528 2.528 0 010 8.834a2.528 2.528 0 012.522-2.521h6.312zM18.956 8.834a2.528 2.528 0 012.522-2.521A2.528 2.528 0 0124 8.834a2.528 2.528 0 01-2.522 2.521h-2.522V8.834zM17.688 8.834a2.528 2.528 0 01-2.523 2.521 2.527 2.527 0 01-2.52-2.521V2.522A2.527 2.527 0 0115.165 0a2.528 2.528 0 012.523 2.522v6.312zM15.165 18.956a2.528 2.528 0 012.523 2.522A2.528 2.528 0 0115.165 24a2.527 2.527 0 01-2.52-2.522v-2.522h2.52zM15.165 17.688a2.527 2.527 0 01-2.52-2.523 2.526 2.526 0 012.52-2.52h6.313A2.527 2.527 0 0124 15.165a2.528 2.528 0 01-2.522 2.523h-6.313z",
  },
  {
    name: "Linear",
    color: "#5E6AD2",
    svg: "M0 18.278 5.722 24 24 5.722 18.278 0 0 18.278zm0 0L5.707 24 0 18.278zM1.494 1.494C3.484-.496 6.634-.496 8.625 1.494l13.88 13.88c1.99 1.99 1.99 5.142 0 7.132-1.99 1.99-5.141 1.99-7.131 0L1.494 8.625c-1.99-1.99-1.99-5.14 0-7.131zM0 15.53L8.471 24H6.368L0 17.633V15.53zm0-3.778 7.645 7.644v2.107L0 13.756v-2.003zm0-3.79 11.435 11.434v2.107L0 9.967V7.963zm0-3.79L15.225 16.39v2.107L0 6.176V4.173zm3.968-3.968L19.016 15.25v2.103L1.866 0h2.102zm3.79 0L20.788 13.03v2.105L5.663 0H7.76zm3.788 0L22.56 10.82v2.104L9.547 0h1.999zm3.79 0L24 8.61v2.104L13.337 0h2.002zm3.789 0L24 4.821v2.104L17.126 0h2.001zm3.333.457L24 1.788v2.576L21.245.457z",
  },
  {
    name: "PagerDuty",
    color: "#06AC38",
    svg: "M16.008 0H7.993C3.579 0 0 3.579 0 7.993v8.015C0 20.422 3.579 24 7.993 24h8.015C20.422 24 24 20.421 24 16.008V7.992C24 3.579 20.421 0 16.008 0zm-2.172 17.579H9.9v-1.923h3.936v1.923zm2.094-7.546c0 2.554-1.67 3.986-4.105 3.986H9.9V3.051h2.183c2.304 0 3.847 1.37 3.847 4.083v2.899z",
  },
  {
    name: "OpsGenie",
    color: "#172B4D",
    svg: "M12 0C5.373 0 0 5.373 0 12s5.373 12 12 12 12-5.373 12-12S18.627 0 12 0zm0 3.6a8.4 8.4 0 110 16.8A8.4 8.4 0 0112 3.6zm0 2.4a6 6 0 100 12A6 6 0 0012 6zm0 2a4 4 0 110 8 4 4 0 010-8z",
  },
  {
    name: "Vercel",
    color: "#000000",
    svg: "M24 22.525H0l12-21.05 12 21.05z",
  },
  {
    name: "DigitalOcean",
    color: "#0080FF",
    svg: "M12.04 0C5.408-.02.005 5.37.005 11.992h4.638c0-4.923 4.882-8.731 10.064-6.855a6.95 6.95 0 014.147 4.148c1.889 5.177-1.924 10.055-6.84 10.064v-4.61H7.376v4.61H3.67v3.678h3.706v3.674h3.678v-3.674h.003c7.887-.003 13.707-7.958 11.18-16.04C20.989 2.524 16.807-.002 12.039 0z",
  },
  {
    name: "Resend",
    color: "#000000",
    svg: "M4.013 0h15.974C22.196 0 24 1.804 24 4.013v15.974C24 22.196 22.196 24 19.987 24H4.013C1.804 24 0 22.196 0 19.987V4.013C0 1.804 1.804 0 4.013 0zm3.246 6.932v10.136h2.171v-3.956h1.765l2.29 3.956h2.46l-2.505-4.278a3.805 3.805 0 001.98-3.37c0-2.17-1.667-2.488-3.578-2.488H7.259zm2.171 1.87h1.67c.927 0 1.6.21 1.6 1.142 0 .931-.673 1.14-1.6 1.14H9.43V8.802z",
  },
  {
    name: "Modal",
    color: "#6B21A8",
    svg: "M12 2C6.477 2 2 6.477 2 12s4.477 10 10 10 10-4.477 10-10S17.523 2 12 2zm-1 14H9V8h2v8zm4 0h-2V8h2v8z",
  },
  {
    name: "Any webhook",
    color: "#64748b",
    svg: "M14.255 4.753a4.498 4.498 0 016.232 6.492l-3 3a4.5 4.5 0 01-6.364-6.364l1.757-1.757a.75.75 0 011.06 1.06l-1.757 1.758a3 3 0 004.243 4.243l3-3a3 3 0 00-4.499-3.98l-.435.437a.75.75 0 01-1.062-1.06l.825-.829zm-5.51 14.494a4.498 4.498 0 01-6.232-6.492l3-3a4.5 4.5 0 016.364 6.364l-1.757 1.757a.75.75 0 11-1.06-1.06l1.757-1.758a3 3 0 00-4.243-4.243l-3 3a3 3 0 004.499 3.98l.435-.437a.75.75 0 011.062 1.06l-.825.829z",
  },
]


const FAQ = (count: number) => [
  {
    q: "What does Conduct actually do?",
    a: "Conduct turns tickets, PRs, alerts, and incidents into reusable AI agent workflows. Your team installs a playbook into a project, configures the environment and credentials, then runs agents for tasks like issue triage, PR review, incident response, release notes, and security scanning.",
  },
  {
    q: "Is Conduct a good fit for my engineering team?",
    a: "Conduct is built for software engineering teams and engineering managers running GitHub-based workflows who want to automate repetitive developer tasks without building custom AI infrastructure. If your team is already using GitHub, Slack, and Linear, Conduct fits around those tools without requiring a migration or workflow overhaul.",
  },
  {
    q: "How does Conduct work once it's connected to our stack?",
    a: "Link GitHub, Slack, and Linear in about five minutes — no migration required. From there, agents run inside your existing workflows. Add Slack approval checkpoints to high-risk steps so a human can approve or reject before the agent proceeds.",
  },
  {
    q: "Which AI model does Conduct use?",
    a: "Conduct automatically routes each agent step to the best model for the job. Security scans use Opus for maximum precision. Triage and summarization use Haiku to keep costs low. Code review uses Sonnet for balanced quality and speed. You set your optimization preference (Quality, Balanced, Speed, or Cost) per agent step — Conduct handles the routing. You can see exactly which model ran and the routing reason in every run trace.",
  },
  {
    q: "How is Conduct different from GitHub Copilot or other AI coding assistants?",
    a: "Copilot and coding assistants help individuals write code. Conduct gives teams reusable agent workflows for the work around code, with project configuration, credentials, run history, and approval gates built in.",
  },
  {
    q: "What specific agents come included?",
    a: `The Playbook Marketplace includes ${count} agents: Autopilot, PR Reviewer, Security Scanner, Security Patch Updater, Issue Triage, Flaky Test Detective, Release Readiness, Release Notes, CI Failure Alert, Incident Responder, Postmortem Drafter, Dependency Updater, Docs Drift Detector, Terraform Reviewer, and more. Each installs in one click — the canvas is pre-wired, just add credentials. Already-installed playbooks are tracked so you never create duplicates.`,
  },
  {
    q: "How long does it take to get up and running?",
    a: "Install a playbook from the Marketplace and your first agent can be running in minutes. Connecting GitHub and Slack takes about five minutes. The playbooks are pre-wired — there's no build phase before they're operational.",
  },
  {
    q: "Will our security team approve this?",
    a: "Conduct is designed for security-first teams. All secrets (API keys, tokens, webhook secrets) are encrypted with AES-256-GCM before they touch the database and decrypted only at runtime — never logged. Webhooks are verified with HMAC-SHA256 signatures. Approval gates are first-class blocks — nothing merges without a human gate via Slack DM. Role-based access (admin / editor / viewer) is enforced at the API level. Every action is event-sourced and audit-logged.",
  },
  {
    q: "What is ConductGuard and do I need it?",
    a: "ConductGuard is the team policy layer that sits on top of Conduct workflows and your developers' local AI tools. It's optional — Conduct works without it. You need Guard when you want to enforce spend limits, block risky actions, or get an audit trail of what every developer's AI tools are doing. Think of Conduct as the automation layer and Guard as the governance layer. Most teams start with Conduct playbooks and add Guard when they're ready to set team-wide policies.",
  },
  {
    q: "Does Guard only work with Conduct workflows, or does it cover local AI tools like Claude Code and Cursor?",
    a: "Both. Guard has two enforcement surfaces. Inside Conduct workflows, a Guard block evaluates policies mid-run and can halt a run before a sensitive action executes. Outside workflows, the PreToolUse hook (installed via 'conduct guard join') intercepts every Claude Code, Cursor, or compatible AI tool call on a developer's machine — before the call reaches the model. The same policies apply in both places.",
  },
  {
    q: "How does the spend cap work? Will it surprise developers?",
    a: "The team lead sets a monthly hard cap per developer in Guard → Settings. When a developer hits their cap, the next AI call is blocked at the hook level — the call never reaches the model. Guard posts a Slack alert when the block fires. The cap resets on the 1st of each month. The budget check is cached for 5 minutes locally, so there's no latency added to normal tool calls. Developers can see their current spend at any time by running 'conduct guard status'.",
  },
  {
    q: "If I add a Guard block to a workflow and a developer hasn't installed Guard, what happens?",
    a: "It depends on the enforcement_mode you set. With enforcement_mode: block (the default), the run halts and logs instructions telling the developer to run 'conduct guard join'. With enforcement_mode: warn or audit, the block logs a warning but the workflow continues — useful if you want to roll Guard out gradually without breaking existing workflows.",
  },
  {
    q: "Can Guard policies be different per project or per workflow?",
    a: "Policies are set at the team level and apply uniformly to all workflows and all developers on that team. You can target specific policies to specific tools using the match_tool field (e.g. only apply a rule when Claude Code is making a file write). Within a workflow, you can use the rule_ids field on a Guard block to evaluate only specific rules rather than all active policies.",
  },
  {
    q: "How does Guard fit into the approval gate model?",
    a: "They're complementary. Approval gates (the approval block in a workflow) pause execution and wait for a human to explicitly approve or reject via Slack. Guard blocks evaluate policies automatically without human input — they either pass or fail based on rules. A typical high-stakes workflow might have a Guard block check policies first, and then an approval block require a human sign-off before the final action runs.",
  },
]

function GitHubIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
      <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0 0 16 8c0-4.42-3.58-8-8-8z"/>
    </svg>
  )
}

function GoogleIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <path d="M15.68 8.18c0-.57-.05-1.12-.14-1.64H8v3.1h4.3a3.67 3.67 0 0 1-1.6 2.41v2h2.58c1.51-1.39 2.4-3.44 2.4-5.87z" fill="#4285F4"/>
      <path d="M8 16c2.16 0 3.97-.72 5.3-1.94l-2.59-2a4.8 4.8 0 0 1-2.71.75c-2.08 0-3.84-1.4-4.47-3.29H.86v2.07A8 8 0 0 0 8 16z" fill="#34A853"/>
      <path d="M3.53 9.52A4.8 4.8 0 0 1 3.28 8c0-.53.09-1.04.25-1.52V4.41H.86A8 8 0 0 0 0 8c0 1.29.31 2.51.86 3.59l2.67-2.07z" fill="#FBBC05"/>
      <path d="M8 3.18c1.17 0 2.22.4 3.05 1.2l2.28-2.28A8 8 0 0 0 .86 4.41L3.53 6.48C4.16 4.6 5.92 3.18 8 3.18z" fill="#EA4335"/>
    </svg>
  )
}
