/**
 * Analytics: the deep-dive companion to the Overview.
 *
 * The Overview shows the headline numbers; this page plots the full dense
 * trend the API already returns (one bucket per day, zero-filled) plus every
 * breakdown, so nothing on the dashboard is hidden from inspection. The
 * window switcher and the payload are identical to the Overview's — only the
 * presentation differs.
 */

import { useCallback, useEffect, useState } from 'react'
import { api, formatApiError } from '../services/api'
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorNotice,
  Field,
  Icon,
  IconBox,
  PageHeader,
  Spinner,
} from '../components/ui'

const WINDOW_OPTIONS = [7, 30, 90]

const DIFFICULTY_COLORS = { Easy: '#22a06b', Medium: '#f5a524', Hard: '#ef5b5b' }
const STATUS_COLORS = { todo: '#a0a5b7', in_progress: '#635bff', done: '#22a06b' }
const PRIORITY_COLORS = { low: '#2676d9', medium: '#f5a524', high: '#ef5b5b' }

const BREAKDOWN_ACCENTS = ['#635bff', '#ff8a65', '#22a06b', '#2676d9', '#f5a524']

/** Horizontal bar list with a max-scaled track (shared by every breakdown). */
function BarList({ title, subtitle, items, labelKey, colorFor, emptyHint }) {
  const max = Math.max(1, ...items.map((item) => item.count))
  return (
    <Card className="p-5 sm:p-6">
      <h2 className="text-base font-bold tracking-[-0.02em]">{title}</h2>
      {subtitle && <p className="mt-1 text-xs text-muted">{subtitle}</p>}
      <div className="mt-5 space-y-3">
        {items.length === 0 && (
          <p className="text-xs text-muted">{emptyHint ?? 'Nothing yet.'}</p>
        )}
        {items.map((item, index) => {
          const label = item[labelKey]
          const color = colorFor ? colorFor(label, index) : BREAKDOWN_ACCENTS[index % 5]
          return (
            <div key={label}>
              <div className="mb-1 flex items-center justify-between text-xs">
                <span className="font-medium capitalize">{String(label).replace('_', ' ')}</span>
                <span className="font-semibold text-muted">{item.count}</span>
              </div>
              <div className="h-1.5 overflow-hidden rounded-full bg-[#eeeff4]">
                <div
                  className="h-full rounded-full transition-[width] duration-500"
                  style={{ width: `${(item.count / max) * 100}%`, backgroundColor: color }}
                />
              </div>
            </div>
          )
        })}
      </div>
    </Card>
  )
}

/** Full dense trend, scrollable, with a zero-line for inactive days. */
function TrendPanel({ points }) {
  const max = Math.max(1, ...points.map((point) => point.count))
  const total = points.reduce((sum, point) => sum + point.count, 0)
  const activeDays = points.filter((point) => point.count > 0).length

  return (
    <Card className="p-5 sm:p-6">
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-bold tracking-[-0.02em]">
            Solved per day · last {points.length} days
          </h2>
          <p className="mt-1 text-xs text-muted">
            {total} solved across {activeDays} active {activeDays === 1 ? 'day' : 'days'}
          </p>
        </div>
        <Badge tone="brand">peak {max}/day</Badge>
      </div>

      <div className="flex h-[180px] items-end gap-[3px] overflow-x-auto pb-1">
        {points.map((point) => (
          <div
            key={point.solved_date}
            className="group relative min-w-[6px] flex-1 self-stretch"
            title={`${point.solved_date}: ${point.count} solved`}
          >
            <div
              className="absolute bottom-0 w-full rounded-t-[3px] transition-[height] duration-500"
              style={{
                height: `${point.count ? Math.max((point.count / max) * 100, 4) : 2}%`,
                backgroundColor: point.count
                  ? 'var(--color-brand)'
                  : 'var(--color-line-strong)',
              }}
            />
          </div>
        ))}
      </div>

      <div className="mt-3 flex justify-between text-[11px] text-muted">
        <span>{points[0]?.solved_date}</span>
        <span>{points[points.length - 1]?.solved_date}</span>
      </div>
    </Card>
  )
}

