"use client"
import { CopyButton } from "@/components/glens/CopyButton"
import { FeedbackButtons } from "@/components/glens/FeedbackButtons"

// ── Message footer (copy + thumbs) ────────────────────────────────────────────
// Rendered after every assistant bubble (except loading + in-flight streaming).
// Universal: past-session restore, live answers, structured bubbles all get
// the same affordance in the same place. Feedback requires a sessionId; copy
// only requires text.

export function MessageFooter({ text, sessionId, messageId }: { text?: string; sessionId: string | null; messageId: string }) {
  if (!text && !sessionId) return null
  return (
    <div
      style={{
        display: "flex",
        justifyContent: "flex-start",
        alignItems: "center",
        gap: 0,
        marginTop: 4,
        marginBottom: 12,
        marginLeft: -4,
      }}
    >
      {text ? <CopyButton text={text} /> : null}
      {sessionId ? <FeedbackButtons sessionId={sessionId} messageId={messageId} /> : null}
    </div>
  )
}
