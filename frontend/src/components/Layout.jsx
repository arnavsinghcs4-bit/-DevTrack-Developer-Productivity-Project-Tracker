/**
 * App shell: top navigation + routed page content.
 * The nav adapts to the session (links when logged in, login/register when not).
 */

import { Link, NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

export default function Layout() {
  const { user, logout } = useAuth()

  return (
    <div className="app">
      <nav className="navbar">
        <Link to="/" className="brand">
          DevTrack
        </Link>

        <div className="nav-links">
          {user && (
            <>
              <NavLink to="/" end>
                Dashboard
              </NavLink>
              <NavLink to="/dsa-problems">DSA Problems</NavLink>
            </>
          )}
        </div>

        <div className="nav-auth">
          {user ? (
            <>
              <span className="nav-user" title={user.email}>
                {user.full_name || user.email}
              </span>
              <button type="button" className="btn btn-ghost" onClick={logout}>
                Log out
              </button>
            </>
          ) : (
            <>
              <Link to="/login" className="btn btn-ghost">
                Log in
              </Link>
              <Link to="/register" className="btn btn-primary">
                Sign up
              </Link>
            </>
          )}
        </div>
      </nav>

      <main className="container">
        <Outlet />
      </main>

      <footer className="footer">DevTrack — track the practice, trust the process.</footer>
    </div>
  )
}
