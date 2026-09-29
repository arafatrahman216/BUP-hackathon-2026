import { BookOpen, X } from 'lucide-react'
import { useEffect } from 'react'
import { NavLink } from 'react-router-dom'
import { API_BASE_URL, healthApi } from '../../api/api'
import { useAsync } from '../../hooks/useAsync'
import { cn } from '../../utils/cn'
import { Button } from '../ui/Button'
import { NAV_ITEMS } from './navigation'
import styles from './Sidebar.module.css'

const API_ORIGIN = (() => {
  try {
    return new URL(API_BASE_URL).origin
  } catch {
    return ''
  }
})()

function ApiStatus() {
  const { data, error, loading, refetch } = useAsync(({ signal }) => healthApi.check({ signal, timeout: 8000 }), [])

  useEffect(() => {
    const id = setInterval(refetch, 30_000)
    return () => clearInterval(id)
  }, [refetch])

  const state = error ? 'down' : data ? (data.database === 'ok' ? 'up' : 'degraded') : 'checking'
  const label = { up: 'API online', degraded: 'Database unavailable', down: 'API offline', checking: 'Checking API…' }[state]

  return (
    <button type="button" className={styles.status} onClick={refetch} title={`${API_BASE_URL} — click to re-check`} disabled={loading && !data && !error}>
      <span className={cn(styles.statusDot, styles[state])} aria-hidden="true" />
      <span className={styles.statusText}>
        <span className={styles.statusLabel}>{label}</span>
        <span className={styles.statusUrl}>{API_BASE_URL.replace(/^https?:\/\//, '')}</span>
      </span>
    </button>
  )
}

export function Sidebar({ open, onClose }) {
  return (
    <aside className={cn(styles.sidebar, open && styles.open)} aria-label="Primary">
      <div className={styles.brand}>
        <span className={styles.logo} aria-hidden="true">
          H
        </span>
        <div className={styles.brandText}>
          <span className={styles.brandName}>Hackathon</span>
          <span className={styles.brandSub}>Console</span>
        </div>
        <Button variant="ghost" size="sm" iconOnly leftIcon={X} aria-label="Close menu" onClick={onClose} className={styles.close} />
      </div>

      <nav className={styles.nav}>
        <p className={styles.sectionLabel}>Workspace</p>
        <ul>
          {NAV_ITEMS.map(({ to, label, icon: Icon, end }) => (
            <li key={to}>
              <NavLink to={to} end={end} onClick={onClose} className={({ isActive }) => cn(styles.link, isActive && styles.active)}>
                <Icon size={16} aria-hidden="true" />
                <span>{label}</span>
              </NavLink>
            </li>
          ))}
        </ul>

        {API_ORIGIN && (
          <>
            <p className={styles.sectionLabel}>Resources</p>
            <ul>
              <li>
                <a className={styles.link} href={`${API_ORIGIN}/docs`} target="_blank" rel="noreferrer">
                  <BookOpen size={16} aria-hidden="true" />
                  <span>API docs</span>
                </a>
              </li>
            </ul>
          </>
        )}
      </nav>

      <div className={styles.footer}>
        <ApiStatus />
      </div>
    </aside>
  )
}
