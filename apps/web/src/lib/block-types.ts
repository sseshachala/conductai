export type BlockType =
  | "trigger"
  | "brain"
  | "tool"
  | "logic"
  | "memory"
  | "approval"
  | "output"
  | "cleanup"

export interface BlockStyle {
  bg: string
  border: string
  label: string
  labelText: string
  text: string
  icon: string
  // Combined classes for use in sidebar buttons (explicit strings for Tailwind JIT)
  buttonClass: string
}

export const BLOCK_STYLES: Record<BlockType, BlockStyle> = {
  trigger:  { bg: "bg-blue-50",   border: "border-blue-200",   label: "bg-blue-50 text-blue-700",    labelText: "TRIGGER",  text: "text-blue-700",   icon: "⚡", buttonClass: "bg-blue-50 border-blue-200 text-blue-700 hover:bg-blue-100"   },
  brain:    { bg: "bg-purple-50", border: "border-purple-300", label: "bg-purple-50 text-purple-700",labelText: "BRAIN",    text: "text-purple-700", icon: "🧠", buttonClass: "bg-purple-50 border-purple-300 text-purple-700 hover:bg-purple-100" },
  tool:     { bg: "bg-green-50",  border: "border-green-200",  label: "bg-green-50 text-green-700",  labelText: "TOOL",     text: "text-green-700",  icon: "🔧", buttonClass: "bg-green-50 border-green-200 text-green-700 hover:bg-green-100"   },
  logic:    { bg: "bg-gray-50",   border: "border-gray-200",   label: "bg-gray-50 text-gray-600",    labelText: "LOGIC",    text: "text-gray-600",   icon: "⤵",  buttonClass: "bg-gray-50 border-gray-200 text-gray-600 hover:bg-gray-100"       },
  memory:   { bg: "bg-amber-50",  border: "border-amber-200",  label: "bg-amber-50 text-amber-700",  labelText: "MEMORY",   text: "text-amber-700",  icon: "💾", buttonClass: "bg-amber-50 border-amber-200 text-amber-700 hover:bg-amber-100"   },
  approval: { bg: "bg-orange-50", border: "border-orange-200", label: "bg-orange-50 text-orange-700",labelText: "APPROVAL", text: "text-orange-700", icon: "✋", buttonClass: "bg-orange-50 border-orange-200 text-orange-700 hover:bg-orange-100" },
  output:   { bg: "bg-rose-50",   border: "border-rose-200",   label: "bg-rose-50 text-rose-700",    labelText: "OUTPUT",   text: "text-rose-700",   icon: "📤", buttonClass: "bg-rose-50 border-rose-200 text-rose-700 hover:bg-rose-100"       },
  cleanup:  { bg: "bg-yellow-50", border: "border-yellow-200", label: "bg-yellow-50 text-yellow-700",labelText: "CLEANUP",  text: "text-yellow-700", icon: "🧹", buttonClass: "bg-yellow-50 border-yellow-200 text-yellow-700 hover:bg-yellow-100" },
}

export const BLOCK_LIBRARY: { type: BlockType; title: string; description: string }[] = [
  { type: "trigger",  title: "Trigger · event",  description: "Start on GitHub issue label or inbound webhook" },
  { type: "brain",    title: "Brain · LLM",          description: "Single LLM call or agentic loop" },
  { type: "tool",     title: "Tool · API call",       description: "Call an external integration" },
  { type: "logic",    title: "Logic · branch",        description: "Route on condition or test result" },
  { type: "approval", title: "Approval · pause",      description: "Pause and wait for human sign-off" },
  { type: "output",   title: "Output · Slack / email",description: "Send a message or notification" },
  { type: "cleanup",  title: "Cleanup · always runs", description: "Teardown resources — always executes" },
]
