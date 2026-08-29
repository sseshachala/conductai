import { describe, it, expect } from "vitest"
import { render } from "@testing-library/react"
import { screen } from "@testing-library/dom"
import {
  permissionsFromList,
  VIEWER_PERMISSIONS,
  ADMIN_PERMISSIONS,
  GuardRoleAdminProvider,
  useGuardRoleContext,
} from "../GuardRoleContext"

describe("permissionsFromList", () => {
  it("returns all-false for empty list", () => {
    expect(permissionsFromList([])).toEqual(VIEWER_PERMISSIONS)
  })

  it("maps guard.policies.edit to canEditPolicies", () => {
    const p = permissionsFromList(["guard.policies.edit"])
    expect(p.canEditPolicies).toBe(true)
    expect(p.canEditSettings).toBe(false)
  })

  it("maps guard.settings.edit to canEditSettings", () => {
    expect(permissionsFromList(["guard.settings.edit"]).canEditSettings).toBe(true)
  })

  it("maps guard.spend.budgets.edit to canEditBudgets", () => {
    expect(permissionsFromList(["guard.spend.budgets.edit"]).canEditBudgets).toBe(true)
  })

  it("maps guard.activity.view_all to canViewAllActivity", () => {
    expect(permissionsFromList(["guard.activity.view_all"]).canViewAllActivity).toBe(true)
  })

  it("maps guard.spend.view_all to canViewAllSpend", () => {
    expect(permissionsFromList(["guard.spend.view_all"]).canViewAllSpend).toBe(true)
  })

  it("maps guard.spend.view_own to canViewOwnSpend", () => {
    expect(permissionsFromList(["guard.spend.view_own"]).canViewOwnSpend).toBe(true)
  })

  it("maps guard.activity.export to canExportActivity", () => {
    expect(permissionsFromList(["guard.activity.export"]).canExportActivity).toBe(true)
  })

  it("ignores unknown permission strings", () => {
    const p = permissionsFromList(["guard.does.not.exist", "totally.made.up"])
    expect(p).toEqual(VIEWER_PERMISSIONS)
  })

  it("granting multiple permissions composes flags additively", () => {
    const p = permissionsFromList([
      "guard.policies.edit",
      "guard.activity.view_all",
      "guard.spend.view_own",
    ])
    expect(p.canEditPolicies).toBe(true)
    expect(p.canViewAllActivity).toBe(true)
    expect(p.canViewOwnSpend).toBe(true)
    expect(p.canEditSettings).toBe(false)
    expect(p.canEditBudgets).toBe(false)
  })

  it("full admin perm set matches ADMIN_PERMISSIONS", () => {
    const all = permissionsFromList([
      "guard.policies.edit",
      "guard.settings.edit",
      "guard.spend.budgets.edit",
      "guard.activity.view_all",
      "guard.spend.view_all",
      "guard.spend.view_own",
      "guard.activity.export",
    ])
    expect(all).toEqual(ADMIN_PERMISSIONS)
  })

  it("duplicate permissions do not corrupt output", () => {
    const p = permissionsFromList(["guard.policies.edit", "guard.policies.edit"])
    expect(p.canEditPolicies).toBe(true)
  })
})

describe("VIEWER_PERMISSIONS constant", () => {
  it("has every flag set to false", () => {
    for (const key of Object.keys(VIEWER_PERMISSIONS) as (keyof typeof VIEWER_PERMISSIONS)[]) {
      expect(VIEWER_PERMISSIONS[key]).toBe(false)
    }
  })
})

describe("ADMIN_PERMISSIONS constant", () => {
  it("has every flag set to true", () => {
    for (const key of Object.keys(ADMIN_PERMISSIONS) as (keyof typeof ADMIN_PERMISSIONS)[]) {
      expect(ADMIN_PERMISSIONS[key]).toBe(true)
    }
  })

  it("has the same keys as VIEWER_PERMISSIONS", () => {
    expect(Object.keys(ADMIN_PERMISSIONS).sort()).toEqual(
      Object.keys(VIEWER_PERMISSIONS).sort(),
    )
  })
})

function RoleProbe() {
  const { role, permissions, loading } = useGuardRoleContext()
  return (
    <div>
      <span data-testid="role">{role ?? "null"}</span>
      <span data-testid="loading">{loading ? "yes" : "no"}</span>
      <span data-testid="edit-policies">{permissions.canEditPolicies ? "yes" : "no"}</span>
      <span data-testid="view-all-activity">{permissions.canViewAllActivity ? "yes" : "no"}</span>
    </div>
  )
}

describe("GuardRoleAdminProvider", () => {
  it("exposes role=admin", () => {
    render(
      <GuardRoleAdminProvider>
        <RoleProbe />
      </GuardRoleAdminProvider>,
    )
    expect(screen.getByTestId("role").textContent).toBe("admin")
  })

  it("exposes loading=false", () => {
    render(
      <GuardRoleAdminProvider>
        <RoleProbe />
      </GuardRoleAdminProvider>,
    )
    expect(screen.getByTestId("loading").textContent).toBe("no")
  })

  it("grants canEditPolicies", () => {
    render(
      <GuardRoleAdminProvider>
        <RoleProbe />
      </GuardRoleAdminProvider>,
    )
    expect(screen.getByTestId("edit-policies").textContent).toBe("yes")
  })

  it("grants canViewAllActivity", () => {
    render(
      <GuardRoleAdminProvider>
        <RoleProbe />
      </GuardRoleAdminProvider>,
    )
    expect(screen.getByTestId("view-all-activity").textContent).toBe("yes")
  })
})

describe("useGuardRoleContext default (no provider)", () => {
  it("defaults role to null when no provider is mounted", () => {
    render(<RoleProbe />)
    expect(screen.getByTestId("role").textContent).toBe("null")
  })

  it("defaults permissions to VIEWER_PERMISSIONS when no provider is mounted", () => {
    render(<RoleProbe />)
    expect(screen.getByTestId("edit-policies").textContent).toBe("no")
    expect(screen.getByTestId("view-all-activity").textContent).toBe("no")
  })
})
