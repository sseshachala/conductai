type ProfileFields = {
  name?: unknown
  model_alias?: unknown
  timeout_seconds?: unknown
  max_attempts?: unknown
  targets?: unknown
}

export function validateGatewayProfileFields(profile: ProfileFields) {
  const errors: Partial<Record<keyof ProfileFields, string>> = {}
  for (const [field, label] of [["name", "name"], ["model_alias", "alias"]] as const) {
    const value = profile[field]
    if (typeof value !== "string" || !value.trim()) {
      errors[field] = `Enter ${label === "alias" ? "an" : "a"} ${label}.`
    } else if (value.trim().length > 128) {
      errors[field] = `Use no more than 128 characters for the ${label}.`
    }
  }
  // Match the API schema. Missing numeric values use the schema defaults.
  const timeout = profile.timeout_seconds === undefined ? 60 : profile.timeout_seconds
  if (typeof timeout !== "number" || !Number.isInteger(timeout) || timeout < 1 || timeout > 600) {
    errors.timeout_seconds = "Enter a whole number from 1 to 600 seconds."
  }
  const attempts = profile.max_attempts === undefined ? 1 : profile.max_attempts
  if (typeof attempts !== "number" || !Number.isInteger(attempts) || attempts < 1 || attempts > 5) {
    errors.max_attempts = "Enter a whole number from 1 to 5."
  }
  if (!Array.isArray(profile.targets) || profile.targets.length === 0) {
    errors.targets = "Add at least one target."
  } else if (profile.targets.length > 8) {
    errors.targets = "Use no more than 8 targets."
  }
  return errors
}
