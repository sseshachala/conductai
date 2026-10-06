"use client"

import { useEffect, useMemo, useState } from "react"
import { workflows, type WorkflowVersionSummary } from "@/lib/api/workflows"
import { diffGraphs, isEmptyDiff, type GraphDiff, type NodeChange, type StoredGraph } from "@/lib/canvas/graphDiff"
import { authHeaders, makeAuthFetch, type GetToken } from "./hooks/useCanvasRuns"

interface Props {
  workflowId: string
  getToken: GetToken
  wsId: string | null
  isViewer: boolean
  /** The graph as it is on the canvas right now (unsaved edits included). */
  currentGraph: StoredGraph
  /** Re-save an old graph through the normal PUT path, then reload. */
  onRestore: (graph: StoredGraph) => Promise<void>
}

const PAGE = 50
const clip = (s: string) => (s.length > 600 ? `${s.slice(0, 600)}…` : s)

/** Version list + "what changed since this version" diff, with permission-checked restore. */
export default function VersionHistory({ workflowId, getToken, wsId, isViewer, currentGraph, onRestore }: Props) {
  const [versions, setVersions] = useState<WorkflowVersionSummary[]>([])
  const [hasMore, setHasMore] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<{ id: string; graph: StoredGraph } | null>(null)
  const [confirming, setConfirming] = useState(false)
  const [restoring, setRestoring] = useState(false)

  const authFetch = async () => makeAuthFetch(await authHeaders(getToken, wsId))

  const loadPage = async (before?: string) => {
    setLoading(true)
    try {
      const page = await workflows.versions.list(await authFetch(), workflowId, { limit: PAGE, before })
      setVersions(prev => (before ? [...prev, ...page] : page))
      setHasMore(page.length === PAGE)
      setError(null)
    } catch {
      setError("Couldn't load version history.")
    } finally {
      setLoading(false)
    }
  }

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { loadPage() }, [workflowId])

  const select = async (id: string) => {
    setConfirming(false)
    try {
      const v = await workflows.versions.get(await authFetch(), workflowId, id)
      setSelected({ id, graph: v.graph as StoredGraph })
    } catch {
      setError("Couldn't load that version.")
    }
  }

  const diff = useMemo(() => (selected ? diffGraphs(selected.graph, currentGraph) : null), [selected, currentGraph])
  const selectedSummary = versions.find(v => v.id === selected?.id)

  const restore = async () => {
    if (!selected) return
    setRestoring(true)
    try { await onRestore(selected.graph) } catch { setError("Restore failed — nothing was changed."); setRestoring(false) }
  }

  return (
    <div className="flex flex-1 overflow-hidden">
      <aside className="w-72 shrink-0 border-r border-stone-200 bg-white overflow-y-auto" aria-label="Versions">
        <p className="px-4 pt-4 pb-2 text-[10px] font-semibold uppercase tracking-wider text-stone-400">Versions</p>
        <ul>
          {versions.map(v => (
            <li key={v.id}>
              <button
                onClick={() => select(v.id)}
                aria-current={selected?.id === v.id}
                className={`w-full text-left px-4 py-2.5 border-t border-stone-100 hover:bg-stone-50 ${selected?.id === v.id ? "bg-violet-50" : ""}`}
              >
                <div className="flex items-center gap-1.5">
                  <span className="text-xs font-medium text-stone-800">{new Date(v.created_at).toLocaleString()}</span>
                  {v.is_current && <span className="text-[9px] font-semibold text-violet-700 bg-violet-100 px-1.5 py-0.5 rounded-full">current</span>}
                  {v.from_yaml && <span className="text-[9px] font-semibold text-stone-600 bg-stone-100 px-1.5 py-0.5 rounded-full">YAML</span>}
                </div>
                <span className="text-[11px] text-stone-400">
                  {v.node_count} blocks · {v.edge_count} edges{v.annotation_count ? ` · ${v.annotation_count} note${v.annotation_count === 1 ? "" : "s"}` : ""}
                </span>
              </button>
            </li>
          ))}
        </ul>
        {loading && <p className="px-4 py-3 text-xs text-stone-400">Loading…</p>}
        {hasMore && !loading && (
          <button onClick={() => loadPage(versions[versions.length - 1]?.created_at)} className="w-full px-4 py-3 text-xs text-violet-600 hover:underline">
            Load older versions
          </button>
        )}
      </aside>

      <section className="flex-1 overflow-y-auto px-6 py-6" aria-live="polite">
        {error && <p role="alert" className="mb-4 text-xs text-red-600">{error}</p>}
        {!selected || !diff ? (
          <p className="text-sm text-stone-400">Select a version to see what changed since then.</p>
        ) : (
          <div className="max-w-3xl">
            <div className="flex items-center justify-between gap-4 mb-5">
              <div>
                <h2 className="text-sm font-semibold text-stone-900">
                  Changes since {selectedSummary ? new Date(selectedSummary.created_at).toLocaleString() : "this version"}
                </h2>
                <p className="text-xs text-stone-400">Compared with the canvas as it is now. Positions are ignored.</p>
              </div>
              {!isViewer && !selectedSummary?.is_current && (
                confirming ? (
                  <div className="flex items-center gap-2">
                    <button onClick={restore} disabled={restoring} className="rounded-lg bg-violet-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-violet-700 disabled:opacity-50">
                      {restoring ? "Restoring…" : "Confirm restore"}
                    </button>
                    <button onClick={() => setConfirming(false)} className="text-xs text-stone-500 hover:text-stone-800">Cancel</button>
                  </div>
                ) : (
                  <button onClick={() => setConfirming(true)} className="rounded-lg border border-stone-200 px-3 py-1.5 text-xs font-medium text-stone-700 hover:bg-stone-50">
                    Restore this version
                  </button>
                )
              )}
            </div>
            {confirming && (
              <p className="mb-4 text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
                Restoring saves this version as a new current version. Nothing is deleted. You can restore the current one again from this list.
              </p>
            )}
            {isEmptyDiff(diff) ? <p className="text-sm text-stone-500">No differences.</p> : <DiffView diff={diff} />}
          </div>
        )}
      </section>
    </div>
  )
}

