import Link from "next/link"

export const metadata = {
  title: "Book a Demo — Conduct",
  description:
    "Talk to the Conduct team. Runtime policy across every AI agent — allow, approve, block, prove.",
}

export default function BookDemoPage() {
  return (
    <div className="min-h-screen bg-white">
      <main className="max-w-3xl mx-auto px-6 py-24 text-center">
        <p className="text-xs font-mono font-bold uppercase tracking-widest text-stone-400 mb-4">
          Book a Demo
        </p>
        <h1 className="text-4xl sm:text-5xl font-black tracking-tight text-stone-900 leading-[1.05] mb-6">
          Talk to the team.
        </h1>
        <p className="text-lg text-stone-500 max-w-xl mx-auto leading-relaxed mb-10">
          One policy across your AI agent stack — allow, approve, block, prove.
          Fifteen minutes with a founder, tailored to your stack.
        </p>
        <div className="flex flex-wrap justify-center gap-3 mb-6">
          <a
            href="mailto:sales@conductai.ai?subject=Conduct%20Demo%20Request"
            className="inline-block rounded-xl bg-stone-900 text-white px-7 py-3.5 text-sm font-semibold hover:bg-stone-700 transition-colors"
          >
            Email us to schedule
          </a>
          <Link
            href="/sign-up"
            className="inline-block rounded-xl border border-stone-200 bg-white text-stone-700 px-7 py-3.5 text-sm font-semibold hover:bg-stone-50 transition-colors"
          >
            Or start Discovery — 14 days free
          </Link>
        </div>
        <p className="mt-8 text-sm text-stone-400">
          Prefer chat? sales@conductai.ai
        </p>
      </main>
    </div>
  )
}
