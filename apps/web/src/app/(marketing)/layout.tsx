"use client"

import { WorkspaceProvider } from "@/lib/WorkspaceContext"
import { CtaLink } from "@/components/marketing/CtaLink"

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
      <a href="#" className="flex items-center gap-1 text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">
        Product
        <svg width="12" height="12" viewBox="0 0 12 12" fill="currentColor" className="opacity-40 mt-0.5"><path d="M2 4l4 4 4-4"/></svg>
      </a>
      <div className="absolute left-0 top-full pt-2 hidden group-hover:block z-50 min-w-[220px]">
        <div className="bg-white border border-stone-200 rounded-xl shadow-lg py-2">
          <a href="/guard" className="flex items-center gap-3 px-4 py-2.5 text-sm text-stone-700 hover:bg-stone-50 transition-colors">
            <span>🛡️</span>
            <div>
              <p className="font-semibold">Conduct Guard</p>
              <p className="text-xs text-stone-400">AI session governance</p>
            </div>
          </a>
          <a href="/registry" className="flex items-center gap-3 px-4 py-2.5 text-sm text-stone-700 hover:bg-stone-50 transition-colors">
            <span>⚡</span>
            <div>
              <p className="font-semibold">Registry</p>
              <p className="text-xs text-stone-400">Compliance &amp; automation packs</p>
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

function SolutionsDropdown() {
  return (
    <div className="relative group">
      <a href="#" className="flex items-center gap-1 text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">
        Solutions
        <svg width="12" height="12" viewBox="0 0 12 12" fill="currentColor" className="opacity-40 mt-0.5"><path d="M2 4l4 4 4-4"/></svg>
      </a>
      <div className="absolute left-0 top-full pt-2 hidden group-hover:block z-50 min-w-[220px]">
        <div className="bg-white border border-stone-200 rounded-xl shadow-lg py-2">
          <a href="/solutions/engineering-leaders" className="flex items-center gap-3 px-4 py-2.5 text-sm text-stone-700 hover:bg-stone-50 transition-colors">
            <div>
              <p className="font-semibold">Engineering leaders</p>
            </div>
          </a>
          <a href="/solutions/security-compliance" className="flex items-center gap-3 px-4 py-2.5 text-sm text-stone-700 hover:bg-stone-50 transition-colors">
            <div>
              <p className="font-semibold">Security &amp; compliance</p>
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
          <SolutionsDropdown />
          <a href="/docs" className="text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">Docs</a>
          <a href="/blog" className="text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors">Blog</a>
        </nav>
        <div className="flex items-center gap-3">
          <a href="https://cal.com/sudhi-seshachala-pks7pd" target="_blank" rel="noopener"
            className="rounded-lg border border-stone-300 text-stone-700 px-4 py-2 text-sm font-semibold hover:border-stone-400 transition-colors hidden sm:block">
            Book Demo
          </a>
          <CtaLink className="rounded-lg bg-stone-900 text-white px-4 py-2 text-sm font-semibold hover:bg-stone-700 transition-colors" />
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
            <p className="text-sm text-stone-400 max-w-xs leading-relaxed">AI Governance for Engineering Teams. Platform or partnership, you choose how.</p>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-8">
            {[
              { heading: "Product", links: [["Guard", "/guard"], ["Registry", "/registry"], ["SDD Scanner", "/sdd"], ["CLI", "/tools/conduct-cli"]] as [string, string][] },
              { heading: "Solutions", links: [["Engineering leaders", "/solutions/engineering-leaders"], ["Security & compliance", "/solutions/security-compliance"]] as [string, string][] },
              { heading: "Company", links: [["About", "/about"], ["Blog", "/blog"]] as [string, string][] },
              { heading: "Resources", links: [["Docs", "/docs"], ["Open source", "/open-source"], ["GitHub", "https://github.com/sseshachala/conduct-cli"]] as [string, string][] },
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
