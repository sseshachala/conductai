// @vitest-environment node
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs"
import { createRequire } from "node:module"
import { join, relative, resolve, sep } from "node:path"
import ts from "typescript"
import { expect, it } from "vitest"

const src = resolve(__dirname, "../..")
const app = join(src, "app")
const nextConfig = createRequire(import.meta.url)(resolve(src, "../next.config.js"))

function sourceFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap(entry => {
    const file = join(dir, entry.name)
    if (entry.isDirectory()) return entry.name === "__tests__" ? [] : sourceFiles(file)
    return /\.tsx?$/.test(file) && !/\.(test|spec|d)\.tsx?$/.test(file) ? [file] : []
  })
}

function routePattern(route: string): RegExp {
  const parts = route.split("/").filter(part => part && !part.startsWith("(") && !part.startsWith("@"))
  const pattern = parts.map(part => {
    if (part.startsWith("[[...") || (part.startsWith(":") && part.endsWith("*"))) return "(?:/.*)?"
    if (part.startsWith("[...")) return "/.+"
    if (part.startsWith("[") || part.startsWith(":")) return "/[^/]+"
    return "/" + part.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")
  }).join("")
  return new RegExp(`^${pattern}/?$`)
}

function hrefs(source: string, file: string): { href: string; line: number }[] {
  const tree = ts.createSourceFile(file, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX)
  const links: { href: string; line: number }[] = []
  function visit(node: ts.Node) {
    let value: string | undefined
    if (ts.isPropertyAssignment(node) && node.name.getText(tree).replace(/^['"]|['"]$/g, "") === "href" &&
        ts.isStringLiteralLike(node.initializer)) value = node.initializer.text
    if (ts.isJsxAttribute(node) && node.name.getText(tree) === "href") {
      const initializer = node.initializer
      if (initializer && ts.isStringLiteral(initializer)) value = initializer.text
      if (initializer && ts.isJsxExpression(initializer) && initializer.expression &&
          ts.isStringLiteralLike(initializer.expression)) value = initializer.expression.text
    }
    if (value?.startsWith("/") && !value.startsWith("//")) {
      links.push({ href: value, line: tree.getLineAndCharacterOfPosition(node.getStart()).line + 1 })
    }
    ts.forEachChild(node, visit)
  }
  visit(tree)
  return links
}

it("finds static hrefs in JSX and navigation data without treating dynamic or external links as internal", () => {
  expect(hrefs(`const links = [{ href: "/settings?tab=credentials" }];
    const view = <><Link href="/demo" /><a href={"/secure"} />
    <Link href={target} /><a href="https://example.test" /></>`, "fixture.tsx").map(link => link.href))
    .toEqual(["/settings?tab=credentials", "/demo", "/secure"])
})

it("matches route groups, dynamic segments, catch-alls and configured redirects", () => {
  expect(routePattern("/(app)/settings").test("/settings")).toBe(true)
  expect(routePattern("/(app)/workflows/[id]").test("/workflows/example")).toBe(true)
  expect(routePattern("/sign-in/[[...sign-in]]").test("/sign-in")).toBe(true)
  expect(routePattern("/sign-in/[[...sign-in]]").test("/sign-in/verify/password")).toBe(true)
  expect(routePattern("/marketplace/:slug*").test("/marketplace/example")).toBe(true)
  expect(routePattern("/(app)/settings").test("/settings/integrations")).toBe(false)
})

it("all static internal hrefs resolve to a page, configured redirect, proxy endpoint or public asset", async () => {
  const files = sourceFiles(src)
  const pages = files.filter(file => file.endsWith(`${sep}page.tsx`)).map(file =>
    routePattern("/" + relative(app, resolve(file, "..")).split(sep).join("/")))
  const configured = [...await nextConfig.redirects(), ...await nextConfig.rewrites()]
    .map((route: { source: string }) => routePattern(route.source))
  const broken: string[] = []
  for (const file of files) {
    for (const link of hrefs(readFileSync(file, "utf8"), file)) {
      const path = new URL(link.href, "https://conduct.test").pathname
      // API routes and oauth2-proxy are not App Router pages.
      if (path.startsWith("/api/") || path === "/oauth2/start") continue
      const asset = join(src, "..", "public", path)
      if (existsSync(asset) && statSync(asset).isFile()) continue
      if (![...pages, ...configured].some(pattern => pattern.test(path))) {
        broken.push(`${relative(src, file)}:${link.line} ${link.href}`)
      }
    }
  }
  expect(broken, "Broken internal links can produce intermittent prefetch 404s in browser smoke").toEqual([])
})
