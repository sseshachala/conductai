import { expect, it } from "vitest"
import { validateGatewayProfileFields } from "./gatewayProfileValidation"

const valid = { name: "Case 3", model_alias: "coding", targets: [{}] }

it("accepts schema defaults and boundary values", () => {
  expect(validateGatewayProfileFields(valid)).toEqual({})
  expect(validateGatewayProfileFields({ ...valid, timeout_seconds: 600, max_attempts: 5,
    name: "a".repeat(128), model_alias: "a".repeat(128), targets: Array(8).fill({}) })).toEqual({})
})

it.each([
  ["model_alias", " "], ["model_alias", "a".repeat(129)],
  ["name", ""], ["name", "a".repeat(129)],
  ["timeout_seconds", null], ["timeout_seconds", 0],
  ["max_attempts", null], ["max_attempts", 1.5],
  ["targets", []], ["targets", Array(9).fill({})],
])("reports invalid %s values", (field, value) => {
  expect(validateGatewayProfileFields({ ...valid, [field]: value })).toHaveProperty(field)
})
