import { afterEach, describe, expect, it, vi } from 'vitest'
import { sessionFetch } from './sessionFetch'

afterEach(() => vi.unstubAllGlobals())

describe('sessionFetch', () => {
  it('waits for a token instead of sending an anonymous request', async () => {
    const getToken = vi.fn().mockResolvedValueOnce(null).mockResolvedValue('test-token')
    const fetcher = vi.fn().mockResolvedValue(new Response('{}'))
    vi.stubGlobal('fetch', fetcher)
    await sessionFetch('/projects', {}, getToken)
    expect(fetcher).toHaveBeenCalledTimes(1)
    expect(fetcher.mock.calls[0][1].headers.get('Authorization')).toBe('Bearer test-token')
  })

  it('retries one 401 with fresh credentials and preserves request options', async () => {
    const getToken = vi.fn().mockResolvedValueOnce('old').mockResolvedValue('new')
    const fetcher = vi.fn().mockResolvedValueOnce(new Response('', { status: 401 })).mockResolvedValue(new Response('{}'))
    vi.stubGlobal('fetch', fetcher)
    await sessionFetch('/projects', { method: 'POST', body: '{}', headers: new Headers({ 'X-Workspace-ID': 'ws' }) }, getToken)
    expect(fetcher).toHaveBeenCalledTimes(2)
    expect(fetcher.mock.calls[1][1].headers.get('Authorization')).toBe('Bearer new')
    expect(fetcher.mock.calls[1][1].headers.get('X-Workspace-ID')).toBe('ws')
    expect(fetcher.mock.calls[1][1].body).toBe('{}')
  })

  it('does not retry a genuine 403', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response('', { status: 403 }))
    vi.stubGlobal('fetch', fetcher)
    expect((await sessionFetch('/projects', {}, vi.fn().mockResolvedValue('token'))).status).toBe(403)
    expect(fetcher).toHaveBeenCalledTimes(1)
  })

  it('bounds 401 retries even when the token does not change', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response('', { status: 401 }))
    vi.stubGlobal('fetch', fetcher)
    expect((await sessionFetch('/projects', {}, vi.fn().mockResolvedValue('token'))).status).toBe(401)
    expect(fetcher).toHaveBeenCalledTimes(2)
  })

  it('never sends a request when the session remains unavailable', async () => {
    const fetcher = vi.fn()
    const getToken = vi.fn().mockResolvedValue(null)
    vi.stubGlobal('fetch', fetcher)
    await expect(sessionFetch('/projects', {}, getToken)).rejects.toThrow('session is not ready')
    expect(fetcher).not.toHaveBeenCalled()
    expect(getToken).toHaveBeenCalledTimes(4)
  })
})
