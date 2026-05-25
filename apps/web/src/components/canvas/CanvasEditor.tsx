"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { useRouter } from "next/navigation"
import { useAuth } from "@clerk/nextjs"
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  addEdge,
  useNodesState,
  useEdgesState,
  useReactFlow,
  ReactFlowProvider,
  ConnectionMode,
  ConnectionLineType,
  MarkerType,
  type Connection,
  type Node,
  type Edge,
  BackgroundVariant,
} from "@xyflow/react"
import "@xyflow/react/dist/style.css"

import BlockNode, { type BlockNodeData } from "./BlockNode"
import BlockEditor from "./BlockEditor"
import BlockPalette from "./BlockPalette"
import RunDrawer from "./RunDrawer"
import CostEstimate from "./CostEstimate"
import YamlPanel from "./YamlPanel"
import { autoLayout } from "@/lib/auto-layout"
import { type BlockType } from "@/lib/block-types"

const nodeTypes = { block: BlockNode }

type SaveStatus = "idle" | "saving" | "saved" | "error"

interface ValidationError {
  blockId: string
  label: string
  message: string
}

function validateNodes(nodes: Node[]): ValidationError[] {
  const errors: ValidationError[] = []

  for (const node of nodes) {
    const data = node.data as BlockNodeData
    const blockType = data.type
    const label = data.label || node.id
    const config = (data.config as Record<string, unknown>) ?? {}
    const integration = data.integration as string | undefined

    if (blockType === "tool" || blockType === "cleanup") {
      if (!integration) {
        errors.push({ blockId: node.id, label, message: "No integration selected" })
        continue
      }
      const action = (config.action as string) || ""
      if (!action) {
        errors.push({ blockId: node.id, label, message: `No action selected for ${integration}` })
        continue
      }
      // Check required params (non-empty, no defaultValue)
      const params = (config.params as Record<string, unknown>) ?? {}
      const requiredEmpty: string[] = []
      for (const [key, val] of Object.entries(params)) {
        if ((val === "" || val === null || val === undefined) && !String(val ?? "").startsWith("{{")) {
          requiredEmpty.push(key)
        }
      }
      if (requiredEmpty.length > 0) {
        errors.push({ blockId: node.id, label, message: `Missing: ${requiredEmpty.join(", ")}` })
      }
    }

    if (blockType === "output") {
      const via = integration || "slack"
      if ((via === "slack" || via === "both") && !config.channel) {
        errors.push({ blockId: node.id, label, message: "Slack channel is required (e.g. #general)" })
      }
      if ((via === "email" || via === "both") && !(config.to as string)) {
        errors.push({ blockId: node.id, label, message: "Email address (To) is required" })
      }
    }

    if (blockType === "approval") {
      if (!config.message) {
        errors.push({ blockId: node.id, label, message: "Approval message is required" })
      }
    }
  }

  return errors
}

interface CanvasEditorProps {
  workflowId: string
  getToken?: (() => Promise<string | null>) | null
  isViewer?: boolean
}

function getWorkspaceId(): string | null {
  if (typeof document === "undefined") return null
  return document.cookie
    .split("; ")
    .find(r => r.startsWith("delegator_project_id="))
    ?.split("=")[1] ?? null
}

async function authHeaders(getToken?: (() => Promise<string | null>) | null): Promise<Record<string, string>> {
  const headers: Record<string, string> = { "Content-Type": "application/json" }
  if (getToken) {
    const token = await getToken()
    if (token) headers["Authorization"] = `Bearer ${token}`
  }
  const ws = getWorkspaceId()
  if (ws) headers["X-Workspace-Id"] = ws
  return headers
}

