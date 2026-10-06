"use client"

import { authEnabled } from "@/lib/auth/runtime"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { useRouter } from "next/navigation"
import { useAuth } from "@/lib/auth/client"
import { useWorkspace } from "@/lib/WorkspaceContext"
import {
  ReactFlow,
  Background,
  MiniMap,
  addEdge,
  useNodesState,
  useEdgesState,
  useReactFlow,
  ReactFlowProvider,
  ConnectionMode,
  ConnectionLineType,
  MarkerType,
  PanOnScrollMode,
  type Connection,
  type Node,
  type Edge,
  BackgroundVariant,
} from "@xyflow/react"
import "@xyflow/react/dist/style.css"

import BlockNode, { type BlockNodeData } from "./BlockNode"
import AnnotationNode, { CanvasReadOnlyContext } from "./AnnotationNode"
import VersionHistory from "./VersionHistory"
import BlockEditor from "./BlockEditor"
import BlockPalette from "./BlockPalette"
import RunDrawer from "./RunDrawer"
import DefinitionPanel from "./DefinitionPanel"
import WorkflowSettingsPanel from "./WorkflowSettingsPanel"
import CanvasHeader from "./CanvasHeader"
import CanvasToolbar from "./CanvasToolbar"
import CanvasOverlays from "./CanvasOverlays"
import NodeSearch from "./NodeSearch"
import RunBanners from "./RunBanners"
import RunModals from "./RunModals"
import RunsListView from "./RunsListView"
import { useCanvasRuns, type CanvasView, type GetToken } from "./hooks/useCanvasRuns"
import { useUndoHistory } from "./hooks/useUndoHistory"
import { useWorkflowDocument, cycleNotice, toStoredGraph } from "./hooks/useWorkflowDocument"
import { useCanvasClipboard } from "./hooks/useCanvasClipboard"
import { useCanvasShortcuts } from "./hooks/useCanvasShortcuts"
import { autoLayout } from "@/lib/auto-layout"
import { reorderZ } from "@/lib/canvas/zOrder"
import { ANNOTATION_TYPE, isAnnotation, newAnnotation, splitAnnotations } from "@/lib/canvas/annotations"
import { type BlockType } from "@/lib/block-types"
import { projects } from "@/lib/api"
import type { AuthFetch } from "@/lib/api"

const nodeTypes = { block: BlockNode, [ANNOTATION_TYPE]: AnnotationNode }
const MINIMAP_KEY = "conduct:canvas:minimap"

interface CanvasEditorProps {
  workflowId: string
  getToken?: GetToken
  isViewer?: boolean
  isAdmin?: boolean
}

