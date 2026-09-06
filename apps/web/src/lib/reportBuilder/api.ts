/**
 * CRUD client for /workspaces/{ws}/report-layouts (#1450 PR 2).
 * Thin wrapper — no caching, no reactive state.
 */
import { API, AuthFetch, del, json, post, put } from "../api/client"
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
  created_by: string
  created_at: string
  updated_at: string
}

const base = (workspaceId: string) =>
  `${API}/workspaces/${workspaceId}/report-layouts`

export const reportLayoutsApi = {
  list: (f: AuthFetch, workspaceId: string) =>
    json<ReportLayout[]>(f, base(workspaceId)),

  get: (f: AuthFetch, workspaceId: string, slug: string) =>
    json<ReportLayout>(f, `${base(workspaceId)}/${slug}`),

  create: (
    f: AuthFetch,
    workspaceId: string,
    body: { slug: string; name: string; layout_spec: WidgetSpec[] },
  ) => post(f, base(workspaceId), body),

  update: (
    f: AuthFetch,
    workspaceId: string,
    slug: string,
    body: { name?: string; layout_spec?: WidgetSpec[] },
  ) => put(f, `${base(workspaceId)}/${slug}`, body),

  remove: (f: AuthFetch, workspaceId: string, slug: string) =>
    del(f, `${base(workspaceId)}/${slug}`),
}
