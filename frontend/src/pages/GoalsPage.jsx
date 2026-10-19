/**
 * Goals: full CRUD with SQL-backed progress bars.
 *
 * Two constraints worth noting:
 * - the backend re-validates end_date >= start_date on PATCH, so the form
 *   keeps both dates in sync and surfaces the 422 verbatim if it still slips;
 * - progress is current_count / target_count, so the +/- buttons PATCH the
 *   counter directly — that's the one field users change most often, and it
 *   keeps the common action to a single request.
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
  inputClass,
  PageHeader,
  ProgressBar,
  Spinner,
} from '../components/ui'

// Fixed per page load so the render stays pure (see the todayIso usage below).
const TODAY_ISO = new Date().toISOString().slice(0, 10)

const GOAL_TYPES = [
  { value: 'daily', label: 'Daily' },
  { value: 'weekly', label: 'Weekly' },
]

const PAGE_SIZE = 10

const EMPTY_FORM = {
  title: '',
  description: '',
  goal_type: 'daily',
  target_count: '1',
  current_count: '0',
  start_date: new Date().toISOString().slice(0, 10),
  end_date: '',
}

function buildPayload(form) {
  const payload = {
    title: form.title,
    goal_type: form.goal_type,
    target_count: Number(form.target_count) || 1,
    current_count: Number(form.current_count) || 0,
    start_date: form.start_date,
  }
  if (form.description.trim()) payload.description = form.description.trim()
  if (form.end_date) payload.end_date = form.end_date
  return payload
}

export default function GoalsPage() {
  const [data, setData] = useState(null)
  const [page, setPage] = useState(1)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)

  const [editingId, setEditingId] = useState(null)
  const [form, setForm] = useState(EMPTY_FORM)
  const [formError, setFormError] = useState(null)
  const [saving, setSaving] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setData(await api.get(`/goals?page=${page}&page_size=${PAGE_SIZE}`))
    } catch (err) {
      setError(formatApiError(err))
    } finally {
      setLoading(false)
    }
  }, [page])

  useEffect(() => {
    load()
  }, [load])

  function setField(key) {
    return (event) => setForm((prev) => ({ ...prev, [key]: event.target.value }))
  }

  function openCreate() {
    setEditingId('new')
    setForm(EMPTY_FORM)
    setFormError(null)
  }

  function openEdit(goal) {
    setEditingId(goal.id)
    setForm({
      title: goal.title,
      description: goal.description ?? '',
      goal_type: goal.goal_type,
      target_count: String(goal.target_count),
      current_count: String(goal.current_count),
      start_date: goal.start_date,
      end_date: goal.end_date ?? '',
    })
    setFormError(null)
  }

  function closeForm() {
    setEditingId(null)
    setFormError(null)
  }

  async function handleSubmit(event) {
    event.preventDefault()
    setFormError(null)

    if (form.end_date && form.end_date < form.start_date) {
      setFormError('End date cannot be before the start date.')
      return
    }

    setSaving(true)
    try {
      if (editingId === 'new') {
        await api.post('/goals', buildPayload(form))
        setPage(1)
      } else {
        await api.patch(`/goals/${editingId}`, buildPayload(form))
      }
      closeForm()
      await load()
    } catch (err) {
      setFormError(formatApiError(err))
    } finally {
      setSaving(false)
    }
  }

  /** Advance progress by one, capped at the target. */
  async function adjustProgress(goal, delta) {
    const next = goal.current_count + delta
    if (next < 0 || next > goal.target_count) return
    setError(null)
    try {
      // Completing a goal is inferred: hitting the target marks it done.
      const isCompleted = next >= goal.target_count
      await api.patch(`/goals/${goal.id}`, {
        current_count: next,
        is_completed: isCompleted,
      })
      await load()
    } catch (err) {
      setError(formatApiError(err))
    }
  }

  async function toggleComplete(goal) {
    setError(null)
    try {
      await api.patch(`/goals/${goal.id}`, { is_completed: !goal.is_completed })
      await load()
    } catch (err) {
      setError(formatApiError(err))
    }
  }

  async function handleDelete(goal) {
    if (!window.confirm(`Delete “${goal.title}”?`)) return
    setError(null)
    try {
      await api.delete(`/goals/${goal.id}`)
      if (data.items.length === 1 && page > 1) setPage(page - 1)
      else await load()
    } catch (err) {
      setError(formatApiError(err))
    }
  }

  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1
  // "Today" for the overdue check is fixed per page load; computing it at
  // module scope keeps the render pure (no Date call during render).
  const todayIso = TODAY_ISO

  return (
    <>
      <PageHeader
        eyebrow="Workspace"
        title="Goals"
        subtitle="Daily and weekly targets, measured against real counts."
      >
        <Button onClick={openCreate}>
          <Icon.Plus size={17} />
          Add goal
        </Button>
      </PageHeader>

      {editingId !== null && (
        <Card className="mb-6 p-5 sm:p-6">
          <div className="mb-5 flex items-center justify-between">
            <h2 className="text-lg font-bold tracking-[-0.02em]">
              {editingId === 'new' ? 'New goal' : 'Edit goal'}
            </h2>
            <button
              type="button"
              className="text-muted hover:text-ink"
              onClick={closeForm}
              aria-label="Close form"
            >
              <Icon.Close size={18} />
            </button>
          </div>

          <form onSubmit={handleSubmit} className="grid gap-4 sm:grid-cols-2">
            <Field label="Title">
              <input
                className={inputClass}
                value={form.title}
                onChange={setField('title')}
                required
                maxLength={200}
                placeholder="Solve 2 problems"
              />
            </Field>
            <Field label="Cadence">
              <select
                className={`${inputClass} cursor-pointer`}
                value={form.goal_type}
                onChange={setField('goal_type')}
              >
                {GOAL_TYPES.map((type) => (
                  <option key={type.value} value={type.value}>
                    {type.label}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Description" hint="optional">
              <input
                className={inputClass}
                value={form.description}
                onChange={setField('description')}
                placeholder="Why this target?"
              />
            </Field>
            <div className="grid grid-cols-2 gap-4">
              <Field label="Target">
                <input
                  type="number"
                  min="1"
                  className={inputClass}
                  value={form.target_count}
                  onChange={setField('target_count')}
                />
              </Field>
              <Field label="Current">
                <input
                  type="number"
                  min="0"
                  className={inputClass}
                  value={form.current_count}
                  onChange={setField('current_count')}
                />
              </Field>
            </div>
            <Field label="Start date">
              <input
                type="date"
                className={inputClass}
                value={form.start_date}
                onChange={setField('start_date')}
                required
              />
            </Field>
            <Field label="End date" hint="optional">
              <input
                type="date"
                className={inputClass}
                value={form.end_date}
                min={form.start_date}
                onChange={setField('end_date')}
              />
            </Field>

            {formError && (
              <p className="text-sm text-danger sm:col-span-2" role="alert">
                {formError}
              </p>
            )}

            <div className="flex gap-3 sm:col-span-2">
              <Button type="submit" disabled={saving}>
                {saving ? 'Saving…' : editingId === 'new' ? 'Create goal' : 'Save changes'}
              </Button>
              <Button variant="ghost" onClick={closeForm}>
                Cancel
              </Button>
            </div>
          </form>
        </Card>
      )}

      <ErrorNotice message={error} onRetry={load} />

      {loading && <Spinner label="Loading goals…" />}

      {data && !loading && data.items.length === 0 && (
        <Card>
          <EmptyState
            title="No goals yet"
            hint="Set a daily or weekly target and track it here."
          />
        </Card>
      )}

      {data && !loading && data.items.length > 0 && (
        <div className="space-y-4">
          {data.items.map((goal) => {
            const percent = goal.target_count
              ? Math.min(100, (goal.current_count / goal.target_count) * 100)
              : 0
            const overdue = goal.end_date && goal.end_date < todayIso && !goal.is_completed
            const achieved = goal.current_count >= goal.target_count

            return (
              <Card key={goal.id} className="p-5 sm:p-6">
                <div className="flex flex-wrap items-start gap-4">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <h3 className="truncate text-base font-semibold">{goal.title}</h3>
                      <Badge tone={goal.goal_type === 'daily' ? 'brand' : 'info'}>
                        {goal.goal_type}
                      </Badge>
                      {goal.is_completed ? (
                        <Badge tone="success">done</Badge>
                      ) : achieved ? (
                        <Badge tone="warning">target hit</Badge>
                      ) : overdue ? (
                        <Badge tone="danger">overdue</Badge>
                      ) : null}
                    </div>
                    {goal.description && (
                      <p className="mt-1 text-xs text-muted">{goal.description}</p>
                    )}

                    <div className="mt-4 max-w-md">
                      <div className="mb-1.5 flex items-center justify-between text-xs">
                        <span className="text-muted">
                          {goal.start_date}
                          {goal.end_date ? ` → ${goal.end_date}` : ''}
                        </span>
                        <span className="font-semibold">
                          {goal.current_count}
                          <span className="font-normal text-[#a0a4b2]">
                            {' '}
                            / {goal.target_count}
                          </span>
                        </span>
                      </div>
                      <ProgressBar
                        percent={percent}
                        color={goal.is_completed || achieved ? '#22a06b' : '#635bff'}
                      />
                    </div>
                  </div>

                  <div className="flex flex-wrap items-center gap-2">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => adjustProgress(goal, -1)}
                      disabled={goal.current_count <= 0}
                      aria-label="Decrease progress"
                    >
                      −
                    </Button>
                    <Button
                      variant="soft"
                      size="sm"
                      onClick={() => adjustProgress(goal, 1)}
                      disabled={goal.current_count >= goal.target_count}
                      aria-label="Increase progress"
                    >
                      +
                    </Button>
                    <Button variant="ghost" size="sm" onClick={() => toggleComplete(goal)}>
                      {goal.is_completed ? 'Reopen' : 'Mark done'}
                    </Button>
                    <Button variant="ghost" size="sm" onClick={() => openEdit(goal)}>
                      Edit
                    </Button>
                    <Button variant="danger" size="sm" onClick={() => handleDelete(goal)}>
                      Delete
                    </Button>
                  </div>
                </div>
              </Card>
            )
          })}
        </div>
      )}

      {data && data.total > 0 && (
        <div className="mt-6 flex items-center justify-center gap-4">
          <Button variant="ghost" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
            ← Prev
          </Button>
          <span className="text-sm text-muted">
            Page {data.page} of {totalPages} · {data.total} total
          </span>
          <Button
            variant="ghost"
            disabled={page >= totalPages}
            onClick={() => setPage((p) => p + 1)}
          >
            Next →
          </Button>
        </div>
      )}
    </>
  )
}
