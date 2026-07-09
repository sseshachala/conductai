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
        <div className="border-t border-stone-100 pt-6 flex flex-col sm:flex-row justify-between items-center gap-4 text-xs text-stone-400">
          <span>© {new Date().getFullYear()} Conduct AI. All rights reserved.</span>
          <div className="flex items-center gap-4">
            <a href="https://www.linkedin.com/company/109653233/" target="_blank" rel="noopener noreferrer" className="hover:text-stone-700 transition-colors" aria-label="LinkedIn">
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="w-4 h-4"><path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433a2.062 2.062 0 0 1-2.063-2.065 2.064 2.064 0 1 1 2.063 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z"/></svg>
            </a>
            <a href="https://www.youtube.com/@Conductai" target="_blank" rel="noopener noreferrer" className="hover:text-stone-700 transition-colors" aria-label="YouTube">
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="w-4 h-4"><path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"/></svg>
            </a>
            <span>Envisioned, designed and developed with love from Houston</span>
          </div>
        </div>
      </div>
    </footer>
  )
}
