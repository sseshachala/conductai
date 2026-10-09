import { API, AuthFetch, del, json, patch, post, put } from "./client"
import { cachedGet, invalidating } from "./sharedCache"

const base = () => `${API}/projects`
// Membership writes change my-role and the derived /me/permissions.
const roleKeys = (projectId: string) => [`${base()}/${projectId}/my-role`, `${API}/me/permissions`]

export const projects = {
  list: (f: AuthFetch) => cachedGet(base(), () => json<any[]>(f, base())),
  get: (f: AuthFetch, id: string) => json<any>(f, `${base()}/${id}`),
  create: (f: AuthFetch, body: Record<string, unknown>) => invalidating(base(), post(f, base(), body)),
  update: (f: AuthFetch, id: string, body: Record<string, unknown>) =>
    invalidating(base(), put(f, `${base()}/${id}`, body)),
  remove: (f: AuthFetch, id: string) => invalidating([base(), `${API}/workspaces/${id}/`], del(f, `${base()}/${id}`)),

  members: {
    list: (f: AuthFetch, projectId: string) =>
      json<any[]>(f, `${base()}/${projectId}/members`),
    add: (f: AuthFetch, projectId: string, body: Record<string, unknown>) =>
      invalidating(roleKeys(projectId), post(f, `${base()}/${projectId}/members`, body)),
    update: (f: AuthFetch, projectId: string, userId: string, body: Record<string, unknown>) =>
      invalidating(roleKeys(projectId), put(f, `${base()}/${projectId}/members/${userId}`, body)),
    patch: (f: AuthFetch, projectId: string, userId: string, body: Record<string, unknown>) =>
      invalidating(roleKeys(projectId), patch(f, `${base()}/${projectId}/members/${userId}`, body)),
    remove: (f: AuthFetch, projectId: string, userId: string) =>
      invalidating(roleKeys(projectId), del(f, `${base()}/${projectId}/members/${userId}`)),
    // Role lives on a workspace (a project is not one): pass the workspace id.
    myRole: (f: AuthFetch, workspaceId: string) => {
      const url = `${base()}/${workspaceId}/my-role?workspace_id=${workspaceId}`
      return cachedGet(url, () => json<any>(f, url), 30_000)
    },
    workspaces: (f: AuthFetch, projectId: string, userId: string) =>
      json<any[]>(f, `${base()}/${projectId}/members/${userId}/workspaces`),
  },

  invites: {
    list: (f: AuthFetch, projectId: string) =>
      json<any[]>(f, `${base()}/${projectId}/invites`),
    cancel: (f: AuthFetch, projectId: string, inviteId: string) =>
      del(f, `${base()}/${projectId}/invites/${inviteId}`),
  },

  guard: {
    install: (f: AuthFetch, projectId: string) =>
      invalidating(`${API}/guard/config`, post(f, `${base()}/${projectId}/guard/install`, {})),
  },
}
