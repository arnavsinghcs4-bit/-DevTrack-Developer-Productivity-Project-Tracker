/**
 * Overview — the reference design's dashboard page, wired to real data.
 *
 * Every number here comes from GET /analytics/dashboard; nothing is summed in
 * the browser except the two things the API deliberately doesn't model:
 * - the current streak (a presentation-friendly run-length over solved_trend);
 * - the "this week" pill chart (the last 7 points of the same dense series).
 *
 * The window switcher re-requests the endpoint with ?days=N, which is also
 * what makes the dense trend array change length.
 */

import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, formatApiError } from '../services/api'
import { useAuth } from '../context/AuthContext'
import {
  accentFor,
  Badge,
  Card,
  EmptyState,
  ErrorNotice,
  Field,
  formatLongDate,
  Icon,
  IconBox,
  inputClass,
  ProgressBar,
  relativeTime,
  Spinner,
} from '../components/ui'

const WINDOW_OPTIONS = [
  { days: 7, label: 'Last 7 days' },
  { days: 30, label: 'Last 30 days' },
  { days: 90, label: 'Last 90 days' },
]

const DIFFICULTY_TONES = { Easy: 'success', Medium: 'warning', Hard: 'danger' }
const DIFFICULTY_COLORS = {
  Easy: '#22a06b',
  Medium: '#f5a524',
  Hard: '#ef5b5b',
}

/**
 * Current streak: consecutive days with at least one solved problem, counting
 * back from the most recent active day. A streak is unbroken if today or
 * yesterday is active (matching how streak counters usually behave — you
 * haven't lost it until a full day passes).
 */
function currentStreak(trend) {
  if (!trend?.length) return 0
  let end = trend.length - 1
  while (end >= 0 && trend[end].count === 0) end -= 1
  if (end < 0) return 0
  const lastActiveIsRecent = end >= trend.length - 2
  if (!lastActiveIsRecent) return 0
  let run = 0
  for (let i = end; i >= 0 && trend[i].count > 0; i -= 1) run += 1
  return run
}

function longestStreak(trend) {
  let best = 0
  let run = 0
  for (const point of trend ?? []) {
    run = point.count > 0 ? run + 1 : 0
    if (run > best) best = run
  }
  return best
}

// Both the greeting and the header date are fixed for the life of a page load,
// so they are computed once at module scope. Calling Date.now() during render
// would make the render impure (and the lint rule flags it) for no benefit.
const NOW = new Date()
const TODAY_LABEL = formatLongDate(NOW.toISOString().slice(0, 10))

function greeting() {
  const hour = NOW.getHours()
  if (hour < 12) return 'Good morning'
  if (hour < 18) return 'Good afternoon'
  return 'Good evening'
}

function StatCard({ label, value, hint, icon, tone, hintTone = 'muted' }) {
  return (
    <Card className="stat-card p-5">
      <div className="mb-5 flex items-center justify-between">
        <p className="text-sm font-medium text-[#777c8f]">{label}</p>
        <IconBox tone={tone}>{icon}</IconBox>
      </div>
      <p className="text-[28px] font-bold tracking-[-0.04em]">{value}</p>
      <p
        className={`mt-1.5 text-xs font-medium ${
          hintTone === 'success' ? 'text-success' : 'text-muted'
        }`}
      >
        {hint}
      </p>
    </Card>
  )
}

/**
 * The reference's per-project row: avatar, title, secondary line, and a
 * percentage progress bar with the accent colour cycling per row.
 */
function ProjectRow({ project, index }) {
  const accent = accentFor(project.title, index)
  const percent = Math.round(project.progress_percent)
  const secondary = project.description || project.status.replace('_', ' ')

  return (
    <div className="grid grid-cols-[auto_1fr_auto] items-center gap-3 rounded-xl px-2 py-3 transition hover:bg-subtle sm:gap-4">
      <div
        className="grid h-11 w-11 place-items-center rounded-xl text-sm font-bold text-white"
        style={{ backgroundColor: accent }}
      >
        {project.title.charAt(0).toUpperCase()}
      </div>
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <p className="truncate text-sm font-semibold">{project.title}</p>
          {project.created_at && (
            <span className="hidden text-[10px] text-[#a0a4b3] sm:inline">
              {relativeTime(project.created_at)}
            </span>
          )}
        </div>
        <p className="mt-1 truncate text-xs text-[#9296a6]">{secondary}</p>
      </div>
      <div className="w-24 sm:w-36">
        <div className="mb-1.5 flex justify-between text-[10px] font-semibold">
          <span className="text-[#999dac]">Progress</span>
          <span>{project.milestone_total ? `${percent}%` : '—'}</span>
        </div>
        <ProgressBar percent={project.progress_percent} color={accent} />
      </div>
    </div>
  )
}

/**
 * LeetCode card: conic ring split by difficulty, plus per-difficulty bars.
 * The denominator is the user's own total (the reference shows the site-wide
 * problem counts; there is no API for those, so the bars are shares of your
 * own solved set instead of an invented "3,438 total problems").
 */
