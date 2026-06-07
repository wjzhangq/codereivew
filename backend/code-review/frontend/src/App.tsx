/* App.tsx — 路由 */
import { Routes, Route, Navigate, useParams } from 'react-router-dom'
import { useAuthStore } from './store/auth'
import AppLayout from './layout/AppLayout'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import ProjectOverview from './pages/ProjectOverview'
import Security from './pages/Security'
import Reports from './pages/Reports'
import QA from './pages/QA'
import Wiki from './pages/Wiki'
import Settings from './pages/Settings'
import Jobs from './pages/Jobs'
import Users from './pages/Users'

function RequireAuth({ children }: { children: JSX.Element }) {
  const token = useAuthStore((s) => s.token)
  return token ? children : <Navigate to="/login" replace />
}

/** 项目子标签分发 */
function ProjectTab() {
  const { tab } = useParams()
  switch (tab) {
    case 'security': return <Security />
    case 'reports': return <Reports />
    case 'qa': return <QA />
    case 'wiki': return <Wiki />
    case 'settings': return <Settings />
    default: return <ProjectOverview />
  }
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route element={<RequireAuth><AppLayout /></RequireAuth>}>
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/projects/:id/:tab" element={<ProjectTab />} />
        <Route path="/projects/:id" element={<Navigate to="overview" replace />} />
        <Route path="/jobs" element={<Jobs />} />
        <Route path="/users" element={<Users />} />
      </Route>
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  )
}
