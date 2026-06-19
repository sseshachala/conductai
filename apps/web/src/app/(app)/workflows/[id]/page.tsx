import AppShell from "@/components/AppShell"
import CanvasEditor from "@/components/canvas/CanvasEditor"

export default async function WorkflowPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  return (
    <AppShell noPadding>
      <CanvasEditor workflowId={id} />
    </AppShell>
  )
}
