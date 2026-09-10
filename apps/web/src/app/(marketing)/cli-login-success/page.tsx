import type { Metadata } from "next"

export const metadata: Metadata = {
  title: "CLI login successful · Conduct AI",
  description: "Your Conduct CLI is authenticated.",
  robots: { index: false, follow: false },
}

export default function CliLoginSuccessPage() {
  return (
    <div className="max-w-xl mx-auto px-6 py-24 text-center">
      <div className="mx-auto mb-6 h-14 w-14 rounded-full bg-emerald-50 flex items-center justify-center">
        <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="text-emerald-600" aria-hidden="true">
          <path d="M20 6L9 17l-5-5" />
        </svg>
      </div>
      <h1 className="text-3xl font-semibold text-stone-900 mb-3">You're signed in</h1>
      <p className="text-stone-500 leading-relaxed mb-8">
        Your Conduct CLI is authenticated. You can close this tab and return to your terminal.
      </p>
      <div className="rounded-lg border border-stone-200 bg-stone-50 px-4 py-3 text-left font-mono text-sm text-stone-700">
        <span className="text-stone-400">$</span> conduct guard status
      </div>
      <div className="mt-8 flex items-center justify-center gap-4 text-sm">
        <a href="/docs" className="text-stone-500 hover:text-stone-900 transition-colors">Docs</a>
        <span className="text-stone-300">·</span>
        <a href="/tools/conduct-cli" className="text-stone-500 hover:text-stone-900 transition-colors">CLI reference</a>
      </div>
    </div>
  )
}
