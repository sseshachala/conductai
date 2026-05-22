"use client"

import { useRouter } from "next/navigation"
import { useAuth, SignInButton } from "@clerk/nextjs"

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

  return (
    <div className="min-h-screen bg-white flex flex-col">

      {/* Nav */}
      <header className="px-6 py-5 flex items-center justify-between max-w-6xl mx-auto w-full">
        <div className="flex items-center gap-2">
          <img src="/icon.svg" alt="Conduct" className="w-7 h-7" />
          <span className="font-bold text-stone-900 text-base tracking-tight">Conduct</span>
        </div>
        <div className="flex items-center gap-4">
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
          Your AI engineering team.<br />
          <span className="text-indigo-600">Running 24 / 7.</span>
        </h1>

        <p className="mt-6 text-xl text-stone-500 max-w-2xl leading-relaxed">
          Conduct ships with 9 ready-made agents — label a GitHub issue, get a PR.
          CI fails, get a diagnosis. Alert fires, get a hypothesis. All in Slack.
          Nothing merges without your approval.
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
                  <GoogleIcon />
                  Sign in with Google — it&apos;s free
                </button>
              </SignInButton>
            ) : null
          )}
          {isLoaded && !isSignedIn && clerkEnabled && (
            <p className="text-xs text-stone-400">No credit card · No setup · Just your Google account</p>
          )}
        </div>

        {/* Post-sign-in next steps — only shown when signed in */}
        {isLoaded && isSignedIn && (
          <div className="mt-8 bg-stone-50 border border-stone-200 rounded-2xl px-6 py-5 max-w-md w-full text-left">
            <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-3">Get started in 3 steps</p>
            <ol className="space-y-2.5">
              {[
                { n: "1", text: "Create a project and connect your GitHub repo" },
                { n: "2", text: "Pick an agent template (Autopilot is a good first one)" },
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

      {/* Trust strip */}
      <div className="border-y border-stone-100 bg-stone-50 py-4 px-6">
        <div className="max-w-3xl mx-auto flex flex-wrap items-center justify-center gap-6 text-xs font-medium text-stone-500">
          <span className="flex items-center gap-1.5"><span className="w-1.5 h-1.5 rounded-full bg-emerald-400 inline-block"/>9 ready-made agents</span>
          <span className="flex items-center gap-1.5"><span className="w-1.5 h-1.5 rounded-full bg-emerald-400 inline-block"/>Zero prompt engineering</span>
          <span className="flex items-center gap-1.5"><span className="w-1.5 h-1.5 rounded-full bg-emerald-400 inline-block"/>Human approval on every merge</span>
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
          </div>
          <div className="flex flex-col gap-2 shrink-0 text-sm">
            <div className="flex items-center gap-2 text-stone-300"><span className="text-emerald-400">✓</span> Executes tasks, not suggestions</div>
            <div className="flex items-center gap-2 text-stone-300"><span className="text-emerald-400">✓</span> Pauses for human approval</div>
            <div className="flex items-center gap-2 text-stone-300"><span className="text-emerald-400">✓</span> Full audit trail, every run</div>
          </div>
        </div>
      </section>

      {/* Templates */}
      <section className="px-6 py-20">
        <div className="max-w-6xl mx-auto">
          <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest text-center mb-3">Ready-made agents</p>
          <h2 className="text-3xl font-bold text-stone-900 text-center mb-4">
            Start from a real playbook.<br />Not a blank canvas.
          </h2>
          <p className="text-center text-stone-500 text-sm max-w-xl mx-auto mb-12">
            Every agent ships with a working YAML playbook. Connect your tools, pick a template, and your first run happens in minutes.
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
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
        </div>
      </section>

      {/* 3-step setup */}
      <section className="bg-stone-50 px-6 py-20">
        <div className="max-w-4xl mx-auto">
          <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest text-center mb-3">Setup in minutes</p>
          <h2 className="text-2xl font-bold text-stone-900 text-center mb-12">Live on day one.</h2>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-6">
            {[
              { step: "1", icon: "🔗", title: "Connect your repo", body: "Link GitHub, Slack, and Linear. No migration, no new tooling — Conduct wraps around what you already use." },
              { step: "2", icon: "⚡", title: "Assign an agent", body: "Pick a template or build on the canvas. Set your environment credentials. The agent is ready to run." },
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

      {/* Why Conduct — the moat */}
      <section className="px-6 py-20">
        <div className="max-w-5xl mx-auto">
          <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest text-center mb-3">Why Conduct</p>
          <h2 className="text-3xl font-bold text-stone-900 text-center mb-12">
            Not just another AI tool.<br />An AI teammate you can trust.
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
            {WHY_DELEGATOR.map(f => (
              <div key={f.title} className="bg-white rounded-2xl border border-stone-200 p-6">
                <div className="text-2xl mb-3">{f.icon}</div>
                <p className="font-semibold text-stone-900 mb-1.5">{f.title}</p>
                <p className="text-sm text-stone-500 leading-relaxed">{f.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Integrations */}
      <section className="bg-stone-50 px-6 py-16">
        <div className="max-w-3xl mx-auto text-center">
          <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-8">Works with your existing stack</p>
          <div className="flex flex-wrap justify-center gap-3">
            {INTEGRATIONS.map(i => (
              <span key={i} className="bg-white border border-stone-200 text-stone-600 text-sm font-medium px-4 py-2 rounded-lg">
                {i}
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
            : "Sign in with Google, connect your GitHub repo, and let Conduct pick up its first ticket."}
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
                <button className="inline-flex items-center gap-3 bg-stone-900 hover:bg-stone-700 text-white font-semibold px-7 py-3.5 rounded-xl text-sm transition-colors">
                  <GoogleIcon />
                  Get started — it&apos;s free
                </button>
              </SignInButton>
              <p className="text-xs text-stone-400 mt-4">No credit card · Instant access · Sign in with Google</p>
            </>
          ) : null
        )}
      </section>

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
              <p className="text-stone-500 text-xs mb-3"># Install</p>
              <p className="text-emerald-400">pip install conduct-cli</p>
              <p className="text-stone-500 text-xs mt-4 mb-3"># Run an agent</p>
              <p className="text-white">conduct --server https://api.conductai.ai \</p>
              <p className="text-white pl-4">--api-key YOUR_KEY \</p>
              <p className="text-white pl-4">run autopilot.yaml</p>
            </div>
            <div className="rounded-xl bg-stone-950 p-5 font-mono text-sm">
              <p className="text-stone-500 text-xs mb-3"># autopilot.yaml</p>
              <p className="text-violet-400">name<span className="text-white">: Fix GitHub Issue</span></p>
              <p className="text-violet-400">workflow_id<span className="text-white">: abc-123</span></p>
              <p className="text-violet-400">trigger<span className="text-white">:</span></p>
              <p className="text-white pl-4">event_type<span className="text-stone-400">: github_issue_labeled</span></p>
              <p className="text-white pl-4">label<span className="text-stone-400">: ai-ready</span></p>
              <p className="text-white pl-4">repo<span className="text-stone-400">:</span></p>
              <p className="text-white pl-8">full_name<span className="text-stone-400">: your-org/repo</span></p>
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
            {FAQ.map(({ q, a }) => (
              <div key={q} className="border-b border-stone-100 pb-6 last:border-0">
                <p className="font-semibold text-stone-900 mb-2">{q}</p>
                <p className="text-sm text-stone-500 leading-relaxed">{a}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <footer className="border-t border-stone-100 py-8 text-center text-xs text-stone-400">
        © {new Date().getFullYear()} Conduct · Built for engineering teams ·{" "}
        <a
          href="https://github.com/sseshachala/conductai"
          target="_blank"
          rel="noopener noreferrer"
          className="hover:text-stone-600 transition-colors"
        >
          GitHub
        </a>
        {" · MIT licensed"}
      </footer>

      {/* FAQ JSON-LD structured data */}
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify({
          "@context": "https://schema.org",
          "@type": "FAQPage",
          "mainEntity": FAQ.map(({ q, a }) => ({
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
]


const WHY_DELEGATOR = [
  {
    icon: "🔒",
    title: "Human approval on every merge",
    body: "Approval gates are first-class blocks, not an afterthought. Every workflow has a Slack checkpoint before anything ships. The thing your CISO will actually sign off on.",
  },
  {
    icon: "📂",
    title: "Open source, config-as-code",
    body: "MIT licensed. The workflow lives as `<project>-delegator.yml` in your repo — diffable, reviewable in PRs, version-controlled like any other config. No black box.",
  },
  {
    icon: "🏠",
    title: "Isolated sandboxes, every run",
    body: "Each agent run executes in an ephemeral Modal sandbox — spun up, used, torn down. Your code and credentials never touch shared infrastructure.",
  },
  {
    icon: "🔍",
    title: "Full audit trail, zero surprises",
    body: "Every action is event-sourced — what the AI read, what it wrote, what it ran, how long it took, what it cost. Debug any run by scrubbing through the trace.",
  },
  {
    icon: "⚡",
    title: "9 pre-built agents, ready to run",
    body: "Autopilot, PR Reviewer, Issue Triage, Release Notes, CI Failure Alert, Incident Responder, Dependency Updater. Pick a template, first run in minutes — not days.",
  },
  {
    icon: "🧩",
    title: "Fits your existing stack",
    body: "GitHub, Slack, PagerDuty, OpsGenie, email, and any inbound webhook. No new tools, no migration — Conduct plugs into what your team already uses.",
  },
]

const INTEGRATIONS = ["GitHub", "Slack", "PagerDuty", "OpsGenie", "Email / Resend", "Any webhook"]

const FAQ = [
  {
    q: "What does Conduct actually do?",
    a: "Conduct ships 9 pre-built AI agents that execute directly inside GitHub and alerting workflows. The agents handle discrete engineering tasks — labeling issues, opening pull requests, generating incident hypotheses from alerts, writing release notes, and more. Nothing needs to be built from scratch.",
  },
  {
    q: "Is Conduct a good fit for my engineering team?",
    a: "Conduct is built for software engineering teams and engineering managers running GitHub-based workflows who want to automate repetitive developer tasks without building custom AI infrastructure. If your team is already using GitHub, Slack, and Linear, Conduct fits around those tools without requiring a migration or workflow overhaul.",
  },
  {
    q: "How does Conduct work once it's connected to our stack?",
    a: "Link GitHub, Slack, and Linear in about five minutes — no migration required. From there, agents run inside your existing workflows. Every workflow includes a Slack approval checkpoint before anything ships — one-click Approve or Reject in a DM.",
  },
  {
    q: "How is Conduct different from GitHub Copilot or other AI coding assistants?",
    a: "Conduct is a team substitute, not a copilot. Agents take ownership of full tasks like opening a PR or responding to an incident, rather than offering suggestions you still have to act on. The 9 agents ship pre-configured and ready to run — no framework to wire up, no prompts to engineer.",
  },
  {
    q: "What specific agents come included?",
    a: "The pre-built suite includes Autopilot, PR Reviewer, Issue Triage, Release Notes, CI Failure Alert, Incident Responder, Dependency Updater, Deploy Monitor, and Scheduled Report — 9 agents total. Each is pre-configured with sensible defaults and editable on the canvas.",
  },
  {
    q: "How long does it take to get up and running?",
    a: "Pick a template and you can have your first agent running in minutes, not days. Connecting GitHub, Slack, and Linear takes about five minutes, and the agents are pre-configured — there's no build phase before they're operational.",
  },
  {
    q: "Will our security team approve this?",
    a: "Conduct is designed with approval gates as first-class blocks — nothing merges without a human gate via Slack DM. Agents run in ephemeral sandboxes when executing code changes, limiting exposure. Every action is event-sourced and audit-logged.",
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
