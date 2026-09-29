import { lazy } from 'react'
import { Route, Routes } from 'react-router-dom'
import { AppLayout } from './components/layout/AppLayout'

// Pages are code-split: each is downloaded the first time it's visited
// (AppLayout shows a spinner meanwhile). Add a page: lazy() it here, add a
// <Route>, then add it to components/layout/navigation.js.
const DashboardPage = lazy(() => import('./pages/Dashboard/DashboardPage'))
const ItemsPage = lazy(() => import('./pages/Items/ItemsPage'))
const AIPlaygroundPage = lazy(() => import('./pages/AIPlayground/AIPlaygroundPage'))
const FilesPage = lazy(() => import('./pages/Files/FilesPage'))
const NotFoundPage = lazy(() => import('./pages/NotFound/NotFoundPage'))

export default function App() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<DashboardPage />} />
        <Route path="items" element={<ItemsPage />} />
        <Route path="ai" element={<AIPlaygroundPage />} />
        <Route path="files" element={<FilesPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  )
}
