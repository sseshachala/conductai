"use client"

/**
 * PolicySnippet — small YAML/Cedar code block with static styling.
 * No heavy syntax highlighter dependency.
 */

export type PolicyLanguage = "yaml" | "cedar"

export interface PolicySnippetProps {
  language?: PolicyLanguage
  title?: string
  code?: string
}

const DEFAULT_YAML = `policy: refund-cap
version: "1.0"
rules:
  - id: block-high-value-refund
    match:
      action: process_refund
      amount_gt: 500
    decision: BLOCK
    reason: >
      Refunds over $500 require
      human approval per FIN-07.`

const DEFAULT_CEDAR = `permit(
  principal,
  action == Action::"deploy_production",
  resource
) when {
  context.change_window == true &&
  context.approved == true
};`

export function PolicySnippet({
  language = "yaml",
  title,
  code,
}: PolicySnippetProps) {
  const displayTitle = title ?? (language === "yaml" ? "refund-cap.yaml" : "production-change.cedar")
  const displayCode = code ?? (language === "yaml" ? DEFAULT_YAML : DEFAULT_CEDAR)

  return (
    <div className="rounded-xl border border-stone-200 overflow-hidden text-xs font-mono bg-stone-950 shadow-sm">
      {/* Title bar */}
      <div className="flex items-center gap-2 px-4 py-2 bg-stone-900 border-b border-stone-800">
        <div className="flex gap-1.5">
          <span className="w-2.5 h-2.5 rounded-full bg-stone-600" />
          <span className="w-2.5 h-2.5 rounded-full bg-stone-600" />
          <span className="w-2.5 h-2.5 rounded-full bg-stone-600" />
        </div>
        <span className="text-stone-400 text-[10px] ml-1">{displayTitle}</span>
        <span className="ml-auto text-[10px] px-1.5 py-0.5 rounded bg-stone-800 text-stone-500 uppercase tracking-wider">
          {language}
        </span>
      </div>

      {/* Code */}
      <pre className="px-4 py-4 text-[11px] leading-relaxed overflow-x-auto">
        <YamlHighlight code={displayCode} language={language} />
      </pre>
    </div>
  )
}

/** Minimal static keyword colouring — no runtime dependency */
function YamlHighlight({ code, language }: { code: string; language: PolicyLanguage }) {
  const lines = code.split("\n")
  return (
    <>
      {lines.map((line, i) => (
        <span key={i} className="block">
          <ColourLine line={line} language={language} />
          {"\n"}
        </span>
      ))}
    </>
  )
}

function ColourLine({ line, language }: { line: string; language: PolicyLanguage }) {
  if (language === "yaml") {
    // Key: value colouring
    const keyMatch = line.match(/^(\s*)([a-z_-]+)(:)(.*)$/)
    if (keyMatch) {
      const [, indent, key, colon, rest] = keyMatch
      return (
        <>
          <span>{indent}</span>
          <span className="text-sky-400">{key}</span>
          <span className="text-stone-500">{colon}</span>
          <ValueSpan value={rest} />
        </>
      )
    }
    // List item
    const listMatch = line.match(/^(\s*)(- )(.*)$/)
    if (listMatch) {
      return (
        <>
          <span>{listMatch[1]}</span>
          <span className="text-stone-500">{listMatch[2]}</span>
          <span className="text-amber-300">{listMatch[3]}</span>
        </>
      )
    }
    // Comment / blank
    return <span className="text-stone-500">{line}</span>
  }

  // Cedar: keywords
  const keywords = ["permit", "forbid", "when", "principal", "action", "resource", "context", "true", "false"]
  let result = line
  keywords.forEach((kw) => {
    result = result.replace(new RegExp(`\\b${kw}\\b`, "g"), `__KW__${kw}__ENDKW__`)
  })
  const parts = result.split(/(__KW__|__ENDKW__)/)
  let inKw = false
  return (
    <>
      {parts.map((part, i) => {
        if (part === "__KW__") { inKw = true; return null }
        if (part === "__ENDKW__") { inKw = false; return null }
        return inKw
          ? <span key={i} className="text-violet-400">{part}</span>
          : <span key={i} className="text-stone-300">{part}</span>
      })}
    </>
  )
}

function ValueSpan({ value }: { value: string }) {
  const trimmed = value.trim()
  if (trimmed.startsWith('"') || trimmed.startsWith("'")) {
    return <span className="text-emerald-400">{value}</span>
  }
  if (["BLOCK", "ALLOW", "APPROVE", "WARN"].includes(trimmed)) {
    return (
      <>
        <span> </span>
        <span className="text-red-400 font-semibold">{trimmed}</span>
      </>
    )
  }
  return <span className="text-amber-300">{value}</span>
}