function CanvasEditorInner({ workflowId, getToken, isViewer = false }: CanvasEditorProps) {
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([])
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([])
  const [selectedNode, setSelectedNode] = useState<Node | null>(null)
  const [workflowName, setWorkflowName] = useState("Untitled agent")
  const [saveStatus, setSaveStatus] = useState<SaveStatus>("idle")
  const autosaveTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const isFirstLoad = useRef(true)
  const { screenToFlowPosition, setCenter, fitView } = useReactFlow()
  const router = useRouter()
  const [canvasLoading, setCanvasLoading] = useState(true)
  const [running, setRunning] = useState<"idle" | "dry" | "live">("idle")
  const [activeRunId, setActiveRunId] = useState<string | null>(null)
  const [drawerVisible, setDrawerVisible] = useState(false)
  const [validationErrors, setValidationErrors] = useState<ValidationError[]>([])
  const [preflight, setPreflight] = useState<{
    suggestedTurns: number
    files: string[]
    pendingDryRun: boolean
    initialState?: Record<string, unknown>
  } | null>(null)
  const [leftOpen, setLeftOpen] = useState(true)
  const [rightOpen, setRightOpen] = useState(true)
  const [activeView, setActiveView] = useState<"canvas" | "yaml" | "runs">("canvas")
  const [runs, setRuns] = useState<{id:string;status:string;triggered_by:string|null;created_at:string}[]>([])
  const [runsLoading, setRunsLoading] = useState(false)
  const [environments, setEnvironments] = useState<Array<{ id: string; name: string }>>([])
  const [selectedEnvId, setSelectedEnvId] = useState<string>("")
  const [envCredentials, setEnvCredentials] = useState<Array<{ handle: string; service: string }>>([])
  // Webhook test modal — shown when manually running a webhook-triggered workflow
  const [webhookModal, setWebhookModal] = useState<{ dryRun: boolean } | null>(null)
  const [webhookRepo, setWebhookRepo] = useState("")
  const [webhookPrNumber, setWebhookPrNumber] = useState("")

  const STORAGE_KEY = `marshal:active-run:${workflowId}`

  // On mount, check if there's an in-progress run we navigated away from.
  useEffect(() => {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (!stored) return
    const { runId, startedAt } = JSON.parse(stored)
    // Ignore stale entries older than 2 hours
    if (Date.now() - startedAt > 2 * 60 * 60 * 1000) {
      localStorage.removeItem(STORAGE_KEY)
      return
    }
    authHeaders(getToken).then(headers =>
      fetch(`${process.env.NEXT_PUBLIC_API_URL}/workflows/${workflowId}/runs/${runId}`, { headers })
        .then(r => r.ok ? r.json() : null)
        .then(run => {
          if (!run) { localStorage.removeItem(STORAGE_KEY); return }
          if (run.status === "running" || run.status === "pending") {
            setActiveRunId(runId)
            setDrawerVisible(true)
          } else {
            localStorage.removeItem(STORAGE_KEY)
          }
        })
        .catch(() => localStorage.removeItem(STORAGE_KEY))
    )
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workflowId])

  // Load available environments for the environment picker
  useEffect(() => {
    authHeaders(getToken).then(headers =>
      fetch(`${process.env.NEXT_PUBLIC_API_URL}/environments`, { headers })
        .then(r => r.ok ? r.json() : [])
        .then(data => setEnvironments(data))
        .catch(() => {})
    )
  }, [getToken])

  // Load credentials for the selected environment
  useEffect(() => {
    if (!selectedEnvId) { setEnvCredentials([]); return }
    authHeaders(getToken).then(headers =>
      fetch(`${process.env.NEXT_PUBLIC_API_URL}/credentials/by-environment/${selectedEnvId}`, { headers })
        .then(r => r.ok ? r.json() : [])
        .then(data => setEnvCredentials(data))
        .catch(() => {})
    )
  }, [getToken, selectedEnvId])

  const fetchRuns = () => {
    if (!workflowId) return
    setRunsLoading(true)
    authHeaders(getToken).then(headers =>
      fetch(`${process.env.NEXT_PUBLIC_API_URL}/workflows/${workflowId}/runs`, { headers })
        .then(r => r.ok ? r.json() : [])
        .then(data => { setRuns(data); setRunsLoading(false) })
        .catch(() => setRunsLoading(false))
    )
  }

  useEffect(() => {
    if (activeView !== "runs") return
    fetchRuns()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeView, workflowId, getToken])

  // Auto-poll every 5s while any run is active
  useEffect(() => {
    if (activeView !== "runs") return
    const hasActive = runs.some(r => r.status === "pending" || r.status === "running")
    if (!hasActive) return
    const t = setInterval(fetchRuns, 5000)
    return () => clearInterval(t)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeView, runs])

  // Load workflow on mount. When a graph arrives without meaningful positions
  // (the YAML loader writes placeholder coords), run dagre so it doesn't open
  // as a stack of overlapping nodes.
  useEffect(() => {
    if (!workflowId || workflowId === "undefined") return
    authHeaders(getToken).then(headers =>
    fetch(`${process.env.NEXT_PUBLIC_API_URL}/workflows/${workflowId}`, { headers })
      .then(async (r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json() })
      .then((data) => {
        setWorkflowName(data.name)
        setSelectedEnvId(data.environment_id ?? "")
        const graph = data.current_version?.graph
        if (graph?.nodes && graph?.edges) {
          // Run auto-layout when:
          // (a) all nodes are at (0,0) — no positions assigned yet
          // (b) all nodes share the same y — backend placeholder grid (yaml_to_graph
          //     assigns sequential x columns but y=80 for every node)
          // In both cases the stored positions are meaningless and dagre produces
          // a much cleaner result. User-repositioned graphs will have varied y values.
          const allAtOrigin = graph.nodes.every(
            (n: Node) => !n.position || (n.position.x === 0 && n.position.y === 0),
          )
          const allSameY = graph.nodes.length > 1 &&
            graph.nodes.every((n: Node) => n.position?.y === graph.nodes[0].position?.y)
          const styledEdges = (es: Edge[]) => es.map(e => ({
            ...e,
            type: e.type ?? "smoothstep",
            markerEnd: e.markerEnd ?? { type: MarkerType.ArrowClosed, width: 16, height: 16, color: "#a8a29e" },
            style: e.style ?? { stroke: "#a8a29e", strokeWidth: 2 },
          }))
          if (allAtOrigin || allSameY) {
            const laid = autoLayout(graph.nodes, graph.edges)
            setNodes(laid.nodes)
            setEdges(styledEdges(laid.edges))
          } else {
            setNodes(graph.nodes)
            setEdges(styledEdges(graph.edges))
          }
        } else {
          if (graph?.nodes) setNodes(graph.nodes)
          if (graph?.edges) setEdges(graph.edges.map((e: Edge) => ({
            ...e,
            type: e.type ?? "smoothstep",
            markerEnd: e.markerEnd ?? { type: MarkerType.ArrowClosed, width: 16, height: 16, color: "#a8a29e" },
            style: e.style ?? { stroke: "#a8a29e", strokeWidth: 2 },
          })))
        }
        setTimeout(() => { isFirstLoad.current = false }, 100)
        setCanvasLoading(false)
        setTimeout(() => fitView({ padding: 0.2, duration: 300 }), 50)
      })
      .catch(() => { isFirstLoad.current = false; setCanvasLoading(false) })
    )
  }, [workflowId, getToken, setNodes, setEdges])

  const handleYamlLoaded = useCallback(
    (next: { name?: string; nodes: Node[]; edges: Edge[] }) => {
      if (next.name) setWorkflowName(next.name)
      setNodes(next.nodes)
      setEdges(next.edges)
      setSelectedNode(null)
      // Bypass the autosave debounce — the YAML save already persisted.
      isFirstLoad.current = true
      setTimeout(() => { isFirstLoad.current = false }, 100)
    },
    [setNodes, setEdges],
  )

  const handleEnvChange = useCallback(async (envId: string) => {
    setSelectedEnvId(envId)
    try {
      const headers = await authHeaders(getToken)
      headers["Content-Type"] = "application/json"
      await fetch(`${process.env.NEXT_PUBLIC_API_URL}/workflows/${workflowId}/environment`, {
        method: "PATCH",
        headers,
        body: JSON.stringify({ environment_id: envId || null }),
      })
    } catch { /* non-fatal */ }
  }, [workflowId, getToken])

  const save = useCallback(async (currentNodes: Node[], currentEdges: Edge[], name: string) => {
    if (!workflowId || workflowId === "undefined") return
    setSaveStatus("saving")
    try {
      const headers = await authHeaders(getToken)
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/workflows/${workflowId}`, {
        method: "PUT",
        headers,
        body: JSON.stringify({ name, graph: { nodes: currentNodes, edges: currentEdges } }),
      })
      if (!res.ok) {
        setSaveStatus("error")
        setTimeout(() => setSaveStatus("idle"), 3000)
        return
      }
      setSaveStatus("saved")
      setTimeout(() => setSaveStatus("idle"), 2000)
    } catch {
      setSaveStatus("error")
      setTimeout(() => setSaveStatus("idle"), 3000)
    }
  }, [workflowId, getToken])

  // Autosave — debounced 1.5s after any node/edge change (skip for viewers)
  useEffect(() => {
    if (isFirstLoad.current || isViewer) return
    if (autosaveTimer.current) clearTimeout(autosaveTimer.current)
    autosaveTimer.current = setTimeout(() => {
      save(nodes, edges, workflowName)
    }, 1500)
    return () => { if (autosaveTimer.current) clearTimeout(autosaveTimer.current) }
  }, [nodes, edges, workflowName, save, isViewer])

  const onConnect = useCallback(
    (connection: Connection) => setEdges((eds) => addEdge({
      ...connection,
      type: "smoothstep",
      markerEnd: { type: MarkerType.ArrowClosed, width: 16, height: 16, color: "#a8a29e" },
      style: { stroke: "#a8a29e", strokeWidth: 2 },
    }, eds)),
    [setEdges]
  )

  const onNodeClick = useCallback((_: React.MouseEvent, node: Node) => {
    setSelectedNode(node)
    setRightOpen(true)
  }, [])

  const onPaneClick = useCallback(() => setSelectedNode(null), [])

  const onDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = "move"
  }, [])

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      const type = e.dataTransfer.getData("application/marshal-block-type")
      const title = e.dataTransfer.getData("application/marshal-block-title")
      if (!type) return
      const position = screenToFlowPosition({ x: e.clientX, y: e.clientY })
      const id = `block-${Date.now()}`
      const blockType = type as BlockType
      const defaults: Record<string, unknown> = {}
      if (blockType === "output") defaults.integration = "slack"
      if (blockType === "trigger") defaults.config = { event_type: "github_issue_labeled" }

      const newNode: Node = {
        id,
        type: "block",
        position,
        data: { type: blockType, label: title.split(" · ")[1] ?? title, description: "", ...defaults } satisfies BlockNodeData,
      }
      setNodes((nds) => [...nds, newNode])
      setSelectedNode(newNode)
    },
    [screenToFlowPosition, setNodes]
  )

  const startRun = useCallback(async (dryRun: boolean) => {
    // Client-side quick checks first
    if (!selectedEnvId) {
      setValidationErrors([{ blockId: "__env__", label: "Environment", message: "Select an environment before running — add one in Settings → Environments" }])
      return
    }
    const localErrors = validateNodes(nodes)
    if (localErrors.length > 0) {
      setValidationErrors(localErrors)
      return
    }
    setValidationErrors([])
    setRunning(dryRun ? "dry" : "live")

    // Server-side pre-flight: credentials, brain descriptions, required fields
    try {
      const headers = await authHeaders(getToken)
      const vRes = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/workflows/${workflowId}/validate`,
        { method: "POST", headers }
      )
      if (vRes.ok) {
        const { valid, errors } = await vRes.json()
        if (!valid) {
          setValidationErrors(errors.map((e: { block_id: string; label: string; message: string }) => ({
            blockId: e.block_id,
            label: e.label,
            message: e.message,
          })))
          setRunning("idle")
          return
        }
      }
    } catch {
      setRunning("idle")
      return
    }

    try {
      const headers = await authHeaders(getToken)
      let initialState: Record<string, unknown> | undefined

      // For webhook-triggered workflows, replicate what the CLI does:
      // find the trigger block, query GitHub for matching issues, inject initial_state.
      const triggerNode = nodes.find(n => {
        const d = n.data as BlockNodeData
        const cfg = (d.config as Record<string, unknown>) ?? {}
        return d.type === "trigger" && (
          cfg.event_type === "github_issue_labeled" ||
          cfg.event_type === "github_issue"
        )
      })

      // Webhook trigger — prompt for PR details before running
      const webhookTriggerNode = nodes.find(n => {
        const d = n.data as BlockNodeData
        const cfg = (d.config as Record<string, unknown>) ?? {}
        return d.type === "trigger" && cfg.event_type === "webhook"
      })
      if (webhookTriggerNode && !triggerNode) {
        const cfg = (webhookTriggerNode.data as BlockNodeData).config as Record<string, unknown>
        // Pre-fill from test_repo, or fall back to first repo in repo_allowlist
        const repoAllowlistFallback = ((cfg.repo_allowlist as string) || "").split(",")[0].trim()
        setWebhookRepo((cfg.test_repo as string) || repoAllowlistFallback || "")
        setWebhookPrNumber((cfg.test_pr_number as string) || "")
        setRunning("idle")
        setWebhookModal({ dryRun })
        return
      }

      if (triggerNode) {
        const cfg = (triggerNode.data as BlockNodeData).config as Record<string, unknown>
        const repoAllowlist = (cfg.repo_allowlist as string) || ""
        const label = (cfg.label as string) || ""
        const repos = repoAllowlist.split(",").map(s => s.trim()).filter(Boolean)
        const repo = repos[0] // try first configured repo

        if (!repo || !label) {
          setValidationErrors([{
            blockId: triggerNode.id,
            label: (triggerNode.data as BlockNodeData).label,
            message: "Set repo_allowlist and label on the trigger block before running",
          }])
          setRunning("idle")
          return
        }

        const issueRes = await fetch(
          `${process.env.NEXT_PUBLIC_API_URL}/credentials/github/issues?repo=${encodeURIComponent(repo)}&label=${encodeURIComponent(label)}`,
          { headers }
        )
        if (!issueRes.ok) {
          setValidationErrors([{
            blockId: triggerNode.id,
            label: (triggerNode.data as BlockNodeData).label,
            message: "Could not fetch GitHub issues — is GitHub connected?",
          }])
          setRunning("idle")
          return
        }

        const issues: Array<{ number: number; title: string; body: string; url: string; author: string; labels: string[]; clone_url: string }> = await issueRes.json()

        if (issues.length === 0) {
          setValidationErrors([{
            blockId: triggerNode.id,
            label: (triggerNode.data as BlockNodeData).label,
            message: `No open issues with label "${label}" found in ${repo}`,
          }])
          setRunning("idle")
          return
        }

        if (issues.length > 1) {
          setValidationErrors([{
            blockId: triggerNode.id,
            label: (triggerNode.data as BlockNodeData).label,
            message: `${issues.length} matching issues found — use the CLI to run all: marshal run autopilot.yaml`,
          }])
          setRunning("idle")
          return
        }

        const issue = issues[0]
        const [repoOwner, repoName] = repo.split("/")
        initialState = {
          github_issue: {
            issue_number:   issue.number,
            title:          issue.title,
            body:           issue.body,
            url:            issue.url,
            author:         issue.author,
            labels:         issue.labels,
            label_added:    label,
            repo_full_name: repo,
            repo_name:      repoName,
            repo_owner:     repoOwner,
            default_branch: "main",
            clone_url:      issue.clone_url,
          },
          github_trigger: {
            event_type: "github_issue_labeled",
            label,
            repo: {
              full_name:      repo,
              name:           repoName,
              owner:          repoOwner,
              default_branch: "main",
              clone_url:      issue.clone_url,
            },
            issue: {
              number: issue.number,
              title:  issue.title,
              body:   issue.body,
              url:    issue.url,
              author: issue.author,
              labels: issue.labels,
            },
          },
        }
      }

      // Preflight: estimate turn budget using Claude (cheap single call per brain block)
      const issue = initialState
        ? (initialState.github_issue as Record<string, string> | undefined)
        : undefined
      try {
        const pfRes = await fetch(
          `${process.env.NEXT_PUBLIC_API_URL}/workflows/${workflowId}/preflight`,
          {
            method: "POST",
            headers,
            body: JSON.stringify({
              issue_title: issue?.title ?? "",
              issue_body:  issue?.body  ?? "",
            }),
          }
        )
        if (pfRes.ok) {
          const pf = await pfRes.json()
          if (pf.suggested_max_turns > 20) {
            setPreflight({
              suggestedTurns: pf.suggested_max_turns,
              files: pf.total_files ?? [],
              pendingDryRun: dryRun,
              initialState: initialState,
            })
            setRunning("idle")
            return
          }
        }
      } catch { /* preflight is best-effort */ }

      await _fireRun(headers, dryRun, initialState, undefined)
    } catch {
      setRunning("idle")
    }
  }, [workflowId, getToken, router, nodes, selectedEnvId])

  const startWebhookRun = useCallback(async (dryRun: boolean, repo: string, prNumber: string) => {
    setWebhookModal(null)
    setRunning(dryRun ? "dry" : "live")
    try {
      const headers = await authHeaders(getToken)
      const [owner, repoName] = repo.split("/")
      const num = parseInt(prNumber, 10)
      const initialState = {
        _trigger: {
          action: "opened",
          number: num,
          repository: { full_name: repo, name: repoName, owner: { login: owner } },
          pull_request: {
            number: num,
            title: `Test PR #${num}`,
            user: { login: "test-user", type: "User" },
            html_url: `https://github.com/${repo}/pull/${num}`,
            diff_url: `https://github.com/${repo}/pull/${num}.diff`,
            base: { ref: "main" },
            head: { ref: `test-branch-${num}` },
          },
        },
      }
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/workflows/${workflowId}/runs`,
        {
          method: "POST",
          headers,
          body: JSON.stringify({ triggered_by: "manual", dry_run: dryRun, initial_state: initialState }),
        }
      )
      if (!res.ok) throw new Error("Failed to start run")
      const run = await res.json()
      localStorage.setItem(STORAGE_KEY, JSON.stringify({ runId: run.id, startedAt: Date.now() }))
      setActiveRunId(run.id)
      setDrawerVisible(true)
      setRunning("idle")
    } catch {
      setRunning("idle")
    }
  }, [workflowId, getToken, STORAGE_KEY])

  const _fireRun = useCallback(async (
    headers: Record<string, string>,
    dryRun: boolean,
    initialState: Record<string, unknown> | undefined,
    maxTurns: number | undefined,
  ) => {
    const res = await fetch(
      `${process.env.NEXT_PUBLIC_API_URL}/workflows/${workflowId}/runs`,
      {
        method: "POST",
        headers,
        body: JSON.stringify({
          triggered_by: "manual",
          dry_run: dryRun,
          ...(initialState ? { initial_state: initialState } : {}),
          ...(maxTurns    ? { max_turns: maxTurns }          : {}),
        }),
      }
    )
    if (!res.ok) throw new Error("Failed to start run")
    const run = await res.json()
    if (dryRun) {
      router.push(`/workflows/${workflowId}/runs/${run.id}`)
    } else {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({ runId: run.id, startedAt: Date.now() }))
      setActiveRunId(run.id)
      setDrawerVisible(true)
      setRunning("idle")
    }
  }, [workflowId, router, STORAGE_KEY])

  const handleBlockStatus = useCallback((blockId: string, status: "running" | "completed" | "failed" | "skipped") => {
    setNodes(nds => nds.map(n =>
      n.id === blockId ? { ...n, data: { ...n.data, runStatus: status } } : n
    ))
  }, [setNodes])

  const handleDrawerHide = useCallback(() => {
    setDrawerVisible(false)
  }, [])

  const handleDrawerClose = useCallback(() => {
    localStorage.removeItem(STORAGE_KEY)
    setActiveRunId(null)
    setDrawerVisible(false)
    setRunning("idle")
    setNodes(nds => nds.map(n => ({ ...n, data: { ...n.data, runStatus: undefined } })))
  }, [setNodes, STORAGE_KEY])

  const handleBlockChange = useCallback(
    (blockId: string, changes: Record<string, unknown>) => {
      setNodes((nds) =>
        nds.map((n) => n.id === blockId ? { ...n, data: { ...n.data, ...changes } } : n)
      )
      setSelectedNode((prev) =>
        prev?.id === blockId ? { ...prev, data: { ...prev.data, ...changes } } : prev
      )
    },
    [setNodes]
  )

  const selectedData = selectedNode?.data as BlockNodeData | undefined

  return (
    <div className="flex flex-col h-full bg-stone-50">
      {/* Top bar */}
      <header className="flex items-center justify-between px-5 py-3 bg-white border-b border-stone-200 shrink-0">
        <div className="flex items-center gap-3">
          <input
            value={workflowName}
            onChange={(e) => !isViewer && setWorkflowName(e.target.value)}
            readOnly={isViewer}
            className="text-base font-semibold text-stone-900 bg-transparent border-none outline-none focus:ring-0 w-64"
          />
          {/* Environment picker */}
          <select
            value={selectedEnvId}
            onChange={e => !isViewer && handleEnvChange(e.target.value)}
            disabled={isViewer}
            className="ml-2 text-xs border border-stone-200 rounded-lg px-2 py-1 text-stone-600 bg-white focus:outline-none focus:ring-2 focus:ring-violet-200 disabled:opacity-60 disabled:cursor-not-allowed"
            title="Agent environment"
          >
            <option value="">— select environment —</option>
            {environments.map(env => (
              <option key={env.id} value={env.id}>{env.name}</option>
            ))}
          </select>
          <div className="ml-3 flex bg-stone-100 rounded-md p-0.5 text-xs">
            <button
              onClick={() => setActiveView("canvas")}
              className={`px-2.5 py-1 rounded ${
                activeView === "canvas"
                  ? "bg-white text-stone-900 shadow-sm font-medium"
                  : "text-stone-500 hover:text-stone-800"
              }`}
            >
              Canvas
            </button>
            <button
              onClick={() => setActiveView("yaml")}
              className={`px-2.5 py-1 rounded ${
                activeView === "yaml"
                  ? "bg-white text-stone-900 shadow-sm font-medium"
                  : "text-stone-500 hover:text-stone-800"
              }`}
            >
              YAML
            </button>
            <button
              onClick={() => setActiveView("runs")}
              className={`px-2.5 py-1 rounded ${
                activeView === "runs"
                  ? "bg-white text-stone-900 shadow-sm font-medium"
                  : "text-stone-500 hover:text-stone-800"
              }`}
            >
              Runs
            </button>
          </div>
        </div>
        <div className="flex items-center gap-3">
          {/* Autosave status */}
          <span className={`text-xs transition-opacity duration-300 ${
            saveStatus === "saving" ? "text-amber-500 opacity-100" :
            saveStatus === "saved"  ? "text-green-500 opacity-100" :
            saveStatus === "error"  ? "text-red-500 opacity-100" :
            "opacity-0"
          }`}>
            {saveStatus === "saving" ? "Saving…" : saveStatus === "error" ? "Save failed" : "Saved ✓"}
          </span>
          <CostEstimate workflowId={workflowId} nodes={nodes} getToken={getToken} />
          <a
            href={`/workflows/${workflowId}/runs`}
            className="text-xs text-stone-500 hover:text-stone-800 transition-colors px-2 py-1 rounded hover:bg-stone-100"
          >
            History
          </a>
          <button
            onClick={() => fitView({ padding: 0.2, duration: 300 })}
            title="Fit all blocks into view"
            className="rounded-lg border border-stone-200 px-3 py-1.5 text-xs font-medium text-stone-500 hover:bg-stone-50 transition-colors"
          >
            ⊡ Fit
          </button>
          {!isViewer && (
            <>
              <button
                onClick={() => startRun(true)}
                disabled={running !== "idle"}
                className="rounded-lg border border-stone-200 px-3 py-1.5 text-xs font-medium text-stone-500 hover:bg-stone-50 transition-colors disabled:opacity-50"
              >
                {running === "dry" ? "Simulating…" : "Dry run"}
              </button>
              <button
                onClick={() => activeRunId ? setDrawerVisible(true) : startRun(false)}
                disabled={running === "live" || running === "dry"}
                className="rounded-lg bg-violet-600 px-4 py-1.5 text-sm font-semibold text-white hover:bg-violet-700 transition-colors disabled:opacity-50"
              >
                {running === "live" ? "Starting…" : activeRunId ? "▶ Running…" : "▶ Run"}
              </button>
            </>
          )}
        </div>
      </header>

      {/* Three-panel layout (or YAML view) */}
      <div className="flex flex-1 overflow-hidden">
        {activeView === "canvas" ? (
          <>
            {/* Left panel — block palette (editors/admins only) */}
            {!isViewer && (
              <div className={`relative flex shrink-0 transition-all duration-200 border-r border-stone-200 ${leftOpen ? "w-44" : "w-12"}`}>
                <button
                  onClick={() => setLeftOpen(v => !v)}
                  className="absolute -right-3 top-1/2 -translate-y-1/2 z-10 w-6 h-6 rounded-full bg-white border border-stone-200 shadow-sm flex items-center justify-center text-stone-400 hover:text-stone-700 transition-colors"
                  title={leftOpen ? "Collapse palette" : "Expand palette"}
                >
                  {leftOpen ? "‹" : "›"}
                </button>
                <BlockPalette getToken={getToken} collapsed={!leftOpen} />
              </div>
            )}

            {/* Center — canvas */}
            <div className="flex-1 relative min-w-0">
              {canvasLoading && (
                <div className="absolute inset-0 z-10 bg-stone-50 flex items-center justify-center">
                  <div className="flex flex-col items-center gap-3">
                    <div className="flex gap-3">
                      {[80, 120, 80].map((w, i) => (
                        <div key={i} className="rounded-xl bg-stone-200 animate-pulse h-16" style={{ width: w }} />
                      ))}
                    </div>
                    <div className="flex gap-2 mt-1">
                      {[1, 2].map(i => <div key={i} className="w-8 h-1 rounded-full bg-stone-200 animate-pulse" />)}
                    </div>
                    <p className="text-xs text-stone-400 mt-2">Loading canvas…</p>
                  </div>
                </div>
              )}
              <ReactFlow
                nodes={nodes}
                edges={edges}
                onNodesChange={isViewer ? undefined : onNodesChange}
                onEdgesChange={isViewer ? undefined : onEdgesChange}
                onConnect={isViewer ? undefined : onConnect}
                onNodeClick={onNodeClick}
                onPaneClick={onPaneClick}
                onDrop={isViewer ? undefined : onDrop}
                onDragOver={isViewer ? undefined : onDragOver}
                nodesDraggable={!isViewer}
                nodesConnectable={!isViewer}
                elementsSelectable={!isViewer}
                nodeTypes={nodeTypes}
                defaultViewport={{ x: 80, y: 80, zoom: 1 }}
                minZoom={0.3}
                maxZoom={2}
                deleteKeyCode="Backspace"
                proOptions={{ hideAttribution: true }}
                connectionMode={ConnectionMode.Loose}
                connectionLineType={ConnectionLineType.SmoothStep}
                connectionRadius={40}
                snapGrid={[16, 16]}
                snapToGrid
                defaultEdgeOptions={{
                  type: "smoothstep",
                  markerEnd: { type: MarkerType.ArrowClosed, width: 16, height: 16, color: "#a8a29e" },
                  style: { stroke: "#a8a29e", strokeWidth: 2 },
                }}
              >
                <Background variant={BackgroundVariant.Dots} gap={20} size={1} color="#E7E5E4" />
                <Controls className="!shadow-none !border !border-stone-200 !rounded-xl" showInteractive={false} />
                <MiniMap
                  nodeColor="#e7e5e4"
                  maskColor="rgba(250,250,249,0.7)"
                  className="!border !border-stone-200 !rounded-xl !shadow-none"
                  pannable
                  zoomable
                />
              </ReactFlow>
              {activeRunId && drawerVisible && (
                <RunDrawer
                  workflowId={workflowId}
                  runId={activeRunId}
                  getToken={getToken}
                  onBlockStatus={handleBlockStatus}
                  onClose={handleDrawerHide}
                  onRunDone={() => { localStorage.removeItem(STORAGE_KEY); setRunning("idle"); setActiveRunId(null) }}
                />
              )}
            </div>

            {/* Right panel — block config */}
            <div className={`relative flex shrink-0 transition-all duration-200 border-l border-stone-200 bg-white ${rightOpen ? "w-72" : "w-8"}`}>
              <button
                onClick={() => setRightOpen(v => !v)}
                className="absolute -left-3 top-1/2 -translate-y-1/2 z-10 w-6 h-6 rounded-full bg-white border border-stone-200 shadow-sm flex items-center justify-center text-stone-400 hover:text-stone-700 transition-colors"
                title={rightOpen ? "Collapse config" : "Expand config"}
              >
                {rightOpen ? "›" : "‹"}
              </button>
              {rightOpen && (
                selectedNode && selectedData ? (
                  <div className="flex-1 overflow-y-auto min-w-0">
                    <BlockEditor
                      workflowId={workflowId}
                      blockId={selectedNode.id}
                      blockType={selectedData.type}
                      label={selectedData.label}
                      description={(selectedData.description as string) ?? ""}
                      blockData={selectedNode.data as Record<string, unknown>}
                      onChange={handleBlockChange}
                      getToken={getToken}
                    />
                  </div>
                ) : (
                  <EnvironmentPanel
                    environments={environments}
                    selectedEnvId={selectedEnvId}
                    credentials={envCredentials}
                    nodes={nodes}
                  />
                )
              )}
            </div>
          </>
        ) : activeView === "yaml" ? (
          <div className="flex-1 flex">
            <YamlPanel
              workflowId={workflowId}
              workflowName={workflowName}
              nodes={nodes}
              edges={edges}
              onLoaded={handleYamlLoaded}
            />
          </div>
        ) : (
          <div className="flex-1 overflow-auto px-6 py-8">
            <div className="mx-auto max-w-3xl flex items-center justify-between mb-4">
              <p className="text-sm font-semibold text-stone-700">{workflowName}</p>
              <button
                onClick={fetchRuns}
                className="text-xs text-stone-400 hover:text-stone-700 border border-stone-200 hover:border-stone-300 rounded-lg px-2.5 py-1 transition-colors"
              >
                Refresh
              </button>
            </div>
            {runsLoading ? (
              <p className="text-sm text-stone-400">Loading…</p>
            ) : runs.length === 0 ? (
              <div className="rounded-xl border border-dashed border-stone-300 p-16 text-center">
                <p className="text-stone-500 text-sm">No runs yet.</p>
              </div>
            ) : (
              <div className="mx-auto max-w-3xl grid gap-2">
                {runs.map(run => {
                  const STATUS_STYLES: Record<string, string> = {
                    pending:   "bg-stone-100 text-stone-500",
                    running:   "bg-blue-100 text-blue-700",
                    succeeded: "bg-green-100 text-green-700",
                    failed:    "bg-red-100 text-red-700",
                    cancelled: "bg-stone-100 text-stone-400",
                  }
                  const isActive = run.status === "pending" || run.status === "running"
                  return (
                    <button
                      key={run.id}
                      onClick={() => router.push(`/workflows/${workflowId}/runs/${run.id}`)}
                      className="flex items-center justify-between rounded-xl border border-stone-200 bg-white px-5 py-4 hover:border-stone-300 hover:shadow-sm transition-all text-left w-full"
                    >
                      <div className="flex items-center gap-3">
                        <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${STATUS_STYLES[run.status] ?? STATUS_STYLES.pending}`}>
                          {isActive && <span className="inline-block w-1.5 h-1.5 rounded-full bg-blue-400 animate-pulse mr-1 align-middle" />}
                          {run.status}
                        </span>
                        <span className="text-sm text-stone-700 font-mono">{run.id.slice(0, 8)}…</span>
                        {run.triggered_by && (
                          <span className="text-xs text-stone-400">{run.triggered_by}</span>
                        )}
                      </div>
                      <span className="text-xs text-stone-400">
                        {new Date(run.created_at).toLocaleString()}
                      </span>
                    </button>
                  )
                })}
              </div>
            )}
          </div>
        )}
      </div>

      {/* No-environment warning banner */}
      {!selectedEnvId && (
        <div className="shrink-0 border-t border-amber-200 bg-amber-50 px-5 py-2.5 flex items-center gap-2">
          <span className="text-amber-600 text-sm">⚠</span>
          <p className="text-xs text-amber-800 flex-1">
            <span className="font-semibold">No environment assigned</span> — credentials won&apos;t be available when this workflow runs.{" "}
            Select one from the dropdown above, or{" "}
            <a href="/settings" className="underline font-medium hover:text-amber-900">add an environment in Settings</a> first.
          </p>
        </div>
      )}

      {/* Preflight turn-budget banner */}
      {preflight && (
        <div className="shrink-0 border-t border-amber-200 bg-amber-50 px-5 py-3">
          <div className="flex items-start justify-between gap-4">
            <div className="flex-1 min-w-0">
              <p className="text-xs font-semibold text-amber-800 mb-1">
                ⚠ Estimated {preflight.suggestedTurns} turns needed — default is 20
              </p>
              {preflight.files.length > 0 && (
                <p className="text-xs text-amber-700 mb-2 font-mono truncate">
                  Files: {preflight.files.join(", ")}
                </p>
              )}
              <div className="flex items-center gap-2">
                <button
                  onClick={async () => {
                    const headers = await authHeaders(getToken)
                    setPreflight(null)
                    setRunning(preflight.pendingDryRun ? "dry" : "live")
                    try {
                      await _fireRun(headers, preflight.pendingDryRun, preflight.initialState, preflight.suggestedTurns)
                    } catch { setRunning("idle") }
                  }}
                  className="text-xs font-semibold bg-amber-600 text-white px-3 py-1.5 rounded-lg hover:bg-amber-700 transition-colors"
                >
                  Run with {preflight.suggestedTurns} turns
                </button>
                <button
                  onClick={async () => {
                    const headers = await authHeaders(getToken)
                    setPreflight(null)
                    setRunning(preflight.pendingDryRun ? "dry" : "live")
                    try {
                      await _fireRun(headers, preflight.pendingDryRun, preflight.initialState, undefined)
                    } catch { setRunning("idle") }
                  }}
                  className="text-xs text-amber-700 hover:text-amber-900 px-2 py-1.5"
                >
                  Run anyway (20 turns)
                </button>
                <button onClick={() => { setPreflight(null); setRunning("idle") }} className="text-xs text-amber-400 hover:text-amber-600 ml-auto">Cancel</button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Webhook test modal */}
      {webhookModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="bg-white rounded-xl shadow-xl w-full max-w-sm mx-4 p-6 flex flex-col gap-4">
            <div>
              <h2 className="text-sm font-semibold text-stone-900">Test with a pull request</h2>
              <p className="text-xs text-stone-400 mt-1">Provide a real PR to review. The workflow will fetch the diff and post a review comment.</p>
            </div>
            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-medium text-stone-500">GitHub repo</label>
              <input
                placeholder="owner/repo"
                value={webhookRepo}
                onChange={e => setWebhookRepo(e.target.value)}
                className="w-full rounded-lg border border-stone-200 bg-white px-3 py-2 text-xs text-stone-900 focus:outline-none focus:ring-2 focus:ring-stone-400"
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-medium text-stone-500">PR number <span className="font-normal text-stone-400">(from the PR URL — e.g. /pull/42)</span></label>
              <input
                placeholder="42"
                value={webhookPrNumber}
                onChange={e => setWebhookPrNumber(e.target.value)}
                className="w-full rounded-lg border border-stone-200 bg-white px-3 py-2 text-xs text-stone-900 focus:outline-none focus:ring-2 focus:ring-stone-400"
              />
            </div>
            <div className="flex gap-2 justify-end">
              <button
                onClick={() => setWebhookModal(null)}
                className="px-4 py-2 text-xs text-stone-500 hover:text-stone-700 rounded-lg hover:bg-stone-100 transition-colors"
              >Cancel</button>
              <button
                onClick={() => startWebhookRun(webhookModal.dryRun, webhookRepo, webhookPrNumber)}
                disabled={!webhookRepo.includes("/") || !webhookPrNumber}
                className="px-4 py-2 text-xs font-medium bg-stone-900 text-white rounded-lg hover:bg-stone-700 disabled:opacity-40 transition-colors"
              >Run review</button>
            </div>
          </div>
        </div>
      )}

      {/* Validation errors */}
      {validationErrors.length > 0 && (
        <div className="shrink-0 border-t border-red-200 bg-red-50 px-5 py-3">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-xs font-semibold text-red-700 mb-1.5">
                Fix {validationErrors.length} issue{validationErrors.length > 1 ? "s" : ""} before running
              </p>
              <div className="flex flex-wrap gap-x-5 gap-y-1">
                {validationErrors.map((e) => (
                  <button
                    key={e.blockId}
                    onClick={() => {
                      if (e.blockId === "__env__") return
                      const node = nodes.find(n => n.id === e.blockId)
                      if (node) {
                        setSelectedNode(node)
                        setRightOpen(true)
                        const x = (node.position.x ?? 0) + (node.width ?? 200) / 2
                        const y = (node.position.y ?? 0) + (node.height ?? 80) / 2
                        setCenter(x, y, { zoom: 1, duration: 400 })
                      }
                    }}
                    className="text-xs text-red-600 hover:text-red-800 hover:underline text-left"
                  >
                    <span className="font-medium">{e.label}</span>
                    <span className="text-red-400"> — {e.message}</span>
                  </button>
                ))}
              </div>
            </div>
            <button onClick={() => setValidationErrors([])} className="text-red-300 hover:text-red-500 text-lg leading-none shrink-0 mt-0.5">×</button>
          </div>
        </div>
      )}
    </div>
  )
}

