/**
 * Auth state for the whole app: who is logged in, and how to log in/out.
 *
 * Session model (Branch E, two-token flow):
 * - The short-lived access token (~30 min) and the rotating refresh token
 *   (7 days, single-use) live in localStorage, written only by
 *   services/api.js. When the access token 401s, api.js silently refreshes
 *   once and retries — users never see token mechanics.
 * - On page load the session is RESTORED from the refresh token alone
 *   (access token may be long dead after a closed tab), so users return to
 *   the dashboard instead of a login wall.
 * - Server-side session death (reuse detection, logout elsewhere, expiry)
 *   surfaces as the devtrack:session-expired event → user=null → the
 *   router's ProtectedRoute redirects to /login.
 */

import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import {
  api,
  clearSession,
  getRefreshToken,
  getToken,
  refreshSession,
  storeSession,
} from '../services/api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true) // initial session check

  useEffect(() => {
    let cancelled = false

    async function restoreSession() {
      try {
        if (!getToken()) {
          // No access token, but a stored refresh token can mint a fresh
          // pair — this is the "close the laptop, come back tomorrow" path
          if (!getRefreshToken()) return
          await refreshSession()
        }
        const me = await api.get('/auth/me')
        if (!cancelled) setUser(me)
      } catch {
        // Unrestorable session (expired/revoked/rejected): stay logged out
        if (!cancelled) setUser(null)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    restoreSession()

    // Fired by api.js when a silent refresh is rejected server-side
    const onSessionExpired = () => setUser(null)
    window.addEventListener('devtrack:session-expired', onSessionExpired)
    return () => {
      cancelled = true
      window.removeEventListener('devtrack:session-expired', onSessionExpired)
    }
  }, [])

  const login = useCallback(async (email, password) => {
    // token: null — never attach a stale token to the login request itself
    const data = await api.post('/auth/login', { email, password }, { token: null })
    storeSession(data)
    const me = await api.get('/auth/me')
    setUser(me)
    return me
  }, [])

  const register = useCallback(
    async (fullName, email, password) => {
      await api.post('/auth/register', { email, password, full_name: fullName }, { token: null })
      // Auto-login after registration: one less screen, and it proves the
      // credentials work before the user sees the dashboard.
      return login(email, password)
    },
    [login],
  )

  const logout = useCallback(() => {
    const refreshToken = getRefreshToken()
    // Best-effort server-side revocation — this is what makes logout REAL
    // for a thief who already copied the token (a pure client-side "logout"
    // only forgets; the JWT stays valid until its ~30-min expiry).
    // skipAuthRetry: no refresh dance for a session we're abandoning, and
    // local state is cleared regardless of the outcome.
    if (refreshToken) {
      api
        .post('/auth/logout', { refresh_token: refreshToken }, { skipAuthRetry: true })
        .catch(() => {
          // Backend down or access token already dead → nothing to revoke
          // that the refresh-token TTL won't handle on its own
        })
    }
    clearSession()
    setUser(null)
  }, [])

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  return useContext(AuthContext)
}
