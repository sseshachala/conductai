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

  const themeScript = `(function(){
    var ACCENTS={indigo:{base:"#4f46e5",hover:"#4338ca",ring:"#818cf8",weak:"#eef2ff",weak2:"#e0e7ff",text:"#4338ca"},violet:{base:"#7c3aed",hover:"#6d28d9",ring:"#a78bfa",weak:"#f5f3ff",weak2:"#ede9fe",text:"#6d28d9"},emerald:{base:"#059669",hover:"#047857",ring:"#34d399",weak:"#ecfdf5",weak2:"#d1fae5",text:"#047857"},blue:{base:"#2563eb",hover:"#1d4ed8",ring:"#93c5fd",weak:"#eff6ff",weak2:"#dbeafe",text:"#1d4ed8"},amber:{base:"#d97706",hover:"#b45309",ring:"#fcd34d",weak:"#fffbeb",weak2:"#fef3c7",text:"#b45309"}};
    var look=localStorage.getItem("conduct-theme")||"light";
    var acc=localStorage.getItem("conduct-accent")||"indigo";
    var A=ACCENTS[acc]||ACCENTS.indigo;
    var dark=look==="dark";
    document.documentElement.setAttribute("data-theme",dark?"dark":"light");
    var r=document.documentElement.style;
    r.setProperty("--accent",A.base);
    r.setProperty("--accent-hover",dark?A.ring:A.hover);
    r.setProperty("--accent-ring",A.ring);
    r.setProperty("--accent-weak",dark?"color-mix(in srgb, "+A.base+" 18%, transparent)":A.weak);
    r.setProperty("--accent-weak-2",dark?"color-mix(in srgb, "+A.base+" 30%, transparent)":A.weak2);
    r.setProperty("--accent-text",dark?A.ring:A.text);
  })()`

  if (clerkEnabled) {
    return (
      <ClerkProvider afterSignInUrl="/workflows" afterSignUpUrl="/setup">
        <html lang="en">
          <head>
            {jsonLd}
            <script dangerouslySetInnerHTML={{ __html: themeScript }} />
          </head>
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
      <head>
        {jsonLd}
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body>
        {children}
        <Script src="https://narratr.ai/widget.js" data-brand-key="c7ae7b0c-2b6" strategy="afterInteractive" />
      </body>
    </html>
  )
}
