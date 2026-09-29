import { hours, liters, num, RISK } from '../../utils/format'
import styles from './Dashboard.module.css'
import { StatusBadge } from './StatusBadge'

/** One fuel at a station: level bar (risk-colored), incoming ghost segment, and the numbers. */
export function FuelGauge({ fuel, tickMinutes }) {
  const risk = RISK[fuel.risk] ?? RISK.unknown
  const cap = fuel.capacity || 1
  const level = Math.min(100, (fuel.inventory / cap) * 100)
  const incoming = Math.min(100 - level, (fuel.incoming / cap) * 100)
  return (
    <div className={styles.gauge}>
      <div className={styles.gaugeHead}>
        <span className={styles.fuel}>{fuel.fuel_type}</span>
        <StatusBadge meta={risk} />
      </div>
      <div className={styles.track} role="img"
           aria-label={`${fuel.fuel_type}: ${liters(fuel.inventory)} of ${liters(fuel.capacity)}, ${risk.label}`}>
        <div className={styles.fill} style={{ width: `${level}%`, background: risk.color }} />
        {incoming > 0 && <div className={styles.incoming} style={{ width: `${incoming}%` }} title={`${liters(fuel.incoming)} on the way`} />}
      </div>
      <div className={styles.gaugeMeta}>
        <span>{liters(fuel.inventory)} / {liters(fuel.capacity)}</span>
        <span>{num(fuel.rate_per_tick)} L/tick</span>
        <span>empty in {fuel.ticks_until_empty === null ? '–' : hours(fuel.ticks_until_empty, tickMinutes)}</span>
        {fuel.incoming > 0 && <span>+{liters(fuel.incoming)} incoming</span>}
      </div>
    </div>
  )
}
