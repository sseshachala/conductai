import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { WorkspaceProvider, useWorkspace } from './WorkspaceContext'

const auth = vi.hoisted(() => ({
  isLoaded: false, isSignedIn: false, sessionId: 'session-a',
  getToken: vi.fn(), status: 'pending',
}))
vi.mock('@clerk/nextjs', () => ({
  useAuth: () => auth,
  useSession: () => ({ session: { status: auth.status } }),
}))

function Probe() {
  const { activeWorkspace, loading, error } = useWorkspace()
  return <div>{loading ? 'loading' : error || activeWorkspace?.id || 'empty'}</div>
}
function tree() { return <WorkspaceProvider clerkEnabled><Probe /></WorkspaceProvider> }
beforeEach(() => {
  Object.assign(auth, { isLoaded: false, isSignedIn: false, sessionId: 'session-a', status: 'pending' })
  auth.getToken.mockReset().mockResolvedValue('test-token')
  document.cookie = 'delegator_project_id=stale; path=/'
})
afterEach(() => { cleanup(); vi.unstubAllGlobals() })

it('waits for an active Clerk session and validates the saved workspace', async () => {
  const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify([{ id: 'allowed', name: 'Allowed' }])))
  vi.stubGlobal('fetch', fetcher)
  const view = render(tree())
  expect(screen.getByText('loading')).toBeInTheDocument()
  expect(fetcher).not.toHaveBeenCalled()
  Object.assign(auth, { isLoaded: true, isSignedIn: true })
  view.rerender(tree())
  expect(fetcher).not.toHaveBeenCalled()
  auth.status = 'active'
  view.rerender(tree())
  expect(await screen.findByText('allowed')).toBeInTheDocument()
  expect(fetcher.mock.calls[0][1].headers.has('X-Workspace-ID')).toBe(false)
})

it('recovers from the first projects 401 without a page refresh', async () => {
  Object.assign(auth, { isLoaded: true, isSignedIn: true, status: 'active' })
  const fetcher = vi.fn().mockResolvedValueOnce(new Response('', { status: 401 }))
    .mockResolvedValueOnce(new Response(JSON.stringify([{ id: 'allowed', name: 'Allowed' }])))
  vi.stubGlobal('fetch', fetcher)
  render(tree())
  expect(await screen.findByText('allowed')).toBeInTheDocument()
  expect(fetcher).toHaveBeenCalledTimes(2)
})

it('does not fall back to a saved workspace on a persistent denial', async () => {
  Object.assign(auth, { isLoaded: true, isSignedIn: true, status: 'active' })
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('', { status: 403 })))
  render(tree())
  expect(await screen.findByText('Failed to load workspaces (403)')).toBeInTheDocument()
  expect(screen.queryByText('stale')).not.toBeInTheDocument()
})

it('discards an old session response after account switching', async () => {
  Object.assign(auth, { isLoaded: true, isSignedIn: true, status: 'active' })
  let resolveOld!: (response: Response) => void
  const old = new Promise<Response>(resolve => { resolveOld = resolve })
  const fetcher = vi.fn().mockReturnValueOnce(old)
    .mockResolvedValueOnce(new Response(JSON.stringify([{ id: 'new-workspace', name: 'New' }])))
  vi.stubGlobal('fetch', fetcher)
  const view = render(tree())
  await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(1))
  auth.sessionId = 'session-b'
  view.rerender(tree())
  await screen.findByText('new-workspace')
  resolveOld(new Response(JSON.stringify([{ id: 'old-workspace', name: 'Old' }])))
  await waitFor(() => expect(screen.getByText('new-workspace')).toBeInTheDocument())
  expect(screen.queryByText('old-workspace')).not.toBeInTheDocument()
})
