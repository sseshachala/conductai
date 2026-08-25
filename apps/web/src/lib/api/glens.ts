import { API } from "./client"

/** URL helpers for GLens endpoints.
 *
 * GLens uses authFetch directly (passed as a prop or from useAuthFetch),
 * so we expose URL builders rather than wrapping in json(). Callers
 * construct their own fetch calls with the URL returned here.
 */
export const glensUrl = {
  sessions: () => `${API}/glens/sessions`,
  session: (id: string) => `${API}/glens/sessions/${id}`,
  opener: () => `${API}/glens/opener`,
  chatStream: () => `${API}/glens/chat/stream`,
  policyApply: (path = "/glens/policy/apply") => `${API}${path}`,
}
