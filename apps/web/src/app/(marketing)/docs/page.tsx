"use client"

import { useEffect, useState } from "react"
import { marked } from "marked"
// @ts-expect-error - .md imported as raw string via webpack asset/source
import onpremDeploymentMd from "../../../../../../docs/reference/onprem-deployment.md"
// @ts-expect-error - .md imported as raw string via webpack asset/source
import mcpClientSupportMd from "../../../../../../docs/reference/mcp-client-support.md"
import { TabApi } from "./_sections/TabApi"
import { TabBlocks } from "./_sections/TabBlocks"
import { TabGettingStarted } from "./_sections/TabGettingStarted"
import { TabGuard } from "./_sections/TabGuard"
import { TabIntegrations } from "./_sections/TabIntegrations"
import { TabMcpTools } from "./_sections/TabMcpTools"
import { TabOverview } from "./_sections/TabOverview"
import { TABS, TAB_NAV, type TabId, VALID_TABS } from "./_sections/nav"

// ── Page ──────────────────────────────────────────────────────────────────────

export default function DocsPage() {
  const [activeTab, setActiveTab] = useState<TabId>("overview")

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const t = params.get("tab")
    if (t && (VALID_TABS as readonly string[]).includes(t)) {
      setActiveTab(t as TabId)
    }
  }, [])

  const navItems = TAB_NAV[activeTab]

  return (
    <div className="min-h-screen bg-stone-50">
      {/* Tab bar */}
      <div className="bg-white border-b border-stone-200 px-6 overflow-x-auto">
        <div className="max-w-5xl mx-auto flex gap-0 items-center">
          {TABS.map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
                activeTab === tab.id
                  ? "border-stone-900 text-stone-900"
                  : "border-transparent text-stone-500 hover:text-stone-700 hover:border-stone-300"
              }`}
            >
              {tab.label}
            </button>
          ))}
          <a
            href="https://github.com/sseshachala/conductai/tree/main/docs#readme"
            target="_blank"
            rel="noopener noreferrer"
            className="ml-auto px-4 py-3 text-sm font-medium text-stone-500 hover:text-stone-900 transition-colors"
            title="Full documentation on GitHub — Start, Reference, Concepts, Automate, Examples, Policy, Integrations, ADRs"
          >
            Full docs on GitHub ↗
          </a>
        </div>
      </div>

      <div className="max-w-5xl mx-auto px-6 py-12 flex gap-12">
        {/* Sidebar */}
        <nav className="w-48 shrink-0 hidden md:block sticky top-8 self-start">
          <ul className="space-y-1 text-sm text-stone-600">
            {navItems.map(({ href, label }) => (
              <li key={href}>
                <a href={href} className="hover:text-stone-900 transition-colors block py-0.5">{label}</a>
              </li>
            ))}
          </ul>
        </nav>

        {/* Content */}
        <main className="flex-1 min-w-0">
          {activeTab === "overview"        && <TabOverview />}
          {activeTab === "getting-started" && <TabGettingStarted />}
          {activeTab === "api"             && <TabApi />}
          {activeTab === "blocks"          && <TabBlocks />}
          {activeTab === "guard"           && <TabGuard />}
          {activeTab === "mcp-tools" && <>
            <TabMcpTools />
            <section id="mcp-client-acceptance"
              className="mt-12 min-w-0 break-words [&_h2]:text-xl [&_h2]:font-bold [&_h2]:mb-4 [&_h3]:text-lg [&_h3]:font-semibold [&_h3]:mt-8 [&_h3]:mb-3 [&_p]:text-sm [&_p]:leading-relaxed [&_p]:mb-4 [&_ul]:list-disc [&_ul]:pl-5 [&_li]:text-sm [&_li]:mb-2 [&_pre]:overflow-x-auto [&_pre]:bg-stone-100 [&_pre]:p-4 [&_pre]:mb-4 [&_code]:text-xs [&_table]:block [&_table]:max-w-full [&_table]:overflow-x-auto [&_table]:text-sm [&_table]:mb-4 [&_th]:text-left [&_th]:p-2 [&_td]:p-2 [&_td]:align-top [&_td]:border-b [&_a]:underline"
              dangerouslySetInnerHTML={{ __html: marked.parse(mcpClientSupportMd, { async: false }) as string }} />
          </>}
          {activeTab === "integrations"    && <TabIntegrations />}
          {activeTab === "on-prem" && <section id="on-prem-deployment"
            className="min-w-0 break-words [&_h2]:text-xl [&_h2]:font-bold [&_h2]:mb-4 [&_h3]:text-lg [&_h3]:font-semibold [&_h3]:mt-8 [&_h3]:mb-3 [&_h4]:font-semibold [&_h4]:mt-6 [&_h4]:mb-3 [&_p]:text-sm [&_p]:leading-relaxed [&_p]:mb-4 [&_ul]:list-disc [&_ul]:pl-5 [&_ol]:list-decimal [&_ol]:pl-5 [&_li]:text-sm [&_li]:mb-2 [&_pre]:overflow-x-auto [&_pre]:bg-stone-100 [&_pre]:p-4 [&_pre]:mb-4 [&_code]:text-xs [&_table]:w-full [&_table]:table-fixed [&_table]:text-sm [&_table]:mb-4 [&_th]:text-left [&_th]:p-2 [&_td]:p-2 [&_td]:align-top [&_td]:border-b [&_a]:underline"
            dangerouslySetInnerHTML={{ __html: marked.parse(onpremDeploymentMd, { async: false }) as string }} />}
        </main>
      </div>
    </div>
  )
}
