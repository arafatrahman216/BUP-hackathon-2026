import { Route, Routes } from 'react-router-dom'
import { AppLayout } from './components/layout'
import ConsolePage from './pages/Console/ConsolePage'
import DashboardPage from './pages/Dashboard/DashboardPage'
import HomePage from './pages/Home/HomePage'
import NotFoundPage from './pages/NotFound/NotFoundPage'

// Add a page: create pages/<Name>/<Name>Page.jsx, then add a <Route> here
// (and a link in components/layout/AppLayout.jsx if it belongs in the nav).
// The operator console has its own full-page layout; the technical pages share AppLayout.
export default function App() {
  return (
    <Routes>
      <Route index element={<ConsolePage />} />
      <Route element={<AppLayout />}>
        <Route path="pipeline" element={<DashboardPage />} />
        <Route path="status" element={<HomePage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  )
}
