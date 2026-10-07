"use client"

import { FaqSection, FooterCTASection } from "./_sections/faqFooter"
import { HooksSection, QuickstartSection, WhatItCoversSection, WorksWithSection } from "./_sections/features"
import { DiagnosticHero, PageHook, TwoToolSection } from "./_sections/hero"
import { GuardInsightsCallout, UseCasesSection } from "./_sections/useCases"
import { WhatsNewSection } from "./_sections/whatsNew"

export default function ConductCliPage() {
  return (
    <>
      <PageHook />
      <TwoToolSection />
      <DiagnosticHero />
      <WhatItCoversSection />
      <HooksSection />
      <QuickstartSection />
      <WorksWithSection />
      <GuardInsightsCallout />
      <UseCasesSection />
      <WhatsNewSection />
      <FaqSection />
      <FooterCTASection />
    </>
  )
}
