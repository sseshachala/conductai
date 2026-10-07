// ── Data ─────────────────────────────────────────────────────────────────────

export const ONB_STEPS = ["Workspace", "Connect tools", "Guard", "Install playbook"] as const

export const INTEGRATIONS = [
  { id: "github",  name: "GitHub",   desc: "Repos, issues, PRs, webhooks", color: "#1c1917" },
  { id: "slack",   name: "Slack",    desc: "Messages, DMs, approvals",      color: "#4a154b" },
  // ponytail: Linear/Vercel/Railway deferred — re-enable when /integrations supports them (#858 slice 2 redesigns this whole step)
  // { id: "linear",  name: "Linear",   desc: "Issues, projects, labels",            color: "#5b5bd6" },
  // { id: "vercel",  name: "Vercel",   desc: "Deployments, logs, domains",          color: "#000000" },
  // { id: "railway", name: "Railway",  desc: "Services, deployments, environments", color: "#0f172a" },
] as const

export const FEATURED_PLAYBOOKS = [
  { name: "Autopilot + Approval", desc: "Issue → branch → fix → draft PR → Slack approval → merge", blocks: 9 },
  { name: "Autopilot Full",       desc: "Issue → branch → fix → tests → auto-merge if CI passes",  blocks: 7 },
  { name: "PR Review Bot",        desc: "PR opened → review comments → approve or request changes", blocks: 5 },
] as const

export const PIPELINE_BLOCKS = [
  { type: "trigger",  label: "TRIGGER",    text: "GitHub issue labelled ai-ready" },
  { type: "memory",   label: "MEMORY",     text: "Recall what the agent learned here" },
  { type: "brain",    label: "AGENT STEP", text: "Claude reads, clones, writes the fix" },
  { type: "guard",    label: "GUARD",      text: "Guard: spend cap + policy check" },
  { type: "tool",     label: "ACTION",     text: "Open a draft pull request" },
  { type: "approval", label: "APPROVAL",   text: "Slack: Approve / Reject" },
  { type: "output",   label: "NOTIFY",     text: "Post result to #eng" },
] as const

export const STEP_HEADS: Record<number, [string, string]> = {
  1: [
    "Set up your workspace",
    "Workspaces live inside your organisation. Each one keeps its own projects, runs, memory, and credentials.",
  ],
  2: [
    "Connect your tools",
    "Agents act through real integrations. Credentials are encrypted at rest and scoped per environment.",
  ],
  3: [
    "Guard protects everything",
    "Guard is on by default for the whole workspace — you don't install it per project.",
  ],
  4: [
    "Create a project & install a playbook",
    "Your first project is created here. Guard governs it automatically — no extra setup.",
  ],
}

// ── Icons ────────────────────────────────────────────────────────────────────

export function ArrowIcon() {
  return (
    <svg width={16} height={16} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M5 12h14M12 5l7 7-7 7" />
    </svg>
  )
}

export function CheckIcon({ size = 16 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <polyline points="20 6 9 17 4 12" />
    </svg>
  )
}

export function ShieldIcon({ size = 19 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
    </svg>
  )
}

export function LockIcon() {
  return (
    <svg width={14} height={14} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
      <path d="M7 11V7a5 5 0 0 1 10 0v4" />
    </svg>
  )
}

export function FlowIcon() {
  return (
    <svg width={17} height={17} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="5" cy="12" r="2" />
      <circle cx="19" cy="5" r="2" />
      <circle cx="19" cy="19" r="2" />
      <path d="M7 12h3l2-7h2M7 12h3l2 7h2" />
    </svg>
  )
}

// ── Shared input style ────────────────────────────────────────────────────────

export const inputStyle: React.CSSProperties = {
  width: "100%",
  height: 40,
  padding: "0 13px",
  borderRadius: 9,
  border: "1px solid var(--border)",
  background: "var(--surface)",
  color: "var(--text)",
  fontSize: 14,
  outline: "none",
  fontFamily: "inherit",
}

// ── Block chip helper ─────────────────────────────────────────────────────────

export function BlockChip({ type, label, hot }: { type: string; label: string; hot: boolean }) {
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        height: 20,
        padding: "0 7px",
        borderRadius: 20,
        fontSize: 9.5,
        letterSpacing: ".08em",
        fontWeight: 700,
        border: "1px solid",
        background: `var(--blk-${type}-bg)`,
        borderColor: hot && type === "guard" ? "var(--accent-ring)" : `var(--blk-${type}-bd)`,
        color: `var(--blk-${type}-tx)`,
        transition: "border-color .2s",
        flexShrink: 0,
      }}
    >
      {label}
    </span>
  )
}