function LeetCodeCard({ dsa, week }) {
  const total = dsa.total
  const byDifficulty = Object.fromEntries(
    dsa.by_difficulty.map((d) => [d.difficulty, d.count]),
  )
  const easy = byDifficulty.Easy ?? 0
  const medium = byDifficulty.Medium ?? 0

  // Conic-gradient stops in degrees for the ring.
  const easyDeg = total ? (easy / total) * 360 : 0
  const mediumDeg = total ? easyDeg + (medium / total) * 360 : 0

  const weekMax = Math.max(1, ...week.map((p) => p.count))

  return (
    <Card className="p-5 sm:p-6">
      <div className="mb-5 flex items-center justify-between">
        <div>
          <h2 className="text-lg font-bold tracking-[-0.02em]">LeetCode progress</h2>
          <p className="mt-1 text-xs text-muted">
            {total} solved across {dsa.active_days} active {dsa.active_days === 1 ? 'day' : 'days'}
          </p>
        </div>
        <Badge tone="warning">All time</Badge>
      </div>

      <div className="flex flex-col items-center gap-6 sm:flex-row">
        <div
          className="ring-track relative grid h-[142px] w-[142px] shrink-0 place-items-center rounded-full"
          style={{
            '--ring-easy': `${easyDeg}deg`,
            '--ring-medium': `${mediumDeg}deg`,
          }}
        >
          <div className="grid h-[106px] w-[106px] place-items-center rounded-full bg-white text-center">
            <div>
              <p className="text-2xl font-bold">{total}</p>
              <p className="mt-0.5 text-[10px] font-semibold uppercase tracking-wider text-[#999dac]">
                Solved
              </p>
            </div>
          </div>
        </div>

        <div className="w-full space-y-4">
          {['Easy', 'Medium', 'Hard'].map((level) => {
            const count = byDifficulty[level] ?? 0
            const share = total ? (count / total) * 100 : 0
            return (
              <div key={level}>
                <div className="mb-1.5 flex items-center justify-between text-xs">
                  <span className="font-semibold" style={{ color: DIFFICULTY_COLORS[level] }}>
                    {level}
                  </span>
                  <span className="font-semibold">
                    {count}
                    <span className="font-normal text-[#a0a4b2]"> / {total}</span>
                  </span>
                </div>
                <ProgressBar percent={share} color={DIFFICULTY_COLORS[level]} />
              </div>
            )
          })}
        </div>
      </div>

      <div className="mt-6 flex items-center justify-between rounded-xl bg-canvas px-4 py-3">
        <div>
          <p className="text-[11px] text-muted">This week</p>
          <p className="mt-0.5 text-sm font-bold">
            {week.reduce((sum, p) => sum + p.count, 0)} problems solved
          </p>
        </div>
        <div className="flex items-end gap-1">
          {week.map((point) => (
            <span
              key={point.solved_date}
              title={`${point.solved_date}: ${point.count}`}
              className="w-1.5 rounded-full"
              style={{
                height: `${Math.max(point.count ? (point.count / weekMax) * 36 : 4, 4)}px`,
                backgroundColor: point.count ? 'var(--color-brand)' : 'var(--color-brand-soft)',
              }}
            />
          ))}
        </div>
      </div>
    </Card>
  )
}

