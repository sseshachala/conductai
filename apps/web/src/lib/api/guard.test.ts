/**
 * Contract tests for the structured-error consumer added in PR 6.
 *
 * Publish + save endpoints for Gateway Profile v2 return errors as
 * { detail: { summary, errors: [...] } }. Without a parser on the
 * frontend, `_mutateJson` used to `throw new Error(rawJsonText)` and
 * the toast showed users a raw JSON blob. `_formatGatewayError` now
 * turns that into either a nicely-formatted string OR a
 * `GatewayValidationError` that carries the structured data for the
 * editor to highlight the offending target row.
 */
import { describe, expect, it } from 'vitest'
import { GatewayValidationError } from './guard'

// Re-import the internal helper via a controlled surface. We test the
// public class here; the internal `_formatGatewayError` is exercised
// by every mutation call so we assert its behavior via a
// module-boundary contract test: a `_mutateJson` invocation against a
// Response whose body matches the structured shape must throw a
// `GatewayValidationError`.

async function _invokeParserWith(bodyText: string, status = 400) {
  // We can't import `_mutateJson` directly (not exported). Reach the
  // parser path via `guard.gatewayProfilesV2.publish`, which is the
  // primary carrier of validation errors — same code path any editor
  // save/publish would hit.
  const { guard } = await import('./guard')
  const fetcher: any = async () =>
    new Response(bodyText, {
      status,
      headers: { 'Content-Type': 'application/json' },
    })
  try {
    await guard.gatewayProfilesV2.publish(fetcher, 'ws', 'profile-1')
    throw new Error('expected throw; got resolved value')
  } catch (err) {
    return err
  }
}

describe('_formatGatewayError (via _mutateJson)', () => {
  it('parses a structured validation-error body into GatewayValidationError', async () => {
    const err = await _invokeParserWith(
      JSON.stringify({
        detail: {
          summary: 'schema invalid',
          errors: [
            {
              path: 'targets.2.credential_ref',
              message: 'invalid vault:// reference',
              target_index: 2,
              type: 'value_error',
            },
          ],
        },
      }),
    )
    expect(err).toBeInstanceOf(GatewayValidationError)
    const gve = err as GatewayValidationError
    expect(gve.summary).toBe('schema invalid')
    expect(gve.errors.length).toBe(1)
    expect(gve.errors[0].target_index).toBe(2)
    // Human-readable message the toast will render.
    expect(gve.message).toContain('Check the profile fields.')
    expect(gve.message).toContain('Target 3 - Credential')
    expect(gve.message).toContain('Choose a credential vault and handle.')
  })

  it('collapses more than three errors with a `+N more` suffix', async () => {
    const errors = Array.from({ length: 5 }, (_, i) => ({
      path: `targets.${i}.credential_ref`,
      message: `bad ${i}`,
      target_index: i,
      type: 'value_error',
    }))
    const err = await _invokeParserWith(
      JSON.stringify({ detail: { summary: 'schema invalid', errors } }),
    )
    expect(err).toBeInstanceOf(GatewayValidationError)
    expect((err as Error).message).toContain('+2 more')
  })

  it('hides raw schema exceptions from older-shape backends', async () => {
    const err = await _invokeParserWith(
      JSON.stringify({ detail: 'schema invalid: legacy string' }),
    )
    expect(err).not.toBeInstanceOf(GatewayValidationError)
    expect((err as Error).message).toBe('Check the profile fields and try again.')
  })

  it('falls back to raw text when the body is not JSON', async () => {
    const err = await _invokeParserWith('gateway timeout', 504)
    expect((err as Error).message).toBe('gateway timeout')
  })

  it('capability_mismatch rides the same shape as schema errors', async () => {
    const err = await _invokeParserWith(
      JSON.stringify({
        detail: {
          summary: 'capability check failed',
          errors: [
            {
              path: 'targets',
              message: "target 'via-openrouter' cannot serve …",
              target_index: null,
              type: 'capability_mismatch',
            },
          ],
        },
      }),
    )
    expect(err).toBeInstanceOf(GatewayValidationError)
    const gve = err as GatewayValidationError
    expect(gve.errors[0].type).toBe('capability_mismatch')
    // No target index → the "where" prefix falls back to the path.
    expect(gve.message).toContain('Targets')
    expect(gve.message).toContain("cannot serve")
  })

  it('names a missing alias without exposing schema internals', async () => {
    const err = await _invokeParserWith(JSON.stringify({ detail: {
      summary: 'schema invalid', errors: [{ path: 'model_alias', target_index: null,
        type: 'string_too_short', message: 'String should have at least 1 character' }],
    } }))
    expect((err as Error).message).toBe('Check the profile fields. Alias: Enter an alias.')
  })

  it('preserves ordinary server errors', async () => {
    const err = await _invokeParserWith(JSON.stringify({ detail: 'Published profile is locked.' }), 409)
    expect((err as Error).message).toBe('Published profile is locked.')
  })
})
