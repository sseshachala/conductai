"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { usePathname } from "next/navigation"
import { useGuardRole } from "@/hooks/useGuardRole"
import type { GuardRole } from "@/hooks/useGuardRole"
import { GLensPanel } from "@/components/guard/GLensPanel"

// ─── Tab definitions ──────────────────────────────────────────────────────────

type TabDef = { href: string; label: string; roles?: GuardRole[] }

// roles = undefined means visible to all; otherwise restrict to listed roles
export const GUARD_TABS: TabDef[] = [
  { href: "/theguard",                 label: "Overview"        },
  { href: "/theguard/spend",           label: "Spend",           roles: ["admin"] },
  { href: "/theguard/policies",        label: "Policies"        },
  { href: "/theguard/activity",        label: "Flight Recorder" },
  { href: "/theguard/discovery",       label: "Discovery"       },
  { href: "/theguard/compliance",       label: "Compliance",      roles: ["admin", "security"] },
  { href: "/theguard/session-reports", label: "Session Reports" },
  { href: "/theguard/team-memory",     label: "Team Memory"     },
  { href: "/theguard/settings",        label: "Settings",        roles: ["admin"] },
]

// ─── Helpers ──────────────────────────────────────────────────────────────────

function relativeTime(ts: Date | null | undefined): string {
  if (!ts) return "never"
  const sec = Math.floor((Date.now() - ts.getTime()) / 1000)
  if (sec < 5) return "just now"
  if (sec < 60) return `${sec}s ago`
  const min = Math.floor(sec / 60)
  if (min < 60) return `${min}m ago`
  return `${Math.floor(min / 60)}h ago`
}

// ─── Props ────────────────────────────────────────────────────────────────────

export interface GuardShellProps {
  children: React.ReactNode
  /** Shown in the header as "last updated X ago". Omit to hide the timestamp. */
  lastFetched?: Date | null
  /** Controls the green "live" / grey "offline" badge. Defaults to true. */
  live?: boolean
  /** Agent rule count — shown in header badge. */
  agentCount?: number | null
  /** Proxy rule count — shown in header badge. */
  proxyCount?: number | null
  /** Shows "Advisory" badge when Guard is in advisory mode. */
  advisory?: boolean
}

// ─── Component ────────────────────────────────────────────────────────────────

export function GuardShell({
  children,
  lastFetched,
  live = true,
  agentCount,
  proxyCount,
  advisory = false,
}: GuardShellProps) {
  const pathname = usePathname()
  const [, setTick] = useState(0)
  const { role } = useGuardRole()

  const visibleTabs = GUARD_TABS.filter(t => !t.roles || (role && t.roles.includes(role)))

  // Re-render every 10 s so the relative timestamp stays fresh
  useEffect(() => {
    const t = setInterval(() => setTick(n => n + 1), 10_000)
    return () => clearInterval(t)
  }, [])

  return (
    <div style={{ maxWidth: 1240, margin: "0 auto", padding: "28px 24px 48px" }}>
      <GLensPanel />
      {/* Page head */}
      <div style={{ display: "flex", alignItems: "flex-start", marginBottom: 20 }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 11 }}>
            <h1 style={{ fontSize: 22, fontWeight: 700, color: "var(--text)", letterSpacing: "-.02em", margin: 0 }}>
              Guard
            </h1>
            {live ? (
              <span className="sbadge ok" style={{ marginTop: 2 }}>
                <span className="conduct-pulse-dot" />
                live
              </span>
            ) : (
              <span className="sbadge" style={{ marginTop: 2, background: "var(--surface-3)", color: "var(--text-muted)", border: "1px solid var(--border)" }}>
                offline
              </span>
            )}
            {advisory && (
              <span style={{ marginTop: 2, fontSize: 11, fontWeight: 700, padding: "2px 9px", borderRadius: 20, background: "var(--warn-bg)", color: "var(--warn)", border: "1px solid var(--warn-bd)", letterSpacing: ".04em" }}>
                ADVISORY
              </span>
            )}
            {(agentCount != null || proxyCount != null) && (
              <span style={{
                marginTop: 2,
                fontSize: 11.5,
                fontWeight: 600,
                padding: "2px 8px",
                borderRadius: 6,
                background: "var(--surface-2)",
                color: "var(--text-2)",
                border: "1px solid var(--border)",
              }}>
                {agentCount ?? 0} agent · {proxyCount ?? 0} proxy
              </span>
            )}
          </div>
          <p style={{ fontSize: 13, color: "var(--text-3)", marginTop: 5 }}>
            MDM for AI coding tools — when a hard cap is hit, every tool call across Claude Code, Codex, and Cursor is blocked immediately and your security team is notified on Slack.
          </p>
        </div>
        <div style={{ marginLeft: "auto", fontSize: 12, color: "var(--text-muted)", paddingTop: 4 }}>
          {lastFetched != null
            ? <>last updated: {relativeTime(lastFetched)}</>
            : null
          }
        </div>
      </div>

      {/* Tab nav */}
      <div className="guard-tab-nav">
        {visibleTabs.map(tab => {
          const isActive = tab.href === "/theguard"
            ? pathname === "/theguard"
            : pathname?.startsWith(tab.href)
          return (
            <Link
              key={tab.href}
              href={tab.href}
              className={`guard-tab${isActive ? " active" : ""}`}
            >
              {tab.label}
            </Link>
          )
        })}
      </div>

      {children}
    </div>
  )
}
