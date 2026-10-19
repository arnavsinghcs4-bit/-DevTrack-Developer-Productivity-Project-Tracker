/**
 * Minimal typed-enough API client for the DevTrack backend.
 *
 * Responsibilities kept deliberately in one file (interview talking points):
 * - Single place that knows the base URL (VITE_API_URL, defaults to the
 *   local uvicorn) and where the JWT lives (localStorage).
 * - Attaches the Bearer token automatically; a 401 on an authenticated call
 *   means the token is stale -> clear it so the router sends the user to
 *   /login instead of silently failing forever.
 * - Normalizes FastAPI error shapes: 422 details arrive as an array of
 *   {loc, msg}, 401/409 as a plain string, 429 carries Retry-After.
 */

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1'
const TOKEN_KEY = 'devtrack_token'

export function getToken() {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token) {
  if (token) {
    localStorage.setItem(TOKEN_KEY, token)
  } else {
    localStorage.removeItem(TOKEN_KEY)
  }
}

export class ApiError extends Error {
  constructor(status, detail, retryAfter) {
    super(typeof detail === 'string' ? detail : 'Request failed')
    this.name = 'ApiError'
    this.status = status // 0 = network failure (API unreachable)
    this.detail = detail
    this.retryAfter = retryAfter
  }
}

/** Renders any thrown error into a single user-facing message string. */
export function formatApiError(err) {
  if (!(err instanceof ApiError)) return 'Something went wrong'
  if (err.status === 0) return err.detail // network error
  if (typeof err.detail === 'string') {
    if (err.status === 429 && err.retryAfter) {
      return `${err.detail} Retry in ${err.retryAfter}s.`
    }
    return err.detail
  }
  // FastAPI 422 validation shape: [{ loc, msg }, ...]
  if (Array.isArray(err.detail)) {
    return err.detail
      .map((issue) => (issue.loc ? `${issue.loc.join('.')}: ${issue.msg}` : issue.msg))
      .join(' · ')
  }
  return 'Request failed'
}

async function request(path, { method = 'GET', body, token } = {}) {
  const headers = {}
  if (body !== undefined) headers['Content-Type'] = 'application/json'

  // `token: null` opts out of attaching the stored token (login/register)
  const effectiveToken = token === null ? null : (token ?? getToken())
  if (effectiveToken) headers['Authorization'] = `Bearer ${effectiveToken}`

  let res
  try {
    res = await fetch(`${API_BASE}${path}`, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    })
  } catch {
    throw new ApiError(0, 'Cannot reach the API. Is the backend running on port 8000?')
  }

  if (res.status === 204) return null

  let data = null
  try {
    data = await res.json()
  } catch {
    // empty or non-JSON body
  }

  if (!res.ok) {
    // A 401 on a token-authenticated call = stale/revoked token: drop it so
    // the next ProtectedRoute check redirects to /login.
    if (res.status === 401 && effectiveToken) setToken(null)
    throw new ApiError(res.status, data?.detail ?? 'Request failed', res.headers.get('Retry-After'))
  }
  return data
}

export const api = {
  get: (path) => request(path),
  post: (path, body, opts = {}) => request(path, { method: 'POST', body, ...opts }),
  patch: (path, body) => request(path, { method: 'PATCH', body }),
  delete: (path) => request(path, { method: 'DELETE' }),
}
