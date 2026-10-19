/**
 * Shared UI primitives for the redesigned shell.
 *
 * Everything here is presentation only — no data fetching, no auth. The
 * palette and geometry come from the design tokens in index.css, so a colour
 * change happens in one place rather than in every page.
 */

import { NavLink } from 'react-router-dom'

/* --------------------------------------------------------------------------
 * Icons — inline SVG, matching the reference's 24px grid, 1.8 stroke,
 * round caps/joins.
 * ------------------------------------------------------------------------ */

function Svg({ children, size = 18, className = '' }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      {children}
    </svg>
  )
}

export const Icon = {
  Overview: (p) => (
    <Svg {...p}>
      <rect x="3" y="3" width="7" height="7" rx="2" />
      <rect x="14" y="3" width="7" height="7" rx="2" />
      <rect x="3" y="14" width="7" height="7" rx="2" />
      <rect x="14" y="14" width="7" height="7" rx="2" />
    </Svg>
  ),
  Projects: (p) => (
    <Svg {...p}>
      <path d="M3 7.5a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-10Z" />
    </Svg>
  ),
  Code: (p) => (
    <Svg {...p}>
      <path d="m8 9-3 3 3 3M16 9l3 3-3 3M14 5l-4 14" />
    </Svg>
  ),
  Tasks: (p) => (
    <Svg {...p}>
      <path d="m3 8 2 2 3.5-3.5M3 17l2 2 3.5-3.5M13 8h8M13 17h8" />
    </Svg>
  ),
  Goals: (p) => (
    <Svg {...p}>
      <circle cx="12" cy="12" r="8" />
      <circle cx="12" cy="12" r="3" />
    </Svg>
  ),
  Analytics: (p) => (
    <Svg {...p}>
      <path d="M4 19V9M10 19V5M16 19v-7M22 19H2" />
    </Svg>
  ),
  Trend: (p) => (
    <Svg {...p}>
      <path d="m3 17 6-6 4 4 8-9" />
      <path d="M15 6h6v6" />
    </Svg>
  ),
  Plus: (p) => (
    <Svg {...p}>
      <path d="M12 5v14M5 12h14" />
    </Svg>
  ),
  Calendar: (p) => (
    <Svg {...p}>
      <rect x="3" y="5" width="18" height="16" rx="2" />
      <path d="M16 3v4M8 3v4M3 10h18" />
    </Svg>
  ),
  Chevron: (p) => (
    <Svg {...p}>
      <path d="m9 18 6-6-6-6" />
    </Svg>
  ),
  ArrowRight: (p) => (
    <Svg {...p}>
      <path d="M5 12h14M14 7l5 5-5 5" />
    </Svg>
  ),
  Logout: (p) => (
    <Svg {...p}>
      <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9" />
    </Svg>
  ),
  Menu: (p) => (
    <Svg {...p}>
      <path d="M4 7h16M4 12h16M4 17h16" />
    </Svg>
  ),
  Close: (p) => (
    <Svg {...p}>
      <path d="m6 6 12 12M18 6 6 18" />
    </Svg>
  ),
}

/* --------------------------------------------------------------------------
 * Primitives
 * ------------------------------------------------------------------------ */

/**
 * Tinted 36px icon tile. `tone` maps to the four colour variants in the
 * reference design (purple / green / orange / blue).
 */
const TONES = {
  brand: 'bg-brand-tint text-brand',
  success: 'bg-success-tint text-success-ink',
  warning: 'bg-warning-tint text-warning-ink',
  info: 'bg-info-tint text-info',
  danger: 'bg-danger-tint text-danger',
}

export function IconBox({ tone = 'brand', children }) {
  return <div className={`icon-box ${TONES[tone] ?? TONES.brand}`}>{children}</div>
}

export function Card({ className = '', children }) {
  return <div className={`card ${className}`}>{children}</div>
}

/** Primary / ghost / danger buttons in three sizes, matching the reference. */
const VARIANTS = {
  primary:
    'bg-brand text-white shadow-brand hover:bg-brand-hover disabled:hover:bg-brand',
  ghost:
    'border border-line-strong bg-white text-muted hover:bg-hover hover:text-ink',
  danger: 'border border-danger/40 bg-white text-danger hover:bg-danger-tint',
  soft: 'bg-brand-tint text-brand hover:bg-brand-soft',
}

const SIZES = {
  sm: 'h-8 px-3 text-xs',
  md: 'h-10 px-3.5 text-sm',
  lg: 'h-11 px-5 text-sm',
}

export function Button({
  variant = 'primary',
  size = 'md',
  className = '',
  type = 'button',
  children,
  ...rest
}) {
  return (
    <button
      type={type}
      className={`inline-flex items-center justify-center gap-2 rounded-xl font-semibold transition disabled:cursor-not-allowed disabled:opacity-50 ${VARIANTS[variant]} ${SIZES[size]} ${className}`}
      {...rest}
    >
      {children}
    </button>
  )
}

/** Small coloured pill (difficulty, status, priority). */
const BADGE_TONES = {
  success: 'bg-success-tint text-success-ink',
  warning: 'bg-warning-tint text-warning-ink',
  danger: 'bg-danger-tint text-danger',
  info: 'bg-info-tint text-info',
  brand: 'bg-brand-tint text-brand',
  neutral: 'bg-canvas text-muted',
}

