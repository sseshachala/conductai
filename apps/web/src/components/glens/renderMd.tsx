"use client"
/**
 * Shared markdown renderer for Lens surfaces (full page + side panel).
 *
 * Handles: bold, inline links, `[text](url)`, GitHub-flavoured tables,
 * bullet lines. Intentionally minimal — Lens outputs are LLM-emitted and
 * predictable; adding a full markdown lib is scope creep.
 */

import type React from "react"


export function renderInline(text: string): React.ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*|\[[^\]]+\]\([^)]+\))/).map((p, j) => {
    if (p.startsWith("**")) return <strong key={j}>{p.slice(2, -2)}</strong>
    const link = p.match(/^\[([^\]]+)\]\(([^)]+)\)$/)
    if (link) return <a key={j} href={link[2]} target="_blank" rel="noopener noreferrer" style={{ color: "var(--accent, #6366f1)", textDecoration: "underline" }}>{link[1]}</a>
    return p
  })
}


export function isTableSeparator(line: string): boolean {
  // e.g. "| --- | --- |" or "|:---|---:|"
  return /^\s*\|(\s*:?-{3,}:?\s*\|)+\s*$/.test(line)
}


export function parseRow(line: string): string[] {
  const trimmed = line.trim().replace(/^\|/, "").replace(/\|$/, "")
  return trimmed.split("|").map(c => c.trim())
}


export function renderTable(header: string[], rows: string[][], key: number): React.ReactNode {
  return (
    <div key={key} style={{ overflowX: "auto", margin: "8px 0" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
        <thead>
          <tr style={{ borderBottom: "1px solid var(--border)" }}>
            {header.map((h, i) => (
              <th key={i} style={{ textAlign: "left", padding: "6px 10px", color: "var(--text-muted)", fontWeight: 600, fontSize: 11.5, textTransform: "uppercase", letterSpacing: ".04em" }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, ri) => (
            <tr key={ri} style={{ borderBottom: ri < rows.length - 1 ? "1px solid var(--border)" : "none" }}>
              {row.map((cell, ci) => (
                <td key={ci} style={{ padding: "6px 10px", color: "var(--text)", verticalAlign: "top" }}>{renderInline(cell)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}


export function renderMd(text: string): React.ReactNode[] {
  const lines = text.split("\n")
  const out: React.ReactNode[] = []
  let i = 0
  while (i < lines.length) {
    const line = lines[i]
    if (line.trim().startsWith("|") && i + 1 < lines.length && isTableSeparator(lines[i + 1])) {
      const header = parseRow(line)
      const rows: string[][] = []
      let j = i + 2
      while (j < lines.length && lines[j].trim().startsWith("|") && !isTableSeparator(lines[j])) {
        rows.push(parseRow(lines[j]))
        j++
      }
      out.push(renderTable(header, rows, i))
      i = j
      continue
    }
    // ATX headers: strip the leading #s and render bold+larger
    const heading = line.match(/^(#{1,6})\s+(.*)$/)
    if (heading) {
      const size = Math.max(13, 20 - heading[1].length * 2)
      out.push(
        <div key={i} style={{ fontSize: size, fontWeight: 700, color: "var(--text)", margin: "10px 0 4px" }}>
          {renderInline(heading[2])}
        </div>
      )
      i++
      continue
    }
    // HR
    if (/^\s*---+\s*$/.test(line)) {
      out.push(<hr key={i} style={{ border: "none", borderTop: "1px solid var(--border)", margin: "8px 0" }} />)
      i++
      continue
    }
    const bullet = line.match(/^[*-]\s+(.+)/)
    const content = bullet ? bullet[1] : line
    const parts = renderInline(content)
    if (bullet) out.push(<div key={i} style={{ paddingLeft: 12, position: "relative" }}><span style={{ position: "absolute", left: 0 }}>•</span>{parts}</div>)
    else out.push(<div key={i} style={{ minHeight: line ? undefined : "0.6em" }}>{parts}</div>)
    i++
  }
  return out
}
