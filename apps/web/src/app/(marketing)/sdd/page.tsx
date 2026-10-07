"use client"

import { ComparisonSection, EnforcementSection, FooterCTASection, SyncSection, TeamOSBridge, WhyNotChatGPTSection } from "./_sections/closing"
import { HeroSection, PrincipleSection, ProblemSection, WorkflowSection } from "./_sections/intro"
import { SpecGenSection } from "./_sections/specGen"

export default function SDDPage() {
  return (
    <>
      <HeroSection />
      <ProblemSection />
      <PrincipleSection />
      <WorkflowSection />
      <SpecGenSection />
      <EnforcementSection />
      <SyncSection />
      <WhyNotChatGPTSection />
      <ComparisonSection />
      <TeamOSBridge />
      <FooterCTASection />
    </>
  )
}
