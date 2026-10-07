// ── SVG Icon helpers ──────────────────────────────────────────────────────────

function Icon({ d, children, size = 16, strokeWidth = 1.5, className = "" }: {
  d?: string
  children?: React.ReactNode
  size?: number
  strokeWidth?: number
  className?: string
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      {d ? <path d={d} /> : children}
    </svg>
  )
}

export const Icons = {
  Spark: () => <Icon><path d="M12 3v4M12 17v4M3 12h4M17 12h4" /><circle cx="12" cy="12" r="4" /></Icon>,
  Shield: () => <Icon><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" /></Icon>,
  Grid: () => <Icon><path d="M3 3h7v7H3zm11 0h7v7h-7zM3 14h7v7H3zm11 0h7v7h-7z" /></Icon>,
  Board: () => <Icon><path d="M3 3h5v18H3zm7 0h5v11h-5zm7 0h5v14h-5z" /></Icon>,
  Flow: () => (
    <Icon>
      <circle cx="5" cy="12" r="2" />
      <circle cx="19" cy="5" r="2" />
      <circle cx="19" cy="19" r="2" />
      <path d="M7 12h3l2-7h2M7 12h3l2 7h2" />
    </Icon>
  ),
  Store: () => (
    <Icon>
      <path d="M3 9l1-6h16l1 6" />
      <path d="M3 9h18v12a1 1 0 01-1 1H4a1 1 0 01-1-1V9z" />
      <path d="M9 9v12M15 9v12" />
    </Icon>
  ),
  Pulse: () => <Icon><polyline points="22 12 18 12 15 21 9 3 6 12 2 12" /></Icon>,
  Eye: () => <Icon><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" /><circle cx="12" cy="12" r="3" /></Icon>,
  Star: () => <Icon><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" /></Icon>,
  Trophy: () => <Icon><path d="M6 9H3V3h18v6h-3" /><path d="M12 15a6 6 0 006-6V3H6v6a6 6 0 006 6z" /><path d="M12 15v6M8 21h8" /></Icon>,
  Gear: () => (
    <Icon>
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z" />
    </Icon>
  ),
  Bell: () => <Icon><path d="M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9M13.73 21a2 2 0 01-3.46 0" /></Icon>,
  Search: () => <Icon><circle cx="11" cy="11" r="8" /><path d="m21 21-4.35-4.35" /></Icon>,
  ChevRight: () => <Icon><polyline points="9 18 15 12 9 6" /></Icon>,
  ChevDown: () => <Icon><polyline points="6 9 12 15 18 9" /></Icon>,
  Plus: () => <Icon><path d="M12 5v14M5 12h14" /></Icon>,
  Play: () => <Icon><polygon points="5 3 19 12 5 21 5 3" /></Icon>,
  Arrow: () => <Icon><path d="M5 12h14M12 5l7 7-7 7" /></Icon>,
  Lock: () => <Icon><rect x="3" y="11" width="18" height="11" rx="2" ry="2" /><path d="M7 11V7a5 5 0 0110 0v4" /></Icon>,
  Plug: () => <Icon><path d="M18 6L6 18M7 17l-4 4M17 7l4-4M9 3v4M15 3v4M9 7h6M9 7a3 3 0 000 6h6a3 3 0 000-6" /></Icon>,
  Users: () => <Icon><path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2" /><circle cx="9" cy="7" r="4" /><path d="M23 21v-2a4 4 0 00-3-3.87M16 3.13a4 4 0 010 7.75" /></Icon>,
  Sparkles: () => <Icon><path d="M12 3l1.5 4.5L18 9l-4.5 1.5L12 15l-1.5-4.5L6 9l4.5-1.5L12 3z" /><path d="M19 14l.7 2.1L22 17l-2.3.9L19 20l-.7-2.1L16 17l2.3-.9L19 14z" /></Icon>,
}
