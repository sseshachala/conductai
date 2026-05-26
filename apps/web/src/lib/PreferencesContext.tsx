"use client"

import React, { createContext, useContext, useEffect, useState, useCallback } from "react"

interface Preferences {
  show_dry_run: boolean
  show_test_trigger: boolean
}

const DEFAULTS: Preferences = {
  show_dry_run: false,
  show_test_trigger: true,
}

interface PreferencesContextValue {
  prefs: Preferences
  loading: boolean
  update: (patch: Partial<Preferences>) => Promise<void>
}

const PreferencesContext = createContext<PreferencesContextValue>({
  prefs: DEFAULTS,
  loading: false,
  update: async () => {},
})

export function PreferencesProvider({
  children,
  workspaceId,
  getToken,
}: {
  children: React.ReactNode
  workspaceId: string
  getToken: (() => Promise<string | null>) | null
}) {
  const [prefs, setPrefs] = useState<Preferences>(DEFAULTS)
  const [loading, setLoading] = useState(true)

  const apiUrl = process.env.NEXT_PUBLIC_API_URL

  const headers = useCallback(async (): Promise<Record<string, string>> => {
    const h: Record<string, string> = { "Content-Type": "application/json" }
    if (getToken) { const t = await getToken(); if (t) h["Authorization"] = `Bearer ${t}` }
    if (workspaceId) h["X-Workspace-Id"] = workspaceId
    return h
  }, [getToken, workspaceId])

  useEffect(() => {
    if (!workspaceId || !apiUrl) { setLoading(false); return }
    ;(async () => {
      try {
        const h = await headers()
        const r = await fetch(`${apiUrl}/workspaces/${workspaceId}/preferences`, { headers: h })
        if (r.ok) setPrefs(await r.json())
      } catch {}
      setLoading(false)
    })()
  }, [workspaceId, apiUrl])

  const update = useCallback(async (patch: Partial<Preferences>) => {
    const optimistic = { ...prefs, ...patch }
    setPrefs(optimistic)
    try {
      const h = await headers()
      await fetch(`${apiUrl}/workspaces/${workspaceId}/preferences`, {
        method: "PATCH",
        headers: h,
        body: JSON.stringify(patch),
      })
    } catch {
      setPrefs(prefs) // rollback on error
    }
  }, [prefs, headers, apiUrl, workspaceId])

  return (
    <PreferencesContext.Provider value={{ prefs, loading, update }}>
      {children}
    </PreferencesContext.Provider>
  )
}

export function usePreferences() {
  return useContext(PreferencesContext)
}
