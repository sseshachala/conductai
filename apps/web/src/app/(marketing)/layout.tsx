"use client"

import { WorkspaceProvider } from "@/lib/WorkspaceContext"

export default function MarketingLayout({ children }: { children: React.ReactNode }) {
  const clerkEnabled = !!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY
  return (
    <WorkspaceProvider clerkEnabled={clerkEnabled}>
      <div className="min-h-screen bg-white flex flex-col">
        <MarketingNav />
        <main className="flex-1">{children}</main>
        <MarketingFooter />
      </div>
    </WorkspaceProvider>
  )
}

function ProductsDropdown() {
  return (
    <div className="relative group">
      <a href="/sign-up" className="flex items-center gap-1 text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">
        Products
        <svg width="12" height="12" viewBox="0 0 12 12" fill="currentColor" className="opacity-40 mt-0.5"><path d="M2 4l4 4 4-4"/></svg>
      </a>
      <div className="absolute left-0 top-full pt-2 hidden group-hover:block z-50 min-w-[220px]">
        <div className="bg-white border border-stone-200 rounded-xl shadow-lg py-2">
          <a href="/guard-landing" className="flex items-center gap-3 px-4 py-2.5 text-sm text-stone-700 hover:bg-stone-50 transition-colors">
            <span>🛡️</span>
            <div>
              <p className="font-semibold">Conduct Guard</p>
              <p className="text-xs text-stone-400">AI session governance</p>
            </div>
          </a>
          <a href="/playbooks" className="flex items-center gap-3 px-4 py-2.5 text-sm text-stone-700 hover:bg-stone-50 transition-colors">
            <span>⚡</span>
            <div>
              <p className="font-semibold">Agent Templates</p>
              <p className="text-xs text-stone-400">Pre-built AI automations</p>
            </div>
          </a>
          <a href="/tools/conduct-cli" className="flex items-center gap-3 px-4 py-2.5 text-sm text-stone-700 hover:bg-stone-50 transition-colors">
            <span className="text-indigo-600 font-bold text-base">◈</span>
            <div>
              <p className="font-semibold">Conduct CLI</p>
              <p className="text-xs text-stone-400">Terminal governance + token savings</p>
            </div>
          </a>
        </div>
      </div>
    </div>
  )
}

function MarketingNav() {
  return (
    <header className="sticky top-0 bg-white/95 backdrop-blur-sm z-50 border-b border-stone-100">
      <div className="px-6 py-4 flex items-center justify-between max-w-6xl mx-auto w-full">
        <a href="/">
          <img src="/logo.png" alt="Conduct AI" className="h-10 w-auto" />
        </a>
        <nav className="hidden md:flex items-center gap-6">
          <ProductsDropdown />
          <a href="/playbooks" className="text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">Agent Templates</a>
          <a href="/blog" className="text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">Blog</a>
          <a href="/docs" className="text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">Docs</a>
          <a href="https://pypi.org/project/conduct-cli/" target="_blank" rel="noopener noreferrer" className="text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">PyPI</a>
          <a href="https://github.com/sseshachala/conduct-cli" target="_blank" rel="noopener noreferrer" className="text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">GitHub</a>
        </nav>
        <div className="flex items-center gap-3">
          <a href="mailto:hello@conductai.ai" className="text-sm font-medium text-stone-600 hover:text-stone-900 transition-colors hidden sm:block">Talk to Us</a>
          <a href="/sign-up" className="rounded-lg bg-stone-900 text-white px-4 py-2 text-sm font-semibold hover:bg-stone-700 transition-colors">
            Start Free
          </a>
        </div>
      </div>
    </header>
  )
}

function MarketingFooter() {
  return (
    <footer className="border-t border-stone-100 py-10 px-6 bg-white">
      <div className="max-w-5xl mx-auto">
        <div className="flex flex-col md:flex-row justify-between gap-8 mb-10">
          <div>
            <img src="/logo.png" alt="Conduct AI" className="h-8 w-auto mb-3" />
            <p className="text-sm text-stone-400 max-w-xs leading-relaxed">AI Governance for Engineering Teams. Platform or partnership — you choose how.</p>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-8">
            {[
              { heading: "Solutions", links: [["Conduct Guard", "/guard-landing"], ["Spec-Driven Dev", "/sdd"], ["Agentic Workflows", "/playbooks"]] as [string, string][] },
              { heading: "Company", links: [["About", "/about"], ["Partners", "/partners"], ["Blog", "/blog"]] as [string, string][] },
              { heading: "Resources", links: [["Docs", "/docs"], ["Agent Templates", "/marketplace"], ["Token Guardrails", "/token-guardrails"]] as [string, string][] },
              { heading: "Legal", links: [["Privacy", "/privacy"], ["Terms", "/terms"]] as [string, string][] },
            ].map(col => (
              <div key={col.heading}>
                <p className="text-xs font-bold uppercase tracking-widest text-stone-400 mb-3">{col.heading}</p>
                <ul className="space-y-2">
                  {col.links.map(([label, href]) => (
                    <li key={label}>
                      <a href={href} className="text-sm text-stone-500 hover:text-stone-900 transition-colors">{label}</a>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </div>
        <div className="border-t border-stone-100 pt-6 flex flex-col sm:flex-row justify-between items-center gap-2 text-xs text-stone-400">
          <span>© {new Date().getFullYear()} Conduct AI. All rights reserved.</span>
          <span>Envisioned, designed and developed with love from Houston</span>
        </div>
      </div>
    </footer>
  )
}
