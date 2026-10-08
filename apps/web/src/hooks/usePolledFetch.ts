"use client"

import { useCallback, useEffect, useRef } from "react"

/**
 * Visibility-aware polling. Calls `tick` every `intervalMs` while the tab is
 * visible, pauses while hidden, and ticks immediately when the tab becomes
 * visible again. `tick` should be a background refresh (never set the
 * initial-loading flag). The latest `tick` is always used, so changing its
 * identity does not restart the interval. Does not tick on mount.
 */
export function usePolledFetch(
  tick: () => void,
  intervalMs: number,
  enabled: boolean = true,
): void {
  const tickRef = useRef(tick)
  tickRef.current = tick

  useEffect(() => {
    if (!enabled) return
    let id: ReturnType<typeof setInterval> | null = null
    const run = () => tickRef.current()
    const start = () => { if (id === null) id = setInterval(run, intervalMs) }
    const stop = () => { if (id !== null) { clearInterval(id); id = null } }
    const onVis = () => {
      if (document.visibilityState === "visible") { run(); start() } else stop()
    }
    if (document.visibilityState === "visible") start()
    document.addEventListener("visibilitychange", onVis)
    return () => {
      document.removeEventListener("visibilitychange", onVis)
      stop()
    }
  }, [intervalMs, enabled])
}

/**
 * Stale-response guard. `const isCurrent = begin()` at the start of a fetch;
 * after awaiting, `if (!isCurrent()) return` drops the response if a newer
 * fetch has started.
 */
export function useLatestRequest(): () => () => boolean {
  const epoch = useRef(0)
  return useCallback(() => {
    const mine = ++epoch.current
    return () => mine === epoch.current
  }, [])
}