function CanvasEditorInner({ workflowId, getToken, isViewer = false, isAdmin = false }: CanvasEditorProps) {
  const { activeWorkspace } = useWorkspace()
  const wsId = activeWorkspace?.id ?? null
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([])
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([])
  const [selectedNode, setSelectedNode] = useState<Node | null>(null)
  const isFirstLoad = useRef(true)
  const { screenToFlowPosition, setCenter, fitView } = useReactFlow()
  const router = useRouter()
  const [leftOpen, setLeftOpen] = useState(true)
  const [rightOpen, setRightOpen] = useState(true)
  const [focusMode, setFocusMode] = useState(false)
  const [activeView, setActiveView] = useState<CanvasView>("canvas")
  const [searchOpen, setSearchOpen] = useState(false)
  const [minimapOpen, setMinimapOpen] = useState(true)
  const [layoutNotice, setLayoutNotice] = useState<string | null>(null)

  // Notes share React Flow state but are invisible to everything that reasons about blocks.
  const blockNodes = useMemo(() => splitAnnotations(nodes).blocks, [nodes])
  const {
    restoreGraph, workflowName, setWorkflowName, githubHookRepo, setGithubHookRepo, githubHookId, setGithubHookId, githubWebhook,
    saveStatus, canvasLoading, environments, selectedEnvId, envCredentials, handleEnvChange, playbookSlug, projectSlug, projectName,
  } = useWorkflowDocument({ workflowId, getToken, wsId, isViewer, nodes, edges, setNodes, setEdges, isFirstLoad, setLayoutNotice })
  const runs = useCanvasRuns({
    workflowId, getToken, wsId, nodes: blockNodes, setNodes, selectedEnvId, githubHookRepo,
    activeView, setActiveView, navigate: href => router.push(href),
  })
  const { undo, redo } = useUndoHistory(nodes, edges, setNodes, setEdges, { disabled: isViewer, isFirstLoad })

  // Minimap visibility is a per-viewer convenience; storage may be unavailable.
  useEffect(() => {
    try { if (localStorage.getItem(MINIMAP_KEY) === "0") setMinimapOpen(false) } catch { /* default open */ }
  }, [])
  const toggleMinimap = () => {
    const next = !minimapOpen
    setMinimapOpen(next)
    try { localStorage.setItem(MINIMAP_KEY, next ? "1" : "0") } catch { /* not persisted */ }
  }

  const applyZOrder = (direction: "front" | "back") => {
    const ids = new Set(nodes.filter(n => n.selected).map(n => n.id))
    if (ids.size) setNodes(reorderZ(nodes, ids, direction))
  }

  const { duplicate } = useCanvasClipboard({ nodes, edges, setNodes, setEdges, editable: !isViewer && activeView === "canvas" })
  useCanvasShortcuts({ undo, redo, duplicate, openSearch: () => setSearchOpen(true), zOrder: applyZOrder, editable: !isViewer && activeView === "canvas" })

  const addNote = () => {
    const pane = document.querySelector(".react-flow")?.getBoundingClientRect()
    const centre = pane ? screenToFlowPosition({ x: pane.left + pane.width / 2, y: pane.top + pane.height / 2 }) : { x: 0, y: 0 }
    const note = newAnnotation(`note-${Date.now().toString(36)}`, { x: centre.x - 120, y: centre.y - 80 })
    setNodes((nds: Node[]) => [...nds.map(n => (n.selected ? { ...n, selected: false } : n)), { ...note, selected: true }])
  }

  const onConnect = useCallback(
    (connection: Connection) => setEdges((eds: Edge[]) => addEdge({
      ...connection,
      type: "smoothstep",
      markerEnd: { type: MarkerType.ArrowClosed, width: 12, height: 12, color: "#a8a29e" },
      style: { stroke: "#a8a29e", strokeWidth: 2 },
    }, eds)),
    [setEdges]
  )

  const onNodeClick = useCallback((_: React.MouseEvent, node: Node) => {
    // Notes edit in place; the config panel is for executable blocks only.
    if (isAnnotation(node)) { setSelectedNode(null); return }
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
      setNodes((nds: Node[]) => [...nds, newNode])
      setSelectedNode(newNode)
    },
    [screenToFlowPosition, setNodes]
  )

  const handleBlockChange = useCallback(
    (blockId: string, changes: Record<string, unknown>) => {
      setNodes((nds: Node[]) =>
        nds.map((n) => n.id === blockId ? { ...n, data: { ...n.data, ...changes } } : n)
      )
      setSelectedNode((prev) =>
        prev?.id === blockId ? { ...prev, data: { ...prev.data, ...changes } } : prev
      )
    },
    [setNodes]
  )

  /** Select a block, open its config and centre the viewport on it. */
  const focusNode = (nodeId: string) => {
    const node = nodes.find(n => n.id === nodeId)
    if (!node) return
    setActiveView("canvas")
    setNodes((nds: Node[]) => nds.map((n: Node) => (n.selected === (n.id === nodeId) ? n : { ...n, selected: n.id === nodeId })))
    setSelectedNode(isAnnotation(node) ? null : node)
    setRightOpen(true)
    const x = (node.position.x ?? 0) + (node.measured?.width ?? node.width ?? 200) / 2
    const y = (node.position.y ?? 0) + (node.measured?.height ?? node.height ?? 80) / 2
    setCenter(x, y, { zoom: 1, duration: 400 })
  }

  const applyLayout = (fitOptions: { padding: number; minZoom?: number }, delay: number) => {
    // Notes keep their hand-placed positions; only blocks are laid out.
    const laid = autoLayout(blockNodes, edges)
    setNodes([...laid.nodes, ...nodes.filter(isAnnotation)])
    setLayoutNotice(cycleNotice(laid.cycleNodeIds, blockNodes))
    setTimeout(() => fitView({ ...fitOptions, duration: 400 }), delay)
  }

  const toggleFocus = () => {
    if (focusMode) { setFocusMode(false); setLeftOpen(true); setRightOpen(true) }
    else { setFocusMode(true); setLeftOpen(false); setRightOpen(false); applyLayout({ padding: 0.2, minZoom: 0.5 }, 80) }
  }

  const selectedData = selectedNode?.data as BlockNodeData | undefined
  const rightVisible = rightOpen && !!selectedNode
  const panelStyle = (open: boolean, width: number, side: "borderRight" | "borderLeft") => ({
    flexBasis: open ? width : 0, width: open ? width : 0, maxWidth: open ? width : 0, minWidth: 0,
    flexGrow: 0, flexShrink: 0, overflow: "hidden" as const, position: "relative" as const,
    [side]: open ? "1px solid #e7e5e4" : "none", background: "white",
  })

  return (
    <CanvasReadOnlyContext.Provider value={isViewer}>
    <div className="flex flex-col h-full bg-stone-50">
      <CanvasHeader
        workflowId={workflowId} getToken={getToken} isViewer={isViewer} nodes={blockNodes}
        workflowName={workflowName} setWorkflowName={setWorkflowName} projectName={projectName} playbookSlug={playbookSlug}
        environments={environments} selectedEnvId={selectedEnvId} envCredentials={envCredentials} onEnvChange={handleEnvChange}
        activeView={activeView} setActiveView={setActiveView} saveStatus={saveStatus} runs={runs}
      />

      {/* Three-panel layout (or YAML view) */}
      <div className="flex flex-1 overflow-hidden">
        {activeView === "canvas" ? (
          <>
            {/* Left panel — block palette (editors/admins only) */}
            {!isViewer && (
              <div style={panelStyle(leftOpen, 212, "borderRight")}>
                {leftOpen && (
                  <button
                    onClick={() => setLeftOpen(false)}
                    className="absolute top-3 right-3 z-10 w-6 h-6 rounded-full bg-white border border-stone-200 shadow-sm flex items-center justify-center text-stone-400 hover:text-stone-700 transition-colors"
                    title="Collapse palette"
                    aria-label="Collapse palette"
                  >
                    ‹
                  </button>
                )}
                <BlockPalette getToken={getToken} collapsed={false} />
              </div>
            )}

            {/* Center — canvas */}
            <div className="flex-1 relative min-w-0">
              {/* Floating reopen button for block palette */}
              {!isViewer && !leftOpen && (
                <button
                  onClick={() => setLeftOpen(true)}
                  className="absolute top-3 left-3 z-10 flex items-center gap-1.5 px-3 py-1.5 bg-white border border-stone-200 rounded-full shadow-sm text-xs font-medium text-stone-600 hover:text-stone-900 hover:border-stone-300 transition-colors"
                  title="Expand block palette"
                >
                  + Blocks
                </button>
              )}
              <CanvasOverlays
                notice={runs.runError ?? layoutNotice}
                onDismissNotice={() => (runs.runError ? runs.setRunError(null) : setLayoutNotice(null))}
                canvasLoading={canvasLoading}
                nodes={nodes}
                githubHookRepo={githubHookRepo}
              />
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
                panOnScroll
                panOnScrollMode={PanOnScrollMode.Free}
                zoomOnScroll={false}
                deleteKeyCode="Backspace"
                proOptions={{ hideAttribution: true }}
                connectionMode={ConnectionMode.Loose}
                connectionLineType={ConnectionLineType.SmoothStep}
                connectionRadius={40}
                snapGrid={[16, 16]}
                snapToGrid
                // Explicit z-order (bring to front / send to back) is the source of truth;
                // React Flow's +1000 selection boost would hide it while a node is selected.
                elevateNodesOnSelect={false}
                defaultEdgeOptions={{
                  type: "smoothstep",
                  markerEnd: { type: MarkerType.ArrowClosed, width: 10, height: 10, color: "#d6d3d1" },
                  style: { stroke: "#d6d3d1", strokeWidth: 1 },
                }}
              >
                <Background variant={BackgroundVariant.Dots} gap={20} size={1} color="#E7E5E4" />
                {minimapOpen && (
                  <MiniMap
                    pannable
                    zoomable
                    ariaLabel="Canvas minimap"
                    position="bottom-right"
                    bgColor="var(--surface)"
                    maskColor="rgba(120, 113, 108, 0.12)"
                    nodeColor={n => (n.selected ? "var(--accent)" : "var(--border-2)")}
                    nodeBorderRadius={6}
                    className="!rounded-xl !border !border-stone-200 !shadow-sm overflow-hidden"
                  />
                )}
                <CanvasToolbar
                  focusMode={focusMode}
                  onOrganize={() => applyLayout({ padding: 0.15 }, 50)}
                  onToggleFocus={toggleFocus}
                  minimapOpen={minimapOpen}
                  onToggleMinimap={toggleMinimap}
                  onSearch={() => setSearchOpen(true)}
                  onAddNote={isViewer ? undefined : addNote}
                  canReorder={!isViewer && nodes.some(n => n.selected)}
                  onZOrder={applyZOrder}
                />
              </ReactFlow>
              {runs.activeRunId && runs.drawerVisible && (
                <RunDrawer
                  workflowId={workflowId}
                  runId={runs.activeRunId}
                  getToken={getToken}
                  onBlockStatus={runs.handleBlockStatus}
                  onBlockTurns={runs.handleBlockTurns}
                  onClose={runs.hideDrawer}
                  onRunDone={runs.onRunDone}
                />
              )}
            </div>

            {/* Right panel — block config only */}
            <div style={panelStyle(rightVisible, 344, "borderLeft")}>
              {rightVisible && selectedNode && selectedData && (
                <div className="flex-1 overflow-y-auto min-w-0 w-[344px] h-full">
                  <BlockEditor
                    workflowId={workflowId}
                    blockId={selectedNode.id}
                    previousBlockId={edges.find(e => e.target === selectedNode.id)?.source ?? undefined}
                    isReadOnly={!!(selectedNode.data as Record<string, unknown>).is_readonly}
                    blockType={selectedData.type}
                    label={selectedData.label}
                    description={(selectedData.description as string) ?? ""}
                    blockData={selectedNode.data as Record<string, unknown>}
                    onChange={handleBlockChange}
                    getToken={getToken}
                    isAdmin={isAdmin}
                    isViewer={isViewer}
                    githubHookRepo={githubHookRepo}
                    githubHookId={githubHookId}
                    githubWebhook={githubWebhook}
                    playbookSlug={playbookSlug}
                    projectSlug={projectSlug}
                    onWebhookChange={(id, repo) => { setGithubHookId(id); setGithubHookRepo(repo) }}
                    onClose={() => setSelectedNode(null)}
                    onDelete={(blockId) => {
                      setNodes((nds: Node[]) => nds.filter(n => n.id !== blockId))
                      setEdges((eds: Edge[]) => eds.filter(e => e.source !== blockId && e.target !== blockId))
                      setSelectedNode(null)
                    }}
                    sandboxBlocks={nodes.filter(n => (n.data as Record<string, unknown>).type === "sandbox").map(n => ({ id: n.id, label: (n.data as Record<string, unknown>).label as string || "Sandbox" }))}
                  />
                </div>
              )}
            </div>
          </>
        ) : activeView === "definition" ? (
          <DefinitionPanel nodes={blockNodes} edges={edges} workflowName={workflowName} getToken={getToken} workflowId={workflowId} runState={runs.lastRunState} runSummary={runs.lastRunSummary} />
        ) : activeView === "runs" ? (
          <RunsListView workflowId={workflowId} workflowName={workflowName} runs={runs} />
        ) : activeView === "history" ? (
          <VersionHistory
            workflowId={workflowId} getToken={getToken} wsId={wsId} isViewer={isViewer}
            currentGraph={toStoredGraph(nodes, edges)} onRestore={restoreGraph}
          />
        ) : activeView === "settings" ? (
          <WorkflowSettingsPanel workflowId={workflowId} getToken={getToken} isViewer={isViewer} onDelete={() => router.push("/workflows")} />
        ) : null}
      </div>

      <RunBanners workflowId={workflowId} selectedEnvId={selectedEnvId} runs={runs} onFocusNode={focusNode} />
      <RunModals workflowId={workflowId} getToken={getToken} wsId={wsId} runs={runs} />
      {searchOpen && <NodeSearch nodes={nodes} onSelect={focusNode} onClose={() => setSearchOpen(false)} />}
    </div>
    </CanvasReadOnlyContext.Provider>
  )
}

