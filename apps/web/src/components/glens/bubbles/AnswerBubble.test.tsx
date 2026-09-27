import { cleanup, render, screen } from "@testing-library/react"
import { afterEach, expect, it } from "vitest"
import { AnswerBubble } from "./AnswerBubble"

afterEach(cleanup)

it("lets evidence answers use the full conversation width", () => {
  render(<AnswerBubble text={"## Gateway spend\n\nRecorded evidence"} />)
  const bubble = screen.getByRole("heading", { name: "Gateway spend" }).closest("p")
  expect(bubble).toBeNull()
  const wrapper = screen.getByRole("heading").parentElement?.parentElement?.parentElement
  expect(wrapper).toHaveStyle({ width: "100%", maxWidth: "100%", minWidth: "0" })
})
