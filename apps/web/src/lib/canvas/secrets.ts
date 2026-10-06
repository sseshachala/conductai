/** Shared secret detection for anything that copies or displays block config. */

/**
 * Key names whose string values are credentials, tokens or encrypted secrets
 * (e.g. trigger `config.webhook_secret` holds an encrypted blob). Numeric values
 * such as `max_tokens` are kept — only strings are dropped.
 */
export const SECRET_KEY = /secret|token|password|passwd|api[_-]?key|private[_-]?key|authorization|bearer/i

/** Values that are recognisably provider credentials regardless of key name. */
export const SECRET_VALUE = /^(sk-[A-Za-z0-9_-]{16,}|sk-ant-|ghp_|gho_|github_pat_|xox[abposr]-|AKIA[0-9A-Z]{16}|eyJ[A-Za-z0-9_-]{10,}\.)/
