import Link from "next/link"

export const metadata = {
  title: "Start Discovery — Conduct",
  description:
    "Discovery scans the AI tools your team is already using and shows you what runs where. 14-day trial, no infrastructure changes.",
}

export default function DiscoveryPage() {
  return (
    <div className="min-h-screen bg-white">
      <main className="max-w-4xl mx-auto px-6 py-24 text-center">
        <p className="text-xs font-mono font-bold uppercase tracking-widest text-stone-400 mb-4">
          Discovery
        </p>
        <h1 className="text-4xl sm:text-5xl font-black tracking-tight text-stone-900 leading-[1.05] mb-6">
          See every AI agent in your stack.
        </h1>
        <p className="text-lg text-stone-500 max-w-2xl mx-auto leading-relaxed mb-10">
          14 days. No infrastructure changes. Point Conduct at your engineering
          tools and we surface which agents are running, what they touch, and
          where policy is missing.
        </p>
        <div className="flex flex-wrap justify-center gap-3">
          <Link
            href="/sign-up"
            className="inline-block rounded-xl bg-stone-900 text-white px-7 py-3.5 text-sm font-semibold hover:bg-stone-700 transition-colors"
          >
            Start Discovery — 14 days free
          </Link>
          <Link
            href="/guard"
            className="inline-block rounded-xl border border-stone-200 bg-white text-stone-700 px-7 py-3.5 text-sm font-semibold hover:bg-stone-50 transition-colors"
          >
            How Guard enforces →
          </Link>
        </div>
        <p className="mt-12 text-sm text-stone-400">
          Full pillar page shipping soon.
        </p>
      </main>
    </div>
  )
}
