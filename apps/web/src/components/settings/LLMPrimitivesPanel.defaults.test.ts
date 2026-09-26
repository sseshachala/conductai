import { expect, it } from "vitest"
import { defaultsFor } from "./LLMPrimitivesPanel"

it.each(["together", "perplexity"])("does not seed OpenAI models for %s", (provider) => {
  expect(defaultsFor(provider)).toEqual({})
})

it("preserves provider-specific Claude and GPT defaults", () => {
  expect(defaultsFor("openai").balanced).toMatch(/^gpt-/)
  expect(defaultsFor("anthropic").balanced).toMatch(/^claude-/)
})
