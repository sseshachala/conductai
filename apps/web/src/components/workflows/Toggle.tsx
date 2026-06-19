export default function Toggle({ on, onClick }: { on: boolean; onClick: () => void }) {
  return (
    <span
      onClick={(e) => { e.stopPropagation(); onClick() }}
      style={{
        width: 36, height: 21, borderRadius: 20,
        background: on ? "var(--accent)" : "var(--border-2)",
        position: "relative", cursor: "pointer", flexShrink: 0,
        transition: "background .15s", display: "inline-block",
      }}
    >
      <span style={{
        position: "absolute", top: 2.5, left: on ? 17.5 : 2.5,
        width: 16, height: 16, borderRadius: "50%", background: "#fff",
        transition: "left .15s", boxShadow: "var(--shadow-sm)",
      }} />
    </span>
  )
}
