import React from "react"
import { marked, type Token } from "marked"
import { ResultTableView } from "./ResultTableView"
import { fmtDate } from "@/lib/glens/formatters"

export function renderInline(text: string): React.ReactNode[] {
  return marked.Lexer.lexInline(text).map(renderToken)
}

function literalText(text: string): string {
  // Decode evidence's HTML escaping only as React text, never as markup.
  return text.replace(/&(amp|lt|gt|quot|#39|#x27);/g, entity => ({
    "&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"', "&#39;": "'", "&#x27;": "'",
  }[entity] ?? entity))
}

export function renderTable(header: string[], rows: string[][], key: number): React.ReactNode {
  return (
    <ResultTableView key={key}>
      <table style={{ width: "max-content", minWidth: "100%", borderCollapse: "collapse", fontSize: 13 }}>
        <thead>
          <tr style={{ borderBottom: "1px solid var(--border)" }}>
            {header.map((h, i) => (
              <th key={i} style={{ textAlign: "left", padding: "6px 10px", color: "var(--text-muted)", fontWeight: 600, fontSize: 11.5 }}>{renderInline(h)}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, ri) => (
            <tr key={ri} style={{ borderBottom: ri < rows.length - 1 ? "1px solid var(--border)" : "none" }}>
              {row.map((cell, ci) => (
                <td key={ci} style={{ padding: "6px 10px", color: "var(--text)", verticalAlign: "top", whiteSpace: "nowrap" }}>{renderInline(/^\d{4}-\d{2}-\d{2}T.*(?:Z|[+-]\d{2}:\d{2})$/.test(cell) ? fmtDate(cell) : cell)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </ResultTableView>
  )
}

export function renderMd(text: string): React.ReactNode[] {
  return marked.lexer(text, { gfm: true }).map(renderToken)
}

function renderToken(token: Token, key: number): React.ReactNode {
  const children = () => ("tokens" in token ? token.tokens ?? [] : []).map(renderToken)
  switch (token.type) {
    case "space": return null
    case "heading": return React.createElement(`h${token.depth}`, {
      key, style: { fontSize: token.depth <= 2 ? 16 : 14, fontWeight: 600, margin: "12px 0 6px", lineHeight: 1.4 },
    }, children())
    case "paragraph": return <p key={key} style={{ margin: "6px 0", overflowWrap: "anywhere" }}>{children()}</p>
    case "strong": return <strong key={key}>{children()}</strong>
    case "em": return <em key={key}>{children()}</em>
    case "del": return <del key={key}>{children()}</del>
    case "codespan": return <code key={key} style={{ overflowWrap: "anywhere" }}>{literalText(token.text)}</code>
    case "code": return <pre key={key} style={{ maxWidth: "100%", overflowX: "auto", padding: 10, background: "var(--surface-1)" }}><code>{token.text}</code></pre>
    case "br": return <br key={key} />
    case "hr": return <hr key={key} />
    case "blockquote": return <blockquote key={key} style={{ margin: "8px 0", paddingLeft: 12, borderLeft: "2px solid var(--border)" }}>{children()}</blockquote>
    case "list": {
      const items = token.items.map((item: Token, i: number) => <li key={i} style={{ margin: "4px 0" }}>{("tokens" in item ? item.tokens ?? [] : []).map(renderToken)}</li>)
      const style = { paddingLeft: 20, margin: "8px 0", listStyleType: token.ordered ? "decimal" : "disc" }
      return token.ordered ? <ol key={key} start={Number(token.start) || 1} style={style}>{items}</ol> : <ul key={key} style={style}>{items}</ul>
    }
    case "table": return renderTable(token.header.map((cell: { text: string }) => cell.text), token.rows.map((row: { text: string }[]) => row.map(cell => cell.text)), key)
    case "link": {
      const href = token.href.trim()
      const safe = /^(?:https?:\/\/|mailto:)/i.test(href) || (/^\/(?!\/)/.test(href) && !href.includes("\\")) || href.startsWith("#")
      return safe && !/[\u0000-\u0020]/.test(href) ? <a key={key} href={href} target="_blank" rel="noopener noreferrer" style={{ color: "var(--accent)", textDecoration: "underline" }}>{children()}</a> : <React.Fragment key={key}>{children()}</React.Fragment>
    }
    case "image": return <React.Fragment key={key}>{literalText(token.text)}</React.Fragment>
    case "text": return <React.Fragment key={key}>{token.tokens ? children() : literalText(token.text)}</React.Fragment>
    case "escape": return <React.Fragment key={key}>{literalText(token.text)}</React.Fragment>
    // Raw HTML stays inert; model output must never become executable markup.
    default: return <React.Fragment key={key}>{literalText(token.raw)}</React.Fragment>
  }
}
