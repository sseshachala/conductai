// Shared in-memory cache for read-only app-shell GETs (organizations,
// projects, preferences, permissions, ...). Every page remounts <AppShell>, so
// without this each client navigation refires ~10 identical calls at a
// single-worker API. Module-level, so it only survives client-side navigation
// (not a full reload). Keys are full URLs; workspace-scoped callers keep the
// workspace id in the URL (or an explicit key) so workspaces never share entries.

const DEFAULT_TTL_MS = 60_000

interface Entry { promise: Promise<unknown>; expires: number }

const entries = new Map<string, Entry>()
let boundUser: string | null | undefined

/** Resolve `load()` once per key within the TTL; concurrent callers share the in-flight promise. */
export function cachedGet<T>(key: string, load: () => Promise<T>, ttlMs = DEFAULT_TTL_MS): Promise<T> {
  const hit = entries.get(key)
  if (hit && hit.expires > Date.now()) return hit.promise as Promise<T>
  const promise = load()
  const entry: Entry = { promise, expires: Date.now() + ttlMs }
  entries.set(key, entry)
  // Failures are never cached, so a retry can succeed.
  promise.catch(() => { if (entries.get(key) === entry) entries.delete(key) })
  return promise
}

/** Drop every entry whose key starts with `prefix`. */
export function invalidate(prefix: string): void {
  for (const key of Array.from(entries.keys())) {
    if (key.startsWith(prefix)) entries.delete(key)
  }
}

/** Run a write; invalidate `prefixes` once it settles (success or failure). */
export function invalidating<T>(prefixes: string | string[], write: Promise<T>): Promise<T> {
  const list = Array.isArray(prefixes) ? prefixes : [prefixes]
  const done = () => list.forEach(invalidate)
  return write.then(r => { done(); return r }, e => { done(); throw e })
}

/** Clear everything when the signed-in user changes, so users never see each other's data. */
export function bindCacheToUser(userId: string | null): void {
  if (boundUser !== undefined && boundUser !== userId) entries.clear()
  boundUser = userId
}

export function clearSharedCache(): void {
  entries.clear()
}
