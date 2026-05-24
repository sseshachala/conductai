import AppShell from "@/components/AppShell"
import AgentTabs from "@/components/canvas/AgentTabs"
import CanvasEditor from "@/components/canvas/CanvasEditor"

interface Props {
  params: { id: string }
}

export default function WorkflowPage({ params }: Props) {
  return (
    <AppShell noPadding>
      <AgentTabs workflowId={params.id} />
      <div className="flex-1 min-h-0">
        <CanvasEditor workflowId={params.id} />
      </div>
    </AppShell>
  )
}
