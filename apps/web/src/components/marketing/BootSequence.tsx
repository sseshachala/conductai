"use client"

import { useEffect, useState } from "react"

const LINES = [
  { text: "$ conduct deploy",              color: "text-white",         final: false },
  { text: "loading policies",              color: "text-stone-400",     final: false },
  { text: "syncing to dev hooks",          color: "text-stone-400",     final: false },
  { text: "ready to capture events",       color: "text-emerald-400",   final: true  },
]

const CHAR_MS = 28
const LINE_PAUSE_MS = 250

export default function BootSequence() {
  const [lineIdx, setLineIdx] = useState(0)
  const [charIdx, setCharIdx] = useState(0)

  useEffect(() => {
    if (lineIdx >= LINES.length) return
    const line = LINES[lineIdx].text
    if (charIdx < line.length) {
      const t = setTimeout(() => setCharIdx(charIdx + 1), CHAR_MS)
      return () => clearTimeout(t)
    }
    if (lineIdx < LINES.length - 1) {
      const t = setTimeout(() => {
        setLineIdx(lineIdx + 1)
        setCharIdx(0)
      }, LINE_PAUSE_MS)
      return () => clearTimeout(t)
    }
  }, [lineIdx, charIdx])

  return (
    <div className="font-mono text-left bg-stone-900 text-stone-100 rounded-2xl shadow-lg px-8 py-6 max-w-md mx-auto mb-10">
      {LINES.map((line, i) => {
        const visible = i < lineIdx ? line.text : i === lineIdx ? line.text.slice(0, charIdx) : ""
        const showCursor = i === lineIdx && charIdx < line.text.length
        const isFinalDone = line.final && lineIdx === i && charIdx >= line.text.length
        return (
          <div key={i} className={`text-base leading-relaxed ${line.color}`}>
            {visible}
            {showCursor && <span className="inline-block w-2 h-4 bg-stone-100 ml-0.5 align-middle animate-pulse" />}
            {isFinalDone && <span className="text-emerald-400"> ✓</span>}
          </div>
        )
      })}
    </div>
  )
}
