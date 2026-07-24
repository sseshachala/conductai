import { API, AuthFetch, del, json, post, put } from "./client"

const base = () => `${API}/projects`

export const projects = {
  list: (f: AuthFetch) => json<any[]>(f, base()),
  get: (f: AuthFetch, id: string) => json<any>(f, `${base()}/${id}`),
  create: (f: AuthFetch, body: Record<string, unknown>) => post(f, base(), body),
  update: (f: AuthFetch, id: string, body: Record<string, unknown>) =>
    put(f, `${base()}/${id}`, body),
  remove: (f: AuthFetch, id: string) => del(f, `${base()}/${id}`),

  members: {
    list: (f: AuthFetch, projectId: string) =>
      json<any[]>(f, `${base()}/${projectId}/members`),
    add: (f: AuthFetch, projectId: string, body: Record<string, unknown>) =>
      post(f, `${base()}/${projectId}/members`, body),
    update: (f: AuthFetch, projectId: string, userId: string, body: Record<string, unknown>) =>
      put(f, `${base()}/${projectId}/members/${userId}`, body),
    remove: (f: AuthFetch, projectId: string, userId: string) =>
      del(f, `${base()}/${projectId}/members/${userId}`),
    myRole: (f: AuthFetch, projectId: string) =>
      json<any>(f, `${base()}/${projectId}/my-role`),
  },

  guard: {
    install: (f: AuthFetch, projectId: string) =>
      post(f, `${base()}/${projectId}/guard/install`, {}),
  },
}
