import { describe, it, expect, vi } from "vitest"
import { render, screen, fireEvent, waitFor, act } from "@testing-library/react"
import {
  SlashDropdown,
  SlashForm,
  composePrompt,
  filterTools,
  COMPLETERS,
  SLASH_TOOLS,
  type SlashTool,
} from "../SlashPicker"

// Flush all pending microtasks from the async completer load so React state
// updates settle before the test asserts. Cheaper than waitFor when a test
// doesn't care about loaded options.
const flush = () => act(async () => { await Promise.resolve() })

// Stub useAuthFetch — ArgAutocomplete imports it. Real useAuthFetch returns
// a stable authFetch via useCallback; the mock must too or the useEffect that
// loads options fires every render.
const authFetchMock = (path: string) => {
  if (path.includes("/workflows")) {
    return Promise.resolve(new Response(JSON.stringify([
      { id: "wf-uuid-1", name: "Ship Feature", playbook_slug: "ship-feature" },
      { id: "wf-uuid-2", name: "Deploy Prod", playbook_slug: null },
    ])))
  }
  if (path.includes("/guard/approvals")) {
    return Promise.resolve(new Response(JSON.stringify({
      items: [{ id: "appr-1", rule_message: "Deploy to prod?", tool_name: "run_workflow" }],
    })))
  }
  if (path.includes("/guard/spend/budgets")) {
    return Promise.resolve(new Response(JSON.stringify([
      { id: "bud-1", email: "alice@example.com", monthly_limit_usd: 500 },
      { id: "bud-2", email: null, monthly_limit_usd: 200 },
    ])))
  }
  if (path.includes("/agent-identities")) {
    return Promise.resolve(new Response(JSON.stringify([
      { id: "agt-1", name: "prod-cli", provider: "anthropic" },
    ])))
  }
  if (path.includes("/compliance/packs/available")) {
    return Promise.resolve(new Response(JSON.stringify([
      { slug: "sr-11-7", name: "SR 11-7", description: "Federal model risk" },
    ])))
  }
  return Promise.resolve(new Response("null", { status: 404 }))
}
const authFetchRef = { authFetch: authFetchMock, workspaceId: "ws-1" }
vi.mock("@/hooks/useAuthFetch", () => ({
  useAuthFetch: () => authFetchRef,
}))

describe("filterTools", () => {
  it("returns all tools for empty filter", () => {
    expect(filterTools("")).toEqual(SLASH_TOOLS)
  })

  it("filters by name prefix, case-insensitive", () => {
    const matches = filterTools("Run")
    expect(matches).toHaveLength(1)
    expect(matches[0].name).toBe("run_workflow")
  })

  it("returns empty when nothing matches", () => {
    expect(filterTools("zzzzz")).toEqual([])
  })

  it("includes update_budget and install_pack in the catalogue", () => {
    const names = SLASH_TOOLS.map(t => t.name)
    expect(names).toContain("update_budget")
    expect(names).toContain("install_pack")
  })

  it("update_budget.budget_id uses the budgets completer", () => {
    const tool = SLASH_TOOLS.find(t => t.name === "update_budget")!
    const arg = tool.args.find(a => a.name === "budget_id")!
    expect(arg.completer).toBe("budgets")
    expect(arg.required).toBe(true)
  })

  it("install_pack.slug uses the marketplace_packs completer", () => {
    const tool = SLASH_TOOLS.find(t => t.name === "install_pack")!
    const arg = tool.args.find(a => a.name === "slug")!
    expect(arg.completer).toBe("marketplace_packs")
    expect(arg.required).toBe(true)
  })
})

describe("composePrompt", () => {
  const tool: SlashTool = SLASH_TOOLS[0]  // run_workflow

  it("wraps filled args as JSON-quoted key=value pairs", () => {
    const out = composePrompt(tool, { name_or_id: "hello-world" })
    expect(out).toBe('Please run run_workflow with name_or_id="hello-world".')
  })

  it("skips empty and whitespace-only args", () => {
    const out = composePrompt(tool, { name_or_id: "wf-1", inputs: "  " })
    expect(out).toBe('Please run run_workflow with name_or_id="wf-1".')
  })

  it("falls through with no args when none are filled", () => {
    const out = composePrompt(tool, {})
    expect(out).toBe("Please run run_workflow.")
  })
})

describe("SlashDropdown", () => {
  it("renders matches and calls onSelect on click", () => {
    const onSelect = vi.fn()
    render(<SlashDropdown matches={filterTools("run")} onSelect={onSelect} onClose={vi.fn()} />)

    const opt = screen.getByRole("option", { name: /run_workflow/ })
    fireEvent.click(opt)
    expect(onSelect).toHaveBeenCalledWith(
      expect.objectContaining({ name: "run_workflow" })
    )
  })

  it("renders nothing when matches is empty", () => {
    const { container } = render(
      <SlashDropdown matches={[]} onSelect={vi.fn()} onClose={vi.fn()} />
    )
    expect(container.firstChild).toBeNull()
  })
})

