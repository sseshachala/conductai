"use client"

import { useState, useEffect } from "react"
import { useWorkspace } from "@/lib/WorkspaceContext"
import { cn } from "@/lib/utils"
import { mcpServers } from "@/lib/api"
import type { AuthFetch } from "@/lib/api"
import { getNestedValue } from "./field-utils"

// ── MCP shared types ──────────────────────────────────────────────────────────

interface MCPTool {
  name: string
  description?: string
  inputSchema?: {
    properties?: Record<string, { type?: string; description?: string }>
    required?: string[]
  }
}

interface MCPServer {
  id: string
  name: string
  url: string
  transport: string
}

// ── Shared auth header builder used by both MCP panels ───────────────────────

async function buildMCPAuthFetch(
  getToken: (() => Promise<string | null>) | null | undefined,
  workspaceId: string,
): Promise<AuthFetch> {
  const h: Record<string, string> = { "Content-Type": "application/json" }
  if (getToken) { const t = await getToken(); if (t) h["Authorization"] = `Bearer ${t}` }
  if (workspaceId) h["X-Workspace-ID"] = workspaceId
  return (url, opts) => fetch(url, { ...opts, headers: { ...h, ...(opts?.headers as Record<string, string> | undefined) } })
}

// ── Fetch tools from the Phase 2 GET endpoint ─────────────────────────────────

async function fetchMCPServerTools(
  serverId: string,
  authFetch: AuthFetch,
): Promise<{ tools: MCPTool[]; error: string | null }> {
  try {
    const data: MCPTool[] = await mcpServers.tools(authFetch, serverId)
    return { tools: Array.isArray(data) ? data : [], error: null }
  } catch (e) {
    const msg = e instanceof Error ? e.message : "Network error"
    return { tools: [], error: msg }
  }
}

// ── Transport badge helper ────────────────────────────────────────────────────

function TransportBadge({ transport }: { transport: string }) {
  const label = transport === "sse" ? "SSE" : transport === "stdio" ? "stdio" : transport.toUpperCase()
  return (
    <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[9px] font-semibold bg-cyan-100 text-cyan-700 border border-cyan-200 ml-1.5 shrink-0">
      {label}
    </span>
  )
}

// ── MCP block config panel (P2.1) ─────────────────────────────────────────────

