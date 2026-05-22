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
          <div className="w-7 h-7 rounded-lg bg-stone-900 flex items-center justify-center">
            <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
          </div>
          <span className="font-bold text-stone-900 text-base tracking-tight">Deligators</span>
        </div>
        {isLoaded && (
          isSignedIn ? (
            <button
              onClick={() => router.push("/projects")}
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
          Deligators ships with 9 ready-made agents — label a GitHub issue, get a PR.
          CI fails, get a diagnosis. Alert fires, get a hypothesis. All in Slack.
          Nothing merges without your approval.
        </p>

        <div className="mt-10 flex flex-col sm:flex-row items-center gap-4">
          {isLoaded && (
            isSignedIn ? (
              <button
                onClick={() => router.push("/projects")}
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

      {/* How it works */}
      <section className="bg-stone-50 px-6 py-20">
        <div className="max-w-4xl mx-auto">
          <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest text-center mb-12">How it works</p>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-8">
            {HOW_IT_WORKS.map((step, i) => (
              <div key={step.title} className="text-center">
                <div className="w-10 h-10 rounded-xl bg-indigo-600 text-white text-sm font-bold flex items-center justify-center mx-auto mb-4">
                  {i + 1}
                </div>
                <p className="font-semibold text-stone-900 mb-2">{step.title}</p>
                <p className="text-sm text-stone-500 leading-relaxed">{step.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Why Deligators — the moat */}
      <section className="px-6 py-20">
        <div className="max-w-5xl mx-auto">
          <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest text-center mb-3">Why Deligators</p>
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
          {isLoaded && isSignedIn ? "Ready to delegate?" : "Try it in 30 seconds"}
        </h2>
        <p className="text-stone-500 mb-8 max-w-md mx-auto">
          {isLoaded && isSignedIn
            ? "Head to your projects and connect your first repo."
            : "Sign in with Google, connect your GitHub repo, and let Deligators pick up its first ticket."}
        </p>
        {isLoaded && (
          isSignedIn ? (
            <button
              onClick={() => router.push("/projects")}
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

      <footer className="border-t border-stone-100 py-8 text-center text-xs text-stone-400">
        © {new Date().getFullYear()} Deligators · Built for engineering teams
      </footer>
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

const HOW_IT_WORKS = [
  {
    title: "Connect your tools",
    body: "Link GitHub, Slack, and Linear in five minutes. No migration, no new workflow — Deligators fits around what you already use.",
  },
  {
    title: "Deligators picks up the work",
    body: "Label an issue `ai-ready` or fire a webhook. Deligators spins up an ephemeral sandbox, clones your repo, implements the fix, and runs your tests.",
  },
  {
    title: "You approve in Slack",
    body: "One-click Approve or Reject in a Slack DM. Nothing merges without a human gate. Every step is event-sourced — debug any run in seconds.",
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
    body: "GitHub, Slack, PagerDuty, OpsGenie, email, and any inbound webhook. No new tools, no migration — Deligators plugs into what your team already uses.",
  },
]

const INTEGRATIONS = ["GitHub", "Slack", "PagerDuty", "OpsGenie", "Email / Resend", "Any webhook"]

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
