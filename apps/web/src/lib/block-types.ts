export type BlockType =
  | "trigger"
  | "brain"
  | "tool"
  | "logic"
  | "for_each"
  | "memory"
  | "approval"
  | "output"
  | "cleanup"
  | "mcp"
  | "sandbox"

export interface BlockStyle {
  bg: string
  border: string
  label: string
  labelText: string
  text: string
  icon: string
  buttonClass: string
}

export const BLOCK_STYLES: Record<BlockType, BlockStyle> = {
  trigger:  { bg: "bg-blue-50",   border: "border-blue-200",   label: "bg-blue-50 text-blue-700",    labelText: "TRIGGER",    text: "text-blue-700",   icon: "trigger",  buttonClass: "bg-blue-50 border-blue-200 text-blue-700 hover:bg-blue-100"     },
  brain:    { bg: "bg-violet-50", border: "border-violet-200", label: "bg-violet-50 text-violet-700",labelText: "AGENT STEP", text: "text-violet-700", icon: "brain",    buttonClass: "bg-violet-50 border-violet-200 text-violet-700 hover:bg-violet-100" },
  tool:     { bg: "bg-emerald-50",border: "border-emerald-200",label: "bg-emerald-50 text-emerald-700",labelText: "ACTION",    text: "text-emerald-700",icon: "tool",     buttonClass: "bg-emerald-50 border-emerald-200 text-emerald-700 hover:bg-emerald-100" },
  logic:    { bg: "bg-stone-50",  border: "border-stone-200",  label: "bg-stone-50 text-stone-600",  labelText: "CONDITION",  text: "text-stone-600",  icon: "logic",    buttonClass: "bg-stone-50 border-stone-200 text-stone-600 hover:bg-stone-100"   },
  for_each: { bg: "bg-teal-50",   border: "border-teal-200",   label: "bg-teal-50 text-teal-700",    labelText: "LOOP",       text: "text-teal-700",   icon: "for_each", buttonClass: "bg-teal-50 border-teal-200 text-teal-700 hover:bg-teal-100"       },
  memory:   { bg: "bg-amber-50",  border: "border-amber-200",  label: "bg-amber-50 text-amber-700",  labelText: "MEMORY",     text: "text-amber-700",  icon: "memory",   buttonClass: "bg-amber-50 border-amber-200 text-amber-700 hover:bg-amber-100"   },
  approval: { bg: "bg-orange-50", border: "border-orange-200", label: "bg-orange-50 text-orange-700",labelText: "APPROVAL",   text: "text-orange-700", icon: "approval", buttonClass: "bg-orange-50 border-orange-200 text-orange-700 hover:bg-orange-100" },
  output:   { bg: "bg-rose-50",   border: "border-rose-200",   label: "bg-rose-50 text-rose-700",    labelText: "NOTIFY",     text: "text-rose-700",   icon: "output",   buttonClass: "bg-rose-50 border-rose-200 text-rose-700 hover:bg-rose-100"       },
  cleanup:  { bg: "bg-sky-50",    border: "border-sky-200",    label: "bg-sky-50 text-sky-700",      labelText: "CLEANUP",    text: "text-sky-700",    icon: "cleanup",  buttonClass: "bg-sky-50 border-sky-200 text-sky-700 hover:bg-sky-100"          },
  mcp:      { bg: "bg-cyan-50",   border: "border-cyan-200",   label: "bg-cyan-50 text-cyan-700",     labelText: "MCP",        text: "text-cyan-700",   icon: "mcp",     buttonClass: "bg-cyan-50 border-cyan-200 text-cyan-700 hover:bg-cyan-100"        },
  sandbox:  { bg: "bg-green-50",  border: "border-green-200",  label: "bg-green-50 text-green-700",   labelText: "SANDBOX",    text: "text-green-700",  icon: "sandbox", buttonClass: "bg-green-50 border-green-200 text-green-700 hover:bg-green-100"    },
}

export const BLOCK_LIBRARY: { type: BlockType; title: string; sub: string; description: string; preferred?: boolean }[] = [
  { type: "trigger",  title: "Trigger",    sub: "starts a run",     description: "Start on GitHub webhook, schedule, or inbound event" },
  { type: "brain",    title: "Agent Step", sub: "reason + act",     description: "LLM reasoning loop — reads context, calls tools, decides" },
  { type: "mcp",      title: "MCP Tool",   sub: "any MCP server",   description: "Connect to any MCP-compatible server and call its tools", preferred: true },
  { type: "tool",     title: "Action",     sub: "direct API call",  description: "Perform an action via GitHub, Slack, Linear, and more — use MCP when available" },
  { type: "logic",    title: "Condition",  sub: "choose path",      description: "Route on any condition or test result" },
  { type: "for_each", title: "For Each",   sub: "loop over list",   description: "Iterate over a list — runs connected blocks once per item" },
  { type: "memory",   title: "Memory",     sub: "recall or record", description: "Read past context or write outcome for future runs" },
  { type: "approval", title: "Approval",   sub: "wait for human",   description: "Pause the run until a human approves or rejects" },
  { type: "output",   title: "Notify",     sub: "send output",      description: "Post to Slack, send email, or write a comment" },
  { type: "sandbox",  title: "Sandbox",    sub: "isolated execution", description: "Run code or commands in an isolated sandbox environment" },
  { type: "cleanup",  title: "Cleanup",    sub: "always runs",      description: "Teardown or finalize — executes even if the run fails" },
]
