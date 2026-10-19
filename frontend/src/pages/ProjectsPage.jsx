/**
 * Projects: full CRUD plus the nested milestone resource.
 *
 * Plan: one list request for the page of projects (`/projects`), and one
 * milestone request per visible project (`/projects/{id}/milestones`) to fill
 * the progress column — the backend has no "include milestones" parameter and
 * per-project progress is only exposed for the dashboard's top 4, so this page
 * is the honest place to pay for the extra calls. Both are paginated, so the
 * request count is bounded by PAGE_SIZE, never by total rows.
 */

import { useCallback, useEffect, useState } from 'react'
import { api, formatApiError } from '../services/api'
import {
  accentFor,
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

const STATUSES = [
  { value: 'planning', label: 'Planning' },
  { value: 'in_progress', label: 'In progress' },
  { value: 'completed', label: 'Completed' },
]

const STATUS_TONES = {
  planning: 'neutral',
  in_progress: 'brand',
  completed: 'success',
}

const PAGE_SIZE = 6

const EMPTY_FORM = {
  title: '',
  description: '',
  tech_stack: '',
  repo_url: '',
  demo_url: '',
  status: 'in_progress',
}

/** Trimmed payload: optional text fields are only sent when non-empty. */
function buildPayload(form) {
  const payload = { title: form.title, status: form.status }
  if (form.description.trim()) payload.description = form.description.trim()
  if (form.tech_stack.trim()) payload.tech_stack = form.tech_stack.trim()
  if (form.repo_url.trim()) payload.repo_url = form.repo_url.trim()
  if (form.demo_url.trim()) payload.demo_url = form.demo_url.trim()
  return payload
}

export default function ProjectsPage() {
  const [data, setData] = useState(null) // { items, total, page, page_size }
  const [milestones, setMilestones] = useState({}) // projectId -> list response
  const [page, setPage] = useState(1)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)

  const [editingId, setEditingId] = useState(null) // project id or 'new'
  const [form, setForm] = useState(EMPTY_FORM)
  const [formError, setFormError] = useState(null)
  const [saving, setSaving] = useState(false)

  const [expandedId, setExpandedId] = useState(null)
  const [milestoneDraft, setMilestoneDraft] = useState('')
  const [milestoneError, setMilestoneError] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const list = await api.get(`/projects?page=${page}&page_size=${PAGE_SIZE}`)
      setData(list)
      // Bounded fan-out: one request per project on this page (never per row
      // in the database), run in parallel and settled independently so one
      // failing project doesn't blank the whole page.
      const pairs = await Promise.all(
        list.items.map(async (project) => {
          try {
            return [project.id, await api.get(`/projects/${project.id}/milestones?page_size=100`)]
          } catch {
            return [project.id, null]
          }
        }),
      )
      setMilestones(Object.fromEntries(pairs))
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

  function openEdit(project) {
    setEditingId(project.id)
    setForm({
      title: project.title,
      description: project.description ?? '',
      tech_stack: project.tech_stack ?? '',
      repo_url: project.repo_url ?? '',
      demo_url: project.demo_url ?? '',
      status: project.status,
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
        await api.post('/projects', buildPayload(form))
        setPage(1) // newest first
      } else {
        await api.patch(`/projects/${editingId}`, buildPayload(form))
      }
      closeForm()
      await load()
    } catch (err) {
      setFormError(formatApiError(err))
    } finally {
      setSaving(false)
    }
  }

  async function handleDelete(project) {
    if (!window.confirm(`Delete “${project.title}”? Its milestones go with it.`)) return
    setError(null)
    try {
      await api.delete(`/projects/${project.id}`)
      if (data.items.length === 1 && page > 1) setPage(page - 1)
      else await load()
    } catch (err) {
      setError(formatApiError(err))
    }
  }

  async function addMilestone(project) {
    if (!milestoneDraft.trim()) return
    setMilestoneError(null)
    try {
      await api.post(`/projects/${project.id}/milestones`, {
        title: milestoneDraft.trim(),
      })
      setMilestoneDraft('')
      await load()
    } catch (err) {
      setMilestoneError(formatApiError(err))
    }
  }

  async function toggleMilestone(project, milestone) {
    setMilestoneError(null)
    try {
      await api.patch(
        `/projects/${project.id}/milestones/${milestone.id}`,
        { is_completed: !milestone.is_completed },
      )
      await load()
    } catch (err) {
      setMilestoneError(formatApiError(err))
    }
  }

  async function deleteMilestone(project, milestone) {
    setMilestoneError(null)
    try {
      await api.delete(`/projects/${project.id}/milestones/${milestone.id}`)
      await load()
    } catch (err) {
      setMilestoneError(formatApiError(err))
    }
  }

  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1

  return (
    <>
      <PageHeader
        eyebrow="Workspace"
        title="Projects"
        subtitle="What you're building, and how far along each one is."
      >
        <Button onClick={openCreate}>
          <Icon.Plus size={17} />
          Add project
        </Button>
      </PageHeader>

      {editingId !== null && (
        <Card className="mb-6 p-5 sm:p-6">
          <div className="mb-5 flex items-center justify-between">
            <h2 className="text-lg font-bold tracking-[-0.02em]">
              {editingId === 'new' ? 'New project' : 'Edit project'}
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
                placeholder="Taskflow API"
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
            <Field label="Tech stack" hint="optional">
              <input
                className={inputClass}
                value={form.tech_stack}
                onChange={setField('tech_stack')}
                maxLength={300}
                placeholder="React, FastAPI, PostgreSQL"
              />
            </Field>
            <Field label="Description" hint="optional">
              <input
                className={inputClass}
                value={form.description}
                onChange={setField('description')}
                placeholder="Backend service for task scheduling"
              />
            </Field>
            <Field label="Repository URL" hint="optional">
              <input
                type="url"
                className={inputClass}
                value={form.repo_url}
                onChange={setField('repo_url')}
                placeholder="https://github.com/…"
              />
            </Field>
            <Field label="Demo URL" hint="optional">
              <input
                type="url"
                className={inputClass}
                value={form.demo_url}
                onChange={setField('demo_url')}
                placeholder="https://…"
              />
            </Field>

            {formError && (
              <p className="text-sm text-danger sm:col-span-2" role="alert">
                {formError}
              </p>
            )}

            <div className="flex gap-3 sm:col-span-2">
              <Button type="submit" disabled={saving}>
                {saving ? 'Saving…' : editingId === 'new' ? 'Create project' : 'Save changes'}
              </Button>
              <Button variant="ghost" onClick={closeForm}>
                Cancel
              </Button>
            </div>
          </form>
        </Card>
      )}

      <ErrorNotice message={error} onRetry={load} />

      {loading && <Spinner label="Loading projects…" />}

      {data && !loading && data.items.length === 0 && (
        <Card>
          <EmptyState
            title="No projects yet"
            hint="Add your first project to start tracking milestones."
          />
        </Card>
      )}

      {data && !loading && data.items.length > 0 && (
        <div className="space-y-4">
          {data.items.map((project, index) => {
            const accent = accentFor(project.title, index)
            const milestoneData = milestones[project.id]
            const items = milestoneData?.items ?? []
            const completed = items.filter((m) => m.is_completed).length
            const percent = items.length ? (completed / items.length) * 100 : 0
            const isExpanded = expandedId === project.id

            return (
              <Card key={project.id} className="p-5 sm:p-6">
                <div className="flex flex-wrap items-start gap-4">
                  <div
                    className="grid h-11 w-11 shrink-0 place-items-center rounded-xl text-sm font-bold text-white"
                    style={{ backgroundColor: accent }}
                  >
                    {project.title.charAt(0).toUpperCase()}
                  </div>

                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <h3 className="truncate text-base font-semibold">{project.title}</h3>
                      <Badge tone={STATUS_TONES[project.status] ?? 'neutral'}>
                        {project.status.replace('_', ' ')}
                      </Badge>
                    </div>
                    {project.description && (
                      <p className="mt-1 text-xs text-muted">{project.description}</p>
                    )}
                    {project.tech_stack && (
                      <p className="mt-1 text-xs text-faint">{project.tech_stack}</p>
                    )}
                    <div className="mt-3 max-w-sm">
                      <div className="mb-1.5 flex justify-between text-[10px] font-semibold">
                        <span className="text-[#999dac]">Milestones</span>
                        <span>
                          {items.length ? `${completed}/${items.length}` : 'none yet'}
                        </span>
                      </div>
                      <ProgressBar percent={percent} color={accent} />
                    </div>
                  </div>

                  <div className="flex flex-wrap items-center gap-2">
                    {project.repo_url && (
                      <a href={project.repo_url} target="_blank" rel="noreferrer">
                        <Button variant="ghost" size="sm">
                          Repo
                        </Button>
                      </a>
                    )}
                    {project.demo_url && (
                      <a href={project.demo_url} target="_blank" rel="noreferrer">
                        <Button variant="ghost" size="sm">
                          Demo
                        </Button>
                      </a>
                    )}
                    <Button
                      variant="soft"
                      size="sm"
                      onClick={() => setExpandedId(isExpanded ? null : project.id)}
                    >
                      {isExpanded ? 'Hide milestones' : 'Milestones'}
                    </Button>
                    <Button variant="ghost" size="sm" onClick={() => openEdit(project)}>
                      Edit
                    </Button>
                    <Button variant="danger" size="sm" onClick={() => handleDelete(project)}>
                      Delete
                    </Button>
                  </div>
                </div>

                {isExpanded && (
                  <div className="mt-5 border-t border-line pt-4">
                    {items.length === 0 ? (
                      <p className="text-xs text-muted">No milestones yet.</p>
                    ) : (
                      <ul className="space-y-2">
                        {items.map((milestone) => (
                          <li
                            key={milestone.id}
                            className="flex items-center gap-3 rounded-xl px-2 py-2 hover:bg-subtle"
                          >
                            <input
                              type="checkbox"
                              className="h-4 w-4 accent-[#635bff]"
                              checked={milestone.is_completed}
                              onChange={() => toggleMilestone(project, milestone)}
                              aria-label={`Toggle ${milestone.title}`}
                            />
                            <span
                              className={`flex-1 text-sm ${
                                milestone.is_completed ? 'text-faint line-through' : ''
                              }`}
                            >
                              {milestone.title}
                            </span>
                            {milestone.due_date && (
                              <span className="text-[11px] text-muted">
                                due {milestone.due_date}
                              </span>
                            )}
                            <button
                              type="button"
                              className="text-xs font-semibold text-danger"
                              onClick={() => deleteMilestone(project, milestone)}
                            >
                              Remove
                            </button>
                          </li>
                        ))}
                      </ul>
                    )}

                    <div className="mt-4 flex flex-wrap gap-2">
                      <input
                        className={`${inputClass} max-w-xs`}
                        value={milestoneDraft}
                        onChange={(event) => setMilestoneDraft(event.target.value)}
                        placeholder="New milestone…"
                        maxLength={200}
                        onKeyDown={(event) => {
                          if (event.key === 'Enter') {
                            event.preventDefault()
                            addMilestone(project)
                          }
                        }}
                      />
                      <Button onClick={() => addMilestone(project)} size="md">
                        Add
                      </Button>
                    </div>
                    {milestoneError && (
                      <p className="mt-2 text-xs text-danger" role="alert">
                        {milestoneError}
                      </p>
                    )}
                  </div>
                )}
              </Card>
            )
          })}
        </div>
      )}

      {data && data.total > 0 && (
        <div className="mt-6 flex items-center justify-center gap-4">
          <Button
            variant="ghost"
            disabled={page <= 1}
            onClick={() => setPage((p) => p - 1)}
          >
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
