/**
 * DSA Problems: paginated list (server-side), create form, delete.
 *
 * Platform/difficulty option lists mirror the backend Literals exactly —
 * a mismatch surfaces as a 422 rendered from the server's validation detail.
 * Pagination is server-driven: page/page_size come back in the response
 * envelope alongside `total`, which is what makes Next/Prev honest.
 */

import { useCallback, useEffect, useState } from 'react'
import { api, formatApiError } from '../services/api'

const PLATFORMS = ['LeetCode', 'Codeforces', 'HackerRank', 'NeetCode', 'Other']
const DIFFICULTIES = ['Easy', 'Medium', 'Hard']
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

  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState(EMPTY_FORM)
  const [formError, setFormError] = useState(null)
  const [saving, setSaving] = useState(false)

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

  async function handleCreate(event) {
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

      await api.post('/dsa-problems', payload)
      setForm(EMPTY_FORM)
      setShowForm(false)
      setPage(1) // newest records sort first
      await load()
    } catch (err) {
      setFormError(formatApiError(err))
    } finally {
      setSaving(false)
    }
  }

  async function handleDelete(id) {
    if (!window.confirm('Delete this record?')) return
    setError(null)
    try {
      await api.delete(`/dsa-problems/${id}`)
      // If we just deleted the last item on this page, step back one page
      if (data.items.length === 1 && page > 1) setPage(page - 1)
      else await load()
    } catch (err) {
      setError(formatApiError(err))
    }
  }

  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1

  return (
    <>
      <div className="page-header">
        <h1>DSA Problems</h1>
        <button type="button" className="btn btn-primary" onClick={() => setShowForm((v) => !v)}>
          {showForm ? 'Close' : '+ Add problem'}
        </button>
      </div>

      {showForm && (
        <div className="panel">
          <h3>Log a problem</h3>
          <form onSubmit={handleCreate} className="form form-grid">
            <label>
              Title *
              <input type="text" value={form.title} onChange={setField('title')} required maxLength={200} />
            </label>
            <label>
              Topic *
              <input
                type="text"
                value={form.topic}
                onChange={setField('topic')}
                placeholder="Arrays, DP, Graphs…"
                required
                maxLength={100}
              />
            </label>
            <label>
              Platform
              <select value={form.platform} onChange={setField('platform')}>
                {PLATFORMS.map((platform) => (
                  <option key={platform}>{platform}</option>
                ))}
              </select>
            </label>
            <label>
              Difficulty
              <select value={form.difficulty} onChange={setField('difficulty')}>
                {DIFFICULTIES.map((difficulty) => (
                  <option key={difficulty}>{difficulty}</option>
                ))}
              </select>
            </label>
            <label>
              Problem URL (optional)
              <input
                type="url"
                value={form.problem_url}
                onChange={setField('problem_url')}
                placeholder="https://…"
              />
            </label>
            <label>
              Notes (optional)
              <input type="text" value={form.notes} onChange={setField('notes')} />
            </label>

            {formError && (
              <p className="form-error" role="alert">
                {formError}
              </p>
            )}

            <div className="form-actions">
              <button type="submit" className="btn btn-primary" disabled={saving}>
                {saving ? 'Saving…' : 'Save'}
              </button>
            </div>
          </form>
        </div>
      )}

      {loading && <div className="loading-screen">Loading problems…</div>}

      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}

      {data && !loading && (
        <>
          {data.items.length === 0 ? (
            <div className="panel empty-state">
              <p>No problems logged yet.</p>
              <p className="muted">Hit “+ Add problem” to start the streak.</p>
            </div>
          ) : (
            <div className="panel table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Title</th>
                    <th>Topic</th>
                    <th>Platform</th>
                    <th>Difficulty</th>
                    <th>Solved</th>
                    <th aria-label="Actions" />
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((problem) => (
                    <tr key={problem.id}>
                      <td>
                        {problem.problem_url ? (
                          <a href={problem.problem_url} target="_blank" rel="noreferrer">
                            {problem.title}
                          </a>
                        ) : (
                          problem.title
                        )}
                      </td>
                      <td>{problem.topic}</td>
                      <td>{problem.platform}</td>
                      <td>
                        <span className={`badge badge-${problem.difficulty.toLowerCase()}`}>
                          {problem.difficulty}
                        </span>
                      </td>
                      <td>{problem.solved_date}</td>
                      <td>
                        <button
                          type="button"
                          className="btn btn-ghost btn-small"
                          onClick={() => handleDelete(problem.id)}
                        >
                          Delete
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <div className="pagination">
            <button
              type="button"
              className="btn btn-ghost"
              disabled={page <= 1}
              onClick={() => setPage(page - 1)}
            >
              ← Prev
            </button>
            <span className="muted">
              Page {data.page} of {totalPages} · {data.total} total
            </span>
            <button
              type="button"
              className="btn btn-ghost"
              disabled={page >= totalPages}
              onClick={() => setPage(page + 1)}
            >
              Next →
            </button>
          </div>
        </>
      )}
    </>
  )
}
