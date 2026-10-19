/**
 * Route table. Everything renders inside the Layout shell; the product pages
 * are session-gated by ProtectedRoute (which remembers where the user was
 * headed and returns them there after login).
 */

import { Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import ProtectedRoute from './components/ProtectedRoute'
import AnalyticsPage from './pages/AnalyticsPage'
import DashboardPage from './pages/DashboardPage'
import DsaProblemsPage from './pages/DsaProblemsPage'
import GoalsPage from './pages/GoalsPage'
import LoginPage from './pages/LoginPage'
import ProjectsPage from './pages/ProjectsPage'
import RegisterPage from './pages/RegisterPage'
import TasksPage from './pages/TasksPage'

/** Wraps a page element in the session gate without repeating the JSX. */
function guarded(element) {
  return <ProtectedRoute>{element}</ProtectedRoute>
}

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={guarded(<DashboardPage />)} />
        <Route path="/projects" element={guarded(<ProjectsPage />)} />
        <Route path="/dsa-problems" element={guarded(<DsaProblemsPage />)} />
        <Route path="/tasks" element={guarded(<TasksPage />)} />
        <Route path="/goals" element={guarded(<GoalsPage />)} />
        <Route path="/analytics" element={guarded(<AnalyticsPage />)} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
      </Route>
    </Routes>
  )
}
