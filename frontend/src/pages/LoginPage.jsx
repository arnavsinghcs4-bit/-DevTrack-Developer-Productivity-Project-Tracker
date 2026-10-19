/**
 * Login page: email + password -> token pair -> back to wherever the user was
 * headed. Server-side rate limiting (10/min per IP) surfaces here as a 429
 * with a friendly retry countdown, handled generically by formatApiError.
 */

import { useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { formatApiError } from '../services/api'
import { Button, Field, inputClass, Icon } from '../components/ui'

export default function LoginPage() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  const from = location.state?.from || '/'

  async function handleSubmit(event) {
    event.preventDefault()
    setError(null)
    setBusy(true)
    try {
      await login(email, password)
      navigate(from, { replace: true })
    } catch (err) {
      setError(formatApiError(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="mx-auto max-w-md">
      <div className="mb-8 text-center">
        <div className="mx-auto mb-4 grid h-12 w-12 place-items-center rounded-2xl bg-brand text-white shadow-brand">
          <Icon.Trend size={22} />
        </div>
        <h1 className="text-2xl font-bold tracking-[-0.04em]">Welcome back</h1>
        <p className="mt-2 text-sm text-muted">
          Log in to keep your streak honest.
        </p>
      </div>

      <div className="card p-6 sm:p-7">
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <Field label="Email">
            <input
              type="email"
              className={inputClass}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              required
              autoComplete="email"
              autoFocus
            />
          </Field>

          <Field label="Password">
            <input
              type="password"
              className={inputClass}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              required
              autoComplete="current-password"
            />
          </Field>

          {error && (
            <p className="text-sm text-danger" role="alert">
              {error}
            </p>
          )}

          <Button type="submit" size="lg" disabled={busy} className="mt-1 w-full">
            {busy ? 'Logging in…' : 'Log in'}
          </Button>
        </form>
      </div>

      <p className="mt-6 text-center text-sm text-muted">
        No account yet?{' '}
        <Link to="/register" className="font-semibold text-brand hover:underline">
          Create one
        </Link>
      </p>
    </div>
  )
}