export function MCPBlockPanel({
  getToken,
  blockData,
  onChange,
  isViewer = false,
  environmentId,
}: {
  getToken?: (() => Promise<string | null>) | null
  blockData: Record<string, unknown>
  onChange: (key: string, value: unknown) => void
  isViewer?: boolean
  environmentId?: string
}) {
  const { activeWorkspace } = useWorkspace()
  const wsId = activeWorkspace?.id ?? ""

  const [servers, setServers] = useState<MCPServer[]>([])
  const [serversLoading, setServersLoading] = useState(true)

  const [tools, setTools] = useState<MCPTool[]>([])
  const [toolsLoading, setToolsLoading] = useState(false)
  const [toolsErr, setToolsErr] = useState<string | null>(null)

  // Read saved values from blockData
  const savedServerId = (getNestedValue(blockData, "config.server_id") as string) || ""
  const [serverId, setServerId] = useState(savedServerId)
  useEffect(() => {
    if (savedServerId && savedServerId !== serverId) setServerId(savedServerId)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [savedServerId])

  const toolName = (getNestedValue(blockData, "config.tool_name") as string) || ""

  // Fetch workspace MCP servers on mount
  useEffect(() => {
    if (!wsId) return
    setServersLoading(true)
    buildMCPAuthFetch(getToken, wsId).then(authFetch =>
      mcpServers.list(authFetch, wsId)
        .then(d => { if (Array.isArray(d)) setServers(d) })
        .catch(() => {})
        .finally(() => setServersLoading(false))
    )
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [wsId, environmentId])

  // Load tools when a server is already saved (e.g. re-opening block)
  useEffect(() => {
    if (!savedServerId || !wsId) return
    buildMCPAuthFetch(getToken, wsId).then(authFetch =>
      fetchMCPServerTools(savedServerId, authFetch).then(({ tools: list, error }) => {
        if (!error) setTools(list)
      })
    )
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [savedServerId, wsId])

  const selectedServer = servers.find(s => s.id === serverId) ?? null
  const selectedTool   = tools.find(t => t.name === toolName) ?? null
  const paramProps     = selectedTool?.inputSchema?.properties ?? {}
  const requiredParams = new Set(selectedTool?.inputSchema?.required ?? [])

  async function handleServerChange(val: string) {
    if (isViewer) return
    const srv = servers.find(s => s.id === val)
    if (!srv) return

    setServerId(val)
    onChange("config.server_id",   srv.id)
    onChange("config.server_name", srv.name)
    onChange("config.transport",   srv.transport)
    onChange("config.tool_name",   "")
    onChange("config.inputs",      {})
    setTools([])
    setToolsErr(null)
    setToolsLoading(true)

    const authFetch = await buildMCPAuthFetch(getToken, wsId)
    const { tools: list, error } = await fetchMCPServerTools(srv.id, authFetch)
    setToolsLoading(false)
    if (error) { setToolsErr(error); return }
    setTools(list)
  }

  function handleToolChange(name: string) {
    if (isViewer) return
    onChange("config.tool_name", name)
    onChange("config.inputs", {})
  }

  function handleInputChange(paramKey: string, value: string) {
    if (isViewer) return
    const currentInputs = (getNestedValue(blockData, "config.inputs") as Record<string, string>) || {}
    onChange("config.inputs", { ...currentInputs, [paramKey]: value })
  }

  const inputBase = "w-full border border-stone-200 rounded-lg px-2.5 py-1.5 text-sm text-stone-900 focus:outline-none focus:ring-2 focus:ring-indigo-200 bg-white disabled:opacity-60 disabled:cursor-not-allowed"
  const sectionLabel = "text-[10px] font-semibold text-stone-400 uppercase tracking-wider mb-1.5 block"

  return (
    <div className="px-4 py-3 space-y-4">

      {/* Step 1 — Server selector */}
      <div>
        <span className={sectionLabel}>Server <span className="text-red-500">*</span></span>
        {serversLoading ? (
          <div className="rounded-lg border border-stone-200 bg-stone-50 px-3 py-2.5 text-[11px] text-stone-400">
            Loading servers…
          </div>
        ) : servers.length === 0 ? (
          <div className="rounded-lg border border-stone-200 bg-stone-50 px-3 py-2.5 text-[11px] text-stone-500 space-y-1">
            <p>No MCP servers registered.</p>
            <a href="/integrations" className="text-cyan-600 hover:text-cyan-800 font-medium">
              Add one at /integrations →
            </a>
          </div>
        ) : (
          <>
            <select
              value={serverId}
              onChange={e => handleServerChange(e.target.value)}
              disabled={isViewer}
              className={inputBase}
            >
              <option value="" disabled>Select a registered MCP server</option>
              {servers.map(s => (
                <option key={s.id} value={s.id}>{s.name}</option>
              ))}
            </select>
            {selectedServer && (
              <div className="flex items-center gap-1.5 mt-1.5">
                <span className="text-[10px] text-stone-400">Transport:</span>
                <TransportBadge transport={selectedServer.transport} />
              </div>
            )}
          </>
        )}
      </div>

      {/* Step 2 — Tool selector (shown after server selected) */}
      {serverId && (
        <div>
          <span className={sectionLabel}>Tool <span className="text-red-500">*</span></span>
          {toolsLoading ? (
            <div className="rounded-lg border border-stone-200 bg-stone-50 px-3 py-2.5 text-[11px] text-stone-400">
              Loading tools…
            </div>
          ) : toolsErr ? (
            <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2.5 text-[11px] text-red-700 space-y-1">
              <p>{toolsErr}</p>
              {toolsErr.toLowerCase().includes("unreachable") && (
                <a href="/integrations" className="text-red-600 hover:text-red-800 font-medium underline">
                  Check connection at /integrations
                </a>
              )}
            </div>
          ) : tools.length > 0 ? (
            <>
              <select
                value={toolName}
                onChange={e => handleToolChange(e.target.value)}
                disabled={isViewer}
                className={inputBase}
              >
                <option value="">— pick a tool —</option>
                {tools.map(t => (
                  <option key={t.name} value={t.name}>
                    {t.name}{t.description ? ` — ${t.description}` : ""}
                  </option>
                ))}
              </select>
              {selectedTool?.description && (
                <p className="text-[10px] text-stone-400 mt-1">{selectedTool.description}</p>
              )}
            </>
          ) : (
            <div className="rounded-lg border border-stone-200 bg-stone-50 px-3 py-2.5 text-[11px] text-stone-400">
              No tools returned by this server.
            </div>
          )}
        </div>
      )}

      {/* Step 3 — Input fields (shown after tool selected, rendered from inputSchema) */}
      {toolName && Object.keys(paramProps).length > 0 && (
        <div className="space-y-3">
          <span className={sectionLabel}>Inputs</span>
          {Object.entries(paramProps).map(([paramKey, paramDef]) => {
            const req = requiredParams.has(paramKey)
            const currentInputs = (getNestedValue(blockData, "config.inputs") as Record<string, string>) || {}
            const val = currentInputs[paramKey] || ""
            return (
              <div key={paramKey}>
                <div className="flex items-center gap-1.5 mb-1">
                  <label className="text-[10px] font-semibold text-stone-400 uppercase tracking-wide">
                    {paramKey}
                  </label>
                  {req && <span className="text-red-500 text-[10px]">*</span>}
                  {paramDef.description && (
                    <span className="text-[10px] text-stone-400">{paramDef.description}</span>
                  )}
                </div>
                <input
                  type="text"
                  value={val}
                  onChange={e => handleInputChange(paramKey, e.target.value)}
                  disabled={isViewer}
                  placeholder={`{{previous_block.${paramKey}}}`}
                  className={inputBase}
                />
              </div>
            )
          })}
          <p className="text-[10px] text-stone-400 pt-1">
            Use <code className="bg-stone-100 px-1 rounded">{"{{block_id.field}}"}</code> to reference earlier outputs.
          </p>
        </div>
      )}

    </div>
  )
}

// ── Brain block MCP server selector (P2.2) ───────────────────────────────────

export function BrainMCPSection({
  getToken,
  blockData,
  blockId,
  onChange,
  isViewer,
  environmentId,
  section,
  sectionLabel,
}: {
  getToken?: (() => Promise<string | null>) | null
  blockData: Record<string, unknown>
  blockId: string
  onChange: (id: string, data: Record<string, unknown>) => void
  isViewer: boolean
  environmentId?: string
  section: string
  sectionLabel: string
}) {
  const { activeWorkspace } = useWorkspace()
  const wsId = activeWorkspace?.id ?? ""

  const [servers, setServers] = useState<MCPServer[]>([])
  const [serversLoading, setServersLoading] = useState(true)
  const [toolCounts, setToolCounts] = useState<Record<string, number>>({})

  // mcp_server_ids: ["all"] means use all; specific UUIDs means selective
  const savedIds = (blockData.mcp_server_ids as string[]) ?? ["all"]
  const useAll = savedIds.length === 1 && savedIds[0] === "all"

  // Fetch workspace MCP servers
  useEffect(() => {
    if (!wsId) return
    setServersLoading(true)
    buildMCPAuthFetch(getToken, wsId).then(authFetch =>
      mcpServers.list(authFetch, wsId)
        .then((d: MCPServer[]) => {
          if (Array.isArray(d)) {
            setServers(d)
            // Fetch tool counts for all servers (cached by backend, fast)
            d.forEach(srv => {
              buildMCPAuthFetch(getToken, wsId).then(hh =>
                fetchMCPServerTools(srv.id, hh).then(({ tools }) => {
                  setToolCounts(prev => ({ ...prev, [srv.id]: tools.length }))
                })
              )
            })
          }
        })
        .catch(() => {})
        .finally(() => setServersLoading(false))
    )
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [wsId, environmentId])

  function setUseAll(val: boolean) {
    if (isViewer) return
    if (val) {
      onChange(blockId, { ...blockData, mcp_server_ids: ["all"] })
    } else {
      // Switch to empty selection — user must opt in to specific servers
      onChange(blockId, { ...blockData, mcp_server_ids: [] })
    }
  }

  function toggleServer(id: string) {
    if (isViewer) return
    const current: string[] = useAll ? servers.map(s => s.id) : (blockData.mcp_server_ids as string[]) ?? []
    const next = current.includes(id) ? current.filter(x => x !== id) : [...current, id]
    onChange(blockId, { ...blockData, mcp_server_ids: next })
  }

  if (servers.length === 0 && !serversLoading) return null

  const selectedIds: string[] = useAll ? servers.map(s => s.id) : savedIds

  return (
    <div className={section}>
      <span className={sectionLabel}>MCP Servers</span>

      {serversLoading ? (
        <p className="text-[11px] text-stone-400">Loading servers…</p>
      ) : (
        <>
          {/* Use-all toggle */}
          <label className="flex items-center gap-2.5 cursor-pointer mb-3">
            <div
              role="checkbox"
              aria-checked={useAll}
              onClick={() => setUseAll(!useAll)}
              className={cn(
                "w-9 h-5 rounded-full transition-colors relative cursor-pointer",
                useAll ? "bg-violet-500" : "bg-stone-300",
                isViewer && "opacity-60 cursor-not-allowed",
              )}
            >
              <span className={cn(
                "absolute top-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform",
                useAll ? "translate-x-4" : "translate-x-0.5",
              )} />
            </div>
            <span className="text-xs font-medium text-stone-700">Use all registered MCP servers</span>
          </label>

          {/* Per-server checkboxes (shown when not using all) */}
          {!useAll && (
            <div className="space-y-2 pl-1">
              {servers.map(srv => {
                const checked = selectedIds.includes(srv.id)
                const count = toolCounts[srv.id]
                return (
                  <label
                    key={srv.id}
                    className={cn(
                      "flex items-center gap-2.5 cursor-pointer rounded-lg px-2.5 py-2 border transition-colors",
                      checked ? "border-violet-200 bg-violet-50" : "border-stone-200 bg-white hover:bg-stone-50",
                      isViewer && "opacity-60 cursor-not-allowed",
                    )}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => toggleServer(srv.id)}
                      disabled={isViewer}
                      className="rounded border-stone-300 text-violet-600 focus:ring-violet-300"
                    />
                    <span className="text-sm font-medium text-stone-800 flex-1">{srv.name}</span>
                    <TransportBadge transport={srv.transport} />
                    {count !== undefined && (
                      <span className="text-[10px] text-stone-400 shrink-0">{count} tools</span>
                    )}
                  </label>
                )
              })}
            </div>
          )}

          {useAll && servers.length > 0 && (
            <p className="text-[10px] text-stone-400">
              {servers.length} server{servers.length !== 1 ? "s" : ""} available — agent will use all of their tools.
            </p>
          )}
        </>
      )}
    </div>
  )
}
