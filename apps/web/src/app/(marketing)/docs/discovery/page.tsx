import Link from "next/link"

export const metadata = {
  title: "Agent Discovery — Conduct Docs",
  description:
    "How Conduct's Agent Discovery flow works. Every hook, MCP call, and proxy request registers an agent automatically — no SDK install, no manual registration.",
}

export default function DocsDiscoveryPage() {
  return (
    <div className="min-h-screen bg-white">
      <main className="max-w-3xl mx-auto px-6 py-20">
        <p className="text-xs font-mono font-bold uppercase tracking-widest text-stone-400 mb-4">
          Docs → Agent Discovery
        </p>
        <h1 className="text-3xl sm:text-4xl font-black tracking-tight text-stone-900 leading-[1.1] mb-4">
          Agent Discovery
        </h1>
        <p className="text-lg text-stone-500 leading-relaxed mb-10">
          Every hook, MCP call, and proxy request registers the agent automatically. No SDK install. No manual registration. Your agent fleet appears as it runs — Claude Code, Cursor, Codex, Copilot, MCP clients — so you know what Guard needs to enforce before you turn it on.
        </p>

        <section className="mb-10">
          <h2 className="text-lg font-bold text-stone-900 mb-3">What it surfaces</h2>
          <ul className="text-sm text-stone-600 space-y-2 list-disc pl-5">
            <li>Every agent tool active on developer machines and CI</li>
            <li>Which resources each tool has reached (files, endpoints, credentials)</li>
            <li>Frequency and cost of tool invocations</li>
            <li>Gaps where policy is missing</li>
          </ul>
        </section>

        <section className="mb-10">
          <h2 className="text-lg font-bold text-stone-900 mb-3">Trial timeline</h2>
          <ul className="text-sm text-stone-600 space-y-2 list-disc pl-5">
            <li>Day 0 — sign up, install CLI on one machine</li>
            <li>Day 1–2 — scan surfaces which tools your team runs</li>
            <li>Day 3–7 — first draft policies suggested from the scan</li>
            <li>Day 8–14 — trial enforcement with block-warn mode</li>
          </ul>
        </section>

        <section className="mb-10">
          <h2 className="text-lg font-bold text-stone-900 mb-3">See also</h2>
          <ul className="text-sm text-stone-600 space-y-2">
            <li>· <Link href="/guard" className="text-stone-900 font-semibold hover:underline">How Guard enforces</Link></li>
            <li>· <Link href="/evidence" className="text-stone-900 font-semibold hover:underline">What each decision leaves behind</Link></li>
            <li>· <Link href="/deployment" className="text-stone-900 font-semibold hover:underline">Where to run Guard</Link></li>
          </ul>
        </section>

        <div className="mt-16 pt-8 border-t border-stone-100 text-sm text-stone-400">
          Full docs shipping soon. Meanwhile: <Link href="/sign-up" className="text-stone-900 font-semibold hover:underline">start Agent Discovery</Link>.
        </div>
      </main>
    </div>
  )
}
