export function buildWorkspaceHeaders(token: string | null, workspaceId?: string | null): Record<string, string> {
  const headers: Record<string, string> = { "Content-Type": "application/json" }
  if (token) headers["Authorization"] = `Bearer ${token}`
  if (workspaceId) headers["x-workspace-id"] = workspaceId
  return headers
}