function CanvasEditorWithClerk({ workflowId }: { workflowId: string }) {
  const { getToken, userId } = useAuth()
  const { activeWorkspace } = useWorkspace()
  const [isViewer, setIsViewer] = useState(false)
  const [isAdmin, setIsAdmin] = useState(false)

  useEffect(() => {
    if (!userId) return
    async function fetchRole() {
      try {
        const ws = activeWorkspace?.id
        if (!ws) return
        const token = getToken ? await getToken() : null
        const headers: Record<string, string> = { "X-Workspace-Id": ws }
        if (token) headers["Authorization"] = `Bearer ${token}`
        const authFetch: AuthFetch = (url, opts) => fetch(url, { ...opts, headers: { ...headers, ...(opts?.headers as Record<string, string> | undefined) } })
        const members: { clerk_user_id: string; role: string }[] = await projects.members.list(authFetch, ws)
        const role = members.find(m => m.clerk_user_id === userId)?.role
        setIsViewer(role === "viewer")
        setIsAdmin(role === "admin")
      } catch { /* stay false */ }
    }
    fetchRole()
  }, [userId, activeWorkspace])

  return (
    <ReactFlowProvider>
      <CanvasEditorInner workflowId={workflowId} getToken={getToken} isViewer={isViewer} isAdmin={isAdmin} />
    </ReactFlowProvider>
  )
}

export default function CanvasEditor({ workflowId }: { workflowId: string }) {
  const clerkEnabled = authEnabled()
  if (clerkEnabled) return <CanvasEditorWithClerk workflowId={workflowId} />
  return (
    <ReactFlowProvider>
      <CanvasEditorInner workflowId={workflowId} getToken={null} />
    </ReactFlowProvider>
  )
}
