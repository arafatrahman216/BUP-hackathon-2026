import { Link, Outlet } from 'react-router-dom'
import styles from './AppLayout.module.css'

export function AppLayout() {
  return (
    <div className={styles.shell}>
      <header className={styles.header}>
        <Link to="/" className={styles.brand}>
          BUP Fuel Operations
        </Link>
        <nav className={styles.nav}>
          <Link to="/">Operator console</Link>
          <Link to="/pipeline">Pipeline</Link>
          <Link to="/status">Backend status</Link>
        </nav>
      </header>
      <main className={styles.main}>
        <Outlet />
      </main>
    </div>
  )
}
