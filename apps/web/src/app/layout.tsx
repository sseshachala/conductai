import type { Metadata } from "next"
import Script from "next/script"
import "./globals.css"
import { ClerkProvider } from "@clerk/nextjs"

export const metadata: Metadata = {
  title: "Conduct AI — Governed AI Automations for Engineering Teams",
  description:
    "Conduct turns tickets, PRs, alerts, and incidents into auditable AI agent workflows with human approval before anything ships.",
  icons: {
    icon: "/icon.png",
    shortcut: "/icon.png",
    apple: "/icon.png",
  },
  openGraph: {
    title: "Conduct AI — Governed AI Automations for Engineering Teams",
    description:
      "Conduct turns tickets, PRs, alerts, and incidents into auditable AI agent workflows with human approval before anything ships.",
    url: "https://conductai.ai",
    siteName: "Conduct",
    type: "website",
    images: [
      {
        url: "https://conductai.ai/og.png",
        width: 1200,
        height: 630,
        alt: "Conduct — governed AI automations for engineering teams",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "Conduct AI — Governed AI Automations for Engineering Teams",
    description:
      "Auditable AI agent workflows for tickets, PRs, alerts, and incidents.",
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
  "description": "Governed AI automations for engineering teams. Turn tickets, PRs, alerts, and incidents into auditable workflows with human approval before anything merges.",
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
    "Workspace-scoped sandbox execution",
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
      <ClerkProvider afterSignInUrl="/guard" afterSignUpUrl="/guard">
        <html lang="en">
          <head>{jsonLd}</head>
          <body>
            {children}
            <Script src="https://narratr.ai/widget.js" data-brand-key="c7ae7b0c-2b6" strategy="afterInteractive" />
            <Script src="https://narratr.ai/embed.js" data-brand="conductai" strategy="afterInteractive" />
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
