import type { WorkflowGraph } from "./blocks"

export interface Workflow {
  id: string
  workspace_id: string
  name: string
  default_mode: "dag" | "agentic"
  current_version_id: string | null
  created_at: string
  updated_at: string
}

export interface WorkflowVersion {
  id: string
  workflow_id: string
  graph: WorkflowGraph
  compiled_artifacts: Record<string, CompiledArtifact> | null
  published_at: string | null
  created_at: string
}

export interface CompiledArtifact {
  system_prompt: string
  tool_schema: Record<string, unknown>
  model?: string
  mode?: "single" | "agentic"
}

export interface WorkflowDetail extends Workflow {
  current_version: WorkflowVersion | null
}