function CanvasEditorWithClerk({ workflowId }: { workflowId: string }) {
  const { getToken, userId } = useAuth()
  const [isViewer, setIsViewer] = useState(false)

  useEffect(() => {
    if (!userId) return
    async function fetchRole() {
      try {
        const ws = typeof document !== "undefined"
          ? document.cookie.split("; ").find(r => r.startsWith("delegator_project_id="))?.split("=")[1]
          : undefined
        if (!ws) return
        const token = getToken ? await getToken() : null
        const headers: Record<string, string> = { "X-Workspace-Id": ws }
        if (token) headers["Authorization"] = `Bearer ${token}`
        const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/projects/${ws}/members`, { headers })
        if (!res.ok) return
        const members: { clerk_user_id: string; role: string }[] = await res.json()
        const role = members.find(m => m.clerk_user_id === userId)?.role
        setIsViewer(role === "viewer")
      } catch { /* stay false (non-viewer) */ }
    }
    fetchRole()
  }, [userId])

  return (
    <ReactFlowProvider>
      <CanvasEditorInner workflowId={workflowId} getToken={getToken} isViewer={isViewer} />
    </ReactFlowProvider>
  )
}

const SERVICE_META: Record<string, { label: string; abbr: string; color: string }> = {
  github:       { label: "GitHub",       abbr: "GH", color: "bg-stone-800 text-white" },
  slack:        { label: "Slack",        abbr: "SL", color: "bg-purple-600 text-white" },
  linear:       { label: "Linear",       abbr: "LN", color: "bg-indigo-600 text-white" },
  digitalocean: { label: "DigitalOcean", abbr: "DO", color: "bg-blue-500 text-white" },
  email:        { label: "Email",        abbr: "EM", color: "bg-emerald-600 text-white" },
}

const ALL_SERVICES = ["github", "slack", "linear", "digitalocean", "email"]

function EnvironmentPanel({
  environments,
  selectedEnvId,
  credentials,
  nodes,
}: {
  environments: Array<{ id: string; name: string }>
  selectedEnvId: string
  credentials: Array<{ handle: string; service: string }>
  nodes: Node[]
}) {
  const env = environments.find(e => e.id === selectedEnvId)
  const connectedServices = new Set(credentials.map(c => c.service))
  // "git" handle covers GitHub/GitLab/Bitbucket — treat as "github" for display
  if (connectedServices.has("git")) connectedServices.add("github")

  // Derive the services this workflow actually uses from block integrations
  const usedServices = Array.from(
    new Set(
      nodes
        .map(n => (n.data as BlockNodeData).integration as string | undefined)
        .filter((s): s is string => !!s && s in SERVICE_META)
    )
  )

  return (
    <div className="flex-1 flex flex-col px-4 py-5 gap-5 min-w-0">
      {/* Environment */}
      <div>
        <p className="text-[10px] font-semibold text-stone-400 uppercase tracking-wider mb-2">Environment</p>
        {env ? (
          <div className="flex items-center gap-2">
            <span className="w-7 h-7 rounded-md text-[10px] font-bold flex items-center justify-center bg-violet-100 text-violet-700">
              {env.name.slice(0, 2).toUpperCase()}
            </span>
            <span className="text-sm font-medium text-stone-900">{env.name}</span>
          </div>
        ) : (
          <p className="text-xs text-stone-400">No environment assigned — use the dropdown above to set one.</p>
        )}
      </div>

      {/* Only show services this workflow needs */}
      {env && usedServices.length > 0 && (
        <div>
          <p className="text-[10px] font-semibold text-stone-400 uppercase tracking-wider mb-2">Integrations</p>
          <div className="space-y-2">
            {usedServices.map(svc => {
              const meta = SERVICE_META[svc]
              const connected = connectedServices.has(svc)
              return (
                <div key={svc} className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className={`w-5 h-5 rounded text-[9px] font-bold flex items-center justify-center ${meta.color}`}>
                      {meta.abbr}
                    </span>
                    <span className="text-xs text-stone-700">{meta.label}</span>
                  </div>
                  {connected ? (
                    <span className="flex items-center gap-1 text-[10px] font-medium text-emerald-600">
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                      connected
                    </span>
                  ) : (
                    <a href="/settings" className="text-[10px] text-amber-600 hover:underline font-medium">
                      ⚠ not connected
                    </a>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      )}

      <p className="text-[10px] text-stone-400 mt-auto leading-relaxed">
        Click a block to configure it.
      </p>
    </div>
  )
}

export default function CanvasEditor({ workflowId }: { workflowId: string }) {
  const clerkEnabled = !!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY
  if (clerkEnabled) return <CanvasEditorWithClerk workflowId={workflowId} />
  return (
    <ReactFlowProvider>
      <CanvasEditorInner workflowId={workflowId} getToken={null} />
    </ReactFlowProvider>
  )
}
