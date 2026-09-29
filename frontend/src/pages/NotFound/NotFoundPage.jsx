import { ArrowLeft, Compass } from 'lucide-react'
import { Link, useLocation } from 'react-router-dom'
import { EmptyState } from '../../components/ui/EmptyState'
import styles from './NotFoundPage.module.css'

export default function NotFoundPage() {
  const { pathname } = useLocation()
  return (
    <div className={styles.wrap}>
      <p className={styles.code}>404</p>
      <EmptyState
        icon={Compass}
        title="Page not found"
        description={
          <>
            Nothing lives at <code>{pathname}</code>. It may have moved, or the link is wrong.
          </>
        }
        action={
          <Link to="/" className={styles.link}>
            <ArrowLeft size={16} aria-hidden="true" /> Back to dashboard
          </Link>
        }
      />
    </div>
  )
}
