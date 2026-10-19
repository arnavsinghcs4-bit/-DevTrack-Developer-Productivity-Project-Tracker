/**
 * DSA Problems ("LeetCode" in the nav): paginated list, create, edit, delete.
 *
 * Platform/difficulty option lists mirror the backend Literals exactly — a
 * mismatch surfaces as a 422 rendered from the server's validation detail.
 * Pagination and search are deliberately NOT combined: `page` is server-driven
 * so Next/Prev stay honest, while the text filter narrows the current page
 * client-side (the API has no search parameter; adding one would be a backend
 * branch, not a redesign).
 */

import { useCallback, useEffect, useMemo, useState } from 'react'
import { api, formatApiError } from '../services/api'
import { useSearchParams } from 'react-router-dom'
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

const PLATFORMS = ['LeetCode', 'Codeforces', 'HackerRank', 'NeetCode', 'Other']
const DIFFICULTIES = ['Easy', 'Medium', 'Hard']
const DIFFICULTY_TONES = { Easy: 'success', Medium: 'warning', Hard: 'danger' }
const PAGE_SIZE = 10

const EMPTY_FORM = {
  title: '',
  platform: 'LeetCode',
  topic: '',
  difficulty: 'Easy',
  problem_url: '',
  notes: '',
}

export default function DsaProblemsPage() {
  const [data, setData] = useState(null) // { items, total, page, page_size }
  const [page, setPage] = useState(1)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)
  const [query, setQuery] = useState('')
  const [searchParams, setSearchParams] = useSearchParams()

  const [editingId, setEditingId] = useState(null)
  const [form, setForm] = useState(EMPTY_FORM)
  const [formError, setFormError] = useState(null)
  const [saving, setSaving] = useState(false)

  // The header's "Add progress" button lands here with ?new=1; opening the
  // form from the URL keeps that shortcut a plain link (no cross-page state).
  useEffect(() => {
    if (searchParams.get('new') === '1') {
      setEditingId('new')
      setForm(EMPTY_FORM)
      setFormError(null)
      setSearchParams({}, { replace: true })
    }
  }, [searchParams, setSearchParams])

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setData(await api.get(`/dsa-problems?page=${page}&page_size=${PAGE_SIZE}`))
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

  function openEdit(problem) {
    setEditingId(problem.id)
    setForm({
      title: problem.title,
      platform: problem.platform,
      topic: problem.topic,
      difficulty: problem.difficulty,
      problem_url: problem.problem_url ?? '',
      notes: problem.notes ?? '',
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
      const payload = {
        title: form.title,
        platform: form.platform,
        topic: form.topic,
        difficulty: form.difficulty,
      }
      // Optional fields: only send them when non-empty, and never send
      // ownership fields — the server assigns user_id from the JWT.
      if (form.problem_url.trim()) payload.problem_url = form.problem_url.trim()
      if (form.notes.trim()) payload.notes = form.notes.trim()

      if (editingId === 'new') {
        await api.post('/dsa-problems', payload)
        setPage(1) // newest records sort first
      } else {
        await api.patch(`/dsa-problems/${editingId}`, payload)
      }
      closeForm()
      await load()
    } catch (err) {
      setFormError(formatApiError(err))
    } finally {
      setSaving(false)
    }
  }

  async function handleDelete(problem) {
    if (!window.confirm(`Delete “${problem.title}”?`)) return
    setError(null)
    try {
      await api.delete(`/dsa-problems/${problem.id}`)
      // If we just deleted the last item on this page, step back one page
      if (data.items.length === 1 && page > 1) setPage(page - 1)
      else await load()
    } catch (err) {
      setError(formatApiError(err))
    }
  }

  const visible = useMemo(() => {
    if (!data) return []
    const needle = query.trim().toLowerCase()
    if (!needle) return data.items
    return data.items.filter((problem) =>
      [problem.title, problem.topic, problem.platform, problem.difficulty]
        .join(' ')
        .toLowerCase()
        .includes(needle),
    )
  }, [data, query])

  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1

  return (
    <>
      <PageHeader
        eyebrow="LeetCode"
        title="DSA Problems"
        subtitle="Every problem you've logged, newest first."
      >
        <Button onClick={openCreate}>
          <Icon.Plus size={17} />
          Add problem
        </Button>
      </PageHeader>

      {editingId !== null && (
        <Card className="mb-6 p-5 sm:p-6">
          <div className="mb-5 flex items-center justify-between">
            <h2 className="text-lg font-bold tracking-[-0.02em]">
              {editingId === 'new' ? 'Log a problem' : 'Edit problem'}
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
                placeholder="Two Sum"
              />
            </Field>
            <Field label="Topic">
              <input
                className={inputClass}
                value={form.topic}
                onChange={setField('topic')}
                placeholder="Arrays, DP, Graphs…"
                required
                maxLength={100}
              />
            </Field>
            <Field label="Platform">
              <select
                className={`${inputClass} cursor-pointer`}
                value={form.platform}
                onChange={setField('platform')}
              >
                {PLATFORMS.map((platform) => (
                  <option key={platform}>{platform}</option>
                ))}
              </select>
            </Field>
            <Field label="Difficulty">
              <select
                className={`${inputClass} cursor-pointer`}
                value={form.difficulty}
                onChange={setField('difficulty')}
              >
                {DIFFICULTIES.map((difficulty) => (
                  <option key={difficulty}>{difficulty}</option>
                ))}
              </select>
            </Field>
            <Field label="Problem URL" hint="optional">
              <input
                type="url"
                className={inputClass}
                value={form.problem_url}
                onChange={setField('problem_url')}
                placeholder="https://…"
              />
            </Field>
            <Field label="Notes" hint="optional">
              <input
                className={inputClass}
                value={form.notes}
                onChange={setField('notes')}
                placeholder="Key insight, complexity…"
              />
            </Field>

            {formError && (
              <p className="text-sm text-danger sm:col-span-2" role="alert">
                {formError}
              </p>
            )}

            <div className="flex gap-3 sm:col-span-2">
              <Button type="submit" disabled={saving}>
                {saving ? 'Saving…' : editingId === 'new' ? 'Save problem' : 'Save changes'}
              </Button>
              <Button variant="ghost" onClick={closeForm}>
                Cancel
              </Button>
            </div>
          </form>
        </Card>
      )}

      <Card className="mb-6 flex flex-wrap items-end gap-4 p-4">
        <Field label="Filter this page" hint="title, topic, platform">
          <input
            className={`${inputClass} sm:w-80`}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search problems…"
            aria-label="Filter problems on this page"
          />
        </Field>
        {query && (
          <Button variant="ghost" onClick={() => setQuery('')}>
            Clear
          </Button>
        )}
      </Card>

      <ErrorNotice message={error} onRetry={load} />

      {loading && <Spinner label="Loading problems…" />}

      {data && !loading && data.items.length === 0 && (
        <Card>
          <EmptyState
            title="No problems logged yet"
            hint="Hit “Add problem” to start the streak."
          />
        </Card>
      )}

      {data && !loading && data.items.length > 0 && visible.length === 0 && (
        <Card>
          <EmptyState
            title="Nothing on this page matches"
            hint="The filter only covers the current page — clear it or go to the next."
          />
        </Card>
      )}

      {data && !loading && visible.length > 0 && (
        <Card className="overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-line">
                  {['Title', 'Topic', 'Platform', 'Difficulty', 'Solved', ''].map(
                    (heading) => (
                      <th
                        key={heading}
                        className="px-5 py-3 text-left text-[11px] font-bold uppercase tracking-[0.08em] text-muted"
                      >
                        {heading}
                      </th>
                    ),
                  )}
                </tr>
              </thead>
              <tbody>
                {visible.map((problem) => (
                  <tr
                    key={problem.id}
                    className="border-b border-line last:border-0 transition hover:bg-subtle"
                  >
                    <td className="px-5 py-3 font-semibold">
                      {problem.problem_url ? (
                        <a
                          href={problem.problem_url}
                          target="_blank"
                          rel="noreferrer"
                          className="text-brand hover:underline"
                        >
                          {problem.title}
                        </a>
                      ) : (
                        problem.title
                      )}
                    </td>
                    <td className="px-5 py-3 text-muted">{problem.topic}</td>
                    <td className="px-5 py-3 text-muted">{problem.platform}</td>
                    <td className="px-5 py-3">
                      <Badge tone={DIFFICULTY_TONES[problem.difficulty] ?? 'neutral'}>
                        {problem.difficulty}
                      </Badge>
                    </td>
                    <td className="px-5 py-3 text-muted">{problem.solved_date}</td>
                    <td className="px-5 py-3">
                      <div className="flex justify-end gap-2">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => openEdit(problem)}
                        >
                          Edit
                        </Button>
                        <Button
                          variant="danger"
                          size="sm"
                          onClick={() => handleDelete(problem)}
                        >
                          Delete
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
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
