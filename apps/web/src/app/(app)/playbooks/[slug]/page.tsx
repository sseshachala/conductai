import { Metadata } from "next"
import PlaybookDetailClient from "./PlaybookDetailClient"

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>
}): Promise<Metadata> {
  const { slug } = await params
  return {
    title: `${slug.replace(/-/g, " ")} — Conduct Playbooks`,
    description: `Install the ${slug} playbook for your team.`,
  }
}

export default function PlaybookPage() {
  return <PlaybookDetailClient />
}
