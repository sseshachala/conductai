/** Typed alias for the authFetch function returned by useAuthFetch. */
export type AuthFetch = (url: string, opts?: RequestInit) => Promise<Response>

export const API = process.env.NEXT_PUBLIC_API_URL ?? ""

export async function json<T>(f: AuthFetch, url: string, opts?: RequestInit): Promise<T> {
  const res = await f(url, opts)
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText)
    throw new Error(text || `${res.status}`)
  }
  return res.json() as Promise<T>
}

export function post(f: AuthFetch, url: string, body: unknown, opts?: RequestInit) {
  return f(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    ...opts,
  })
}

export function put(f: AuthFetch, url: string, body: unknown) {
  return f(url, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  })
}

export function patch(f: AuthFetch, url: string, body: unknown) {
  return f(url, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  })
}

export function del(f: AuthFetch, url: string) {
  return f(url, { method: "DELETE" })
}
