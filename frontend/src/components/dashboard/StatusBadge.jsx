import styles from './Dashboard.module.css'

/** Icon + label + status color. Never color alone. */
export function StatusBadge({ meta, label, title }) {
  return (
    <span className={styles.badge} title={title}>
      <span aria-hidden="true" style={{ color: meta.color }}>{meta.icon}</span>
      {label ?? meta.label}
    </span>
  )
}
