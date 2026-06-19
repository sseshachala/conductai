import { Metadata } from "next"
import PlaybookDetailClient from "./PlaybookDetailClient"

export async function generateMetadata({
  params,
}: {
  params: { slug: string }
}): Promise<Metadata> {
  return {
    title: `${params.slug.replace(/-/g, " ")} — Conduct Playbooks`,
    description: `Install the ${params.slug} playbook for your team.`,
  }
}

export default function PlaybookPage() {
  return <PlaybookDetailClient />
}
