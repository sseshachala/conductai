import AppShell from "@/components/AppShell"
import AgentTabs from "@/components/canvas/AgentTabs"

export default async function WorkflowLayout({
  children,
  params,
}: {
  children: React.ReactNode
  params: Promise<{ id: string }>
}) {
  const { id } = await params
  return (
    <AppShell noPadding>
      <div className="flex flex-col flex-1 min-h-0">
        <AgentTabs workflowId={id} />
        <div className="flex-1 min-h-0 overflow-auto">
          {children}
        </div>
      </div>
    </AppShell>
  )
}
