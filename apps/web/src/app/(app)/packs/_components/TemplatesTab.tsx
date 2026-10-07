"use client"

import type { Dispatch, SetStateAction } from "react"
import Link from "next/link"
import { type MouseEvent as ReactMouseEvent } from "react"
import type { Playbook, PlaybookScore } from "./catalog"
import { PlaybookCard } from "./PlaybookCard"

// Agent Templates tab
export function TemplatesTab({
  search, setSearch, loading, showFeatured, featuredPlaybooks, filtered, installedCount, installing, openInstallModal, openYamlModal, scores,
}: {
  search: string
  setSearch: Dispatch<SetStateAction<string>>
  loading: boolean
  showFeatured: boolean
  featuredPlaybooks: Playbook[]
  filtered: Playbook[]
  installedCount: Map<string, number>
  installing: boolean
  openInstallModal: (slug: string) => Promise<void>
  openYamlModal: (slug: string) => Promise<void>
  scores: Map<string, PlaybookScore>
}) {
  return (
    <>

        {/* Search + submit row */}
        <div style={{ display: "flex", gap: 10, marginBottom: 22, alignItems: "center" }}>
          <div style={{ position: "relative", maxWidth: 420, flex: "0 0 420px" }}>
            <svg
              width={16} height={16}
              viewBox="0 0 16 16"
              fill="none"
              style={{ position: "absolute", left: 12, top: 11, color: "var(--text-muted)", pointerEvents: "none" }}
            >
              <circle cx="6.5" cy="6.5" r="4.5" stroke="currentColor" strokeWidth="1.5" />
              <path d="M10 10l3 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
            </svg>
            <input
              type="text"
              placeholder="Search agent templates…"
              value={search}
              onChange={e => setSearch(e.target.value)}
              style={{
                width: "100%",
                height: 38,
                padding: "0 12px 0 36px",
                borderRadius: 9,
                border: "1px solid var(--border)",
                background: "var(--surface)",
                color: "var(--text)",
                fontSize: 13.5,
                outline: "none",
              }}
            />
          </div>
          <Link
            href="/playbooks/submit"
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 6,
              height: 38,
              padding: "0 14px",
              fontSize: 13,
              fontWeight: 600,
              color: "var(--text-2)",
              border: "1px solid var(--border)",
              borderRadius: 9,
              background: "transparent",
              textDecoration: "none",
              transition: "background .12s, color .12s",
            }}
            onMouseEnter={(e: ReactMouseEvent<HTMLElement>) => { (e.currentTarget as HTMLAnchorElement).style.background = "var(--surface-2)"; (e.currentTarget as HTMLAnchorElement).style.color = "var(--text)" }}
            onMouseLeave={(e: ReactMouseEvent<HTMLElement>) => { (e.currentTarget as HTMLAnchorElement).style.background = "transparent"; (e.currentTarget as HTMLAnchorElement).style.color = "var(--text-2)" }}
          >
            <span style={{ fontSize: 16, lineHeight: 1 }}>+</span>
            Submit agent template
          </Link>
        </div>

        {loading ? (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(290px, 1fr))", gap: 14 }}>
            {[1,2,3,4,5,6].map(i => (
              <div key={i} style={{ height: 190, borderRadius: 12, background: "var(--surface-3)", animation: "pulse 2s cubic-bezier(0.4,0,0.6,1) infinite" }} />
            ))}
          </div>
        ) : (
          <>
            {/* Featured section */}
            {showFeatured && (
              <div style={{ marginBottom: 30 }}>
                <div className="eyebrow" style={{ marginBottom: 11 }}>Featured · Issue → PR</div>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 14 }}>
                  {featuredPlaybooks.map(p => (
                    <PlaybookCard
                      key={p.slug}
                      playbook={p}
                      installing={installing}
                      installCount={installedCount.get(p.slug) ?? 0}
                      grade={scores.get(p.slug)?.grade}
                      onInstall={openInstallModal}
                      onViewYaml={openYamlModal}
                    />
                  ))}
                </div>
              </div>
            )}



            {/* Playbooks grid */}
            {filtered.length === 0 ? (
              <div style={{ padding: "48px 0", textAlign: "center", color: "var(--text-muted)", fontSize: 13.5 }}>
                No agent templates match your search.
              </div>
            ) : (
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(290px, 1fr))", gap: 14 }}>
                {filtered.map(p => (
                  <PlaybookCard
                    key={p.slug}
                    playbook={p}
                    installing={installing}
                    installCount={installedCount.get(p.slug) ?? 0}
                    grade={scores.get(p.slug)?.grade}
                    onInstall={openInstallModal}
                    onViewYaml={openYamlModal}
                  />
                ))}
              </div>
            )}
          </>
        )}
    </>
  )
}
