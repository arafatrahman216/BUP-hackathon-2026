import { Route, Routes } from 'react-router-dom'
import { AppLayout } from './components/layout'
import HomePage from './pages/Home/HomePage'
import NotFoundPage from './pages/NotFound/NotFoundPage'

// Add a page: create pages/<Name>/<Name>Page.jsx, then add a <Route> here
// (and a link in components/layout/AppLayout.jsx if it belongs in the nav).
export default function App() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<HomePage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  )
}
