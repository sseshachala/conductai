import type { Metadata } from "next"
import Script from "next/script"
import "./globals.css"
import { ClerkProvider } from "@clerk/nextjs"

export const metadata: Metadata = {
  metadataBase: new URL("https://conductai.ai"),
  title: {
    default: "ConductAI: Runtime Governance for AI Agents",
    template: "%s | ConductAI",
  },
  description:
    "Runtime governance for AI agents. Allow, warn, or block every model and tool call before it commits. Hash-chained audit for every decision. Compliance packs for SOC 2, HIPAA, PCI DSS, EU AI Act, SR 11-7, FDA CSA, and more.",
  keywords: [
    "runtime governance",
    "AI agent governance",
    "agentic AI governance",
    "AI governance platform",
    "runtime AI governance",
    "AI agent identity",
    "agent policy enforcement",
    "AI audit trail",
    "AI compliance SOC 2",
    "EU AI Act compliance",
    "SR 11-7 agents",
    "FDA CSA agents",
    "Claude Code governance",
    "Cursor governance",
    "Copilot governance",
  ],
  authors: [{ name: "ConductAI" }],
  alternates: {
    canonical: "https://conductai.ai",
  },
  icons: {
    icon: "/icon.png",
    shortcut: "/icon.png",
    apple: "/icon.png",
  },
  openGraph: {
    title: "ConductAI: Runtime Governance for AI Agents",
    description:
      "Policy is a document. Runtime is a hook. One identity, one policy, one hash-chained audit trail across every AI agent and every tool call.",
    url: "https://conductai.ai",
    siteName: "ConductAI",
    type: "website",
    locale: "en_US",
    images: [
      {
        url: "https://conductai.ai/og.png",
        width: 1200,
        height: 630,
        alt: "ConductAI: Runtime Governance for AI Agents",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "ConductAI: Runtime Governance for AI Agents",
    description:
      "Allow, warn, or block every model and tool call before it commits. Hash-chained audit. Compliance packs for SOC 2, HIPAA, EU AI Act, SR 11-7, FDA CSA.",
    images: ["https://conductai.ai/og.png"],
  },
  robots: {
    index: true,
    follow: true,
    googleBot: {
      index: true,
      follow: true,
      "max-image-preview": "large",
      "max-snippet": -1,
    },
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
    function accentContrast(hex){
      if(!/^#[0-9a-fA-F]{6}$/.test(hex)) return "#ffffff";
      var r=parseInt(hex.slice(1,3),16)/255;
      var g=parseInt(hex.slice(3,5),16)/255;
      var b=parseInt(hex.slice(5,7),16)/255;
      function f(v){return v<=0.03928?v/12.92:Math.pow((v+0.055)/1.055,2.4)}
      var l=0.2126*f(r)+0.7152*f(g)+0.0722*f(b);
      return l>0.45?"#111827":"#ffffff";
    }
    var SEMANTIC=["--ok","--ok-bg","--ok-bd","--warn","--warn-bg","--warn-bd","--err","--err-bg","--err-bd","--info","--info-bg","--info-bd"];
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
    r.setProperty("--accent-contrast",accentContrast(A.base));
    for(var i=0;i<SEMANTIC.length;i++) r.removeProperty(SEMANTIC[i]);
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
            <Script src="https://narratr.ai/widget.js" strategy="afterInteractive" {...({ "data-brand-key": "c7ae7b0c-2b6" } as Record<string, string>)} />
            <Script src="https://narratr.ai/embed.js" strategy="afterInteractive" {...({ "data-brand": "conductai" } as Record<string, string>)} />
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
        <Script src="https://narratr.ai/widget.js" strategy="afterInteractive" {...({ "data-brand-key": "c7ae7b0c-2b6" } as Record<string, string>)} />
      </body>
    </html>
  )
}
