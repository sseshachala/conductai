"use client"

export default function CanvasError({ error, reset }: { error: Error; reset: () => void }) {
  return (
    <div style={{ padding: 40, textAlign: "center" }}>
      <p style={{ color: "var(--err)", marginBottom: 8 }}>Something went wrong loading the canvas.</p>
      {error.message && (
        <p style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 16, fontFamily: "monospace" }}>
          {error.message}
        </p>
      )}
      <button onClick={reset} className="btn btn-primary" style={{ marginTop: 8 }}>
        Try again
      </button>
    </div>
  )
}
