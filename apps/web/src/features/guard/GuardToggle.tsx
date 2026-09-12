export function GuardToggle({ on, onClick, disabled }: { on: boolean; onClick: () => void; disabled?: boolean }) {
  return (
    <span
      onClick={disabled ? undefined : onClick}
      role="switch"
      aria-checked={on}
      aria-disabled={disabled}
      style={{
        width: 40,
        height: 23,
        borderRadius: 20,
        background: on ? "var(--accent)" : "var(--border-2)",
        position: "relative",
        cursor: disabled ? "default" : "pointer",
        flexShrink: 0,
        transition: "background .15s",
        display: "inline-block",
        opacity: disabled ? 0.5 : 1,
      }}
    >
      <span
        style={{
          position: "absolute",
          top: 2.5,
          left: on ? 19.5 : 2.5,
          width: 18,
          height: 18,
          borderRadius: "50%",
          background: "#fff",
          transition: "left .15s",
          boxShadow: "var(--shadow-sm)",
        }}
      />
    </span>
  )
}
