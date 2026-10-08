"use client"

import { Fragment, useEffect, useRef, type ReactNode } from "react"
import { GuardSkeletonRows } from "./GuardSkeletonRows"

export interface GuardListProps<T> {
  rows: T[]
  renderRow: (row: T, index: number) => ReactNode
  getKey: (row: T) => string
  /** First load only; never pass the load-more state here. */
  loading?: boolean
  hasMore?: boolean
  onLoadMore?: () => void
  loadingMore?: boolean
  emptyState?: ReactNode
  /** Sticky "N new ↑" pill; clicking calls onShowNew. */
  newCount?: number
  onShowNew?: () => void
  skeletonRows?: number
  /** Spaced, rounded skeleton cards (for lists not inside a card). */
  skeletonGap?: boolean
  /** Wrap the rows (e.g. <table><tbody>…); the load-more footer stays outside. */
  wrap?: (rows: ReactNode) => ReactNode
}

export function GuardList<T>({
  rows, renderRow, getKey, loading, hasMore, onLoadMore, loadingMore, emptyState,
  newCount = 0, onShowNew, skeletonRows = 4, skeletonGap, wrap,
}: GuardListProps<T>) {
  const sentinel = useRef<HTMLDivElement>(null)
  const load = useRef(onLoadMore)
  load.current = onLoadMore
  useEffect(() => {
    const el = sentinel.current
    if (!el || !hasMore || loadingMore || typeof IntersectionObserver === "undefined") return
    const io = new IntersectionObserver(([e]) => { if (e.isIntersecting) load.current?.() }, { rootMargin: "200px" })
    io.observe(el)
    return () => io.disconnect()
  }, [hasMore, loadingMore, rows.length])

  if (loading) return <GuardSkeletonRows count={skeletonRows} gap={skeletonGap} />
  if (rows.length === 0) return <>{emptyState ?? null}</>
  const items = rows.map((r, i) => <Fragment key={getKey(r)}>{renderRow(r, i)}</Fragment>)
  return (
    <div>
      {newCount > 0 && onShowNew && (
        <div style={{ position: "sticky", top: 8, zIndex: 5, display: "flex", justifyContent: "center", pointerEvents: "none" }}>
          <button type="button" className="btn btn-sm" onClick={onShowNew} style={{ pointerEvents: "auto" }}>
            {newCount} new ↑
          </button>
        </div>
      )}
      {wrap ? wrap(items) : items}
      {hasMore && (
        <div ref={sentinel} style={{ padding: "10px 0", textAlign: "center" }}>
          <button type="button" className="btn btn-ghost btn-sm" disabled={loadingMore} onClick={onLoadMore}>
            {loadingMore ? "Loading…" : "Load more"}
          </button>
        </div>
      )}
    </div>
  )
}