export default function AnalyticsPage() {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)
  const [days, setDays] = useState(30)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
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

  if (loading) return <Spinner label="Crunching your numbers…" />

  if (error) {
    return (
      <Card className="p-6">
        <ErrorNotice message={error} onRetry={load} />
      </Card>
    )
  }

  if (!data) return null

  const { dsa, goals, tasks, projects } = data

  return (
    <>
      <PageHeader
        eyebrow="Insights"
        title="Analytics"
        subtitle="Every metric the API aggregates, in one place."
      >
        <Field label="Window">
          <div className="flex gap-2">
            {WINDOW_OPTIONS.map((option) => (
              <Button
                key={option}
                variant={days === option ? 'primary' : 'ghost'}
                onClick={() => setDays(option)}
              >
                {option}d
              </Button>
            ))}
          </div>
        </Field>
      </PageHeader>

      <div className="mb-6 grid gap-6 xl:grid-cols-[1.6fr_1fr]">
        <TrendPanel points={dsa.solved_trend} />

        <Card className="p-5 sm:p-6">
          <h2 className="text-base font-bold tracking-[-0.02em]">Goal health</h2>
          <p className="mt-1 text-xs text-muted">
            {goals.completed}/{goals.total} completed · {goals.avg_progress_percent}% average progress
          </p>

          <div className="mt-5 flex items-center gap-4">
            <div className="grid h-20 w-20 shrink-0 place-items-center rounded-2xl bg-brand-tint">
              <span className="text-xl font-bold text-brand">
                {goals.completion_rate}%
              </span>
            </div>
            <p className="text-xs leading-5 text-muted">
              Completion rate across every goal you own, computed in SQL from the
              stored counters.
            </p>
          </div>

          <div className="mt-5 space-y-2">
            {goals.by_type.map((bucket) => (
              <div
                key={bucket.goal_type}
                className="flex items-center justify-between rounded-xl bg-canvas px-3 py-2 text-xs"
              >
                <span className="font-semibold capitalize">{bucket.goal_type}</span>
                <span className="text-muted">
                  {bucket.completed}/{bucket.total} done
                </span>
              </div>
            ))}
          </div>
        </Card>
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <BarList
          title="Problems by difficulty"
          subtitle={`${dsa.total} solved in total`}
          items={dsa.by_difficulty}
          labelKey="difficulty"
          colorFor={(label) => DIFFICULTY_COLORS[label] ?? '#635bff'}
        />
        <BarList
          title="Top topics"
          subtitle="Your ten most-logged topics"
          items={dsa.by_topic}
          labelKey="topic"
          emptyHint="Log problems with topics to see your strengths."
        />
        <BarList
          title="By platform"
          subtitle="Where you're practising"
          items={dsa.by_platform}
          labelKey="platform"
        />
        <BarList
          title="Tasks by status"
          subtitle={`${tasks.total} total · ${tasks.overdue} overdue`}
          items={tasks.by_status}
          labelKey="status"
          colorFor={(label) => STATUS_COLORS[label] ?? '#635bff'}
        />
        <BarList
          title="Tasks by priority"
          subtitle="Where the work sits"
          items={tasks.by_priority}
          labelKey="priority"
          colorFor={(label) => PRIORITY_COLORS[label] ?? '#635bff'}
        />
        <BarList
          title="Projects by status"
          subtitle={`${projects.milestones_completed}/${projects.milestones_total} milestones complete`}
          items={projects.by_status}
          labelKey="status"
          colorFor={(label) => STATUS_COLORS[label] ?? '#635bff'}
        />
      </div>

      <Card className="mt-6 p-5 sm:p-6">
        <div className="mb-5 flex items-center justify-between">
          <div>
            <h2 className="text-base font-bold tracking-[-0.02em]">Project progress</h2>
            <p className="mt-1 text-xs text-muted">
              Milestone completion for your most recent projects
            </p>
          </div>
          <IconBox tone="brand">
            <Icon.Projects />
          </IconBox>
        </div>

        {projects.items.length === 0 ? (
          <EmptyState title="No projects to chart yet" />
        ) : (
          <div className="grid gap-4 sm:grid-cols-2">
            {projects.items.map((project, index) => (
              <div key={project.id} className="rounded-xl border border-line p-4">
                <div className="flex items-center justify-between gap-3">
                  <p className="truncate text-sm font-semibold">{project.title}</p>
                  <Badge tone={project.status === 'completed' ? 'success' : 'neutral'}>
                    {project.status.replace('_', ' ')}
                  </Badge>
                </div>
                <p className="mt-1 text-[11px] text-muted">
                  {project.milestone_total
                    ? `${project.milestone_completed}/${project.milestone_total} milestones`
                    : 'no milestones yet'}
                </p>
                <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-[#eeeff4]">
                  <div
                    className="h-full rounded-full"
                    style={{
                      width: `${project.progress_percent}%`,
                      backgroundColor: BREAKDOWN_ACCENTS[index % 5],
                    }}
                  />
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>
    </>
  )
}
