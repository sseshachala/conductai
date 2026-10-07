import { GuardReferenceSections } from "./GuardReferenceSections"
import { GuardSavingsSections } from "./GuardSavingsSections"
import { GuardSetupSections } from "./GuardSetupSections"

export function TabGuard() {
  return (
    <div className="space-y-16">
      <GuardSetupSections />
      <GuardSavingsSections />
      <GuardReferenceSections />
    </div>
  )
}
