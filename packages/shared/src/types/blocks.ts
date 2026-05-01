export type BlockType =
  | "trigger"
  | "brain"
  | "tool"
  | "logic"
  | "memory"
  | "approval"
  | "output"
  | "cleanup"

export interface Block {
  id: string
  type: BlockType
  label: string
  description: string
  position: { x: number; y: number }
  config: Record<string, unknown>
  isAgentic?: boolean
  integration?: string
}

export interface Edge {
  id: string
  source: string
  target: string
  sourceHandle?: string
  targetHandle?: string
}

export interface WorkflowGraph {
  nodes: Block[]
  edges: Edge[]
}
