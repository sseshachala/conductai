import AppShell from "@/components/AppShell"
import CanvasEditor from "@/components/canvas/CanvasEditor"

interface Props {
  params: { id: string }
}

export default function WorkflowPage({ params }: Props) {
  return (
    <AppShell noPadding>
      <div className="flex-1 min-h-0">
        <CanvasEditor workflowId={params.id} />
      </div>
    </AppShell>
  )
}
