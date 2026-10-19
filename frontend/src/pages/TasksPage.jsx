/**
 * Tasks: full CRUD with the backend's real status/priority filters.
 *
 * Filtering is server-side (?status=&priority=) rather than in the browser,
 * which keeps the pagination totals honest — a client-side filter over one
 * page would show "3 of 20" while the server still reports 41.
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
  Spinner,
} from '../components/ui'

// Fixed per page load so the render stays pure (see the todayIso usage below).
const TODAY_ISO = new Date().toISOString().slice(0, 10)

const STATUSES = [
  { value: 'todo', label: 'To do' },
  { value: 'in_progress', label: 'In progress' },
  { value: 'done', label: 'Done' },
]

const PRIORITIES = [
  { value: 'low', label: 'Low' },
  { value: 'medium', label: 'Medium' },
  { value: 'high', label: 'High' },
]

const STATUS_TONES = { todo: 'neutral', in_progress: 'brand', done: 'success' }
const PRIORITY_TONES = { low: 'info', medium: 'warning', high: 'danger' }

const PAGE_SIZE = 10

const EMPTY_FORM = {
  title: '',
  description: '',
  status: 'todo',
  priority: 'medium',
  due_date: '',
  project_id: '',
}

function buildPayload(form) {
  const payload = { title: form.title, status: form.status, priority: form.priority }
  if (form.description.trim()) payload.description = form.description.trim()
  if (form.due_date) payload.due_date = form.due_date
  // Empty string means "no project"; the API accepts an explicit null to
  // detach, so an untouched selector genuinely clears the link.
  if (form.project_id) payload.project_id = Number(form.project_id)
  return payload
}

export default function TasksPage() {
  const [data, setData] = useState(null)
  const [projects, setProjects] = useState([])
  const [page, setPage] = useState(1)
  const [statusFilter, setStatusFilter] = useState('')
  const [priorityFilter, setPriorityFilter] = useState('')
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
      const params = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) })
      if (statusFilter) params.set('status', statusFilter)
      if (priorityFilter) params.set('priority', priorityFilter)

      const [list, projectList] = await Promise.all([
        api.get(`/tasks?${params.toString()}`),
        // The task form needs the user's projects for its optional link.
        api.get('/projects?page=1&page_size=100'),
      ])
      setData(list)
      setProjects(projectList.items)
    } catch (err) {
      setError(formatApiError(err))
    } finally {
      setLoading(false)
    }
  }, [page, statusFilter, priorityFilter])

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

  function openEdit(task) {
    setEditingId(task.id)
    setForm({
      title: task.title,
      description: task.description ?? '',
      status: task.status,
      priority: task.priority,
      due_date: task.due_date ?? '',
      project_id: task.project_id ? String(task.project_id) : '',
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
    setSaving(true)
    try {
      if (editingId === 'new') {
        await api.post('/tasks', buildPayload(form))
        setPage(1)
      } else {
        await api.patch(`/tasks/${editingId}`, buildPayload(form))
      }
      closeForm()
      await load()
    } catch (err) {
      setFormError(formatApiError(err))
    } finally {
      setSaving(false)
    }
  }

  /** Quick status transition straight from the row (the common action). */
  async function cycleStatus(task) {
    const order = ['todo', 'in_progress', 'done']
    const next = order[(order.indexOf(task.status) + 1) % order.length]
    setError(null)
    try {
      await api.patch(`/tasks/${task.id}`, { status: next })
      await load()
    } catch (err) {
      setError(formatApiError(err))
    }
  }

  async function handleDelete(task) {
    if (!window.confirm(`Delete “${task.title}”?`)) return
    setError(null)
    try {
      await api.delete(`/tasks/${task.id}`)
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
        title="Tasks"
        subtitle="The next actions that move your projects forward."
      >
        <Button onClick={openCreate}>
          <Icon.Plus size={17} />
          Add task
        </Button>
      </PageHeader>

      <Card className="mb-6 flex flex-wrap items-end gap-4 p-4">
        <Field label="Status">
          <select
            className={`${inputClass} cursor-pointer`}
            value={statusFilter}
            onChange={(event) => {
              setStatusFilter(event.target.value)
              setPage(1)
            }}
          >
            <option value="">All</option>
            {STATUSES.map((status) => (
              <option key={status.value} value={status.value}>
                {status.label}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Priority">
          <select
            className={`${inputClass} cursor-pointer`}
            value={priorityFilter}
            onChange={(event) => {
              setPriorityFilter(event.target.value)
              setPage(1)
            }}
          >
            <option value="">All</option>
            {PRIORITIES.map((priority) => (
              <option key={priority.value} value={priority.value}>
                {priority.label}
              </option>
            ))}
          </select>
        </Field>
        {(statusFilter || priorityFilter) && (
          <Button
            variant="ghost"
            onClick={() => {
              setStatusFilter('')
              setPriorityFilter('')
              setPage(1)
            }}
          >
            Clear filters
          </Button>
        )}
      </Card>

      {editingId !== null && (
        <Card className="mb-6 p-5 sm:p-6">
          <div className="mb-5 flex items-center justify-between">
            <h2 className="text-lg font-bold tracking-[-0.02em]">
              {editingId === 'new' ? 'New task' : 'Edit task'}
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
                placeholder="Polish dashboard empty states"
              />
            </Field>
            <Field label="Description" hint="optional">
              <input
                className={inputClass}
                value={form.description}
                onChange={setField('description')}
                placeholder="What does done look like?"
              />
            </Field>
            <Field label="Status">
              <select
                className={`${inputClass} cursor-pointer`}
                value={form.status}
                onChange={setField('status')}
              >
                {STATUSES.map((status) => (
                  <option key={status.value} value={status.value}>
                    {status.label}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Priority">
              <select
                className={`${inputClass} cursor-pointer`}
                value={form.priority}
                onChange={setField('priority')}
              >
                {PRIORITIES.map((priority) => (
                  <option key={priority.value} value={priority.value}>
                    {priority.label}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Due date" hint="optional">
              <input
                type="date"
                className={inputClass}
                value={form.due_date}
                onChange={setField('due_date')}
              />
            </Field>
            <Field label="Project" hint="optional">
              <select
                className={`${inputClass} cursor-pointer`}
                value={form.project_id}
                onChange={setField('project_id')}
              >
                <option value="">No project</option>
                {projects.map((project) => (
                  <option key={project.id} value={project.id}>
                    {project.title}
                  </option>
                ))}
              </select>
            </Field>

            {formError && (
              <p className="text-sm text-danger sm:col-span-2" role="alert">
                {formError}
              </p>
            )}

            <div className="flex gap-3 sm:col-span-2">
              <Button type="submit" disabled={saving}>
                {saving ? 'Saving…' : editingId === 'new' ? 'Create task' : 'Save changes'}
              </Button>
              <Button variant="ghost" onClick={closeForm}>
                Cancel
              </Button>
            </div>
          </form>
        </Card>
      )}

      <ErrorNotice message={error} onRetry={load} />

      {loading && <Spinner label="Loading tasks…" />}

      {data && !loading && data.items.length === 0 && (
        <Card>
          <EmptyState
            title="No tasks here"
            hint={
              statusFilter || priorityFilter
                ? 'Nothing matches those filters — try clearing them.'
                : 'Add a task to start tracking your next actions.'
            }
          />
        </Card>
      )}

      {data && !loading && data.items.length > 0 && (
        <Card className="divide-y divide-line">
          {data.items.map((task) => {
            const overdue =
              task.due_date && task.due_date < todayIso && task.status !== 'done'
            const project = projects.find((p) => p.id === task.project_id)

            return (
              <div
                key={task.id}
                className="flex flex-wrap items-center gap-3 px-5 py-4 transition hover:bg-subtle"
              >
                <button
                  type="button"
                  onClick={() => cycleStatus(task)}
                  className="shrink-0"
                  title="Advance status"
                >
                  <Badge tone={STATUS_TONES[task.status] ?? 'neutral'}>
                    {task.status.replace('_', ' ')}
                  </Badge>
                </button>

                <div className="min-w-0 flex-1">
                  <p
                    className={`truncate text-sm font-semibold ${
                      task.status === 'done' ? 'text-faint line-through' : ''
                    }`}
                  >
                    {task.title}
                  </p>
                  <div className="mt-1 flex flex-wrap items-center gap-2 text-[11px] text-muted">
                    {task.description && <span className="truncate">{task.description}</span>}
                    {project && <span>· {project.title}</span>}
                    {task.due_date && (
                      <span className={overdue ? 'font-semibold text-danger' : ''}>
                        · due {task.due_date}
                        {overdue ? ' (overdue)' : ''}
                      </span>
                    )}
                  </div>
                </div>

                <Badge tone={PRIORITY_TONES[task.priority] ?? 'neutral'}>
                  {task.priority}
                </Badge>

                <div className="flex gap-2">
                  <Button variant="ghost" size="sm" onClick={() => openEdit(task)}>
                    Edit
                  </Button>
                  <Button variant="danger" size="sm" onClick={() => handleDelete(task)}>
                    Delete
                  </Button>
                </div>
              </div>
            )
          })}
        </Card>
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
