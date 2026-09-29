import { liters, RISK } from '../../utils/format'
import styles from './Dashboard.module.css'
import { StatusBadge } from './StatusBadge'

export function DepotCard({ depot }) {
  const limit = depot.dispatch_capacity_per_tick || 1
  return (
    <section className={styles.panel}>
      <header className={styles.panelHead}>
        <h3>{depot.name}</h3>
        <StatusBadge meta={depot.status === 'OPEN' ? RISK.safe : RISK.watch} label={depot.status} />
      </header>
      <p className={styles.muted}>
        Dispatch this tick: {liters(depot.dispatch_used)} / {liters(depot.dispatch_capacity_per_tick)}
      </p>
      <div className={styles.track}>
        <div className={styles.fillNeutral} style={{ width: `${Math.min(100, (depot.dispatch_used / limit) * 100)}%` }} />
      </div>
      {depot.fuels.map((f) => (
        <div key={f.fuel_type} className={styles.gauge}>
          <div className={styles.gaugeHead}>
            <span className={styles.fuel}>{f.fuel_type}</span>
            <span className={styles.muted}>{liters(f.inventory)} / {liters(f.capacity)}</span>
          </div>
          <div className={styles.track}>
            <div className={styles.fillNeutral} style={{ width: `${Math.min(100, (f.inventory / (f.capacity || 1)) * 100)}%` }} />
          </div>
        </div>
      ))}
    </section>
  )
}
