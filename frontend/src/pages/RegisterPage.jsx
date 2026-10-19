/**
 * Registration page. Client-side checks (password match, 8+ chars) mirror the
 * server's rules so the common mistakes never cost a round trip; anything the
 * server still rejects (e.g. >72 UTF-8 bytes) is rendered from its 422 detail.
 * On success the context auto-logs-in and we land on the dashboard.
 */

import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { formatApiError } from '../services/api'
import { Button, Field, inputClass, Icon } from '../components/ui'

export default function RegisterPage() {
  const { register } = useAuth()
  const navigate = useNavigate()
  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  async function handleSubmit(event) {
    event.preventDefault()
    setError(null)

    if (password !== confirm) {
      setError('Passwords do not match.')
      return
    }
    if (password.length < 8) {
      setError('Password must be at least 8 characters.')
      return
    }

    setBusy(true)
    try {
      await register(fullName, email, password)
      navigate('/', { replace: true })
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
          <Icon.Plus size={22} />
        </div>
        <h1 className="text-2xl font-bold tracking-[-0.04em]">Create your account</h1>
        <p className="mt-2 text-sm text-muted">
          8+ characters. The server also caps passwords at 72 bytes.
        </p>
      </div>

      <div className="card p-6 sm:p-7">
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <Field label="Full name">
            <input
              type="text"
              className={inputClass}
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              placeholder="Ada Lovelace"
              required
              autoComplete="name"
              autoFocus
            />
          </Field>

          <Field label="Email">
            <input
              type="email"
              className={inputClass}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              required
              autoComplete="email"
            />
          </Field>

          <Field label="Password">
            <input
              type="password"
              className={inputClass}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="At least 8 characters"
              required
              autoComplete="new-password"
              minLength={8}
            />
          </Field>

          <Field label="Confirm password">
            <input
              type="password"
              className={inputClass}
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              placeholder="Repeat it"
              required
              autoComplete="new-password"
              minLength={8}
            />
          </Field>

          {error && (
            <p className="text-sm text-danger" role="alert">
              {error}
            </p>
          )}

          <Button type="submit" size="lg" disabled={busy} className="mt-1 w-full">
            {busy ? 'Creating account…' : 'Sign up'}
          </Button>
        </form>
      </div>

      <p className="mt-6 text-center text-sm text-muted">
        Already registered?{' '}
        <Link to="/login" className="font-semibold text-brand hover:underline">
          Log in
        </Link>
      </p>
    </div>
  )
}
