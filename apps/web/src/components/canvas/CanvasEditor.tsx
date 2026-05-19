"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { useRouter } from "next/navigation"
import AuthButton from "@/components/AuthButton"
import {
  ReactFlow,
  Background,
  Controls,
  addEdge,
  useNodesState,
  useEdgesState,
  useReactFlow,
  ReactFlowProvider,
  type Connection,
  type Node,
  type Edge,
  BackgroundVariant,
} from "@xyflow/react"
import "@xyflow/react/dist/style.css"

import BlockNode, { type BlockNodeData } from "./BlockNode"
import BlockEditor from "./BlockEditor"
import Sidebar from "./Sidebar"
import CostEstimate from "./CostEstimate"
import YamlPanel from "./YamlPanel"
import { autoLayout } from "@/lib/auto-layout"
import { type BlockType } from "@/lib/block-types"

const nodeTypes = { block: BlockNode }

type SaveStatus = "idle" | "saving" | "saved"

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
}

function CanvasEditorInner({ workflowId }: CanvasEditorProps) {
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([])
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([])
  const [selectedNode, setSelectedNode] = useState<Node | null>(null)
  const [workflowName, setWorkflowName] = useState("Untitled agent")
  const [saveStatus, setSaveStatus] = useState<SaveStatus>("idle")
  const autosaveTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const isFirstLoad = useRef(true)
  const { screenToFlowPosition } = useReactFlow()
  const router = useRouter()
  const [running, setRunning] = useState<"idle" | "dry" | "live">("idle")
  const [validationErrors, setValidationErrors] = useState<ValidationError[]>([])
  // "canvas" — drag-and-drop designer. "yaml" — source-of-truth view that
  // mirrors what the runtime will actually execute.
  const [activeView, setActiveView] = useState<"canvas" | "yaml">("canvas")

  // Load workflow on mount. When a graph arrives without meaningful positions
  // (the YAML loader writes placeholder coords), run dagre so it doesn't open
  // as a stack of overlapping nodes.
  useEffect(() => {
    fetch(`${process.env.NEXT_PUBLIC_API_URL}/workflows/${workflowId}`)
      .then((r) => r.json())
      .then((data) => {
        setWorkflowName(data.name)
        const graph = data.current_version?.graph
        if (graph?.nodes && graph?.edges) {
          const needsLayout = graph.nodes.every(
            (n: Node) => !n.position || (n.position.x === 0 && n.position.y === 0),
          )
          if (needsLayout) {
            const laid = autoLayout(graph.nodes, graph.edges)
            setNodes(laid.nodes)
            setEdges(laid.edges)
          } else {
            setNodes(graph.nodes)
            setEdges(graph.edges)
          }
        } else {
          if (graph?.nodes) setNodes(graph.nodes)
          if (graph?.edges) setEdges(graph.edges)
        }
        setTimeout(() => { isFirstLoad.current = false }, 100)
      })
      .catch(() => { isFirstLoad.current = false })
  }, [workflowId, setNodes, setEdges])

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

  const save = useCallback(async (currentNodes: Node[], currentEdges: Edge[], name: string) => {
    setSaveStatus("saving")
    try {
      await fetch(`${process.env.NEXT_PUBLIC_API_URL}/workflows/${workflowId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, graph: { nodes: currentNodes, edges: currentEdges } }),
      })
      setSaveStatus("saved")
      setTimeout(() => setSaveStatus("idle"), 2000)
    } catch {
      setSaveStatus("idle")
    }
  }, [workflowId])

  // Autosave — debounced 1.5s after any node/edge change
  useEffect(() => {
    if (isFirstLoad.current) return
    if (autosaveTimer.current) clearTimeout(autosaveTimer.current)
    autosaveTimer.current = setTimeout(() => {
      save(nodes, edges, workflowName)
    }, 1500)
    return () => { if (autosaveTimer.current) clearTimeout(autosaveTimer.current) }
  }, [nodes, edges, workflowName, save])

  const onConnect = useCallback(
    (connection: Connection) => setEdges((eds) => addEdge(connection, eds)),
    [setEdges]
  )

  const onNodeClick = useCallback((_: React.MouseEvent, node: Node) => {
    setSelectedNode(node)
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
      if (blockType === "trigger") defaults.config = { event_type: "manual" }

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
    const errors = validateNodes(nodes)
    if (errors.length > 0) {
      setValidationErrors(errors)
      return
    }
    setValidationErrors([])
    setRunning(dryRun ? "dry" : "live")
    try {
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/workflows/${workflowId}/runs`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ triggered_by: "manual", dry_run: dryRun }),
        }
      )
      if (!res.ok) throw new Error("Failed to start run")
      const run = await res.json()
      router.push(`/workflows/${workflowId}/runs/${run.id}`)
    } catch {
      setRunning("idle")
    }
  }, [workflowId, router, nodes])

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
    <div className="flex flex-col h-screen bg-stone-50">
      {/* Top bar */}
      <header className="flex items-center justify-between px-5 py-3 bg-white border-b border-stone-200 shrink-0">
        <div className="flex items-center gap-3">
          <a href="/workflows" className="text-stone-400 hover:text-stone-700 text-sm">←</a>
          <input
            value={workflowName}
            onChange={(e) => setWorkflowName(e.target.value)}
            className="text-base font-semibold text-stone-900 bg-transparent border-none outline-none focus:ring-0 w-64"
          />
          <span className="text-xs text-stone-400 bg-stone-100 px-2 py-0.5 rounded-full">draft</span>
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
          </div>
        </div>
        <div className="flex items-center gap-3">
          {/* Autosave status */}
          <span className={`text-xs transition-opacity duration-300 ${
            saveStatus === "saving" ? "text-amber-500 opacity-100" :
            saveStatus === "saved"  ? "text-green-500 opacity-100" :
            "opacity-0"
          }`}>
            {saveStatus === "saving" ? "Saving…" : "Saved ✓"}
          </span>
          <CostEstimate workflowId={workflowId} />
          <a
            href={`/workflows/${workflowId}/runs`}
            className="text-xs text-stone-500 hover:text-stone-800 transition-colors px-2 py-1 rounded hover:bg-stone-100"
          >
            History
          </a>
          <button
            onClick={() => startRun(true)}
            disabled={running !== "idle"}
            className="rounded-lg border border-stone-200 px-3 py-1.5 text-xs font-medium text-stone-500 hover:bg-stone-50 transition-colors disabled:opacity-50"
          >
            {running === "dry" ? "Simulating…" : "Dry run"}
          </button>
          <button
            onClick={() => startRun(false)}
            disabled={running !== "idle"}
            className="rounded-lg bg-violet-600 px-4 py-1.5 text-sm font-semibold text-white hover:bg-violet-700 transition-colors disabled:opacity-50"
          >
            {running === "live" ? "Starting…" : "▶ Run"}
          </button>
          <AuthButton afterSignOutUrl="/sign-in" />
        </div>
      </header>

      {/* Canvas + Sidebar (or YAML view) */}
      <div className="flex flex-1 overflow-hidden">
        {activeView === "canvas" ? (
          <>
            <div className="flex-1 relative">
              <ReactFlow
                nodes={nodes}
                edges={edges}
                onNodesChange={onNodesChange}
                onEdgesChange={onEdgesChange}
                onConnect={onConnect}
                onNodeClick={onNodeClick}
                onPaneClick={onPaneClick}
                onDrop={onDrop}
                onDragOver={onDragOver}
                nodeTypes={nodeTypes}
                defaultViewport={{ x: 80, y: 80, zoom: 1 }}
                minZoom={0.3}
                maxZoom={2}
                deleteKeyCode="Backspace"
                proOptions={{ hideAttribution: true }}
              >
                <Background variant={BackgroundVariant.Dots} gap={20} size={1} color="#E7E5E4" />
                <Controls className="!shadow-none !border !border-stone-200 !rounded-xl" showInteractive={false} />
              </ReactFlow>
            </div>
            <Sidebar />
          </>
        ) : (
          <div className="flex-1 flex">
            <YamlPanel
              workflowId={workflowId}
              workflowName={workflowName}
              nodes={nodes}
              edges={edges}
              onLoaded={handleYamlLoaded}
            />
          </div>
        )}
      </div>

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
                      const node = nodes.find(n => n.id === e.blockId)
                      if (node) { setSelectedNode(node) }
                    }}
                    className="text-xs text-red-600 hover:text-red-800 hover:underline text-left"
                  >
                    <span className="font-medium">{e.label}</span>
                    <span className="text-red-400"> — {e.message}</span>
                  </button>
                ))}
              </div>
            </div>
            <button
              onClick={() => setValidationErrors([])}
              className="text-red-300 hover:text-red-500 text-lg leading-none shrink-0 mt-0.5"
            >
              ×
            </button>
          </div>
        </div>
      )}

      {/* Block editor bottom panel */}
      {selectedNode && selectedData && (
        <div className="shrink-0 max-h-64 overflow-y-auto border-t border-stone-200">
          <BlockEditor
            workflowId={workflowId}
            blockId={selectedNode.id}
            blockType={selectedData.type}
            label={selectedData.label}
            description={(selectedData.description as string) ?? ""}
            blockData={selectedNode.data as Record<string, unknown>}
            onChange={handleBlockChange}
          />
        </div>
      )}
    </div>
  )
}

export default function CanvasEditor({ workflowId }: CanvasEditorProps) {
  return (
    <ReactFlowProvider>
      <CanvasEditorInner workflowId={workflowId} />
    </ReactFlowProvider>
  )
}
