"use client"

/**
 * Subscribe a component to Lens session events for one entity (#1480 PR 4).
 *
 * Component-level entity subscription — no global reducer, no coupled state.
 * Each bubble subscribes to its own approval_id or run_id and reacts when
 * events arrive from the session stream.
 *
 * Silent no-op when `stream` is null (feature flag off, or no active session).
 */
import { useEffect, useRef } from "react"

import type { LensEvent, LensSessionStream } from "./useLensSessionStream"


export function useLensEvent(
  stream: LensSessionStream | null,
  entityType: string,
  entityId: string | null | undefined,
  handler: (evt: LensEvent) => void,
): void {
  // Keep the latest handler in a ref so we don't tear down + re-subscribe
  // every time the parent re-renders with a new closure.
  const handlerRef = useRef(handler)
  handlerRef.current = handler

  useEffect(() => {
    if (!stream || !entityId) return
    return stream.subscribe(
      (evt) => evt.entity?.type === entityType && evt.entity?.id === entityId,
      (evt) => handlerRef.current(evt),
    )
  }, [stream, entityType, entityId])
}
