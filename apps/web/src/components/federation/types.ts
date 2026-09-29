export type TrustConfig = {
  status: "draft" | "active" | "disabled"
  integration_type: "generic" | "pcai" | "litellm"
  method: "oauth_access_token"
  issuer: string
  audience: string
  jwks_uri: string
  discovery_uri: string | null
  token_profile: "at+jwt" | "token_use_access"
  algorithms: string[]
  claim_mappings: { name: string; source_claim: string }[]
}
export type Connection = {
  id: string; integration_id: string; revision: number; name: string; config: TrustConfig
}
export type Approval = {
  id: string; revision: number; status: "active" | "disabled"; actions: string[]
  issuer?: string; subject?: string; kind?: "human" | "workload"
  caller_id?: string; connection_id?: string; binding_id?: string; principal_id?: string; expires_at?: string
}
export type ApprovalKind = "principals" | "bindings" | "grants"
export type Overview = {
  connections: Connection[]; principals: Approval[]; bindings: Approval[]; grants: Approval[]
  callers: { id: string; name: string }[]; actions: string[]
}
export type Save = (path: string, body: unknown, method?: string) => Promise<boolean>

export function approvalBody(row: Approval) {
  const { id, revision, ...values } = row
  return { ...values, expected_revision: revision }
}
export const connectionPath = (workspace: string, row: Connection) =>
  `/workspaces/${workspace}/integrations/${row.integration_id}/federation`

export function apiError(status: number, detail: unknown): string {
  if (status === 403) return "Workspace administrator access is required."
  if (status === 409) return "This record changed or conflicts with an existing record. Refresh before saving again."
  if (Array.isArray(detail)) return detail.map(d => `${d.loc?.slice(1).join(".") || "Configuration"}: ${d.msg}`).join("; ")
  return typeof detail === "string" ? detail.replaceAll("_", " ") : `Request failed (${status}).`
}
