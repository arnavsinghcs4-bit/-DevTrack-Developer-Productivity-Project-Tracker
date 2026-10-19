/**
 * Dashboard: renders the SQL-aggregated metrics from GET /analytics/dashboard.
 *
 * All numbers come pre-computed and user-scoped from the backend — this page
 * never sums anything itself. The trend series is dense (one bucket per day,
 * zero-filled by the API), so it can be plotted directly: each bar's height
 * is simply count / maxCount.
 */

import { useCallback, useEffect, useState } from 'react'
import { api, formatApiError } from '../services/api'

const WINDOW_OPTIONS = [7, 30, 90]

function StatCard({ label, value, hint }) {
  return (
    <div className="stat-card">
      <div className="stat-value">{value}</div>
      <div className="stat-label">{label}</div>
      {hint && <div className="stat-hint">{hint}</div>}
    </div>
  )
}

function BreakdownBars({ title, items, labelKey }) {
  const max = Math.max(1, ...items.map((item) => item.count))
  return (
    <div className="panel">
      <h3>{title}</h3>
      {items.length === 0 && <p className="muted">Nothing yet.</p>}
      {items.map((item) => (
        <div className="bar-row" key={item[labelKey]}>
          <span className="bar-label">{item[labelKey]}</span>
          <div className="bar-track">
            <div className="bar-fill" style={{ width: `${(item.count / max) * 100}%` }} />
          </div>
          <span className="bar-count">{item.count}</span>
        </div>
      ))}
    </div>
  )
}

function TrendChart({ points }) {
  const max = Math.max(1, ...points.map((p) => p.count))
  return (
    <div className="panel">
      <h3>Solved per day (last {points.length} days)</h3>
      <div className="trend-chart" role="img" aria-label="Daily problems solved">
        {points.map((point) => (
          <div
            key={point.solved_date}
            className="trend-bar"
            style={{ height: `${Math.max(point.count ? (point.count / max) * 100 : 0, 2)}%` }}
            title={`${point.solved_date}: ${point.count} solved`}
          />
        ))}
      </div>
      <div className="trend-axis muted">
        <span>{points[0]?.solved_date}</span>
        <span>{points[points.length - 1]?.solved_date}</span>
      </div>
    </div>
  )
}

export default function DashboardPage() {
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

  if (loading) return <div className="loading-screen">Loading dashboard…</div>
  if (error)
    return (
      <div className="panel">
        <p className="form-error" role="alert">
          {error}
        </p>
        <button type="button" className="btn btn-ghost" onClick={load}>
          Retry
        </button>
      </div>
    )
  if (!data) return null

  const { dsa, goals, tasks, projects } = data

  return (
    <>
      <div className="page-header">
        <h1>Dashboard</h1>
        <div className="window-picker">
          {WINDOW_OPTIONS.map((option) => (
            <button
              key={option}
              type="button"
              className={`btn btn-ghost ${days === option ? 'active' : ''}`}
              onClick={() => setDays(option)}
            >
              {option}d
            </button>
          ))}
        </div>
      </div>

      <div className="stat-grid">
        <StatCard label="Problems solved" value={dsa.total} hint={`${dsa.active_days} active days`} />
        <StatCard
          label="Goal completion"
          value={`${goals.completion_rate}%`}
          hint={`${goals.completed}/${goals.total} goals · ${goals.avg_progress_percent}% avg progress`}
        />
        <StatCard label="Open tasks" value={tasks.total} hint={`${tasks.overdue} overdue`} />
        <StatCard
          label="Milestones"
          value={`${projects.milestones_completed}/${projects.milestones_total}`}
          hint={`${projects.total} projects`}
        />
      </div>

      <div className="panel-grid">
        <TrendChart points={dsa.solved_trend} />
        <BreakdownBars title="By difficulty" items={dsa.by_difficulty} labelKey="difficulty" />
      </div>

      <div className="panel-grid">
        <BreakdownBars title="Top topics" items={dsa.by_topic} labelKey="topic" />
        <BreakdownBars title="Tasks by status" items={tasks.by_status} labelKey="status" />
        <BreakdownBars title="Projects by status" items={projects.by_status} labelKey="status" />
      </div>
    </>
  )
}
