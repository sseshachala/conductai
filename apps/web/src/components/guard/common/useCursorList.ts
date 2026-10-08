"use client"

import { useCallback, useEffect, useRef, useState } from "react"

interface Opts<T> { limit?: number; mode?: "cursor" | "offset"; cursorOf?: (row: T) => string; enabled?: boolean }

/** Default cursor: `${ts}|${id}`. Pass `cursorOf` for rows keyed on another time field. */
const defaultCursor = (row: unknown) => { const r = row as { ts: string; id: string }; return `${r.ts}|${r.id}` }

/**
 * Paged list state. `fetchPage(before?, offset?)` must be stable (useCallback); a new identity resets the list.
 * cursor mode passes `before` built from the last row; offset mode passes `offset` = rows loaded so far.
 * `loading` is true for the first page only; `loadingMore` for later pages. hasMore = page.length === limit.
 */
export function useCursorList<T>(fetchPage: (before?: string, offset?: number) => Promise<T[]>, opts: Opts<T> = {}) {
  const { limit = 50, mode = "cursor", cursorOf = defaultCursor, enabled = true } = opts
  const [rows, setRows] = useState<T[]>([])
  const [loading, setLoading] = useState(enabled)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [hasMore, setHasMore] = useState(false)
  const gen = useRef(0)
  const busy = useRef(false)
  const rowsRef = useRef<T[]>([])
  rowsRef.current = rows

  const run = useCallback(async (first: boolean) => {
    if (!first && busy.current) return
    const id = first ? ++gen.current : gen.current
    busy.current = true
    if (first) setLoading(true); else setLoadingMore(true)
    setError(null)
    try {
      const cur = first ? [] : rowsRef.current
      const last = cur[cur.length - 1]
      const page = await fetchPage(mode === "cursor" && last ? cursorOf(last) : undefined, mode === "offset" ? cur.length : 0)
      if (id !== gen.current) return
      setRows(first ? page : [...cur, ...page])
      setHasMore(page.length === limit)
    } catch (e) {
      if (id === gen.current) setError(e instanceof Error ? e.message : "Unable to load")
    } finally {
      if (id === gen.current) { busy.current = false; setLoading(false); setLoadingMore(false) }
    }
  }, [fetchPage, limit, mode, cursorOf])

  useEffect(() => {
    if (!enabled) { setLoading(false); return }
    const g = gen, b = busy
    void run(true)
    return () => { g.current++; b.current = false }
  }, [enabled, fetchPage]) // eslint-disable-line react-hooks/exhaustive-deps

  const loadMore = useCallback(() => { if (hasMore) void run(false) }, [hasMore, run])
  const reload = useCallback(() => run(true), [run])
  return { rows, loading, loadingMore, error, hasMore, loadMore, reload }
}
