/**
 * Route guard: renders children only when a session is confirmed.
 * While the initial /auth/me check is in flight we show a spinner rather
 * than flashing the login page at already-authenticated users.
 */

import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

export default function ProtectedRoute({ children }) {
  const { user, loading } = useAuth()
  const location = useLocation()

  if (loading) {
    return (
      <div className="loading-screen" role="status">
        Checking your session…
      </div>
    )
  }

  if (!user) {
    // Remember where the user wanted to go so login can send them back
    return <Navigate to="/login" state={{ from: location.pathname }} replace />
  }

  return children
}
