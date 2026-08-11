import { readdirSync, statSync } from "fs"
import { join, relative, sep } from "path"

/**
 * Walk src/app for every page.tsx, translate the App-Router directory to a
 * URL, substitute deterministic values for dynamic segments, and skip catch-
 * alls that aren't safe to smoke without Clerk.
 */
const APP_ROOT = join(__dirname, "..", "src", "app")

// Substitutions for dynamic segments. Anything not in this map falls back to
// SUBSTITUTION_DEFAULT.
const SUBSTITUTION_DEFAULT = "smoke"
const SUBSTITUTIONS: Record<string, string> = {
  id: "00000000-0000-0000-0000-000000000000",
  run_id: "00000000-0000-0000-0000-000000000000",
  sessionId: "00000000-0000-0000-0000-000000000000",
  slug: "smoke",
  edition: "2026",
  token: "smoke-token",
}

// Route groups like (app) / (marketing) are not part of the URL. Catch-alls
// [[...x]] typically wrap third-party widgets (Clerk sign-in) and can't be
// smoked without their runtime.
const CATCHALL_RE = /\[\[?\.\.\..+?\]\]?/
const DYNAMIC_RE = /\[(.+?)\]/g
const GROUP_RE = /\/\(([^)]+)\)/g

function walk(dir: string, acc: string[] = []): string[] {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry)
    if (statSync(full).isDirectory()) {
      walk(full, acc)
    } else if (entry === "page.tsx") {
      acc.push(full)
    }
  }
  return acc
}

export interface Route {
  url: string
  file: string
  isMarketing: boolean
}

export function discoverRoutes(): Route[] {
  const files = walk(APP_ROOT)
  const routes: Route[] = []

  for (const file of files) {
    const rel = relative(APP_ROOT, file).replace(new RegExp(`\\${sep}`, "g"), "/")
    let path = "/" + rel.replace(/\/page\.tsx$/, "").replace(/^page\.tsx$/, "")

    if (CATCHALL_RE.test(path)) continue

    // Strip route groups.
    path = path.replace(GROUP_RE, "")
    if (path === "" || path === "/page.tsx") path = "/"

    // Substitute dynamic segments.
    path = path.replace(DYNAMIC_RE, (_m, name) => SUBSTITUTIONS[name] ?? SUBSTITUTION_DEFAULT)

    // Collapse doubled slashes from stripped groups.
    path = path.replace(/\/+/g, "/")
    if (path.length > 1 && path.endsWith("/")) path = path.slice(0, -1)

    routes.push({
      url: path,
      file: rel,
      isMarketing: rel.startsWith("(marketing)"),
    })
  }

  // Dedupe (route groups can produce the same URL from different files).
  const seen = new Set<string>()
  return routes.filter(r => (seen.has(r.url) ? false : (seen.add(r.url), true)))
}
