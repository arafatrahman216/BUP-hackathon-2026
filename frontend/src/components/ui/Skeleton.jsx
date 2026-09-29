import { cn } from '../../utils/cn'
import styles from './Skeleton.module.css'

/** Shimmering placeholder block for loading states. */
export function Skeleton({ width = '100%', height = 14, radius, className, style }) {
  return <span aria-hidden="true" className={cn(styles.skeleton, className)} style={{ width, height, borderRadius: radius, ...style }} />
}
