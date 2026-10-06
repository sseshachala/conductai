"use client"

import { useEffect, useRef } from "react"
import { apiUrl } from "@/lib/auth/runtime"

export interface RunStreamEvent {
  id?: string | number
  kind: string
  block_id?: string | null
  payload: Record<string, unknown>
  [key: string]: unknown
}

interface Options {
  workflowId: string
  runId: string
  getToken?: (() => Promise<string | null>) | null
  workspaceId: string | null | undefined
  /** False once the caller knows the run is finished — no (re)connect. */
  enabled?: boolean
  onEvent: (event: RunStreamEvent) => void
  /** Server sent the `[DONE]` terminal frame; the stream will not reconnect. */
  onDone?: () => void
  onOpen?: () => void
  /** Connection dropped; a reconnect is already scheduled. */
  onError?: () => void
}

/**
 * The one SSE client for `/workflows/{id}/runs/{id}/stream`.
 *
 * - Reconnects with exponential backoff (1s → 30s) until `[DONE]`.
 * - The server replays the run from the start on every connect, so events are
 *   de-duplicated by id across reconnects — handlers see each event once, in order.
 * - Callbacks are read through a ref, so re-renders never tear down the stream.
 */
export function useRunEventStream({ workflowId, runId, getToken, workspaceId, enabled = true, onEvent, onDone, onOpen, onError }: Options) {
  const handlers = useRef({ onEvent, onDone, onOpen, onError, getToken, workspaceId })
  handlers.current = { onEvent, onDone, onOpen, onError, getToken, workspaceId }

  useEffect(() => {
    if (!enabled) return
    let es: EventSource | null = null
    let cancelled = false
    let finished = false
    let attempt = 0
    let retryTimer: ReturnType<typeof setTimeout> | null = null
    const seen = new Set<string | number>()

    async function connect() {
      if (cancelled) return
      const params = new URLSearchParams()
      const token = handlers.current.getToken ? await handlers.current.getToken() : null
      if (token) params.set("token", token)
      if (handlers.current.workspaceId) params.set("workspace_id", handlers.current.workspaceId)
      if (cancelled) return
      const qs = params.toString() ? `?${params}` : ""
      es = new EventSource(`${apiUrl()}/workflows/${workflowId}/runs/${runId}/stream${qs}`)
      es.onopen = () => { attempt = 0; handlers.current.onOpen?.() }
      es.onmessage = (e) => {
        if (cancelled) return
        if (e.data === "[DONE]") {
          finished = true
          es?.close()
          handlers.current.onDone?.()
          return
        }
        let event: RunStreamEvent
        try { event = JSON.parse(e.data) } catch { return }
        if (event.id != null) {
          if (seen.has(event.id)) return
          seen.add(event.id)
        }
        handlers.current.onEvent(event)
      }
      es.onerror = () => {
        es?.close()
        if (cancelled || finished) return
        handlers.current.onError?.()
        const delay = Math.min(1000 * 2 ** attempt, 30_000)
        attempt++
        retryTimer = setTimeout(connect, delay)
      }
    }

    connect()
    return () => { cancelled = true; es?.close(); if (retryTimer) clearTimeout(retryTimer) }
  }, [workflowId, runId, enabled])
}
