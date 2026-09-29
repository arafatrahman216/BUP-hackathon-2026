import { cn } from '../../utils/cn'
import styles from './Spinner.module.css'

export function Spinner({ size = 16, label = 'Loading', className }) {
  return (
    <span role="status" aria-label={label} className={cn(styles.spinner, className)} style={{ width: size, height: size }} />
  )
}
