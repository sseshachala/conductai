export default function AgentStatusPill({ s }: { s: string }) {
  const m = ({
    ok:   ["ok",   "Succeeded"],
    wait: ["warn", "Awaiting"],
    run:  ["run",  "Running"],
    err:  ["err",  "Failed"],
    idle: ["idle", "Never run"],
    warn: ["warn", "Degraded"],
  } as Record<string, [string, string]>)[s] ?? ["idle", "Never run"]
  return (
    <span className={"sbadge " + m[0]}>
      {(s === "run" || s === "wait") && (
        <span className="dot pulse" style={{ background: m[0] === "warn" ? "var(--warn)" : "var(--info)" }} />
      )}
      {m[1]}
    </span>
  )
}
