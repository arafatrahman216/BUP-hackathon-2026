import { Link } from 'react-router-dom'
import { Skeleton } from '../../components/ui/Skeleton'
import { cn } from '../../utils/cn'
import styles from './StatCard.module.css'

/** One KPI tile. `tone` colors the status dot: success | warning | danger | accent | neutral. */
export function StatCard({ icon: Icon, label, value, meta, tone = 'neutral', loading = false, to }) {
  const content = (
    <>
      <div className={styles.top}>
        <span className={styles.label}>
          {Icon && <Icon size={15} aria-hidden="true" />}
          {label}
        </span>
        <span className={cn(styles.dot, styles[tone])} aria-hidden="true" />
      </div>
      {loading ? (
        <>
          <Skeleton width="55%" height={26} className={styles.skeletonValue} />
          <Skeleton width="70%" height={12} />
        </>
      ) : (
        <>
          <p className={styles.value}>{value}</p>
          {meta && <p className={styles.meta}>{meta}</p>}
        </>
      )}
    </>
  )

  return to ? (
    <Link to={to} className={cn(styles.card, styles.link)}>
      {content}
    </Link>
  ) : (
    <div className={styles.card}>{content}</div>
  )
}
