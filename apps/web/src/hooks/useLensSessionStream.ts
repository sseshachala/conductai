"use client"

/**
 * Client for the Lens session SSE stream (#1480 PR 4).
 *
 *   GET /glens/sessions/{id}/stream  →  SSE frames of session events
 *
 * We use fetch + ReadableStream instead of the browser's EventSource so we
 * can attach the Clerk Bearer token + X-Workspace-ID header (EventSource
 * only supports cookies). The wire format is standard SSE; we parse it in
 * ~30 lines below.
 *
 * Consumers use `useLensEvent(stream, entityType, entityId, handler)` from
 * `useLensEvent.ts` to react to events for one entity (approval/run) without
 * building a global reducer.
 *
 * Reconnect: on network error / stream end, wait 3s and reconnect with the
 * last-seen event id so the server replays anything we missed.
 *
 * Feature flag: NEXT_PUBLIC_LENS_SSE_SURFACE === "true" — off by default.
 */
import { useEffect, useRef, useState } from "react"

import { API } from "@/lib/api"

import { useAuthFetch } from "./useAuthFetch"

export type LensEvent = {
  id: string
  type: string
  at: string
  entity?: { type: string; id: string }
  payload?: Record<string, unknown>
}

type Subscriber = {
  predicate: (evt: LensEvent) => boolean
  handler: (evt: LensEvent) => void
}

export type LensSessionStream = {
  subscribe: (
    predicate: (evt: LensEvent) => boolean,
    handler: (evt: LensEvent) => void,
  ) => () => void
}

const SSE_ENABLED = process.env.NEXT_PUBLIC_LENS_SSE_SURFACE === "true"
const RECONNECT_DELAY_MS = 3000


export function useLensSessionStream(sessionId: string | null): LensSessionStream | null {
  const { authFetch } = useAuthFetch()
  const subsRef = useRef<Subscriber[]>([])
  const [stream, setStream] = useState<LensSessionStream | null>(null)

  useEffect(() => {
    if (!SSE_ENABLED || !sessionId) {
      setStream(null)
      return
    }

    let cancelled = false
    let lastEventId: string | null = null
    let controller = new AbortController()

    const streamHandle: LensSessionStream = {
      subscribe(predicate, handler) {
        const sub = { predicate, handler }
        subsRef.current.push(sub)
        return () => {
          subsRef.current = subsRef.current.filter((s) => s !== sub)
        }
      },
    }
    setStream(streamHandle)

    const dispatch = (evt: LensEvent) => {
      for (const sub of subsRef.current) {
        try {
          if (sub.predicate(evt)) sub.handler(evt)
        } catch {
          // Subscriber threw — swallow so one bad bubble doesn't nuke the stream.
        }
      }
    }

    const connect = async () => {
      while (!cancelled) {
        controller = new AbortController()
        try {
          const headers: Record<string, string> = {}
          if (lastEventId) headers["Last-Event-Id"] = lastEventId
          const res = await authFetch(`${API}/glens/sessions/${sessionId}/stream`, {
            method: "GET",
            headers,
            signal: controller.signal,
          })
          if (!res.ok || !res.body) {
            throw new Error(`stream open failed: ${res.status}`)
          }

          const reader = res.body.getReader()
          const decoder = new TextDecoder()
          let buf = ""

          while (!cancelled) {
            const { done, value } = await reader.read()
            if (done) break
            buf += decoder.decode(value, { stream: true })

            // SSE frames are separated by a blank line.
            const parts = buf.split("\n\n")
            buf = parts.pop() ?? ""
            for (const raw of parts) {
              // Ignore SSE comments (keepalives) — they start with ":".
              if (raw.startsWith(":") || raw.trim() === "") continue

              let idLine = ""
              let dataLine = ""
              for (const line of raw.split("\n")) {
                if (line.startsWith("id: ")) idLine = line.slice(4)
                else if (line.startsWith("data: ")) dataLine = line.slice(6)
              }
              if (!dataLine) continue

              try {
                const parsed = JSON.parse(dataLine) as LensEvent
                if (idLine) lastEventId = idLine
                else if (parsed.id) lastEventId = parsed.id
                dispatch(parsed)
              } catch {
                // Malformed frame — skip, don't crash the stream.
              }
            }
          }
        } catch (err) {
          if (cancelled) return
          if (err instanceof Error && err.name === "AbortError") return
          // Fall through to reconnect after delay.
        }
        if (cancelled) return
        await new Promise((r) => setTimeout(r, RECONNECT_DELAY_MS))
      }
    }

    connect()

    return () => {
      cancelled = true
      controller.abort()
      subsRef.current = []
      setStream(null)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId])

  return stream
}
