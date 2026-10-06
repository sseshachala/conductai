import { describe, expect, it } from "vitest"
import type { Edge, Node } from "@xyflow/react"
import { newAnnotation, splitAnnotations, withLockState } from "../annotations"
import { materializePaste, parsePayload, serializeSelection, stripSecrets } from "../clipboard"
import { diffGraphs, isEmptyDiff, MASK } from "../graphDiff"
import { toStoredGraph } from "@/components/canvas/hooks/useWorkflowDocument"

const block = (id: string, data: Record<string, unknown> = {}, extra: Partial<Node> = {}): Node =>
  ({ id, type: "block", position: { x: 10, y: 20 }, data: { label: id, type: "tool", ...data }, ...extra })
const edge = (source: string, target: string): Edge => ({ id: `${source}-${target}`, source, target })

describe("annotations", () => {
  it("persist outside graph.nodes so the runtime never sees them", () => {
    const note = newAnnotation("note-1", { x: 0, y: 0 })
    const g = toStoredGraph([block("a"), { ...note, selected: true }], [])
    expect(g.nodes.map(n => n.id)).toEqual(["a"])
    expect(g.annotations).toHaveLength(1)
    expect(g.annotations[0]).not.toHaveProperty("selected")
    expect(splitAnnotations([block("a"), note]).annotations.map(n => n.id)).toEqual(["note-1"])
  })

  it("locked notes are not draggable", () => {
    const locked = { ...newAnnotation("n", { x: 0, y: 0 }), data: { title: "", text: "", color: "yellow", locked: true } }
    expect(withLockState(locked).draggable).toBe(false)
    expect(withLockState(block("a")).draggable).toBeUndefined()
  })
})

describe("clipboard", () => {
  const nodes = [
    block("t", { type: "trigger", config: { webhook_secret: "enc:abc", repo_allowlist: "o/r", max_tokens: 4000 } }, { selected: true }),
    block("b", { runStatus: "running", liveTurn: 3, config: { headers: { Authorization: "Bearer x" }, note: "sk-ant-api03-zzzz" } }, { selected: true }),
    block("c"),
  ]
  const edges = [edge("t", "b"), edge("b", "c")]

  it("copies selected nodes and only edges between them", () => {
    const p = serializeSelection(nodes, edges)!
    expect(p.nodes.map(n => n.id)).toEqual(["t", "b"])
    expect(p.edges.map(e => e.id)).toEqual(["t-b"])
  })

  it("never puts secrets, tokens or live-run state on the clipboard", () => {
    const text = JSON.stringify(serializeSelection(nodes, edges))
    for (const leaked of ["enc:abc", "Bearer x", "sk-ant-", "runStatus", "liveTurn"]) expect(text).not.toContain(leaked)
    expect(text).toContain("o/r")       // ordinary config survives
    expect(text).toContain("4000")      // numeric max_tokens is not a secret
  })

  it("pastes with fresh ids, remapped edges and an offset", () => {
    const p = parsePayload(JSON.stringify(serializeSelection(nodes, edges)))!
    let i = 0
    const out = materializePaste(p, 40, () => `new-${i++}`)
    expect(out.nodes.map(n => n.id)).toEqual(["new-0", "new-1"])
    expect(out.nodes[0].position).toEqual({ x: 50, y: 60 })
    expect(out.nodes.every(n => n.selected)).toBe(true)
    expect(out.edges).toHaveLength(1)
    expect([out.edges[0].source, out.edges[0].target]).toEqual(["new-0", "new-1"])
  })

  it("ignores clipboard text it did not produce", () => {
    expect(parsePayload("hello")).toBeNull()
    expect(parsePayload(JSON.stringify({ kind: "other", nodes: [], edges: [] }))).toBeNull()
  })

  it("stripSecrets keeps credential handles (references, not secrets)", () => {
    expect(stripSecrets({ credential_key: "mcp-vercel", api_key: "k" })).toEqual({ credential_key: "mcp-vercel" })
  })
})

describe("graphDiff", () => {
  const v1 = {
    nodes: [
      { id: "a", data: { label: "Triage", config: { model: "haiku", webhook_secret: "enc:1", prompt: "old" } } },
      { id: "b", data: { label: "Old step" } },
    ],
    edges: [{ source: "a", target: "b" }],
    annotations: [],
  }
  const v2 = {
    nodes: [
      { id: "a", data: { label: "Triage", runStatus: "running", config: { model: "sonnet", webhook_secret: "enc:2", prompt: "old" } } },
      { id: "c", data: { label: "New step" } },
    ],
    edges: [{ source: "a", target: "c" }],
    annotations: [{ id: "n", type: "annotation", data: { title: "Why", text: "context" } }],
  }

  it("reports added, removed and changed blocks, edges and notes", () => {
    const d = diffGraphs(v1, v2)
    expect(d.blocks.added.map(n => n.label)).toEqual(["New step"])
    expect(d.blocks.removed.map(n => n.label)).toEqual(["Old step"])
    expect(d.edges).toEqual({ added: ["a → c"], removed: ["a → b"] })
    expect(d.notes.added.map(n => n.label)).toEqual(["Why"])
  })

  it("flags governance fields, masks secrets but still shows that they changed", () => {
    const fields = diffGraphs(v1, v2).blocks.changed[0].fields
    expect(fields.map(f => f.path)).toEqual(["config.model", "config.webhook_secret"]) // runStatus ignored
    expect(fields[0]).toMatchObject({ before: "haiku", after: "sonnet", governance: true })
    expect(fields[1]).toMatchObject({ before: MASK, after: MASK })
  })

  it("shows secret references, which are not secret values", () => {
    const d = diffGraphs(
      { nodes: [{ id: "a", data: { config: { api_key: "{{secrets.OLD}}" } } }] },
      { nodes: [{ id: "a", data: { config: { api_key: "{{secrets.NEW}}" } } }] },
    )
    expect(d.blocks.changed[0].fields[0]).toMatchObject({ before: "{{secrets.OLD}}", after: "{{secrets.NEW}}" })
  })

  it("is empty when only positions or run state differ", () => {
    expect(isEmptyDiff(diffGraphs({ nodes: [{ id: "a", data: { label: "x" } }] }, { nodes: [{ id: "a", data: { label: "x", liveTurn: 2 } }] }))).toBe(true)
  })
})
