/**
 * HTML report generator.
 *
 * After all role flows complete, call generateReport() with the collected
 * results. It writes reports/index.html with:
 *   - A role × feature matrix at the top showing pass/fail at a glance
 *   - Per-role sections with step-by-step screenshots inline
 *   - Pass/fail badges and duration per role
 *   - Timestamp and total duration in the footer
 */

import { mkdirSync, writeFileSync, readFileSync, existsSync } from "fs"
import { join, relative } from "path"

export interface TestStep {
  description: string
  passed: boolean
  screenshotPath?: string
  note?: string
}

export interface RoleResult {
  role: string
  steps: TestStep[]
  startedAt: Date
  completedAt: Date
}

const ROLE_LABELS: Record<string, string> = {
  admin: "Admin",
  security: "Security",
  editor: "Editor",
  viewer: "Viewer",
}

function durationMs(result: RoleResult): number {
  return result.completedAt.getTime() - result.startedAt.getTime()
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`
  const m = Math.floor(ms / 60_000)
  const s = Math.round((ms % 60_000) / 1000)
  return `${m}m ${s}s`
}

function passRate(steps: TestStep[]): string {
  if (steps.length === 0) return "0/0"
  const passed = steps.filter((s) => s.passed).length
  return `${passed}/${steps.length}`
}

function badge(passed: boolean): string {
  return passed
    ? `<span class="badge pass">PASS</span>`
    : `<span class="badge fail">FAIL</span>`
}

function roleBadge(result: RoleResult): string {
  const allPassed = result.steps.every((s) => s.passed)
  const label = ROLE_LABELS[result.role] ?? result.role
  return allPassed
    ? `<span class="role-badge role-pass">${label}</span>`
    : `<span class="role-badge role-fail">${label}</span>`
}

/**
 * Converts an absolute screenshot path to a relative path from the report's
 * output directory, so the <img src="..."> references work when the report
 * directory is served or opened locally.
 */
function relativeScreenshotPath(screenshotPath: string, outputDir: string): string {
  return relative(outputDir, screenshotPath).replace(/\\/g, "/")
}

function screenshotImg(screenshotPath: string | undefined, outputDir: string): string {
  if (!screenshotPath) return ""
  const rel = relativeScreenshotPath(screenshotPath, outputDir)
  return `<div class="screenshot-wrap"><img src="${rel}" alt="screenshot" loading="lazy" /></div>`
}

function buildMatrixHtml(results: RoleResult[]): string {
  // Collect the union of all step descriptions across all roles
  const allSteps = Array.from(
    new Set(results.flatMap((r) => r.steps.map((s) => s.description)))
  )

  if (allSteps.length === 0) return ""

  const headerCells = results
    .map((r) => `<th>${ROLE_LABELS[r.role] ?? r.role}</th>`)
    .join("")

  const rows = allSteps.map((desc) => {
    const cells = results.map((r) => {
      const step = r.steps.find((s) => s.description === desc)
      if (!step) return `<td class="cell-na">—</td>`
      return step.passed
        ? `<td class="cell-pass">✓</td>`
        : `<td class="cell-fail">✗</td>`
    })
    return `<tr><td class="step-label">${escHtml(desc)}</td>${cells.join("")}</tr>`
  })

  return `
    <section class="matrix">
      <h2>Feature Matrix</h2>
      <table>
        <thead>
          <tr>
            <th class="step-label">Step</th>
            ${headerCells}
          </tr>
        </thead>
        <tbody>
          ${rows.join("\n")}
        </tbody>
      </table>
    </section>
  `
}

function escHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
}

function buildRoleSectionHtml(result: RoleResult, outputDir: string): string {
  const allPassed = result.steps.every((s) => s.passed)
  const label = ROLE_LABELS[result.role] ?? result.role
  const dur = formatDuration(durationMs(result))
  const rate = passRate(result.steps)

  const stepRows = result.steps
    .map(
      (step, i) => `
      <div class="step ${step.passed ? "step-pass" : "step-fail"}">
        <div class="step-header">
          <span class="step-num">${i + 1}</span>
          <span class="step-desc">${escHtml(step.description)}</span>
          ${badge(step.passed)}
        </div>
        ${step.note ? `<p class="step-note">${escHtml(step.note)}</p>` : ""}
        ${screenshotImg(step.screenshotPath, outputDir)}
      </div>
    `
    )
    .join("")

  return `
    <section class="role-section" id="role-${result.role}">
      <div class="role-header">
        <h2>${label} ${roleBadge(result)}</h2>
        <div class="role-meta">
          <span>${rate} steps passed</span>
          <span>${dur}</span>
          <span>${result.startedAt.toISOString()}</span>
        </div>
      </div>
      <div class="steps">
        ${stepRows}
      </div>
    </section>
  `
}

const CSS = `
  *, *::before, *::after { box-sizing: border-box; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: #f8f7f5;
    color: #1c1917;
    margin: 0;
    padding: 0 0 60px;
  }
  header {
    background: #fff;
    border-bottom: 1px solid #e7e5e4;
    padding: 20px 40px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    position: sticky;
    top: 0;
    z-index: 10;
  }
  header h1 { margin: 0; font-size: 18px; font-weight: 600; }
  header .meta { font-size: 13px; color: #78716c; }
  main { max-width: 1100px; margin: 0 auto; padding: 32px 24px; }
  h2 { font-size: 15px; font-weight: 600; margin: 0 0 12px; }
  .summary { display: flex; gap: 12px; margin-bottom: 32px; flex-wrap: wrap; }

  /* Role badges */
  .role-badge { display: inline-block; padding: 3px 10px; border-radius: 99px; font-size: 13px; font-weight: 600; margin-left: 8px; }
  .role-pass { background: #dcfce7; color: #166534; }
  .role-fail { background: #fee2e2; color: #991b1b; }

  /* Pass/fail badges */
  .badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 700; letter-spacing: .03em; }
  .pass { background: #dcfce7; color: #166534; }
  .fail { background: #fee2e2; color: #991b1b; }

  /* Matrix */
  .matrix { background: #fff; border: 1px solid #e7e5e4; border-radius: 12px; overflow: hidden; margin-bottom: 40px; }
  .matrix h2 { padding: 16px 20px 0; }
  .matrix table { width: 100%; border-collapse: collapse; font-size: 13px; }
  .matrix thead th { background: #fafaf9; font-weight: 600; padding: 10px 14px; text-align: center; border-bottom: 1px solid #e7e5e4; }
  .matrix thead .step-label { text-align: left; }
  .matrix tbody tr:hover { background: #fafaf9; }
  .matrix td { padding: 9px 14px; border-bottom: 1px solid #f5f5f4; text-align: center; }
  .step-label { text-align: left; color: #57534e; max-width: 420px; }
  .cell-pass { color: #16a34a; font-weight: 700; }
  .cell-fail { color: #dc2626; font-weight: 700; }
  .cell-na { color: #d6d3d1; }

  /* Role sections */
  .role-section { background: #fff; border: 1px solid #e7e5e4; border-radius: 12px; overflow: hidden; margin-bottom: 32px; }
  .role-header { padding: 16px 20px; border-bottom: 1px solid #e7e5e4; display: flex; align-items: center; justify-content: space-between; }
  .role-header h2 { margin: 0; }
  .role-meta { display: flex; gap: 16px; font-size: 12px; color: #78716c; }

  /* Steps */
  .steps { padding: 12px 16px; display: flex; flex-direction: column; gap: 8px; }
  .step { border: 1px solid #e7e5e4; border-radius: 8px; overflow: hidden; }
  .step-pass { border-color: #bbf7d0; }
  .step-fail { border-color: #fecaca; }
  .step-header { display: flex; align-items: center; gap: 10px; padding: 10px 14px; background: #fafaf9; }
  .step-pass .step-header { background: #f0fdf4; }
  .step-fail .step-header { background: #fff5f5; }
  .step-num { display: inline-flex; align-items: center; justify-content: center; width: 22px; height: 22px; border-radius: 50%; background: #e7e5e4; font-size: 11px; font-weight: 700; flex-shrink: 0; }
  .step-desc { flex: 1; font-size: 13px; font-weight: 500; }
  .step-note { margin: 0; padding: 6px 14px 8px; font-size: 12px; color: #78716c; border-top: 1px solid #f5f5f4; }
  .screenshot-wrap { padding: 12px; background: #1c1917; }
  .screenshot-wrap img { display: block; max-width: 100%; border-radius: 4px; }

  footer { text-align: center; font-size: 12px; color: #a8a29e; margin-top: 48px; }
`

/**
 * Generates the HTML report and writes it to outputDir/index.html.
 * Returns the absolute path to the report file.
 */
export async function generateReport(
  results: RoleResult[],
  outputDir: string
): Promise<string> {
  mkdirSync(outputDir, { recursive: true })

  const totalSteps = results.flatMap((r) => r.steps).length
  const totalPassed = results.flatMap((r) => r.steps).filter((s) => s.passed).length
  const allPassed = totalPassed === totalSteps
  const generatedAt = new Date().toISOString()

  const summaryBadges = results
    .map((r) => `<a href="#role-${r.role}" style="text-decoration:none">${roleBadge(r)}</a>`)
    .join("")

  const matrixHtml = buildMatrixHtml(results)
  const roleSections = results
    .map((r) => buildRoleSectionHtml(r, outputDir))
    .join("\n")

  const overallStatus = allPassed ? "All roles passed" : "Some roles failed"
  const overallColour = allPassed ? "#16a34a" : "#dc2626"

  const html = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Conduct Guard — UI Test Report</title>
  <style>${CSS}</style>
</head>
<body>
  <header>
    <h1>Conduct Guard — UI Test Report</h1>
    <div class="meta">${generatedAt}</div>
  </header>

  <main>
    <div class="summary">
      <div style="display:flex;align-items:center;gap:8px;font-size:14px;font-weight:600;color:${overallColour}">
        ${overallStatus}
      </div>
      <div style="display:flex;align-items:center;gap:8px;font-size:13px;color:#57534e">
        ${totalPassed}/${totalSteps} steps passed
      </div>
      <div style="display:flex;gap:6px;flex-wrap:wrap">${summaryBadges}</div>
    </div>

    ${matrixHtml}

    ${roleSections}
  </main>

  <footer>
    Generated by conduct-guard-tests &middot; ${generatedAt}
  </footer>
</body>
</html>`

  const outputPath = join(outputDir, "index.html")
  writeFileSync(outputPath, html, "utf8")
  return outputPath
}
