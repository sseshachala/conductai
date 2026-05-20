"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import type { Edge, Node } from "@xyflow/react"

import { autoLayout } from "@/lib/auto-layout"
import { yamlFilenameFor } from "@/lib/yaml-filename"

type Status = "idle" | "loading" | "saving" | "saved" | "error"

interface YamlPanelProps {
  workflowId: string
  workflowName: string
  nodes: Node[]
  edges: Edge[]
  onLoaded: (next: { name?: string; nodes: Node[]; edges: Edge[] }) => void
}

const API = process.env.NEXT_PUBLIC_API_URL

/**
 * YAML view of the workflow. The user can:
 *   - inspect what the canvas serialises to (regenerated whenever the canvas changes)
 *   - paste a workflow YAML and load it onto the canvas
 *   - save the current YAML as the new workflow definition
 *
 * The canvas remains the design tool; YAML is the deployment artifact. The
 * conversions both directions are handled server-side so the schema is owned
 * by a single source of truth (apps/api/app/dsl).
 */
export default function YamlPanel({
  workflowId,
  workflowName,
  nodes,
  edges,
  onLoaded,
}: YamlPanelProps) {
  const [yamlText, setYamlText] = useState("")
  const [status, setStatus] = useState<Status>("idle")
  const [error, setError] = useState<string | null>(null)

  // Regenerate YAML whenever the canvas changes underneath us. This is the
  // "view" half of the round-trip.
  useEffect(() => {
    let cancelled = false
    setStatus("loading")
    setError(null)
    fetch(`${API}/workflows/yaml/from-graph`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        id: workflowId,
        workspace_id: document.cookie.match(/delegator_project_id=([^;]+)/)?.[1],
        name: workflowName,
        graph: { nodes, edges },
      }),
    })
      .then(async (r) => {
        if (!r.ok) throw new Error((await r.json()).detail || `HTTP ${r.status}`)
        return r.json() as Promise<{ yaml: string }>
      })
      .then((data) => {
        if (cancelled) return
        setYamlText(data.yaml)
        setStatus("idle")
      })
      .catch((e) => {
        if (cancelled) return
        setError(String(e.message ?? e))
        setStatus("error")
      })
    return () => {
      cancelled = true
    }
  }, [workflowName, nodes, edges])

  const save = useCallback(async () => {
    setStatus("saving")
    setError(null)
    try {
      // 1. Validate + persist YAML on the server.
      const putRes = await fetch(`${API}/workflows/${workflowId}/yaml`, {
        method: "PUT",
        headers: { "Content-Type": "application/x-yaml" },
        body: yamlText,
      })
      if (!putRes.ok) {
        const detail = await putRes.json().catch(() => ({}))
        throw new Error(detail.detail || `Save failed (${putRes.status})`)
      }

      // 2. Pull the derived graph straight from validate — this is the same
      //    graph the runtime will execute, so the canvas stays in sync.
      const valRes = await fetch(`${API}/workflows/yaml/validate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ yaml: yamlText }),
      })
      const val = (await valRes.json()) as {
        ok: boolean
        error?: string
        name?: string
        graph?: { nodes: Node[]; edges: Edge[] }
      }
      if (!val.ok || !val.graph) {
        throw new Error(val.error || "Invalid YAML")
      }

      const { nodes: laidOut, edges: layoutEdges } = autoLayout(
        val.graph.nodes,
        val.graph.edges,
      )
      onLoaded({ name: val.name, nodes: laidOut, edges: layoutEdges })
      setStatus("saved")
      setTimeout(() => setStatus("idle"), 1500)
    } catch (e) {
      setError((e as Error).message)
      setStatus("error")
    }
  }, [workflowId, yamlText, onLoaded])

  const copy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(yamlText)
    } catch {
      /* no-op — clipboard isn't critical */
    }
  }, [yamlText])

  // Canonical filename for this workflow: `<projectname>-delegator.yml`.
  // The "projectname" portion is the slugified workflow name — so each
  // workflow in a workspace gets its own file even if the user keeps them
  // all in the same repo.
  const filename = useMemo(() => yamlFilenameFor(workflowName), [workflowName])

  const download = useCallback(() => {
    const blob = new Blob([yamlText], { type: "application/x-yaml" })
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }, [yamlText, filename])

  return (
    <div className="flex flex-col h-full bg-white border-l border-stone-200">
      <div className="flex items-center justify-between px-4 py-2 border-b border-stone-200 shrink-0">
        <div className="text-xs font-mono text-stone-600" title="Suggested filename when committing to your repo">
          {filename}
        </div>
        <div className="flex items-center gap-2">
          <span
            className={`text-xs transition-opacity duration-200 ${
              status === "saving"
                ? "text-amber-500"
                : status === "saved"
                  ? "text-green-600"
                  : status === "error"
                    ? "text-red-600"
                    : "text-stone-400"
            }`}
          >
            {status === "saving"
              ? "Saving…"
              : status === "saved"
                ? "Saved ✓"
                : status === "loading"
                  ? "Generating…"
                  : status === "error"
                    ? "Error"
                    : ""}
          </span>
          <button
            onClick={copy}
            className="text-xs text-stone-500 hover:text-stone-900 px-2 py-1 rounded hover:bg-stone-100"
          >
            Copy
          </button>
          <button
            onClick={download}
            className="text-xs text-stone-500 hover:text-stone-900 px-2 py-1 rounded hover:bg-stone-100"
          >
            Download
          </button>
          <button
            onClick={save}
            disabled={status === "saving" || status === "loading"}
            className="text-xs rounded-md bg-violet-600 text-white font-semibold px-3 py-1 hover:bg-violet-700 disabled:opacity-50"
          >
            Save YAML
          </button>
        </div>
      </div>

      {error ? (
        <div className="px-4 py-2 text-xs text-red-700 bg-red-50 border-b border-red-100 whitespace-pre-wrap">
          {error}
        </div>
      ) : null}

      <textarea
        spellCheck={false}
        value={yamlText}
        onChange={(e) => setYamlText(e.target.value)}
        className="flex-1 font-mono text-[12px] leading-relaxed text-stone-800 bg-stone-50 p-4 outline-none resize-none"
      />
    </div>
  )
}
