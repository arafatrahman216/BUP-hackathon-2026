import { Link } from 'react-router-dom'
import styles from './NotFoundPage.module.css'

export default function NotFoundPage() {
  return (
    <div className={styles.wrap}>
      <h1>404</h1>
      <p>Page not found.</p>
      <Link to="/">Back home</Link>
    </div>
  )
}
