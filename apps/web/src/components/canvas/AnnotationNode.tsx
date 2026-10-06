"use client"

import { createContext, memo, useContext, useState } from "react"
import { NodeResizer, useReactFlow, type NodeProps } from "@xyflow/react"
import { renderMd } from "@/components/glens/glensMarkdown"
import { ANNOTATION_COLORS, type AnnotationColor, type AnnotationData } from "@/lib/canvas/annotations"

/** True for viewers — notes render but can't be edited, recoloured or locked. */
export const CanvasReadOnlyContext = createContext(false)

const COLOR_CLASSES: Record<AnnotationColor, string> = {
  yellow: "bg-amber-50 border-amber-200",
  blue:   "bg-sky-50 border-sky-200",
  green:  "bg-emerald-50 border-emerald-200",
  pink:   "bg-rose-50 border-rose-200",
  gray:   "bg-stone-100 border-stone-300",
}
const SWATCH: Record<AnnotationColor, string> = {
  yellow: "bg-amber-300", blue: "bg-sky-300", green: "bg-emerald-300", pink: "bg-rose-300", gray: "bg-stone-400",
}

/** Non-executable sticky note: title + Markdown body. Never reaches the runtime. */
function AnnotationNode({ id, data, selected }: NodeProps) {
  const note = data as AnnotationData
  const readOnly = useContext(CanvasReadOnlyContext)
  const { updateNode, updateNodeData } = useReactFlow()
  const [editing, setEditing] = useState(false)
  const editable = !readOnly && !note.locked

  return (
    <div
      className={`h-full w-full flex flex-col rounded-lg border shadow-sm ${COLOR_CLASSES[note.color] ?? COLOR_CLASSES.yellow} ${selected ? "ring-1 ring-[var(--accent)]" : ""}`}
      onDoubleClick={() => editable && setEditing(true)}
      // Leave edit mode only when focus leaves the whole note (title ↔ body keeps it).
      onBlur={e => { if (!e.currentTarget.contains(e.relatedTarget as globalThis.Node | null)) setEditing(false) }}
      onKeyDown={e => { if (e.key === "Escape") setEditing(false) }}
      role="note"
      aria-label={note.title ? `Note: ${note.title}` : "Note"}
    >
      <NodeResizer isVisible={selected && editable} minWidth={140} minHeight={80} />
      <div className="flex items-center gap-1.5 px-2.5 pt-2">
        {editing ? (
          <input
            autoFocus
            aria-label="Note title"
            placeholder="Title"
            value={note.title}
            onChange={e => updateNodeData(id, { title: e.target.value })}
            className="nodrag flex-1 min-w-0 bg-transparent text-xs font-semibold text-stone-800 outline-none"
          />
        ) : (
          <span className="flex-1 min-w-0 truncate text-xs font-semibold text-stone-800">{note.title}</span>
        )}
        {selected && !readOnly && (
          <div className="nodrag flex items-center gap-1">
            {ANNOTATION_COLORS.map(c => (
              <button
                key={c}
                type="button"
                aria-label={`Colour ${c}`}
                aria-pressed={note.color === c}
                disabled={note.locked}
                onClick={() => updateNodeData(id, { color: c })}
                className={`w-3 h-3 rounded-full ${SWATCH[c]} ${note.color === c ? "ring-1 ring-offset-1 ring-stone-500" : ""} disabled:opacity-40`}
              />
            ))}
            <button
              type="button"
              aria-label={note.locked ? "Unlock note" : "Lock note"}
              aria-pressed={note.locked}
              title={note.locked ? "Unlock" : "Lock — prevent moving and editing"}
              onClick={() => { setEditing(false); updateNode(id, { draggable: note.locked, data: { ...note, locked: !note.locked } }) }}
              className="ml-0.5 text-[11px] text-stone-500 hover:text-stone-800"
            >
              {note.locked ? "🔒" : "🔓"}
            </button>
          </div>
        )}
      </div>
      {editing ? (
        <textarea
          aria-label="Note text (Markdown)"
          placeholder="Write in Markdown…"
          value={note.text}
          onChange={e => updateNodeData(id, { text: e.target.value })}
          className="nodrag nowheel flex-1 m-2 resize-none bg-white/60 rounded p-1.5 text-xs text-stone-800 outline-none"
        />
      ) : (
        <div className="nowheel flex-1 overflow-auto px-2.5 pb-2 text-xs text-stone-700 leading-relaxed">
          {note.text ? renderMd(note.text) : (
            <span className="text-stone-400 italic">{editable ? "Double-click to write a note" : ""}</span>
          )}
        </div>
      )}
    </div>
  )
}

export default memo(AnnotationNode)