function DiffView({ diff }: { diff: GraphDiff }) {
  return (
    <div className="flex flex-col gap-5">
      <NodeSection title="Blocks" group={diff.blocks} />
      {(diff.edges.added.length > 0 || diff.edges.removed.length > 0) && (
        <div>
          <h3 className="text-[10px] font-semibold uppercase tracking-wider text-stone-400 mb-1.5">Connections</h3>
          <ul className="font-mono text-xs">
            {diff.edges.added.map(e => <li key={`+${e}`} className="text-emerald-700">+ {e}</li>)}
            {diff.edges.removed.map(e => <li key={`-${e}`} className="text-red-600">− {e}</li>)}
          </ul>
        </div>
      )}
      <NodeSection title="Notes" group={diff.notes} />
    </div>
  )
}

function NodeSection({ title, group }: { title: string; group: GraphDiff["blocks"] }) {
  if (!group.added.length && !group.removed.length && !group.changed.length) return null
  return (
    <div>
      <h3 className="text-[10px] font-semibold uppercase tracking-wider text-stone-400 mb-1.5">{title}</h3>
      <ul className="flex flex-col gap-1 text-xs">
        {group.added.map(n => <li key={`+${n.id}`} className="text-emerald-700">+ {n.label}</li>)}
        {group.removed.map(n => <li key={`-${n.id}`} className="text-red-600">− {n.label}</li>)}
      </ul>
      {group.changed.map(n => <ChangedNode key={n.id} change={n} />)}
    </div>
  )
}

function ChangedNode({ change }: { change: NodeChange }) {
  return (
    <div className="mt-2 rounded-lg border border-stone-200 bg-white">
      <p className="px-3 py-2 text-xs font-medium text-stone-800 border-b border-stone-100">~ {change.label}</p>
      <table className="w-full text-[11px]">
        <tbody>
          {change.fields.map(f => (
            <tr key={f.path} className="border-t border-stone-50 align-top">
              <td className="px-3 py-1.5 font-mono text-stone-500 whitespace-nowrap">
                {f.path}
                {f.governance && <span className="ml-1.5 text-[9px] font-semibold text-amber-700 bg-amber-100 px-1 py-0.5 rounded">governance</span>}
              </td>
              <td className="px-3 py-1.5 text-red-600 line-through break-all">{clip(f.before)}</td>
              <td className="px-3 py-1.5 text-emerald-700 break-all">{clip(f.after)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
