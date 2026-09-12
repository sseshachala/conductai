export type GetSessionToken = (options?: { skipCache?: boolean }) => Promise<string | null>

/** Wait for Clerk's initial token without sending anonymous API requests. */
export async function sessionFetch(
  url: string,
  options: RequestInit,
  getToken: GetSessionToken | null,
): Promise<Response> {
  if (!getToken) return fetch(url, options)
  let token = await getToken()
  for (let attempt = 0; !token && attempt < 3; attempt++) {
    await new Promise(resolve => setTimeout(resolve, 250))
    token = await getToken({ skipCache: true })
  }
  if (!token) throw new Error('Your session is not ready. Please sign in again.')
  const send = (bearer: string) => {
    const headers = new Headers(options.headers)
    headers.set('Authorization', `Bearer ${bearer}`)
    return fetch(url, { ...options, headers })
  }
  const response = await send(token)
  if (response.status !== 401) return response
  const fresh = await getToken({ skipCache: true })
  return fresh ? send(fresh) : response
}
