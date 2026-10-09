import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { AuditExportBubble, filenameFromDisposition, parseAuditExport, type AuditExportResult } from "./AuditExportBubble"

const base: AuditExportResult = {
  kind: "audit_export",
  row_count: 1234,
  since: "2026-10-01T00:00:00Z",
  until: "2026-10-08T00:00:00Z",
  format: "ndjson",
  capped: false,
  cap: 50000,
  head_hash: "abcdef0123456789abcdef",
  tail_hash: "fedcba9876543210fedcba",
  download_path: "/guard/events/export?since=a&until=b&format=ndjson",
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe("AuditExportBubble", () => {
  const create = vi.fn(() => "blob:x")
  const revoke = vi.fn()
  let click: ReturnType<typeof vi.spyOn>

  beforeEach(() => {
    create.mockClear()
    revoke.mockClear()
    Object.assign(URL, { createObjectURL: create, revokeObjectURL: revoke })
    click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {})
  })

  it("renders range, rows, format, short hashes and no cap notice", () => {
    render(<AuditExportBubble result={base} authFetch={vi.fn()} />)
    expect(screen.getByText("1,234")).toBeTruthy()
    expect(screen.getByText("NDJSON")).toBeTruthy()
    expect(screen.getByText("abcdef01…cdef")).toBeTruthy()
    expect(screen.getByText("fedcba98…dcba")).toBeTruthy()
    expect(screen.getByText(/2026-10-01 00:00 UTC to 2026-10-08 00:00 UTC/)).toBeTruthy()
    expect(screen.queryByRole("note")).toBeNull()
  })

  it("shows the capped notice", () => {
    render(<AuditExportBubble result={{ ...base, capped: true }} authFetch={vi.fn()} />)
    expect(screen.getByRole("note").textContent).toContain("Capped at 50,000 rows — narrow the range")
  })

  it("download fetches with authFetch and saves the blob", async () => {
    const authFetch = vi.fn().mockResolvedValue(
      new Response("{}\n", { status: 200, headers: { "Content-Disposition": 'attachment; filename="audit-2026.ndjson"' } }),
    )
    render(<AuditExportBubble result={base} authFetch={authFetch} />)
    fireEvent.click(screen.getByRole("button", { name: "Download" }))
    await waitFor(() => expect(click).toHaveBeenCalled())
    expect(authFetch).toHaveBeenCalledWith(expect.stringContaining(base.download_path))
    expect(create).toHaveBeenCalledTimes(1)
    expect(revoke).toHaveBeenCalledWith("blob:x")
  })

  it("maps 403 to an access message", async () => {
    const authFetch = vi.fn().mockResolvedValue(new Response("", { status: 403 }))
    render(<AuditExportBubble result={base} authFetch={authFetch} />)
    fireEvent.click(screen.getByRole("button", { name: "Download" }))
    expect((await screen.findByRole("alert")).textContent).toBe("You need audit log access")
    expect(click).not.toHaveBeenCalled()
  })

  it("shows an error on network failure", async () => {
    const authFetch = vi.fn().mockRejectedValue(new Error("down"))
    render(<AuditExportBubble result={base} authFetch={authFetch} />)
    fireEvent.click(screen.getByRole("button", { name: "Download" }))
    expect((await screen.findByRole("alert")).textContent).toMatch(/Download failed/)
  })
})

describe("helpers", () => {
  it("filenameFromDisposition parses and falls back", () => {
    expect(filenameFromDisposition(null, "f.csv")).toBe("f.csv")
    expect(filenameFromDisposition('attachment; filename="a.csv"', "f")).toBe("a.csv")
    expect(filenameFromDisposition("attachment; filename*=UTF-8''a%20b.csv", "f")).toBe("a b.csv")
  })
  it("parseAuditExport accepts top-level or nested, rejects others", () => {
    expect(parseAuditExport(base)).toBe(base)
    expect(parseAuditExport({ audit_export: base })).toBe(base)
    expect(parseAuditExport({ kind: "other" })).toBeNull()
    expect(parseAuditExport(null)).toBeNull()
  })
})
