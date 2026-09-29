import { Link, Outlet } from 'react-router-dom'
import styles from './AppLayout.module.css'

export function AppLayout() {
  return (
    <div className={styles.shell}>
      <header className={styles.header}>
        <Link to="/" className={styles.brand}>
          Hackathon App
        </Link>
        <nav className={styles.nav}>
          <Link to="/">Home</Link>
        </nav>
      </header>
      <main className={styles.main}>
        <Outlet />
      </main>
    </div>
  )
}
