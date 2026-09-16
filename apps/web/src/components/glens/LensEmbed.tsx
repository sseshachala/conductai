"use client"
/**
 * LensEmbed — inline Lens surface (#1830).
 *
 * Drop-in Lens chat that fills its parent container. No AppShell chrome, no
 * dock, no expand/close buttons — the host page owns everything around it.
 * Reuses the same streaming loop, composer, and bubble rendering as the
 * docked LensPanel and the full-page canvas.
 *
 *   <LensEmbed sessionId={runThreadId} initialQuery="…" height={480} />
 *
 * Pass `sessionId` to attach to an existing thread (e.g. a live playbook run
 * on /theguard/try Tab II). Pass `initialQuery` to auto-send the first turn.
 */

import { LensChat } from "@/components/glens/LensChat"

export function LensEmbed({
  sessionId,
  initialQuery,
  height = 480,
  title,
  emptyText,
  placeholder,
  persistKey,
  onActionCompleted,
}: {
  sessionId?: string | null
  initialQuery?: string | null
  /** Fixed height in px, or any valid CSS height (e.g. "60vh"). Default 480px. */
  height?: number | string
  /** Optional header label. Omit for chromeless. */
  title?: string
  emptyText?: string
  placeholder?: string
  /** Persist the server-issued session id in localStorage under
   *  `lens.session.<persistKey>`. Reload = same session, no lost
   *  pending_action_ids. Omit for one-shot surfaces. */
  persistKey?: string
  /** Fires when an ActionConfirmBubble resolves (server-side execute
   *  succeeded). Host pages use this to reload whatever they render
   *  from the API — e.g. the Gateway Profiles list. */
  onActionCompleted?: () => void
}) {
  return (
    <div
      style={{
        height: typeof height === "number" ? `${height}px` : height,
        display: "flex", flexDirection: "column",
        background: "var(--surface)",
        border: "1px solid var(--border)",
        borderRadius: 10,
        overflow: "hidden",
      }}
      role="region"
      aria-label={title ?? "Lens"}
    >
      {title && (
        <div style={{
          padding: "10px 14px", borderBottom: "1px solid var(--border)",
          background: "var(--surface-1)",
          fontSize: 13, fontWeight: 600, color: "var(--text)",
        }}>
          {title}
        </div>
      )}
      <LensChat
        pathname={null}
        initialQuery={initialQuery ?? null}
        initialSessionId={sessionId ?? null}
        emptyText={emptyText}
        placeholder={placeholder}
        persistKey={persistKey}
        onActionCompleted={onActionCompleted}
      />
    </div>
  )
}
