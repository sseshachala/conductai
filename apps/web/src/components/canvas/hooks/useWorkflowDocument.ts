import { useCallback, useEffect, useRef, useState, type MutableRefObject } from "react"
import { MarkerType, useReactFlow, type Edge, type Node } from "@xyflow/react"
import type { BlockNodeData } from "../BlockNode"
import type { SaveStatus } from "../CanvasHeader"
import { autoLayout } from "@/lib/auto-layout"
import { splitAnnotations, withLockState } from "@/lib/canvas/annotations"
import { workflows, credentials, environments as environmentsApi } from "@/lib/api"
import { authHeaders, makeAuthFetch, type GetToken } from "./useCanvasRuns"

const styleEdges = (es: Edge[]) => es.map(e => ({
  ...e,
  type: e.type ?? "smoothstep",
  markerEnd: e.markerEnd ?? { type: MarkerType.ArrowClosed, width: 12, height: 12, color: "#a8a29e" },
  style: e.style ?? { stroke: "#a8a29e", strokeWidth: 2 },
}))

/** React Flow state → persisted graph: blocks in `nodes`, sticky notes in `annotations`. */
export function toStoredGraph(nodes: Node[], edges: Edge[]) {
  const { blocks, annotations } = splitAnnotations(nodes)
  return {
    nodes: blocks,
    edges,
    annotations: annotations.map(({ id, type, position, width, height, zIndex, data }) => ({ id, type, position, width, height, zIndex, data })),
  }
}

/** Warning text for blocks the runtime's topological sort would reject. */
export function cycleNotice(cycleNodeIds: string[], nodes: Node[]): string | null {
  if (cycleNodeIds.length === 0) return null
  const labels = cycleNodeIds.map(id => (nodes.find(n => n.id === id)?.data as BlockNodeData | undefined)?.label || id)
  return `This workflow has a loop involving: ${labels.join(", ")}. Runs will fail until you remove an edge to break it.`
}

interface Options {
  workflowId: string
  getToken: GetToken
  wsId: string | null
  isViewer: boolean
  nodes: Node[]
  edges: Edge[]
  setNodes: (nodes: Node[]) => void
  setEdges: (edges: Edge[]) => void
  isFirstLoad: MutableRefObject<boolean>
  setLayoutNotice: (notice: string | null) => void
}

