"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"

export interface GuardSectionTab {
  href: string
  label: string
}

export const CONNECTIONS_TABS: readonly GuardSectionTab[] = [
  { href: "/theguard/connections/proxy",         label: "Proxy & gateways" },
  { href: "/theguard/connections/notifications", label: "Notifications" },
  { href: "/theguard/connections/sync",          label: "Sync" },
]

export const SPEND_TABS: readonly GuardSectionTab[] = [
  // Configure = budget controls. Optimization = savings actions.
  // "Spend at a glance" content moved out of this section entirely and
  // now lives on /theguard/spend/glance, surfaced as a peer view of
  // Overview on the /theguard landing page.
  { href: "/theguard/spend",              label: "Configure" },
  { href: "/theguard/spend/optimization", label: "Optimization" },
]

export function GuardSectionTabs({ tabs }: { tabs: readonly GuardSectionTab[] }) {
  const pathname = usePathname()
  return (
    <nav
      aria-label="Section tabs"
      style={{
        display: "flex",
        gap: 4,
        borderBottom: "1px solid var(--border)",
        marginBottom: 20,
      }}
    >
      {tabs.map(t => {
        const active = pathname === t.href
        return (
          <Link
            key={t.href}
            href={t.href}
            style={{
              padding: "8px 14px",
              fontSize: 13,
              fontWeight: active ? 600 : 500,
              color: active ? "var(--text)" : "var(--text-3)",
              borderBottom: `2px solid ${active ? "var(--accent)" : "transparent"}`,
              marginBottom: -1,
              textDecoration: "none",
              transition: "color .12s",
            }}
          >
            {t.label}
          </Link>
        )
      })}
    </nav>
  )
}
