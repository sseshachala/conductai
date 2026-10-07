export interface RunEvent {
  id: string
  kind: string
  block_id: string | null
  payload: Record<string, unknown>
  created_at?: string
}

export interface FailureSummary {
  code?: string
  category?: string
  stop_reason?: string
  message?: string
  block_id?: string | null
  next_action?: string
}

export interface RunMeta {
  triggered_by: string | null
  started_at: string | null
  completed_at: string | null
  paused_at: string | null
  current_block_id: string | null
  workflow_version_id: string | null
  explainability?: {
    version?: string
    source?: string
    trigger_provider?: string
    budget?: { max_turns?: number; max_cost_usd?: number }
  } | null
  governance?: {
    policy_surface?: string
    provider?: string
    enforcement_mode?: string
    version?: string
  } | null
}

// ── Block row component ───────────────────────────────────────────────────────

export interface FileChanged {
  path: string
  action: "created" | "modified" | "deleted"
}

export interface ToolCall {
  tool: string
  summary: string
  turn: number
}

export interface BlockRow {
  blockId: string
  label: string
  type: string
  status: "running" | "completed" | "failed" | "skipped"
  startedAt?: string
  completedAt?: string
  output?: Record<string, unknown>
  error?: string
  costUsd?: number
  inputTokens?: number
  outputTokens?: number
  filesChanged?: FileChanged[]
  diffStat?: string
  toolCalls?: ToolCall[]
  budgetExhausted?: {
    turns: number
    costUsd: number
    reason?: string
    stopReason?: string
    nextAction?: string
    maxTurns?: number
    maxCostUsd?: number
  }
  provider?: string
  model?: string
  upstreamUrl?: string
  llmUpstream?: string
  routingReason?: string
  sandboxProvider?: string
  sandboxDecision?: string
  timedOut?: boolean
  failure?: FailureSummary
  nextAction?: string
}
