"use client"

import { useEffect } from "react"
import { useRouter } from "next/navigation"
import { useAuth, SignInButton } from "@clerk/nextjs"

export default function Home() {
  const clerkEnabled = !!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY

  useEffect(() => {
    if (!clerkEnabled) window.location.replace("/projects")
  }, [clerkEnabled])

  if (!clerkEnabled) return null
  return <LandingPage />
}

function LandingPage() {
  const router = useRouter()
  const { isSignedIn, isLoaded } = useAuth()

  useEffect(() => {
    if (isLoaded && isSignedIn) router.replace("/projects")
  }, [isLoaded, isSignedIn, router])

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
          <span className="font-bold text-stone-900 text-base tracking-tight">Delegator</span>
        </div>
        <SignInButton mode="modal">
          <button className="text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">
            Sign in →
          </button>
        </SignInButton>
      </header>

      {/* Hero */}
      <section className="flex-1 flex flex-col items-center justify-center px-6 pt-16 pb-24 text-center">
        <div className="inline-flex items-center gap-2 bg-stone-100 text-stone-600 text-xs font-medium px-3 py-1.5 rounded-full mb-8">
          <span className="w-1.5 h-1.5 rounded-full bg-green-500 inline-block" />
          Now in early access — request your invite
        </div>

        <h1 className="text-5xl sm:text-6xl font-bold text-stone-900 leading-[1.1] tracking-tight max-w-3xl">
          Your engineering team,<br />
          <span className="text-indigo-600">with an AI co-pilot</span>
        </h1>

        <p className="mt-6 text-xl text-stone-500 max-w-2xl leading-relaxed">
          Delegator picks up tickets, writes the code, runs tests, and opens pull requests —
          while your team stays in control of every merge.
        </p>

        <div className="mt-10 flex flex-col sm:flex-row items-center gap-4">
          <SignInButton mode="modal">
            <button className="inline-flex items-center gap-3 bg-stone-900 hover:bg-stone-700 text-white font-semibold px-7 py-3.5 rounded-xl text-sm transition-colors shadow-sm">
              <GoogleIcon />
              Request early access
            </button>
          </SignInButton>
          <p className="text-xs text-stone-400">Free during early access · No credit card</p>
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

      {/* Why Delegator — the moat */}
      <section className="px-6 py-20">
        <div className="max-w-5xl mx-auto">
          <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest text-center mb-3">Why Delegator</p>
          <h2 className="text-3xl font-bold text-stone-900 text-center mb-12">
            Not just another AI tool.<br />An AI teammate.
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
        <h2 className="text-3xl font-bold text-stone-900 mb-4">Ready to delegate?</h2>
        <p className="text-stone-500 mb-8 max-w-md mx-auto">
          Join engineering teams using Delegator to ship faster without losing control.
        </p>
        <SignInButton mode="modal">
          <button className="inline-flex items-center gap-3 bg-stone-900 hover:bg-stone-700 text-white font-semibold px-7 py-3.5 rounded-xl text-sm transition-colors">
            <GoogleIcon />
            Request early access
          </button>
        </SignInButton>
      </section>

      <footer className="border-t border-stone-100 py-8 text-center text-xs text-stone-400">
        © {new Date().getFullYear()} Delegator · Built for engineering teams
      </footer>
    </div>
  )
}

const HOW_IT_WORKS = [
  {
    title: "Connect your tools",
    body: "Link GitHub, Linear, and Slack in minutes. No migration, no new workflow — Delegator fits around what you already use.",
  },
  {
    title: "Delegator picks up the work",
    body: "Label an issue 'autopilot ready' or trigger a workflow. Delegator clones the repo, implements the fix, runs tests, and opens a PR.",
  },
  {
    title: "You review and approve",
    body: "Nothing merges without your sign-off. You get a Slack notification with the PR link and a full audit trail of every action taken.",
  },
]

const WHY_DELEGATOR = [
  {
    icon: "⚡",
    title: "Pre-built SDLC workflows",
    body: "Not a blank canvas. Delegator ships with battle-tested workflows for common engineering tasks — Autopilot, Story→PR, Deploy — ready to connect to your stack.",
  },
  {
    icon: "🔒",
    title: "Human approval on every merge",
    body: "Approval gates are first-class, not an afterthought. Every workflow has a checkpoint where a human reviews before anything ships to production.",
  },
  {
    icon: "🔍",
    title: "Full audit trail",
    body: "Every action is logged — what the AI read, what it wrote, what it ran, how long it took, what it cost. Debug any run in seconds.",
  },
  {
    icon: "🧩",
    title: "Fits your existing tools",
    body: "No new issue tracker. No new chat tool. No new CI system. Delegator plugs into GitHub, Linear, Slack, and Vercel — the tools your team already lives in.",
  },
]

const INTEGRATIONS = ["GitHub", "Linear", "Slack", "Vercel", "Railway", "DigitalOcean", "Email"]

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
