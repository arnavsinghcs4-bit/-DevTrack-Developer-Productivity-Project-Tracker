/**
 * Auth state for the whole app: who is logged in, and how to log in/out.
 *
 * The JWT itself lives in localStorage (see services/api.js); this context
 * keeps the current user profile in memory and revalidates it on page load
 * via GET /auth/me, so a stale token (expired past the 120-minute window)
 * cleanly bounces the user to /login instead of rendering a broken shell.
 */

import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { api, getToken, setToken } from '../services/api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true) // initial session check

  useEffect(() => {
    let cancelled = false
    if (!getToken()) {
      setLoading(false)
      return undefined
    }
    api
      .get('/auth/me')
      .then((me) => {
        if (!cancelled) setUser(me)
      })
      .catch(() => {
        // 401: token expired/invalid — api.js already cleared it
        if (!cancelled) setUser(null)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const login = useCallback(async (email, password) => {
    // token: null — never attach a stale token to the login request itself
    const { access_token } = await api.post('/auth/login', { email, password }, { token: null })
    setToken(access_token)
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
    setToken(null)
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
