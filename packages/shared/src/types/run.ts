export type RunStatus =
  | "pending"
  | "running"
  | "paused"
  | "succeeded"
  | "failed"
  | "cancelled"

export interface Run {
  id: string
  workflow_version_id: string
  triggered_by: string | null
  status: RunStatus
  started_at: string | null
  paused_at: string | null
  completed_at: string | null
  current_block_id: string | null
  created_at: string
}

export type RunEventKind =
  | "block_started"
  | "block_completed"
  | "block_failed"
  | "approval_requested"
  | "approval_received"
  | "run_started"
  | "run_completed"
  | "run_failed"
  | "agent_turn"

export interface RunEvent {
  id: string
  run_id: string
  block_id: string | null
  kind: RunEventKind
  payload: Record<string, unknown>
  created_at: string
}

export interface RunDetail extends Run {
  events: RunEvent[]
}