export function Badge({ tone = 'neutral', children }) {
  return (
    <span
      className={`inline-block rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${BADGE_TONES[tone] ?? BADGE_TONES.neutral}`}
    >
      {children}
    </span>
  )
}

/**
 * Horizontal progress bar. `color` is a CSS colour so callers can give each
 * project/report row its own accent (as the reference design does).
 */
export function ProgressBar({ percent, color = 'var(--color-brand)', className = '' }) {
  const clamped = Math.max(0, Math.min(100, percent ?? 0))
  return (
    <div className={`h-1.5 overflow-hidden rounded-full bg-[#eeeff4] ${className}`}>
      <div
        className="h-full rounded-full transition-[width] duration-500"
        style={{ width: `${clamped}%`, backgroundColor: color }}
      />
    </div>
  )
}

/** Page heading block: eyebrow, title, subtitle, optional right-hand slot. */
export function PageHeader({ eyebrow, title, subtitle, children }) {
  return (
    <section className="mb-8 flex flex-col gap-5 sm:flex-row sm:items-end sm:justify-between">
      <div>
        {eyebrow && (
          <p className="mb-2 text-xs font-bold uppercase tracking-[0.14em] text-brand">
            {eyebrow}
          </p>
        )}
        <h1 className="text-3xl font-bold tracking-[-0.04em] sm:text-[36px]">{title}</h1>
        {subtitle && <p className="mt-2 text-sm text-muted">{subtitle}</p>}
      </div>
      {children}
    </section>
  )
}

/** Inline error banner used by every page's fetch/validation failure path. */
export function ErrorNotice({ message, onRetry }) {
  if (!message) return null
  return (
    <div
      role="alert"
      className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-danger/30 bg-danger-tint px-4 py-3 text-sm text-danger"
    >
      <span>{message}</span>
      {onRetry && (
        <Button variant="ghost" size="sm" onClick={onRetry}>
          Retry
        </Button>
      )}
    </div>
  )
}

export function EmptyState({ title, hint }) {
  return (
    <div className="px-6 py-12 text-center">
      <p className="text-sm font-semibold text-ink">{title}</p>
      {hint && <p className="mt-1 text-xs text-muted">{hint}</p>}
    </div>
  )
}

export function Spinner({ label = 'Loading…' }) {
  return (
    <div className="flex items-center justify-center gap-3 px-6 py-16 text-sm text-muted">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-line-strong border-t-brand" />
      {label}
    </div>
  )
}

/** Labelled input/select used by every form on the app. */
export function Field({ label, hint, children }) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-xs font-semibold text-muted">
        {label}
        {hint && <span className="ml-1 font-normal text-faint">{hint}</span>}
      </span>
      {children}
    </label>
  )
}

export const inputClass =
  'h-10 w-full rounded-xl border border-line-strong bg-subtle px-3 text-sm outline-none transition placeholder:text-faint focus:border-brand/60 focus:bg-white focus:ring-4 focus:ring-brand/10'

/* --------------------------------------------------------------------------
 * Sidebar helpers
 * ------------------------------------------------------------------------ */

/** Sidebar nav item — active state mirrors the reference's tinted pill. */
export function SidebarLink({ to, icon, label, end, onClick }) {
  return (
    <NavLink
      to={to}
      end={end}
      onClick={onClick}
      className={({ isActive }) =>
        `flex w-full items-center gap-3 rounded-xl px-3 py-3 text-sm font-semibold transition ${
          isActive
            ? 'bg-brand-tint text-brand'
            : 'text-[#74798d] hover:bg-hover hover:text-[#34384b]'
        }`
      }
    >
      {icon}
      {label}
    </NavLink>
  )
}

/* --------------------------------------------------------------------------
 * Formatting helpers (presentation-only, shared by pages)
 * ------------------------------------------------------------------------ */

/** "2h ago" style relative time from an ISO timestamp. */
export function relativeTime(iso) {
  if (!iso) return ''
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return ''
  const seconds = Math.round((Date.now() - then) / 1000)
  if (seconds < 60) return 'just now'
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.round(hours / 24)
  if (days === 1) return 'Yesterday'
  if (days < 30) return `${days}d ago`
  const months = Math.round(days / 30)
  return months < 12 ? `${months}mo ago` : `${Math.round(months / 12)}y ago`
}

/** Initials for avatar chips: "Alex Morgan" -> "AM". */
export function initials(name, email) {
  const source = (name || email || '?').trim()
  const parts = source.split(/[\s@._-]+/).filter(Boolean)
  if (parts.length === 0) return '?'
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase()
  return (parts[0][0] + parts[1][0]).toUpperCase()
}

/**
 * Long date in the reference's "Monday, June 24" style.
 * Parsed as UTC so a date-only string never shifts a day across timezones.
 */
export function formatLongDate(iso) {
  if (!iso) return ''
  const d = new Date(`${iso}T00:00:00Z`)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleDateString('en-US', {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
    timeZone: 'UTC',
  })
}

/** Reusable accent palette for per-row colours (projects, charts). */
export const ACCENTS = ['#635bff', '#ff8a65', '#22a06b', '#2676d9', '#f5a524', '#ef5b5b']

export function accentFor(key, index) {
  if (typeof index === 'number') return ACCENTS[index % ACCENTS.length]
  const str = String(key ?? '')
  let hash = 0
  for (let i = 0; i < str.length; i += 1) hash = (hash * 31 + str.charCodeAt(i)) >>> 0
  return ACCENTS[hash % ACCENTS.length]
}
