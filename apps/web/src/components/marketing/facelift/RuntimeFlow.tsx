"use client"

/**
 * RuntimeFlow — Agent → Guard → downstream diagram.
 * Simple SVG/HTML, no external dependencies.
 */

export interface RuntimeFlowProps {
  variant?: "default" | "compact"
}

export function RuntimeFlow({ variant = "default" }: RuntimeFlowProps) {
  if (variant === "compact") {
    return <CompactFlow />
  }
  return <FullFlow />
}

function FullFlow() {
  return (
    <div className="flex flex-col items-center gap-0 text-xs font-mono select-none">
      {/* Agent row */}
      <div className="flex items-center gap-3">
        <AgentBox label="claude-code / deploy-agent" />
        <Arrow />
        <AgentBox label="cursor-agent-17" />
        <Arrow />
        <AgentBox label="Custom agent" />
      </div>

      {/* Down arrows */}
      <div className="flex items-center gap-3 my-1">
        <DownArrow />
        <DownArrow />
        <DownArrow />
      </div>

      {/* Guard */}
      <div className="bg-stone-900 text-white rounded-xl px-10 py-3 font-bold text-sm shadow-md tracking-wide w-full max-w-md text-center">
        ConductGuard
        <p className="text-[10px] font-normal text-stone-400 mt-0.5">CLI hook · HTTP proxy · MCP layer</p>
      </div>

      {/* Decision fan */}
      <div className="flex items-start gap-2 mt-3">
        <DecisionBranch label="ALLOW" colour="emerald" />
        <DecisionBranch label="APPROVE" colour="amber" />
        <DecisionBranch label="BLOCK" colour="red" />
      </div>

      {/* Downstream */}
      <div className="mt-3 flex items-center gap-3 text-[10px] text-stone-400">
        <span>Foundation Models</span>
        <span>·</span>
        <span>BYO Gateways</span>
        <span>·</span>
        <span>MCP Tools</span>
      </div>
    </div>
  )
}

function CompactFlow() {
  return (
    <div className="flex items-center gap-2 font-mono text-[11px] flex-wrap justify-center">
      <Node label="Agent" />
      <Arrow />
      <Node label="Guard" dark />
      <Arrow />
      <Node label="Model / Tool" />
    </div>
  )
}

function AgentBox({ label }: { label: string }) {
  return (
    <div className="bg-white border border-stone-200 rounded-lg px-3 py-2 text-[10px] text-stone-600 shadow-sm text-center w-32">
      {label}
    </div>
  )
}

function Node({ label, dark }: { label: string; dark?: boolean }) {
  return (
    <span
      className={`rounded-lg px-3 py-1.5 text-[11px] font-semibold border ${
        dark
          ? "bg-stone-900 text-white border-stone-900"
          : "bg-white text-stone-700 border-stone-200 shadow-sm"
      }`}
    >
      {label}
    </span>
  )
}

function Arrow() {
  return <span className="text-stone-400 font-normal">→</span>
}

function DownArrow() {
  return <span className="text-stone-300 text-base leading-none w-32 text-center">↓</span>
}

function DecisionBranch({ label, colour }: { label: string; colour: "emerald" | "amber" | "red" }) {
  const map = {
    emerald: "border-emerald-200 bg-emerald-50 text-emerald-700",
    amber: "border-amber-200 bg-amber-50 text-amber-700",
    red: "border-red-200 bg-red-50 text-red-700",
  }
  return (
    <div className={`border ${map[colour]} rounded-lg px-4 py-2 text-[10px] font-bold uppercase tracking-wider`}>
      {label}
    </div>
  )
}
