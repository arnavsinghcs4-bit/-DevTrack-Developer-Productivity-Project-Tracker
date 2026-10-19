/**
 * Minimal typed-enough API client for the DevTrack backend.
 *
 * Responsibilities kept deliberately in one file (interview talking points):
 * - Single place that knows the base URL (VITE_API_URL, defaults to the
 *   local uvicorn) and where tokens live (localStorage).
 * - Two-token session model: a short-lived JWT access token (~30 min) on
 *   every request, and a long-lived single-use refresh token (7 days) that
 *   mints new pairs via POST /auth/refresh.
 * - SILENT REFRESH: a 401 on an authenticated call triggers exactly one
 *   refresh + retry. Concurrent 401s (multi-request pages) share a single
 *   in-flight refresh — the "refresh stampede" is a real production bug and
 *   one promise reference fixes it.
 * - When refresh itself fails (revoked, reused, expired server-side) the
 *   local session is cleared and a `devtrack:session-expired` event fires
 *   so AuthContext can bounce the router to /login.
 * - Normalizes FastAPI error shapes: 422 details arrive as an array of
 *   {loc, msg}, 401/409 as a plain string, 429 carries Retry-After.
 */

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1'
const ACCESS_TOKEN_KEY = 'devtrack_token'
const REFRESH_TOKEN_KEY = 'devtrack_refresh_token'

export function getToken() {
  return localStorage.getItem(ACCESS_TOKEN_KEY)
}

export function setToken(token) {
  if (token) {
    localStorage.setItem(ACCESS_TOKEN_KEY, token)
  } else {
    localStorage.removeItem(ACCESS_TOKEN_KEY)
  }
}

export function getRefreshToken() {
  return localStorage.getItem(REFRESH_TOKEN_KEY)
}

export function setRefreshToken(token) {
  if (token) {
    localStorage.setItem(REFRESH_TOKEN_KEY, token)
  } else {
    localStorage.removeItem(REFRESH_TOKEN_KEY)
  }
}

/** Persist a full login/refresh response atomically from the caller's view. */
export function storeSession(data) {
  setToken(data.access_token)
  if (data.refresh_token) setRefreshToken(data.refresh_token)
}

export function clearSession() {
  localStorage.removeItem(ACCESS_TOKEN_KEY)
  localStorage.removeItem(REFRESH_TOKEN_KEY)
}

function notifySessionExpired() {
  window.dispatchEvent(new CustomEvent('devtrack:session-expired'))
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

async function request(path, { method = 'GET', body, token, skipAuthRetry = false } = {}) {
  const headers = {}
  if (body !== undefined) headers['Content-Type'] = 'application/json'

  // `token: null` opts out of attaching the stored token (login/register/refresh)
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
    // A 401 on a token-authenticated call usually just means the ~30-min
    // access token went stale. Silently rotate once and retry the original
    // request; if refresh fails the session is truly dead and the caller
    // sees a clean "session expired" error instead of a login redirect mid-form.
    if (res.status === 401 && effectiveToken && !skipAuthRetry) {
      try {
        await refreshSession()
      } catch {
        throw new ApiError(401, 'Your session has expired. Please log in again.')
      }
      return request(path, { method, body, token, skipAuthRetry: true })
    }
    throw new ApiError(res.status, data?.detail ?? 'Request failed', res.headers.get('Retry-After'))
  }
  return data
}

// ---------------------------------------------------------------------------
// Silent refresh (single-flight)
// ---------------------------------------------------------------------------

let refreshPromise = null

/**
 * Exchanges the stored refresh token for a new pair, storing both.
 * Concurrent callers share one in-flight refresh (single-flight): without
 * this, a page firing five parallel requests on an expired token would
 * fire five rotations — and the backend's reuse detection would correctly
 * interpret the second one as THEFT and kill the whole token family,
 * logging the user out for being fast. Rotation-aware clients MUST
 * serialize refreshes.
 */
export function refreshSession() {
  if (!refreshPromise) {
    refreshPromise = performTokenRefresh().finally(() => {
      refreshPromise = null
    })
  }
  return refreshPromise
}

async function performTokenRefresh() {
  const stored = getRefreshToken()
  if (!stored) {
    throw new ApiError(401, 'No refresh token')
  }
  let data
  try {
    // token: null + skipAuthRetry: the refresh call itself must never try
    // to refresh (infinite loop) or ride a dead access token.
    data = await request('/auth/refresh', {
      method: 'POST',
      body: { refresh_token: stored },
      token: null,
      skipAuthRetry: true,
    })
  } catch (err) {
    // Revoked / reused / expired / network — local state dies either way,
    // but only server-confirmed failures notify the app (network errors
    // shouldn't log the user out; the token may still be good).
    if (!(err instanceof ApiError) || err.status !== 0) {
      clearSession()
      notifySessionExpired()
    }
    throw err
  }
  storeSession(data)
  return data
}

export const api = {
  get: (path) => request(path),
  post: (path, body, opts = {}) => request(path, { method: 'POST', body, ...opts }),
  patch: (path, body) => request(path, { method: 'PATCH', body }),
  delete: (path) => request(path, { method: 'DELETE' }),
}
