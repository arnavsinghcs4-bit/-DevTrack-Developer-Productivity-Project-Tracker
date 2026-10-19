/**
 * App shell: fixed sidebar (248px) + sticky topbar + routed content.
 *
 * Structure follows the reference design (DESIGN_NOTES.md). Two deliberate
 * departures, both because the design's versions would be dead UI here:
 * - the global search box is a real filter for the current page rather than
 *   a decorative input, so it lives in the pages that own the data;
 * - the notifications button is replaced by the log-out action, which the
 *   backend actually supports (refresh-token revocation).
 *
 * The nav adapts to the session: navigation when logged in, brand-only plus
 * auth links when not (so /login and /register still render inside the shell).
 */

import { useEffect, useState } from 'react'
import { Link, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { Button, Icon, initials, SidebarLink } from './ui'

const NAV_ITEMS = [
  { to: '/', label: 'Overview', icon: <Icon.Overview size={19} />, end: true },
  { to: '/projects', label: 'Projects', icon: <Icon.Projects size={19} /> },
  { to: '/dsa-problems', label: 'LeetCode', icon: <Icon.Code size={19} /> },
  { to: '/tasks', label: 'Tasks', icon: <Icon.Tasks size={19} /> },
  { to: '/goals', label: 'Goals', icon: <Icon.Goals size={19} /> },
  { to: '/analytics', label: 'Analytics', icon: <Icon.Analytics size={19} /> },
]

export default function Layout() {
  const { user, logout } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()
  const [menuOpen, setMenuOpen] = useState(false)

  // Close the mobile drawer whenever the route changes, otherwise it stays
  // open over the page the user just navigated to.
  useEffect(() => {
    setMenuOpen(false)
  }, [location.pathname])

  return (
    <div className="min-h-screen bg-canvas text-ink">
      <Sidebar open={menuOpen} onClose={() => setMenuOpen(false)} user={user} />

      <main className="min-h-screen lg:ml-[248px]">
        <header className="sticky top-0 z-20 flex h-[76px] items-center justify-between border-b border-line bg-white/90 px-5 backdrop-blur-md sm:px-8 lg:px-10">
          <div className="flex items-center gap-3">
            <button
              type="button"
              className="grid h-10 w-10 place-items-center rounded-xl border border-line-strong text-[#555a6d] lg:hidden"
              aria-label="Open menu"
              onClick={() => setMenuOpen(true)}
            >
              <Icon.Menu size={20} />
            </button>
            <p className="text-sm font-semibold text-muted lg:text-base">
              {user ? 'Welcome back' : 'DevTrack'}
            </p>
          </div>

          <div className="flex items-center gap-3">
            {user ? (
              <>
                {/*
                  The reference's "Add progress" button is the header's primary
                  action. It points at the one place progress is actually
                  logged (the LeetCode page) and opens its create form via a
                  query param rather than being decorative.
                */}
                <Button onClick={() => navigate('/dsa-problems?new=1')}>
                  <Icon.Plus size={17} />
                  <span className="hidden sm:inline">Add progress</span>
                </Button>
                <Button variant="ghost" onClick={logout} title="Revoke this session">
                  <Icon.Logout size={17} />
                  <span className="hidden sm:inline">Log out</span>
                </Button>
              </>
            ) : (
              <>
                <Link to="/login">
                  <Button variant="ghost">Log in</Button>
                </Link>
                <Link to="/register">
                  <Button>Sign up</Button>
                </Link>
              </>
            )}
          </div>
        </header>

        <div className="mx-auto max-w-[1450px] px-5 py-8 sm:px-8 lg:px-10 lg:py-10">
          <Outlet />
        </div>
      </main>
    </div>
  )
}

function Sidebar({ open, onClose, user }) {
  return (
    <>
      {open && (
        <div
          className="fixed inset-0 z-30 bg-ink/40 lg:hidden"
          onClick={onClose}
          aria-hidden="true"
        />
      )}

      <aside
        className={`fixed inset-y-0 left-0 z-40 flex w-[248px] flex-col border-r border-line bg-white px-4 py-7 transition-transform lg:translate-x-0 ${
          open ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <div className="mb-9 flex items-center justify-between px-3">
          <Link to="/" className="flex items-center gap-2.5">
            <div className="grid h-9 w-9 place-items-center rounded-xl bg-brand text-white shadow-brand">
              <span className="text-lg font-bold tracking-tight">D</span>
            </div>
            <span className="text-xl font-bold tracking-[-0.04em]">DevTrack</span>
          </Link>
          <button
            type="button"
            className="text-[#7b8195] lg:hidden"
            aria-label="Close menu"
            onClick={onClose}
          >
            <Icon.Close size={20} />
          </button>
        </div>

        <nav className="space-y-1">
          <p className="mb-2 px-3 text-[10px] font-bold uppercase tracking-[0.16em] text-faint">
            Workspace
          </p>
          {NAV_ITEMS.map((item) => (
            <SidebarLink key={item.to} {...item} onClick={onClose} />
          ))}
        </nav>

        <div className="mt-auto">
          <MomentumCard />
          {user && <IdentityChip user={user} />}
        </div>
      </aside>
    </>
  )
}

/**
 * Contextual nudge in the sidebar.
 *
 * The reference hardcodes "You're 3 days away from a new personal best." There
 * is no personal-best field in the API, so this version states something the
 * dashboard can actually back up (the streak lives on the Overview) instead of
 * inventing a number.
 */
function MomentumCard() {
  return (
    <div className="mx-1 mb-3 rounded-2xl bg-ink p-4 text-white">
      <div className="mb-3 flex h-8 w-8 items-center justify-center rounded-lg bg-white/10 text-[#aaa6ff]">
        <Icon.Trend size={17} />
      </div>
      <p className="text-sm font-semibold">Keep the momentum</p>
      <p className="mt-1 text-xs leading-5 text-white/55">
        Log a problem today — the streak on your Overview is the honest scoreboard.
      </p>
    </div>
  )
}

function IdentityChip({ user }) {
  return (
    <div className="mt-3 flex items-center gap-3 border-t border-[#eceef4] px-3 pt-5">
      <div className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-[#ddf3eb] text-xs font-bold text-[#187a56]">
        {initials(user.full_name, user.email)}
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-semibold">{user.full_name}</p>
        <p className="truncate text-[11px] text-[#9a9fb0]">{user.email}</p>
      </div>
      <Icon.Chevron size={15} className="shrink-0 text-[#c3c6d1]" />
    </div>
  )
}
