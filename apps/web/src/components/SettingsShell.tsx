"use client"

/**
 * Shared settings surface — header + TabBar + tabpanels, wrapped in AppShell.
 *
 * Used by /settings (workspace), /theguard/settings (Guard), and workflow
 * settings so every settings page has the same shape. See issue #1359.
 *
 * When embedding inside another page shell (e.g. GuardShell already owns
 * AppShell + h1 + top-level nav), pass wrapInAppShell={false} and omit
 * title — SettingsShell then renders only the TabBar + panels.
 */

import { useState, type ReactNode } from "react"
import AppShell from "@/components/AppShell"
import { TabBar } from "@/components/TabBar"

export interface SettingsTab<K extends string> {
  key: K
  label: string
  adminOnly?: boolean
}

export function SettingsShell<K extends string>({
  title,
  description,
  tabs,
  isAdmin,
  panels,
  initialTab,
  rightSlot,
  wrapInAppShell = true,
  children,
}: {
  title?: string
  description?: string
  tabs: readonly SettingsTab<K>[]
  isAdmin: boolean
  panels: Partial<Record<K, ReactNode>>
  initialTab?: K
  rightSlot?: ReactNode
  wrapInAppShell?: boolean
  children?: ReactNode
}) {
  const visibleTabs = tabs.filter(t => !t.adminOnly || isAdmin)
  const firstKey = visibleTabs[0]?.key as K
  const [activeTab, setActiveTab] = useState<K>(initialTab ?? firstKey)
  const labels = Object.fromEntries(visibleTabs.map(t => [t.key, t.label])) as Record<K, string>
  const tabKeys = visibleTabs.map(t => t.key) as readonly K[]

  const body = (
    <>
      {title && (
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 16, marginBottom: 20 }}>
          <div>
            <h1 style={{ fontSize: 25, fontWeight: 680, letterSpacing: "-.02em", color: "var(--text)", margin: 0 }}>
              {title}
            </h1>
            {description && (
              <p style={{ fontSize: 14, color: "var(--text-3)", margin: "5px 0 0" }}>
                {description}
              </p>
            )}
          </div>
          {rightSlot && <div style={{ flexShrink: 0 }}>{rightSlot}</div>}
        </div>
      )}

      {children}

      <div style={{ marginBottom: 24 }}>
        <TabBar tabs={tabKeys} labels={labels} activeTab={activeTab} onSelect={setActiveTab} />
      </div>

      {visibleTabs.map(t => (
        <div
          key={t.key}
          role="tabpanel"
          id={`tabpanel-${t.key}`}
          aria-labelledby={`tab-${t.key}`}
          hidden={activeTab !== t.key}
        >
          {panels[t.key]}
        </div>
      ))}
    </>
  )

  if (!wrapInAppShell) return <>{body}</>

  return (
    <AppShell>
      <div style={{ maxWidth: 960, margin: "0 auto", padding: "40px 24px" }}>
        {body}
      </div>
    </AppShell>
  )
}
