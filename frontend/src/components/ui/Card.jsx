import { cn } from '../../utils/cn'
import styles from './Card.module.css'

export function Card({ title, actions, className, children }) {
  return (
    <section className={cn(styles.card, className)}>
      {(title || actions) && (
        <header className={styles.header}>
          {title && <h2 className={styles.title}>{title}</h2>}
          {actions}
        </header>
      )}
      <div className={styles.body}>{children}</div>
    </section>
  )
}