/** Loads the workflow + its vault/environment context and autosaves graph edits. */
export function useWorkflowDocument({ workflowId, getToken, wsId, isViewer, nodes, edges, setNodes, setEdges, isFirstLoad, setLayoutNotice }: Options) {
  const { fitView } = useReactFlow()
  const [workflowName, setWorkflowName] = useState("Untitled agent")
  const [githubHookRepo, setGithubHookRepo] = useState<string | null>(null)
  const [githubHookId, setGithubHookId] = useState<string | null>(null)
  const [githubWebhook, setGithubWebhook] = useState<boolean>(false)
  const [saveStatus, setSaveStatus] = useState<SaveStatus>("idle")
  const autosaveTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const savingInFlightRef = useRef(false)
  const [canvasLoading, setCanvasLoading] = useState(true)
  const [environments, setEnvironments] = useState<Array<{ id: string; name: string }>>([])
  const [selectedEnvId, setSelectedEnvId] = useState<string>("")
  const [envCredentials, setEnvCredentials] = useState<Array<{ handle: string; service: string }>>([])
  const [playbookSlug, setPlaybookSlug] = useState<string | null>(null)
  const [projectSlug, setProjectSlug] = useState<string | null>(null)
  const [projectName, setProjectName] = useState<string | null>(null)

  // Load available environments for the environment picker
  useEffect(() => {
    const abort = new AbortController()
    ;(async () => {
      try {
        const headers = await authHeaders(getToken, wsId)
        if (abort.signal.aborted) return
        const list = await environmentsApi.list(makeAuthFetch(headers, abort.signal)).catch(() => [])
        if (!abort.signal.aborted) setEnvironments(list)
      } catch {}
    })()
    return () => abort.abort()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [getToken])

  // Load credentials for the selected environment
  useEffect(() => {
    if (!selectedEnvId) { setEnvCredentials([]); return }
    const abort = new AbortController()
    ;(async () => {
      try {
        const headers = await authHeaders(getToken, wsId)
        if (abort.signal.aborted) return
        const list = await credentials.byEnvironment(makeAuthFetch(headers, abort.signal), selectedEnvId).catch(() => [])
        if (!abort.signal.aborted) setEnvCredentials(list)
      } catch {}
    })()
    return () => abort.abort()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [getToken, selectedEnvId])

  // Load workflow on mount. When a graph arrives without meaningful positions
  // (the YAML loader writes placeholder coords), run dagre so it doesn't open
  // as a stack of overlapping nodes.
  useEffect(() => {
    if (!workflowId || workflowId === "undefined") return
    const abort = new AbortController()
    authHeaders(getToken, wsId)
      .then(headers => workflows.get(makeAuthFetch(headers, abort.signal), workflowId))
      .then((data) => {
        setWorkflowName(data.name)
        setSelectedEnvId(data.environment_id ?? "")
        setGithubHookRepo(data.github_hook_repo ?? null)
        setGithubHookId(data.github_hook_id ?? null)
        setGithubWebhook(data.github_webhook ?? false)
        setPlaybookSlug(data.playbook_slug ?? null)
        setProjectSlug(data.project_slug ?? null)
        setProjectName(data.project_name ?? null)
        const graph = data.current_version?.graph
        // Notes persist outside graph.nodes (see lib/canvas/annotations); merge them back for React Flow.
        const notes: Node[] = (graph?.annotations ?? []).map(withLockState)
        if (graph?.nodes && graph?.edges) {
          // Run auto-layout when:
          // (a) all nodes are at (0,0) — no positions assigned yet
          // (b) all nodes share the same y — backend placeholder grid (yaml_to_graph
          //     assigns sequential x columns but y=80 for every node)
          // User-repositioned graphs will have varied y values.
          const allAtOrigin = graph.nodes.every(
            (n: Node) => !n.position || (n.position.x === 0 && n.position.y === 0),
          )
          const allSameY = graph.nodes.length > 1 &&
            graph.nodes.every((n: Node) => n.position?.y === graph.nodes[0].position?.y)
          const laid = autoLayout(graph.nodes, graph.edges)
          setNodes([...(allAtOrigin || allSameY ? laid.nodes : graph.nodes), ...notes])
          setEdges(styleEdges(graph.edges))
          setLayoutNotice(cycleNotice(laid.cycleNodeIds, graph.nodes))
        } else {
          if (graph?.nodes || notes.length) setNodes([...(graph?.nodes ?? []), ...notes])
          if (graph?.edges) setEdges(styleEdges(graph.edges))
        }
        setTimeout(() => { isFirstLoad.current = false }, 100)
        setCanvasLoading(false)
        setTimeout(() => fitView({ padding: 0.15, duration: 400 }), 150)
      })
      .catch(() => { if (!abort.signal.aborted) { isFirstLoad.current = false; setCanvasLoading(false) } })
    return () => abort.abort()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workflowId, getToken, setNodes, setEdges])

  const handleEnvChange = useCallback(async (envId: string) => {
    setSelectedEnvId(envId)
    try {
      await workflows.patchEnvironment(makeAuthFetch(await authHeaders(getToken, wsId)), workflowId, { environment_id: envId || null })
    } catch { /* non-fatal */ }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workflowId, getToken])

  const save = useCallback(async (currentNodes: Node[], currentEdges: Edge[], name: string) => {
    if (!workflowId || workflowId === "undefined") return
    if (savingInFlightRef.current) return
    savingInFlightRef.current = true
    setSaveStatus("saving")
    try {
      const res = await workflows.update(makeAuthFetch(await authHeaders(getToken, wsId)), workflowId, { name, graph: toStoredGraph(currentNodes, currentEdges) })
      setSaveStatus(res.ok ? "saved" : "error")
      setTimeout(() => setSaveStatus("idle"), res.ok ? 2000 : 3000)
    } catch {
      setSaveStatus("error")
      setTimeout(() => setSaveStatus("idle"), 3000)
    } finally {
      savingInFlightRef.current = false
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workflowId, getToken])

  // Autosave — debounced 1.5s after any node/edge change (skip for viewers)
  useEffect(() => {
    if (isFirstLoad.current || isViewer) return
    if (autosaveTimer.current) clearTimeout(autosaveTimer.current)
    autosaveTimer.current = setTimeout(() => {
      save(nodes, edges, workflowName)
    }, 1500)
    return () => { if (autosaveTimer.current) clearTimeout(autosaveTimer.current) }
  }, [nodes, edges, workflowName, save, isViewer, isFirstLoad])

  /** Version restore: re-save an old graph through the normal PUT path, then reload. */
  const restoreGraph = async (graph: Record<string, unknown>) => {
    // A pending autosave of the current canvas must not land after (and undo) the restore.
    if (autosaveTimer.current) clearTimeout(autosaveTimer.current)
    isFirstLoad.current = true // blocks autosave until the reload
    try {
      const res = await workflows.update(makeAuthFetch(await authHeaders(getToken, wsId)), workflowId, { name: workflowName, graph })
      if (!res.ok) throw new Error(`Restore failed (${res.status})`)
    } catch (e) {
      isFirstLoad.current = false
      throw e
    }
    window.location.reload()
  }

  return {
    restoreGraph,
    workflowName, setWorkflowName, githubHookRepo, setGithubHookRepo, githubHookId, setGithubHookId, githubWebhook,
    saveStatus, canvasLoading, environments, selectedEnvId, envCredentials, handleEnvChange, playbookSlug, projectSlug, projectName,
  }
}
