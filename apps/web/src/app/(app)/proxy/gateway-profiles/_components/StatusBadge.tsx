import type { GatewayProfileV2Out } from "@/lib/api/guard"

import { profileStatus, STATUS_LABEL } from "./presets"

const TONE = { draft: "idle", published: "ok", unpublished: "warn" } as const

export function StatusBadge({ profile }: { profile: GatewayProfileV2Out }) {
  const status = profileStatus(profile)
  return <span className={`sbadge ${TONE[status]}`}>{STATUS_LABEL[status]}</span>
}

/** Shown when the working copy has edits that are not yet in a revision. */
export function ChangesBadge({ profile }: { profile: GatewayProfileV2Out }) {
  if (!profile.has_unpublished_changes || profileStatus(profile) === "draft") return null
  return <span className="sbadge info">Unpublished changes</span>
}
