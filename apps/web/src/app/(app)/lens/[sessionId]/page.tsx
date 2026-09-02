"use client"

import { useEffect, useRef, useState } from "react"
import { useParams } from "next/navigation"
import Link from "next/link"
import AppShell from "@/components/AppShell"
import { useAuthFetch } from "@/hooks/useAuthFetch"
import { API } from "@/lib/api/client"
import { GlensDashboard } from "@/components/glens/GlensDashboard"
import type { GlensDashboardSpec } from "@/components/glens/GlensDashboard"

function SessionIdBadge({ sessionId }: { sessionId: string }) {
  const [copied, setCopied] = useState<"" | "id" | "url">("")

  async function copy(text: string, kind: "id" | "url") {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(kind)
      setTimeout(() => setCopied(""), 1500)
    } catch {
      // ponytail: silent fail on clipboard denial — user sees no state change, can select manually
    }
  }

  const shareUrl =
    typeof window !== "undefined" ? `${window.location.origin}/lens/${sessionId}` : ""

  return (
    <div style={{ display: "inline-flex", alignItems: "center", gap: 10, marginLeft: 16 }}>
      <button
        type="button"
        onClick={() => copy(sessionId, "id")}
        title={`Session ID: ${sessionId} (click to copy)`}
        style={{
          fontFamily: "var(--font-mono, ui-monospace, monospace)",
          fontSize: 12,
          color: "var(--text-muted)",
          background: "var(--surface-2)",
          border: "1px solid var(--border-subtle)",
          borderRadius: 4,
          padding: "2px 8px",
          cursor: "pointer",
        }}
      >
        {copied === "id" ? "copied ✓" : sessionId.slice(0, 8)}
      </button>
      <button
        type="button"
        onClick={() => copy(shareUrl, "url")}
        title="Copy shareable link"
        style={{
          fontSize: 12,
          color: "var(--text-muted)",
          background: "transparent",
          border: "1px solid var(--border-subtle)",
          borderRadius: 4,
          padding: "2px 8px",
          cursor: "pointer",
        }}
      >
        {copied === "url" ? "copied ✓" : "share link"}
      </button>
    </div>
  )
}

interface LensSessionResponse {
  session_id: string
  ready: boolean
  spec?: GlensDashboardSpec
}

export default function LensSessionPage() {
  const params = useParams()
  const sessionId = typeof params.sessionId === "string" ? params.sessionId : ""

  const { authFetch, workspaceId } = useAuthFetch()

  const [spec, setSpec] = useState<GlensDashboardSpec | null>(null)
  const [loadingSpec, setLoadingSpec] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const abortRef = useRef<AbortController | null>(null)

  useEffect(() => {
    return () => {
      abortRef.current?.abort()
    }
  }, [])

  useEffect(() => {
    if (!sessionId || !workspaceId) return

    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller

    async function load() {
      setLoadingSpec(true)
      setError(null)

      try {
        const res = await authFetch(`${API}/glens/sessions/${sessionId}`, {
          signal: controller.signal,
        })

        if (!res.ok) {
          setError(`Could not load dashboard (${res.status}).`)
          setLoadingSpec(false)
          return
        }

        const data: LensSessionResponse = await res.json()

        if (!data.spec) {
          setError("This session does not have a dashboard.")
          setLoadingSpec(false)
          return
        }

        setSpec(data.spec)
      } catch (err) {
        if (err instanceof Error && err.name === "AbortError") return
        setError("Network error loading dashboard.")
      } finally {
        setLoadingSpec(false)
      }
    }

    load()
  }, [sessionId, workspaceId, authFetch])

  return (
    <AppShell>
      <div
        style={{
          maxWidth: 900,
          margin: "0 auto",
          padding: "32px 24px 64px",
        }}
      >
        <div style={{ marginBottom: 28, display: "flex", alignItems: "center" }}>
          <Link
            href="/lens"
            style={{
              fontSize: 13,
              color: "var(--text-muted)",
              textDecoration: "none",
              display: "inline-flex",
              alignItems: "center",
              gap: 6,
            }}
          >
            ← Back to Lens
          </Link>
          {sessionId && <SessionIdBadge sessionId={sessionId} />}
        </div>

        {loadingSpec && (
          <div>
            <div
              style={{
                height: 28,
                width: 260,
                background: "var(--surface-2)",
                borderRadius: 6,
                marginBottom: 24,
              }}
            />
            <div
              style={{
                display: "flex",
                gap: 12,
                marginBottom: 24,
              }}
            >
              {[1, 2, 3].map(n => (
                <div
                  key={n}
                  style={{
                    flex: "1 1 140px",
                    height: 80,
                    background: "var(--surface-2)",
                    borderRadius: 8,
                  }}
                />
              ))}
            </div>
            <div
              style={{
                height: 180,
                background: "var(--surface-2)",
                borderRadius: 8,
              }}
            />
          </div>
        )}

        {!loadingSpec && error && (
          <div
            style={{
              padding: "16px 20px",
              background: "var(--err-bg)",
              border: "1px solid var(--err-bd)",
              borderRadius: "var(--r-card)",
              fontSize: 14,
              color: "var(--err)",
            }}
          >
            {error}
          </div>
        )}

        {!loadingSpec && spec && (
          <GlensDashboard
            spec={spec}
            sessionId={sessionId}
            compact={false}
            authFetch={authFetch}
          />
        )}
      </div>
    </AppShell>
  )
}
