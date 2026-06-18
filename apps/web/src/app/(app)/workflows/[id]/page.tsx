import AppShell from "@/components/AppShell"
import CanvasEditor from "@/components/canvas/CanvasEditor"
import AgentTabs from "@/components/canvas/AgentTabs"

export default async function WorkflowPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  return (
    <AppShell noPadding>
      <div className="flex flex-col flex-1 min-h-0">
        <AgentTabs workflowId={id} />
        <div className="flex-1 min-h-0">
          <CanvasEditor workflowId={id} />
        </div>
      </div>
    </AppShell>
  )
}
