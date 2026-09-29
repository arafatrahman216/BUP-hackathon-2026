import { FolderOpen, LayoutDashboard, Package, Sparkles } from 'lucide-react'

/** Sidebar entries. Add a page: create it in src/pages, add a <Route> in App.jsx, add it here. */
export const NAV_ITEMS = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard, end: true, description: 'Backend health, database and AI providers at a glance.' },
  { to: '/items', label: 'Items', icon: Package, description: 'Full CRUD example backed by the /items endpoints.' },
  { to: '/ai', label: 'AI Playground', icon: Sparkles, description: 'Chat with the provider chain and inspect fallbacks.' },
  { to: '/files', label: 'Files', icon: FolderOpen, description: 'Upload to Supabase Storage and share signed URLs.' },
]
