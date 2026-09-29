import { RISK } from '../../utils/format'
import styles from './Dashboard.module.css'
import { FuelGauge } from './FuelGauge'
import { StatusBadge } from './StatusBadge'

export function StationCard({ station, tickMinutes }) {
  const open = station.status === 'OPEN'
  return (
    <section className={styles.panel}>
      <header className={styles.panelHead}>
        <h3>{station.name}</h3>
        <div className={styles.row}>
          {station.demand_multiplier !== 1 && (
            <StatusBadge meta={RISK.watch} label={`demand ×${station.demand_multiplier}`} />
          )}
          <StatusBadge meta={open ? RISK.safe : RISK.outage} label={station.status} />
        </div>
      </header>
      <p className={styles.muted}>{station.region_id} · {station.demand_profile}</p>
      {station.fuels.map((fuel) => (
        <FuelGauge key={fuel.fuel_type} fuel={fuel} tickMinutes={tickMinutes} />
      ))}
    </section>
  )
}
