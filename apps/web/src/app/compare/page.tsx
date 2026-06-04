import type { Metadata } from "next"
import HtmlPrototypeFrame from "@/components/HtmlPrototypeFrame"

export const metadata: Metadata = {
  title: "AI Engineering Tools Compared | Conduct AI",
  description: "Honest side-by-side comparison of Conduct AI, GitHub Copilot, Devin, CodeRabbit, LinearB, Bito, Amazon Q, and xHawk — features, trade-offs, and which tool fits your team.",
  openGraph: {
    title: "AI Engineering Tools Compared | Conduct AI",
    description: "Honest side-by-side comparison of the leading AI engineering tools. Features, trade-offs, and decision guide.",
    url: "https://conductai.ai/compare",
    siteName: "Conduct AI",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "AI Engineering Tools Compared | Conduct AI",
    description: "Honest side-by-side comparison of the leading AI engineering tools.",
  },
}

export default function ComparePage() {
  return <HtmlPrototypeFrame title="Conduct Compare Page" src="/conduct-pages/conduct-compare.html" />
}