export default function DashboardPage() {
  const { user } = useAuth()
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)
  const [days, setDays] = useState(30)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      // A single request: the analytics payload carries everything the
      // Overview renders, including created_at for the project rows.
      setData(await api.get(`/analytics/dashboard?days=${days}`))
    } catch (err) {
      setError(formatApiError(err))
    } finally {
      setLoading(false)
    }
  }, [days])

  useEffect(() => {
    load()
  }, [load])

  const streak = useMemo(() => currentStreak(data?.dsa.solved_trend), [data])
  const best = useMemo(() => longestStreak(data?.dsa.solved_trend), [data])

  if (loading) return <Spinner label="Loading your dashboard…" />

  if (error) {
    return (
      <Card className="p-6">
        <ErrorNotice message={error} onRetry={load} />
      </Card>
    )
  }

  if (!data) return null

  const { dsa, goals, tasks, projects: projectStats } = data
  const week = dsa.solved_trend.slice(-7)

  return (
    <>
      <section className="mb-8 flex flex-col gap-5 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="mb-2 text-xs font-bold uppercase tracking-[0.14em] text-brand">
            {TODAY_LABEL}
          </p>
          <h1 className="text-3xl font-bold tracking-[-0.04em] sm:text-[36px]">
            {greeting()}, {user?.full_name?.split(' ')[0] ?? 'there'}
          </h1>
          <p className="mt-2 text-sm text-muted">
            Here&apos;s how your building and problem solving is going.
          </p>
        </div>

        {/* Real <select>: the reference overlays an invisible select on a fake
            button, which breaks keyboard affordance for no visual gain. */}
        <Field label="Reporting period" hint="trend window">
          <select
            className={`${inputClass} cursor-pointer bg-white font-semibold`}
            value={days}
            onChange={(event) => setDays(Number(event.target.value))}
            aria-label="Select reporting period"
          >
            {WINDOW_OPTIONS.map((option) => (
              <option key={option.days} value={option.days}>
                {option.label}
              </option>
            ))}
          </select>
        </Field>
      </section>

      <section className="mb-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Total projects"
          value={projectStats.total}
          hint={`${projectStats.milestones_completed}/${projectStats.milestones_total} milestones complete`}
          icon={<Icon.Projects />}
          tone="brand"
          hintTone={
            projectStats.milestones_total &&
            projectStats.milestones_completed === projectStats.milestones_total
              ? 'success'
              : 'muted'
          }
        />
        <StatCard
          label="Problems solved"
          value={dsa.total}
          hint={`${dsa.active_days} active ${dsa.active_days === 1 ? 'day' : 'days'}`}
          icon={<Icon.Code />}
          tone="success"
          hintTone={dsa.total > 0 ? 'success' : 'muted'}
        />
        <StatCard
          label="Current streak"
          value={`${streak} ${streak === 1 ? 'day' : 'days'}`}
          hint={best ? `Longest in window: ${best}` : 'No activity yet'}
          icon={<Icon.Trend />}
          tone="warning"
        />
        <StatCard
          label="Goal completion"
          value={`${goals.completion_rate}%`}
          hint={`${goals.completed}/${goals.total} goals done · ${goals.avg_progress_percent}% avg progress`}
          icon={<Icon.Analytics />}
          tone="info"
          hintTone={goals.completion_rate >= 50 ? 'success' : 'muted'}
        />
      </section>

      <section className="grid gap-6 xl:grid-cols-[1.45fr_1fr]">
        <Card className="p-5 sm:p-6">
          <div className="mb-6 flex items-center justify-between">
            <div>
              <h2 className="text-lg font-bold tracking-[-0.02em]">Recent projects</h2>
              <p className="mt-1 text-xs text-muted">
                Your latest work and progress
              </p>
            </div>
            <Link
              to="/projects"
              className="flex items-center gap-1 text-xs font-bold text-brand"
            >
              View all <Icon.ArrowRight size={14} />
            </Link>
          </div>

          {projectStats.items.length === 0 ? (
            <EmptyState
              title="No projects yet"
              hint="Create one and its milestone progress shows up here."
            />
          ) : (
            <div className="space-y-1">
              {projectStats.items.map((project, index) => (
                <ProjectRow key={project.id} index={index} project={project} />
              ))}
            </div>
          )}
        </Card>

        <LeetCodeCard dsa={dsa} week={week} />
      </section>

      <section className="mt-6 grid gap-6 xl:grid-cols-[1.45fr_1fr]">
        <Card className="p-5 sm:p-6">
          <div className="mb-5 flex items-center justify-between">
            <div>
              <h2 className="text-lg font-bold tracking-[-0.02em]">Tasks</h2>
              <p className="mt-1 text-xs text-muted">
                {tasks.total} total · {tasks.overdue} overdue
              </p>
            </div>
            <Link
              to="/tasks"
              className="flex items-center gap-1 text-xs font-bold text-brand"
            >
              Manage <Icon.ArrowRight size={14} />
            </Link>
          </div>
          <div className="space-y-4">
            {tasks.by_status.map((bucket) => (
              <div key={bucket.status}>
                <div className="mb-1.5 flex items-center justify-between text-xs">
                  <span className="font-semibold capitalize">
                    {bucket.status.replace('_', ' ')}
                  </span>
                  <span className="font-semibold">
                    {bucket.count}
                    <span className="font-normal text-[#a0a4b2]"> / {tasks.total}</span>
                  </span>
                </div>
                <ProgressBar
                  percent={tasks.total ? (bucket.count / tasks.total) * 100 : 0}
                  color={
                    bucket.status === 'done'
                      ? '#22a06b'
                      : bucket.status === 'in_progress'
                        ? '#635bff'
                        : '#a0a5b7'
                  }
                />
              </div>
            ))}
          </div>
        </Card>

        <Card className="p-5 sm:p-6">
          <h2 className="text-lg font-bold tracking-[-0.02em]">Problems by difficulty</h2>
          <p className="mt-1 text-xs text-muted">
            All time, across {dsa.by_platform.length}{' '}
            {dsa.by_platform.length === 1 ? 'platform' : 'platforms'}
          </p>
          <div className="mt-5 flex flex-wrap gap-2">
            {dsa.by_difficulty.map((bucket) => (
              <Badge
                key={bucket.difficulty}
                tone={DIFFICULTY_TONES[bucket.difficulty] ?? 'neutral'}
              >
                {bucket.difficulty}: {bucket.count}
              </Badge>
            ))}
          </div>
          <div className="mt-5 space-y-3">
            {dsa.by_platform.length === 0 && (
              <p className="text-xs text-muted">No problems logged yet.</p>
            )}
            {dsa.by_platform.map((bucket) => (
              <div
                key={bucket.platform}
                className="flex items-center justify-between text-xs"
              >
                <span className="font-medium">{bucket.platform}</span>
                <span className="font-semibold text-muted">{bucket.count}</span>
              </div>
            ))}
          </div>
        </Card>
      </section>
    </>
  )
}
