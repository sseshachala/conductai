export type LensEntry = {
  kind: "event" | "run" | "trial"
  workspace_id: string
  resource_id?: string
  block_id?: string
}

const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

export function parseLensEntry(params: Pick<URLSearchParams, "get">): LensEntry | null {
  const kind = params.get("context")
  if (kind === null) return null
  const workspace = params.get("workspace_id") ?? ""
  const resource = params.get("resource_id")
  const block = params.get("block_id")
  if (!["event", "run", "trial"].includes(kind) || !uuid.test(workspace)
    || (kind === "trial" ? resource !== null : !resource || !uuid.test(resource))
    || (block !== null && (kind !== "run" || !block || block.length > 255))) {
    throw new Error("This Lens context link is invalid.")
  }
  return { kind: kind as LensEntry["kind"], workspace_id: workspace.toLowerCase(),
    ...(resource ? { resource_id: resource.toLowerCase() } : {}), ...(block ? { block_id: block } : {}) }
}

export function lensEntryHref(entry: LensEntry): string {
  const params = new URLSearchParams({ context: entry.kind, workspace_id: entry.workspace_id })
  if (entry.resource_id) params.set("resource_id", entry.resource_id)
  if (entry.block_id) params.set("block_id", entry.block_id)
  parseLensEntry(params)
  return `/lens?${params}`
}

export function lensEntryQuestion(entry: LensEntry): string {
  if (entry.kind === "trial") return "Explain my recorded trial activity and usage."
  if (entry.kind === "run") return entry.block_id
    ? "Explain this recorded workflow step and its run context."
    : "Explain this workflow run, its recorded steps and linked model calls."
  return "Explain this recorded activity, its policy decision and available usage."
}