describe("SlashForm", () => {
  const tool: SlashTool = SLASH_TOOLS[0]  // run_workflow — first arg required

  it("disables Send until required args are filled", async () => {
    render(
      <SlashForm tool={tool} disabled={false} onSubmit={vi.fn()} onCancel={vi.fn()} />
    )
    await flush()
    const send = screen.getByRole("button", { name: /^Send$/ })
    expect(send).toBeDisabled()

    fireEvent.change(screen.getAllByRole("textbox")[0], { target: { value: "wf-1" } })
    expect(send).not.toBeDisabled()
  })

  it("submits with a composed prompt", async () => {
    const onSubmit = vi.fn()
    render(
      <SlashForm tool={tool} disabled={false} onSubmit={onSubmit} onCancel={vi.fn()} />
    )
    await flush()
    fireEvent.change(screen.getAllByRole("textbox")[0], { target: { value: "wf-1" } })
    fireEvent.click(screen.getByRole("button", { name: /^Send$/ }))
    expect(onSubmit).toHaveBeenCalledWith('Please run run_workflow with name_or_id="wf-1".')
  })

  it("calls onCancel when × is clicked", async () => {
    const onCancel = vi.fn()
    render(
      <SlashForm tool={tool} disabled={false} onSubmit={vi.fn()} onCancel={onCancel} />
    )
    await flush()
    fireEvent.click(screen.getByRole("button", { name: /^Cancel$/i }))
    expect(onCancel).toHaveBeenCalled()
  })
})

describe("ArgAutocomplete (via SlashForm run_workflow)", () => {
  const tool = SLASH_TOOLS[0]  // run_workflow.name_or_id has completer=workflows

  it("loads options from the completer and displays them", async () => {
    render(<SlashForm tool={tool} disabled={false} onSubmit={vi.fn()} onCancel={vi.fn()} />)
    fireEvent.focus(screen.getAllByRole("textbox")[0])
    await waitFor(() => expect(screen.getByText("Ship Feature")).toBeTruthy())
    expect(screen.getByText("Deploy Prod")).toBeTruthy()
  })

  it("clicking an option fills the arg with its value (slug preferred)", async () => {
    const onSubmit = vi.fn()
    render(<SlashForm tool={tool} disabled={false} onSubmit={onSubmit} onCancel={vi.fn()} />)
    fireEvent.focus(screen.getAllByRole("textbox")[0])
    await waitFor(() => screen.getByText("Ship Feature"))
    fireEvent.click(screen.getByText("Ship Feature"))
    fireEvent.click(screen.getByRole("button", { name: /^Send$/ }))
    expect(onSubmit).toHaveBeenCalledWith('Please run run_workflow with name_or_id="ship-feature".')
  })

  it("filters options as the user types", async () => {
    render(<SlashForm tool={tool} disabled={false} onSubmit={vi.fn()} onCancel={vi.fn()} />)
    const input = screen.getAllByRole("textbox")[0]
    fireEvent.focus(input)
    await waitFor(() => screen.getByText("Ship Feature"))
    fireEvent.change(input, { target: { value: "deploy" } })
    expect(screen.queryByText("Ship Feature")).toBeNull()
    expect(screen.getByText("Deploy Prod")).toBeTruthy()
  })

  it("falls through to free-text when no option is selected", async () => {
    const onSubmit = vi.fn()
    render(<SlashForm tool={tool} disabled={false} onSubmit={onSubmit} onCancel={vi.fn()} />)
    await flush()
    const input = screen.getAllByRole("textbox")[0]
    fireEvent.change(input, { target: { value: "raw-uuid-value" } })
    fireEvent.click(screen.getByRole("button", { name: /^Send$/ }))
    expect(onSubmit).toHaveBeenCalledWith('Please run run_workflow with name_or_id="raw-uuid-value".')
  })
})

describe("Dormant completers (PR 3)", () => {
  // These completers are registered but not yet wired to any SLASH_TOOLS arg —
  // they light up when the #1300-#1304 mutators land. Exercise them directly
  // so we know the mapping to REST endpoints is correct today.

  it("budgets: id as value, email as label, monthly limit as sublabel", async () => {
    const opts = await COMPLETERS.budgets(authFetchMock, "ws-1")
    expect(opts).toEqual([
      { value: "bud-1", label: "alice@example.com", sublabel: "$500/mo" },
      { value: "bud-2", label: "bud-2", sublabel: "$200/mo" },
    ])
  })

  it("agents: id as value, name as label, provider as sublabel", async () => {
    const opts = await COMPLETERS.agents(authFetchMock, "ws-1")
    expect(opts).toEqual([
      { value: "agt-1", label: "prod-cli", sublabel: "provider: anthropic" },
    ])
  })

  it("agents: returns empty when no workspaceId", async () => {
    expect(await COMPLETERS.agents(authFetchMock, null)).toEqual([])
  })

  it("marketplace_packs: slug as value, name as label, description as sublabel", async () => {
    const opts = await COMPLETERS.marketplace_packs(authFetchMock, "ws-1")
    expect(opts).toEqual([
      { value: "sr-11-7", label: "SR 11-7", sublabel: "Federal model risk" },
    ])
  })
})
