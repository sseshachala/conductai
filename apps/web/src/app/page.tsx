"use client"

import { useEffect } from "react"
import { useRouter } from "next/navigation"
import { useAuth, SignInButton } from "@clerk/nextjs"

export default function Home() {
  const router = useRouter()
  const clerkEnabled = !!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY

  // Without Clerk, go straight to app
  useEffect(() => {
    if (!clerkEnabled) router.replace("/projects")
  }, [clerkEnabled, router])

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
    <div className="min-h-screen bg-stone-50 flex flex-col">
      {/* Nav */}
      <header className="px-6 py-4 flex items-center justify-between max-w-5xl mx-auto w-full">
        <span className="font-bold text-stone-900 text-lg tracking-tight">Delegator</span>
        <SignInButton mode="modal">
          <button className="text-sm font-medium text-stone-600 hover:text-stone-900 transition-colors">
            Sign in →
          </button>
        </SignInButton>
      </header>

      {/* Hero */}
      <main className="flex-1 flex flex-col items-center justify-center px-6 text-center">
        <div className="inline-flex items-center gap-2 bg-indigo-50 text-indigo-700 text-xs font-medium px-3 py-1 rounded-full mb-6">
          <span className="w-1.5 h-1.5 rounded-full bg-indigo-500 inline-block" />
          AI-native engineering automation
        </div>

        <h1 className="text-4xl sm:text-5xl font-bold text-stone-900 leading-tight max-w-2xl">
          Your AI layer for<br />
          <span className="text-indigo-600">shipping faster</span>
        </h1>

        <p className="mt-5 text-stone-500 text-lg max-w-xl leading-relaxed">
          Delegator picks up tickets, writes code, runs tests, and opens PRs —
          with a human approving before anything ships.
        </p>

        <div className="mt-10">
          <SignInButton mode="modal">
            <button className="inline-flex items-center gap-3 bg-stone-900 hover:bg-stone-700 text-white font-medium px-6 py-3 rounded-xl text-sm transition-colors shadow-sm">
              <GoogleIcon />
              Request early access
            </button>
          </SignInButton>
          <p className="mt-3 text-xs text-stone-400">No credit card required</p>
        </div>

        <div className="mt-20 grid grid-cols-1 sm:grid-cols-3 gap-6 max-w-3xl w-full text-left">
          {FEATURES.map(f => (
            <div key={f.title} className="bg-white rounded-xl border border-stone-200 p-5">
              <div className="text-2xl mb-3">{f.icon}</div>
              <p className="text-sm font-semibold text-stone-900 mb-1">{f.title}</p>
              <p className="text-sm text-stone-500 leading-relaxed">{f.body}</p>
            </div>
          ))}
        </div>
      </main>

      <footer className="py-8 text-center text-xs text-stone-400">
        © {new Date().getFullYear()} Delegator
      </footer>
    </div>
  )
}

const FEATURES = [
  {
    icon: "⚡",
    title: "Ticket to PR",
    body: "Label a GitHub issue and Delegator writes the code, runs tests, and opens the PR.",
  },
  {
    icon: "🔍",
    title: "Full auditability",
    body: "Every action is logged. See exactly what the AI did, what it cost, and how long it took.",
  },
  {
    icon: "✋",
    title: "Human approval gates",
    body: "Nothing ships without your sign-off. You stay in control of what hits production.",
  },
]

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
