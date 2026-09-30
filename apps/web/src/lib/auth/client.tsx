"use client"

import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react"
import { useAuth as useClerkAuth, useUser as useClerkUser, useSession as useClerkSession, useClerk as useClerkSdk } from "@clerk/nextjs"
import { runtimeConfig } from "./runtime"

type ProxySession = { token: string; expires_at: number; user: { id: string; name: string } }
type ConsoleContext = {
  loaded: boolean
  session: ProxySession | null
  getToken: (options?: { skipCache?: boolean }) => Promise<string | null>
}
const Context = createContext<ConsoleContext>({ loaded: false, session: null, getToken: async () => null })
const ClerkContext = createContext<{
  auth: ReturnType<typeof useClerkAuth>
  user: ReturnType<typeof useClerkUser>
  session: ReturnType<typeof useClerkSession>
  clerk: ReturnType<typeof useClerkSdk>
} | null>(null)

export function ClerkAuthBridge({ children }: { children: React.ReactNode }) {
  const auth = useClerkAuth()
  const user = useClerkUser()
  const session = useClerkSession()
  const clerk = useClerkSdk()
  return <ClerkContext.Provider value={{ auth, user, session, clerk }}>{children}</ClerkContext.Provider>
}
const developmentContext: ConsoleContext = {
  loaded: true, session: { token: "", expires_at: 0, user: { id: "dev", name: "Developer" } },
  getToken: async () => null,
}

function useConsoleContext() {
  const context = useContext(Context)
  return runtimeConfig().authMode === "development" ? developmentContext : context
}

export function ConsoleProvider({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<ProxySession | null>(null)
  const [loaded, setLoaded] = useState(false)
  const current = useRef<ProxySession | null>(null)
  const pending = useRef<Promise<string | null> | null>(null)
  const getToken = useCallback(async (options?: { skipCache?: boolean }) => {
    if (!options?.skipCache && current.current && current.current.expires_at > Date.now() / 1000 + 10) {
      return current.current.token
    }
    if (pending.current) return pending.current
    pending.current = (async () => {
      try {
        const response = await fetch("/api/auth/session", {
          method: "POST", credentials: "same-origin", cache: "no-store", redirect: "error",
          headers: { "Content-Type": "application/json" },
        })
        if (!response.ok) throw new Error("Session unavailable")
        const next = await response.json() as ProxySession
        current.current = next
        setSession(next)
        return next.token
      } catch {
        current.current = null
        setSession(null)
        return null
      } finally { setLoaded(true) }
    })()
    try { return await pending.current } finally { pending.current = null }
  }, [])
  useEffect(() => { void getToken() }, [getToken])
  return <Context.Provider value={{ loaded, session, getToken }}>{children}</Context.Provider>
}

export function useAuth() {
  const clerk = useContext(ClerkContext)
  const state = useConsoleContext()
  if (clerk) return clerk.auth
  return { isLoaded: state.loaded, isSignedIn: !!state.session, userId: state.session?.user.id ?? null,
    sessionId: state.session?.user.id ?? null, getToken: state.getToken } as ReturnType<typeof useClerkAuth>
}

export function useUser() {
  const clerk = useContext(ClerkContext)
  const { loaded, session } = useConsoleContext()
  if (clerk) return clerk.user
  return { isLoaded: loaded, isSignedIn: !!session, user: session ? {
    id: session.user.id, fullName: session.user.name, firstName: session.user.name,
    lastName: "", imageUrl: "", primaryEmailAddress: null,
  } : null } as unknown as ReturnType<typeof useClerkUser>
}

export function useSession() {
  const clerk = useContext(ClerkContext)
  const { loaded, session } = useConsoleContext()
  if (clerk) return clerk.session
  return { isLoaded: loaded, isSignedIn: !!session, session: session ? {
    id: session.user.id, status: "active",
  } : null } as ReturnType<typeof useClerkSession>
}

export function useClerk() {
  const clerk = useContext(ClerkContext)
  if (clerk) return clerk.clerk
  return { signOut: async () => {
    // POST has a same-origin check; the response contains only a fixed local logout URL.
    const response = await fetch("/api/auth/logout", { method: "POST", credentials: "same-origin" })
    if (!response.ok) throw new Error("Sign out failed")
    window.location.assign("/oauth2/sign_out?rd=%2Fsigned-out")
  } } as unknown as ReturnType<typeof useClerkSdk>
}
