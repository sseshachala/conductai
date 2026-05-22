import type { Metadata } from "next"
import "./globals.css"
import { ClerkProvider } from "@clerk/nextjs"

export const metadata: Metadata = {
  title: "Conduct — 9 Pre-Built AI Agents for GitHub Workflows",
  description:
    "Conduct ships 9 pre-built AI agents that execute inside GitHub, Slack, and your alerting stack. No prompt engineering. No custom infrastructure. Human approval before anything merges.",
  icons: {
    icon: "/icon.svg",
    shortcut: "/icon.svg",
    apple: "/icon.svg",
  },
  openGraph: {
    title: "Conduct — 9 Pre-Built AI Agents for GitHub Workflows",
    description:
      "Conduct ships 9 pre-built AI agents that execute inside GitHub, Slack, and your alerting stack. Human approval before anything merges.",
    url: "https://conductai.ai",
    siteName: "Conduct",
    type: "website",
    images: [
      {
        url: "https://conductai.ai/og.png",
        width: 1200,
        height: 630,
        alt: "Conduct — AI agents for GitHub workflows",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "Conduct — 9 Pre-Built AI Agents for GitHub Workflows",
    description:
      "AI agents that execute inside your stack. Human approval before anything merges.",
  },
}

const clerkEnabled = !!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY

export default function RootLayout({ children }: { children: React.ReactNode }) {
  if (clerkEnabled) {
    return (
      <ClerkProvider>
        <html lang="en">
          <body>{children}</body>
        </html>
      </ClerkProvider>
    )
  }
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  )
}
