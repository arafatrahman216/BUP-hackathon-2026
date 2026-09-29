import { Suspense, useEffect, useState } from 'react'
import { Outlet } from 'react-router-dom'
import { Spinner } from '../ui/Spinner'
import styles from './AppLayout.module.css'
import { Header } from './Header'
import { Sidebar } from './Sidebar'

/** Shell for every page: sidebar (drawer on mobile) + sticky header + content. */
export function AppLayout() {
  const [mobileOpen, setMobileOpen] = useState(false)
  useEffect(() => {
    if (!mobileOpen) return undefined
    const onKey = (e) => e.key === 'Escape' && setMobileOpen(false)
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [mobileOpen])

  return (
    <div className={styles.shell}>
      <a href="#main" className={styles.skipLink}>
        Skip to content
      </a>
      <Sidebar open={mobileOpen} onClose={() => setMobileOpen(false)} />
      {mobileOpen && <div className={styles.scrim} onClick={() => setMobileOpen(false)} aria-hidden="true" />}
      <div className={styles.main}>
        <Header onMenuClick={() => setMobileOpen(true)} menuOpen={mobileOpen} />
        <main id="main" className={styles.content} tabIndex={-1}>
          <Suspense
            fallback={
              <div className={styles.pageLoading}>
                <Spinner size={22} label="Loading page" />
              </div>
            }
          >
            <Outlet />
          </Suspense>
        </main>
      </div>
    </div>
  )
}
