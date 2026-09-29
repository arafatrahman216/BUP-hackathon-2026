import { useState } from 'react'
import { RISK, cv, dur, fmt, lvlColor, pct, pctN } from '../../utils/console/format'
import styles from './Console.module.css'
import { NetworkMap } from './NetworkMap'

function FuelCell({ lvl, cap, label }) {
  const p = pctN(lvl, cap)
  return (
    <div className={styles.fuelCell}>
      <div className={styles.fuelCellHead}>
        <span className={styles.fuelPct}>{pct(lvl, cap)}</span>
        <span className={styles.fuelL}>{label}</span>
      </div>
      <div className={styles.bar}><div className={styles.barFill} style={{ width: `${Math.min(100, p)}%`, ...cv(lvlColor(p)) }} /></div>
    </div>
  )
}

function StateTables({ stations, depots, roads, onOpen }) {
  return (
    <div className={styles.tables}>
      <div className={styles.legend}>
        <span className={styles.legendItem}><span className={styles.swBar} style={cv('var(--low)')} />Low &lt;25%</span>
        <span className={styles.legendItem}><span className={styles.swBar} style={cv('var(--mid)')} />Medium 25–50%</span>
        <span className={styles.legendItem}><span className={styles.swBar} style={cv('var(--good)')} />Good &gt;50%</span>
      </div>

      <div className={styles.table}>
        <div className={`${styles.gridFuel} ${styles.thead}`}>
          <span>Station</span><span>Diesel</span>
          <span>Petrol</span><span>Octane</span>
        </div>
        {stations.map((s) => (
          <button key={s.id} type="button" className={`${styles.gridFuel} ${styles.trow}`} onClick={() => onOpen(s.id)}>
            <div className={styles.rowName}>
              <span className={styles.rowTitle}>{s.name}</span>
              <span className={styles.rowSub}>{s.nextOrder}</span>
            </div>
            {s.fuels.map((f) => <FuelCell key={f.f} lvl={f.lvl} cap={f.cap} label={`${fmt(f.lvl)} L`} />)}
          </button>
        ))}
      </div>

      <div className={styles.table}>
        <div className={`${styles.gridFuel} ${styles.thead}`}>
          <span>Depot</span><span>Diesel</span>
          <span>Petrol</span><span>Octane</span>
        </div>
        {depots.map((d) => (
          <button key={d.id} type="button" className={`${styles.gridFuel} ${styles.trow}`} onClick={() => onOpen(d.id)}>
            <div className={styles.rowName}>
              <span className={styles.rowTitle}>{d.name}</span>
              <span className={styles.rowSub}>Next ship {d.shipShort}</span>
            </div>
            {d.fuels.map((f) => <FuelCell key={f.f} lvl={f.lvl} cap={f.cap} label={`${fmt(f.lvl / 1000)}k L`} />)}
          </button>
        ))}
      </div>

      <div className={styles.table}>
        <div className={`${styles.gridRoad} ${styles.thead}`}>
          <span>Road</span><span>Type</span><span>Travel time</span>
          <span>Max per truck</span><span>Status</span>
        </div>
        {roads.map((r) => (
          <div key={r.id} className={`${styles.gridRoad} ${styles.troad}`}>
            <span style={{ fontWeight: 500 }}>{r.name}</span>
            <span className={styles.muted}>{r.main ? 'Main' : 'Backup'}</span>
            <span className={styles.muted}>{r.min} min</span>
            <span className={styles.muted}>{fmt(r.max)} L</span>
            <span className={styles.roadStatus}><span className={styles.dot} style={cv(r.c)} />{r.status}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

export function NetworkPanel({ model, onOpen }) {
  const [view, setView] = useState('map')
  return (
    <section className={styles.networkPanel} aria-labelledby="network-title">
      <div className={styles.panelHead}>
        <h2 id="network-title" className={styles.h2}>Network</h2>
        <div className={styles.segmented}>
          <button type="button" className={styles.segment} aria-pressed={view === 'map'} onClick={() => setView('map')}>Map</button>
          <button type="button" className={styles.segment} aria-pressed={view === 'table'} onClick={() => setView('table')}>All states</button>
        </div>
      </div>
      {view === 'map'
        ? <NetworkMap stations={model.stations} depots={model.depots} roads={model.roads} trucks={model.trucks} onOpen={onOpen} />
        : <StateTables stations={model.stations} depots={model.depots} roads={model.roads} onOpen={onOpen} />}
    </section>
  )
}

export function ActionQueue({ queue, emptyText, onOpen }) {
  return (
    <section className={styles.queuePanel} aria-labelledby="queue-title">
      <div className={styles.panelHeadBaseline}>
        <h2 id="queue-title" className={styles.h2}>Action queue</h2>
        <span className={styles.hint}>Earliest deadline first</span>
      </div>
      {queue.length === 0 && <div className={styles.empty}>{emptyText}</div>}
      {queue.map((q) => {
        const risk = RISK[q.sev] ?? RISK.safe
        return (
          <button key={q.id} type="button" className={styles.qItem} onClick={() => onOpen(q.id)}>
            <div className={styles.qDeadline} style={cv(risk.c)}>
              <span className={styles.qDecide}>DECIDE BY</span>
              <span className={q.dl.length > 5 ? styles.qTimeLong : styles.qTime}>{q.dl}</span>
              <span className={styles.qLeft}>{q.leftMin > 0 ? `${dur(q.leftMin)} left` : 'overdue'}</span>
            </div>
            <div className={styles.qBody}>
              <span className={styles.qTitle}>{q.title}</span>
              <span className={styles.qLine}>{fmt(q.qty)} L · {q.road}</span>
              <div className={styles.pills}>
                <span className={styles.sevPill} style={cv(risk.c)}><span className={styles.sevDot} />{risk.label}</span>
                {q.needs && <span className={styles.reviewPill}>Needs your review</span>}
              </div>
            </div>
          </button>
        )
      })}
    </section>
  )
}

export function ActionLog({ log, onOpen }) {
  return (
    <section className={styles.logPanel} aria-labelledby="log-title">
      <h2 id="log-title" className={styles.h2Log}>Action log</h2>
      <div className={styles.logHead}><span>Action · newest first</span><span>Status</span></div>
      {log.length === 0 && <div className={styles.empty}>No actions yet</div>}
      {log.map((r) => (
        <button key={r.id} type="button" className={styles.logRow} onClick={() => onOpen(r.id)}>
          <div className={styles.logMain}>
            <span className={styles.logTitle}>{r.title}</span>
            <div className={styles.logMeta}>
              <span className={r.actor === 'Autopilot' ? styles.actorAuto : styles.actor}>{r.actor}</span>
              <span className={styles.logDate}>{r.taken.replace(/(Day \d+) /, '$1 · ')}</span>
            </div>
          </div>
          <span className={styles.statusPill} style={cv(r.c)}><span className={styles.dot} />{r.status}</span>
        </button>
      ))}
    </section>
  )
}
