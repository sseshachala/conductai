import AppShell from "@/components/AppShell"
import CanvasEditor from "@/components/canvas/CanvasEditor"

interface Props {
  params: { id: string }
}

export default function WorkflowPage({ params }: Props) {
  return (
    <AppShell noPadding>
      <CanvasEditor workflowId={params.id} />
    </AppShell>
  )
}
