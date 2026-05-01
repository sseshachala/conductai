import CanvasEditor from "@/components/canvas/CanvasEditor"

interface Props {
  params: { id: string }
}

export default function WorkflowPage({ params }: Props) {
  return <CanvasEditor workflowId={params.id} />
}
