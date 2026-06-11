import type { Metadata } from "next"

export const metadata: Metadata = { title: "Docs — Conduct AI" }

export default function DocsLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>
}
