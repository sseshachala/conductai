"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { usePathname } from "next/navigation"

// ─── Tab definitions ──────────────────────────────────────────────────────────

export const GUARD_TABS = [
  { href: "/guard",                 label: "Overview"        },
  { href: "/guard/spend",           label: "Spend"           },
  { href: "/guard/policies",        label: "Policies"        },
  { href: "/guard/activity",        label: "Activity"        },
  { href: "/guard/session-reports", label: "Session Reports" },
  { href: "/guard/team-memory",     label: "Team Memory"     },
  { href: "/guard/settings",        label: "Settings"        },
]

// ─── Helpers ──────────────────────────────────────────────────────────────────

const PERSONA_BADGE: Record<string, { emoji: string; color: string }> = {
  conservative: { emoji: "🔴", color: "#dc2626" },
  standard:     { emoji: "🟡", color: "#d97706" },
  developer:    { emoji: "🟢", color: "#16a34a" },
}

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
  /** Active persona name — renders a coloured badge next to the live badge. */
  persona?: string
  /** Number of rules for the active persona — appended to the persona badge. */
  ruleCount?: number | null
}

// ─── Component ────────────────────────────────────────────────────────────────

export function GuardShell({
  children,
  lastFetched,
  live = true,
  persona,
  ruleCount,
}: GuardShellProps) {
  const pathname = usePathname()
  const [, setTick] = useState(0)

  // Re-render every 10 s so the relative timestamp stays fresh
  useEffect(() => {
    const t = setInterval(() => setTick(n => n + 1), 10_000)
    return () => clearInterval(t)
  }, [])

  return (
    <div style={{ maxWidth: 1240, margin: "0 auto", padding: "28px 24px 48px" }}>
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
            {persona && (
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
                {PERSONA_BADGE[persona]?.emoji ?? "🟡"} {persona.charAt(0).toUpperCase() + persona.slice(1)}
                {ruleCount != null ? ` · ${ruleCount} rules` : ""}
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
        {GUARD_TABS.map(tab => {
          const isActive = tab.href === "/guard"
            ? pathname === "/guard"
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
