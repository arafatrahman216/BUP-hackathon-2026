import styles from './PageHeader.module.css'

/** Title row at the top of every page. */
export function PageHeader({ title, description, actions, icon: Icon }) {
  return (
    <div className={styles.pageHeader}>
      <div className={styles.text}>
        <h1 className={styles.title}>
          {Icon && <Icon size={22} className={styles.icon} aria-hidden="true" />}
          {title}
        </h1>
        {description && <p className={styles.description}>{description}</p>}
      </div>
      {actions && <div className={styles.actions}>{actions}</div>}
    </div>
  )
}
