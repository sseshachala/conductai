/* ─── sdd-spec-gen free tool ───────────────────────────────────────────── */

export type Stage = "input" | "asking" | "clarify" | "generating" | "output" | "error"
export type Question = { key: string; question: string }
export type ScaffoldFile = { name: string; content: string }
export type ScaffoldStage = "idle" | "generating" | "done"

function renderInline(text: string): React.ReactNode[] {
  const parts = text.split(/(\*\*[^*]+\*\*|_[^_]+_|`[^`]+`)/g)
  return parts.map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**")) return <strong key={i}>{part.slice(2, -2)}</strong>
    if (part.startsWith("_") && part.endsWith("_")) return <em key={i} className="text-stone-500 not-italic">{part.slice(1, -1)}</em>
    if (part.startsWith("`") && part.endsWith("`")) return <code key={i} className="bg-stone-100 px-1 rounded text-xs font-mono text-indigo-700">{part.slice(1, -1)}</code>
    return part
  })
}

export function MarkdownViewer({ content, name }: { content: string; name: string }) {
  if (name === "spec-index.json") {
    return <pre className="px-5 py-5 text-xs font-mono text-stone-600 leading-relaxed whitespace-pre-wrap max-h-[420px] overflow-y-auto">{content}</pre>
  }
  const lines = content.split("\n")
  return (
    <div className="px-6 py-5 max-h-[420px] overflow-y-auto space-y-1">
      {lines.map((line, i) => {
        if (line.startsWith("# ")) return <h1 key={i} className="text-lg font-bold text-stone-900 mt-2 mb-1 first:mt-0">{renderInline(line.slice(2))}</h1>
        if (line.startsWith("## ")) return <h2 key={i} className="text-sm font-bold text-stone-800 mt-5 mb-1 pb-1 border-b border-stone-100">{renderInline(line.slice(3))}</h2>
        if (line.startsWith("### ")) return <h3 key={i} className="text-sm font-semibold text-stone-700 mt-3 mb-0.5">{renderInline(line.slice(4))}</h3>
        if (line.startsWith("---")) return <hr key={i} className="border-stone-200 my-3" />
        if (line.startsWith("- ") || line.startsWith("* ")) return (
          <div key={i} className="flex gap-2 text-xs text-stone-600 leading-relaxed">
            <span className="text-stone-300 shrink-0 mt-0.5">•</span>
            <span>{renderInline(line.slice(2))}</span>
          </div>
        )
        if (line.startsWith("❓")) return (
          <div key={i} className="bg-amber-50 border border-amber-100 rounded-lg px-3 py-2 text-xs text-amber-800 my-1">{renderInline(line)}</div>
        )
        if (/^\*\*FR-\d+\*\*/.test(line)) return (
          <div key={i} className="mt-3 mb-0.5 text-xs font-bold text-indigo-700">{renderInline(line)}</div>
        )
        if (/^\*\*NFR-\d+\*\*/.test(line)) return (
          <div key={i} className="mt-3 mb-0.5 text-xs font-bold text-violet-700">{renderInline(line)}</div>
        )
        if (line.startsWith("_Acceptance")) return (
          <div key={i} className="ml-4 text-xs text-emerald-700 border-l-2 border-emerald-200 pl-3 py-0.5 italic">{renderInline(line)}</div>
        )
        if (line.trim() === "") return <div key={i} className="h-1.5" />
        return <p key={i} className="text-xs text-stone-600 leading-relaxed">{renderInline(line)}</p>
      })}
    </div>
  )
}
