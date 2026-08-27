import { describe, it, expect } from "vitest"
import { renderHook } from "@testing-library/react"
import type { ReactNode } from "react"
import { useGuardRole } from "../useGuardRole"
import { GuardRoleAdminProvider } from "@/lib/GuardRoleContext"

describe("useGuardRole (hook wrapper)", () => {
  it("returns null role, viewer permissions, and loading=true when no provider is mounted", () => {
    const { result } = renderHook(() => useGuardRole())
    expect(result.current.role).toBeNull()
    expect(result.current.permissions.canEditPolicies).toBe(false)
    expect(result.current.loading).toBe(true)
  })

  it("returns admin role under GuardRoleAdminProvider", () => {
    const wrapper = ({ children }: { children: ReactNode }) => (
      <GuardRoleAdminProvider>{children}</GuardRoleAdminProvider>
    )
    const { result } = renderHook(() => useGuardRole(), { wrapper })
    expect(result.current.role).toBe("admin")
  })

  it("exposes the full ADMIN_PERMISSIONS surface under admin provider", () => {
    const wrapper = ({ children }: { children: ReactNode }) => (
      <GuardRoleAdminProvider>{children}</GuardRoleAdminProvider>
    )
    const { result } = renderHook(() => useGuardRole(), { wrapper })
    expect(result.current.permissions.canEditPolicies).toBe(true)
    expect(result.current.permissions.canEditSettings).toBe(true)
    expect(result.current.permissions.canEditBudgets).toBe(true)
    expect(result.current.permissions.canViewAllActivity).toBe(true)
    expect(result.current.permissions.canViewAllSpend).toBe(true)
    expect(result.current.permissions.canExportActivity).toBe(true)
  })

  it("reports loading=false under GuardRoleAdminProvider", () => {
    const wrapper = ({ children }: { children: ReactNode }) => (
      <GuardRoleAdminProvider>{children}</GuardRoleAdminProvider>
    )
    const { result } = renderHook(() => useGuardRole(), { wrapper })
    expect(result.current.loading).toBe(false)
  })

  it("ignores teamId and workspaceId arguments (delegated to context)", () => {
    const wrapper = ({ children }: { children: ReactNode }) => (
      <GuardRoleAdminProvider>{children}</GuardRoleAdminProvider>
    )
    const { result: withArgs } = renderHook(
      () => useGuardRole("team-abc", "ws-xyz"),
      { wrapper },
    )
    const { result: withoutArgs } = renderHook(() => useGuardRole(), { wrapper })
    expect(withArgs.current.role).toBe(withoutArgs.current.role)
    expect(withArgs.current.permissions).toEqual(withoutArgs.current.permissions)
    expect(withArgs.current.loading).toBe(withoutArgs.current.loading)
  })
})
