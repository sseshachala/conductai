import type { GlensDashboardSpec } from "@/components/glens/GlensDashboard"

// ─── Types ────────────────────────────────────────────────────────────────────

export interface GLensSession {
  id: string
  title: string
  has_dashboard: boolean
  created_at: string
}

export interface PolicyMapping {
  field: string
  column: string
  description: string
}

export type MessageBody =
  | { role: "user"; text: string }
  | { role: "assistant"; kind: "answer"; text: string; skill?: string; drilldown?: { path: string; filters?: Record<string, string> }; followups?: string[]; understoodAs?: string }
  | { role: "assistant"; kind: "streaming"; text: string }
  | { role: "assistant"; kind: "dashboard"; spec: GlensDashboardSpec; sessionId: string; drilldown?: { path: string; filters?: Record<string, string> } }
  | { role: "assistant"; kind: "loading"; label?: string }
  | { role: "assistant"; kind: "page"; answer: string; pageKind: string; pageData: Record<string, unknown>; warning?: string; skill: string; drilldown?: { path: string; filters?: Record<string, string> } }
  | { role: "assistant"; kind: "policy_confirm"; answer: string; action: string; draft: Record<string, unknown>; mapping: PolicyMapping[]; targetRuleId?: string; sessionId: string; skill: string; warning?: string }
  | { role: "assistant"; kind: "action_confirm"; toolName: string; approvalRequestId: string; summary: string; warnings?: string[]; expiresAt?: string }
  | { role: "assistant"; kind: "run"; runId: string; workflowName: string; initialStatus: string }
  | { role: "assistant"; kind: "blocks"; answer: string; blocks: unknown[]; warning?: string; skill: string; drilldown?: { path: string; filters?: Record<string, string> }; understoodAs?: string }
  | { role: "assistant"; kind: "table"; answer: string; columns?: unknown[]; rows: unknown[]; warning?: string; skill: string; drilldown?: { path: string; filters?: Record<string, string> }; understoodAs?: string }

export type Message = MessageBody & { id: string }

export type RunBlockState = {
  id: string
  status: "pending" | "running" | "succeeded" | "failed"
  label?: string
  error?: string
}

// Stable ids so React keys on the message feed never depend on array index.
// Index-based keys re-mount bubbles on every splice → scroll resets, flicker.
let _msgSeq = 0
export const nextMsgId = () => `m${++_msgSeq}`
export const withId = <T extends MessageBody>(body: T): Message => ({ ...body, id: nextMsgId() } as Message)
// Morph the last bubble in place (loading → answer, etc.) without changing its id.
export const replaceLast = (prev: Message[], body: MessageBody): Message[] => {
  const last = prev[prev.length - 1]
  return last ? [...prev.slice(0, -1), { ...body, id: last.id } as Message] : [withId(body)]
}
// Morph a specific bubble in place (approve → run/answer) without re-keying siblings.
export const replaceById = (prev: Message[], id: string, body: MessageBody): Message[] =>
  prev.map(m => (m.id === id ? ({ ...body, id } as Message) : m))
