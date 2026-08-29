"use client"

/**
 * Shared settings surface — header + vertical left-rail sub-nav + tabpanels,
 * wrapped in AppShell.
 *
 * Used by /settings (workspace), /theguard/settings (Guard), and workflow
 * settings so every settings page has the same shape. See issue #1359.
 *
 * Vertical left-rail matches the standard settings pattern used by Vercel,
 * Linear, Stripe, GitHub, and Datadog — instantly distinguishable from any
 * horizontal parent nav (e.g. Guard's top strip) and scales past 6+ tabs.
 *
 * When embedding inside another page shell (e.g. GuardShell already owns
 * AppShell + h1 + top-level nav), pass wrapInAppShell={false} and omit
 * title — SettingsShell then renders only the left rail + panels.
 */

import { useState, type ReactNode } from "react"
import AppShell from "@/components/AppShell"

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

      <div style={{ display: "grid", gridTemplateColumns: "220px 1fr", gap: 32, alignItems: "start", marginTop: 8 }}>
        <nav role="tablist" aria-orientation="vertical" style={{ display: "flex", flexDirection: "column", gap: 2, borderRight: "1px solid var(--border)", paddingRight: 16 }}>
          {visibleTabs.map(t => {
            const active = activeTab === t.key
            return (
              <button
                key={t.key}
                role="tab"
                aria-selected={active}
                aria-controls={`tabpanel-${t.key}`}
                id={`tab-${t.key}`}
                onClick={() => setActiveTab(t.key)}
                style={{
                  textAlign: "left",
                  padding: "8px 12px",
                  fontSize: 13.5,
                  fontWeight: active ? 650 : 500,
                  color: active ? "var(--text)" : "var(--text-3)",
                  background: active ? "var(--surface-2)" : "transparent",
                  border: "none",
                  borderRadius: 6,
                  cursor: "pointer",
                  transition: "background .12s, color .12s",
                }}
              >
                {t.label}
              </button>
            )
          })}
        </nav>

        <div style={{ minWidth: 0 }}>
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
        </div>
      </div>
    </>
  )

  if (!wrapInAppShell) return <>{body}</>

  return (
    <AppShell>
      <div style={{ maxWidth: 1080, margin: "0 auto", padding: "40px 24px" }}>
        {body}
      </div>
    </AppShell>
  )
}
