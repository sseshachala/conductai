"use client"

export function LoadingBubble({ label }: { label?: string }) {
  return (
    <div style={{ display: "flex", justifyContent: "flex-start", marginBottom: 16 }}>
      <div style={{
        background: "var(--surface-2)",
        border: "1px solid var(--border)",
        borderRadius: "4px 14px 14px 14px",
        padding: "12px 16px",
        fontSize: 14,
        color: "var(--text-muted)",
        display: "flex",
        alignItems: "center",
        gap: 10,
      }} aria-label="Lens is thinking" role="status">
        <span style={{ display: "inline-flex", alignItems: "flex-end", gap: 4, height: 12 }}>
          <span className="conduct-typing-dot" />
          <span className="conduct-typing-dot" />
          <span className="conduct-typing-dot" />
        </span>
        {label && <span style={{ fontSize: 12, opacity: 0.8 }}>{label}</span>}
      </div>
    </div>
  )
}
