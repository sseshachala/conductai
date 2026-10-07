"use client"

import { authEnabled } from "@/lib/auth/runtime"
import { useAuth } from "@/lib/auth/client"
import { LensPanel } from "@/components/glens/LensPanel"
import { PreferencesProvider } from "@/lib/PreferencesContext"
import Toast from "@/components/ui/Toast"
import ErrorBoundary from "@/components/ui/ErrorBoundary"
import { useAppShellState } from "./app-shell/useAppShellState"
import { Sidebar } from "./app-shell/Sidebar"
import { Topbar } from "./app-shell/Topbar"
import { CommandPalette } from "./app-shell/CommandPalette"

export default function AppShell({ children, noPadding }: { children: React.ReactNode; noPadding?: boolean }) {
  return <AppShellInner noPadding={noPadding}>{children}</AppShellInner>
}

function AppShellInner({ children, noPadding }: { children: React.ReactNode; noPadding?: boolean }) {
  const clerkEnabled = authEnabled()
  if (clerkEnabled) return <AppShellInnerWithAuth noPadding={noPadding}>{children}</AppShellInnerWithAuth>
  return <AppShellInnerContent noPadding={noPadding} getToken={null} userId={null}>{children}</AppShellInnerContent>
}

function AppShellInnerWithAuth({ children, noPadding }: { children: React.ReactNode; noPadding?: boolean }) {
  const { getToken, userId } = useAuth()
  return <AppShellInnerContent noPadding={noPadding} getToken={getToken} userId={userId ?? null}>{children}</AppShellInnerContent>
}

function AppShellInnerContent({
  children,
  noPadding,
  getToken,
  userId,
}: {
  children: React.ReactNode
  noPadding?: boolean
  getToken: (() => Promise<string | null>) | null
  userId: string | null
}) {
  const shell = useAppShellState({ userId })
  const {
    pathname,
    isMobile,
    mobileNavOpen,
    setMobileNavOpen,
    mainAreaRef,
    toast,
    setToast,
    paletteOpen,
    activeWorkspace,
    lensPanelOpen,
    setLensPanelOpen,
    lensPanelInitialQuery,
    setLensPanelInitialQuery,
    lensPanelEntry,
    setLensPanelEntry,
    lensPanelGeneration,
    lensPanelSuppressed,
  } = shell

  return (
    <PreferencesProvider workspaceId={activeWorkspace?.id ?? ""} getToken={getToken}>
    <div style={{ display: "flex", height: "100dvh", width: "100%", minWidth: 0, background: "var(--bg)" }}>
      {isMobile && mobileNavOpen && <div aria-hidden="true" onClick={() => setMobileNavOpen(false)} style={{ position: "fixed", inset: 0, zIndex: 299, background: "rgba(0,0,0,0.35)" }} />}

      {/* ── Sidebar ─────────────────────────────────────────────────────── */}
      <Sidebar shell={shell} getToken={getToken} />

      {/* ── Main area ───────────────────────────────────────────────────── */}
      <div ref={mainAreaRef} style={{ flex: 1, minWidth: 0, minHeight: 0, display: "flex", flexDirection: "column" }}>

        {/* Topbar */}
        <Topbar shell={shell} />

        {/* Page content */}
        <main style={{ flex: 1, minWidth: 0, minHeight: 0, overflow: noPadding ? "hidden" : "auto", display: noPadding ? "flex" : "block", flexDirection: noPadding ? "column" : undefined }}>
          <ErrorBoundary>{children}</ErrorBoundary>
        </main>
      </div>

      {/* Lens — docked side panel (pushes content, not an overlay) */}
      {!lensPanelSuppressed && (
        <LensPanel
          key={`${activeWorkspace?.id}:${lensPanelGeneration}`}
          open={lensPanelOpen}
          initialQuery={lensPanelInitialQuery}
          initialEntry={lensPanelEntry}
          pathname={pathname}
          onClose={() => { setLensPanelOpen(false); setLensPanelInitialQuery(null); setLensPanelEntry(null) }}
        />
      )}
    </div>

    {paletteOpen && (
      <CommandPalette shell={shell} />
    )}

    {toast && <Toast message={toast.message} type={toast.type} onDismiss={() => setToast(null)} />}
    </PreferencesProvider>
  )
}
