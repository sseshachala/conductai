import type { Metadata } from "next"
import Image from "next/image"
import { CheckCircle2, ArrowRight } from "lucide-react"

export const metadata: Metadata = {
  title: "CLI connected",
  robots: { index: false, follow: false },
  referrer: "no-referrer",
}

export default function CliConnectedPage() {
  return (
    <main className="min-h-dvh bg-white px-6 py-10 text-zinc-900 flex flex-col items-center">
      <a href="https://conductai.ai" aria-label="Conduct AI home" className="flex items-center gap-3 text-xl font-semibold">
        <Image src="/logo.png" alt="" width={36} height={36} />
        Conduct AI
      </a>
      <section className="flex flex-1 flex-col items-center justify-center text-center w-full max-w-lg py-16" aria-labelledby="connected-title">
        <CheckCircle2 size={48} strokeWidth={1.5} className="text-emerald-600 mb-6" aria-hidden="true" />
        <h1 id="connected-title" className="text-3xl font-semibold leading-tight">You&apos;re signed in.</h1>
        <p className="mt-4 text-lg text-zinc-600">You can close this tab and return to your terminal.</p>
        <a href="https://app.conductai.ai/theguard" className="mt-8 inline-flex items-center gap-2 rounded-md bg-zinc-900 px-5 py-3 text-sm font-medium text-white hover:bg-zinc-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-zinc-900">
          Open Conduct <ArrowRight size={16} aria-hidden="true" />
        </a>
      </section>
      <p className="text-sm text-zinc-500">Conduct CLI</p>
    </main>
  )
}
