export default function WorkflowMenu({
  wfId,
  wfName,
  menuOpen,
  onToggleMenu,
  onRename,
  onDelete,
}: {
  wfId: string
  wfName: string
  menuOpen: string | null
  onToggleMenu: (id: string) => void
  onRename: (id: string, name: string) => void
  onDelete: (id: string) => void
}) {
  const isOpen = menuOpen === wfId
  return (
    <div style={{ position: "relative" }}>
      <button
        className="btn btn-ghost btn-icon btn-sm"
        title="More"
        aria-label="Workflow options"
        onClick={e => { e.stopPropagation(); onToggleMenu(wfId) }}
      >⋯</button>
      {isOpen && (
        <div
          role="menu"
          onMouseDown={e => e.stopPropagation()}
          style={{ position: "absolute", right: 0, top: "100%", marginTop: 4, zIndex: 20, minWidth: 130, background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 10, boxShadow: "var(--shadow-md)", padding: "4px 0" }}
        >
          <button
            role="menuitem"
            onClick={e => { e.stopPropagation(); onToggleMenu(wfId); onRename(wfId, wfName) }}
            style={{ width: "100%", textAlign: "left", padding: "7px 14px", fontSize: 13, color: "var(--text)", background: "none", border: "none", cursor: "pointer" }}
            onMouseEnter={e => (e.currentTarget as HTMLElement).style.background = "var(--surface-2)"}
            onMouseLeave={e => (e.currentTarget as HTMLElement).style.background = "none"}
          >Rename</button>
          <button
            role="menuitem"
            onMouseDown={e => { e.stopPropagation(); onToggleMenu(wfId); onDelete(wfId) }}
            style={{ width: "100%", textAlign: "left", padding: "7px 14px", fontSize: 13, color: "var(--err, #dc2626)", background: "none", border: "none", cursor: "pointer" }}
            onMouseEnter={e => (e.currentTarget as HTMLElement).style.background = "var(--surface-2)"}
            onMouseLeave={e => (e.currentTarget as HTMLElement).style.background = "none"}
          >Delete</button>
        </div>
      )}
    </div>
  )
}
