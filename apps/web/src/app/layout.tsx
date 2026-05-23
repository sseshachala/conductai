import type { Metadata } from "next"
import Script from "next/script"
import "./globals.css"
import { ClerkProvider } from "@clerk/nextjs"

export const metadata: Metadata = {
  title: "Conduct AI — 11 Pre-Built AI Agents for GitHub Workflows",
  description:
    "Conduct AI ships 11 pre-built AI agents that execute inside GitHub, Slack, and your alerting stack. No prompt engineering. No custom infrastructure. Human approval before anything merges.",
  icons: {
    icon: "/icon.png",
    shortcut: "/icon.png",
    apple: "/icon.png",
  },
  openGraph: {
    title: "Conduct AI — 11 Pre-Built AI Agents for GitHub Workflows",
    description:
      "Conduct AI ships 11 pre-built AI agents that execute inside GitHub, Slack, and your alerting stack. Human approval before anything merges.",
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
    title: "Conduct AI — 11 Pre-Built AI Agents for GitHub Workflows",
    description:
      "AI agents that execute inside your stack. Human approval before anything merges.",
  },
}

const clerkEnabled = !!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY

const softwareAppJsonLd = {
  "@context": "https://schema.org",
  "@type": "SoftwareApplication",
  "name": "Conduct",
  "applicationCategory": "DeveloperApplication",
  "operatingSystem": "Web",
  "url": "https://conductai.ai",
  "description": "9 pre-built AI agents for GitHub workflows. Automate issue triage, PR reviews, incident response, and release notes — with human approval before anything merges.",
  "offers": {
    "@type": "Offer",
    "price": "0",
    "priceCurrency": "USD",
  },
  "featureList": [
    "Autopilot: GitHub issue to pull request",
    "PR Reviewer",
    "Issue Triage",
    "Release Notes generator",
    "Incident Responder",
    "Dependency Updater",
    "Deploy Monitor",
    "Human approval gates via Slack",
    "Ephemeral sandbox execution",
  ],
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  const jsonLd = (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{ __html: JSON.stringify(softwareAppJsonLd) }}
    />
  )

  if (clerkEnabled) {
    return (
      <ClerkProvider>
        <html lang="en">
          <head>{jsonLd}</head>
          <body>
            {children}
            <Script src="https://narratr.ai/widget.js" data-brand-key="c7ae7b0c-2b6" strategy="afterInteractive" />
            <Script src="https://narratr.ai/embed.js" data-brand="conduct-agentic" strategy="afterInteractive" />
          </body>
        </html>
      </ClerkProvider>
    )
  }
  return (
    <html lang="en">
      <head>{jsonLd}</head>
      <body>
        {children}
        <Script src="https://narratr.ai/widget.js" data-brand-key="c7ae7b0c-2b6" strategy="afterInteractive" />
      </body>
    </html>
  )
}
