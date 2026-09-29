import { KeyRound, Menu, Moon, Sun } from 'lucide-react'
import { matchPath, useLocation } from 'react-router-dom'
import { useAuth } from '../../hooks/useAuth'
import { useTheme } from '../../hooks/useTheme'
import { Badge } from '../ui/Badge'
import { Button } from '../ui/Button'
import styles from './Header.module.css'
import { NAV_ITEMS } from './navigation'

export function Header({ onMenuClick, menuOpen }) {
  const { pathname } = useLocation()
  const { theme, toggle } = useTheme()
  const { isAuthenticated } = useAuth()
  const current = NAV_ITEMS.find((item) => matchPath({ path: item.to, end: Boolean(item.end) }, pathname))

  return (
    <header className={styles.header}>
      <Button variant="ghost" iconOnly leftIcon={Menu} aria-label="Open menu" aria-expanded={menuOpen} onClick={onMenuClick} className={styles.menu} />
      <nav aria-label="Breadcrumb" className={styles.breadcrumb}>
        <span className={styles.crumbRoot}>Console</span>
        <span className={styles.sep} aria-hidden="true">
          /
        </span>
        <span className={styles.crumbCurrent} aria-current="page">
          {current?.label ?? 'Not found'}
        </span>
      </nav>
      <div className={styles.actions}>
        <Badge variant={isAuthenticated ? 'success' : 'neutral'} icon={KeyRound} title={isAuthenticated ? 'A bearer token is attached to every request' : 'No auth token set'} className={styles.auth}>
          {isAuthenticated ? 'Token set' : 'Guest'}
        </Badge>
        <Button
          variant="ghost"
          iconOnly
          leftIcon={theme === 'dark' ? Sun : Moon}
          aria-label={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
          title="Toggle theme"
          onClick={toggle}
        />
      </div>
    </header>
  )
}
