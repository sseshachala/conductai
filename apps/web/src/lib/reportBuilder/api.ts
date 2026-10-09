/**
 * CRUD client for /workspaces/{ws}/report-layouts (#1450 PR 2).
 * Thin wrapper — only `list` is cached (shared cache; writes invalidate it).
 */
import { API, AuthFetch, del, json, post, put } from "../api/client"
import { cachedGet, invalidating } from "../api/sharedCache"
import type { WidgetHint } from "./widgets"

export interface WidgetSpec {
  tool_name: string
  hint: WidgetHint | string
}

export interface ReportLayout {
  id: string
  slug: string
  name: string
  layout_spec: WidgetSpec[]
  is_pinned: boolean
  created_by: string
  created_at: string
  updated_at: string
}

const base = (workspaceId: string) =>
  `${API}/workspaces/${workspaceId}/report-layouts`

export const reportLayoutsApi = {
  list: (f: AuthFetch, workspaceId: string) =>
    cachedGet(base(workspaceId), () => json<ReportLayout[]>(f, base(workspaceId))),

  get: (f: AuthFetch, workspaceId: string, slug: string) =>
    json<ReportLayout>(f, `${base(workspaceId)}/${slug}`),

  create: (
    f: AuthFetch,
    workspaceId: string,
    body: { slug: string; name: string; layout_spec: WidgetSpec[] },
  ) => invalidating(base(workspaceId), post(f, base(workspaceId), body)),

  update: (
    f: AuthFetch,
    workspaceId: string,
    slug: string,
    body: { name?: string; layout_spec?: WidgetSpec[]; is_pinned?: boolean },
  ) => invalidating(base(workspaceId), put(f, `${base(workspaceId)}/${slug}`, body)),

  remove: (f: AuthFetch, workspaceId: string, slug: string) =>
    invalidating(base(workspaceId), del(f, `${base(workspaceId)}/${slug}`)),
}
