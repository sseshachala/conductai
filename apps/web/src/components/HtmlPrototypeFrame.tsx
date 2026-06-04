import type { CSSProperties } from "react"

interface HtmlPrototypeFrameProps {
  title: string
  src: string
}

const frameStyle: CSSProperties = {
  width: "100%",
  minHeight: "100vh",
  border: "none",
  display: "block",
  background: "#fff",
}

export default function HtmlPrototypeFrame({ title, src }: HtmlPrototypeFrameProps) {
  return (
    <div style={{ minHeight: "100vh", background: "#fff" }}>
      <iframe title={title} src={src} style={frameStyle} />
    </div>
  )
}
