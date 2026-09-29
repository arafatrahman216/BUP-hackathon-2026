import { liters, LEVEL, RISK, shortId, STAGE } from '../../utils/format'
import styles from './Dashboard.module.css'
import { StatusBadge } from './StatusBadge'

function Empty({ children }) {
  return <p className={styles.muted}>{children}</p>
}

export function AlertList({ alerts, blocked }) {
  if (!alerts.length && !blocked.length) return <Empty>No alerts.</Empty>
  return (
    <ul className={styles.alerts}>
      {alerts.map((a, i) => (
        <li key={`${a.code}-${a.entity_id}-${i}`}>
          <StatusBadge meta={LEVEL[a.level] ?? LEVEL.info} label={a.code} />
          <span>{a.message}</span>
        </li>
      ))}
      {blocked.map((b) => (
        <li key={`blocked-${b.station_id}-${b.fuel_type}`}>
          <StatusBadge meta={LEVEL.warning} label="BLOCKED" />
          <span>{shortId(b.station_id)} {b.fuel_type}: {b.reason}</span>
        </li>
      ))}
    </ul>
  )
}

const ALLOCATION = {
  PENDING: STAGE.pending, IN_TRANSIT: { icon: '➜', color: 'var(--status-warning)' }, ARRIVED: STAGE.ok,
  FAILED: STAGE.error, CANCELLED: STAGE.skipped,
}

export function ShipmentTable({ allocations }) {
  if (!allocations.length) return <Empty>No shipments yet.</Empty>
  return (
    <div className={styles.tableWrap}>
      <table className={styles.table}>
        <thead>
          <tr><th>ID</th><th>Status</th><th>Route</th><th>Fuel</th><th className={styles.num}>Qty</th><th>Created</th><th>ETA</th></tr>
        </thead>
        <tbody>
          {allocations.map((a) => (
            <tr key={a.id}>
              <td>{a.id}</td>
              <td><StatusBadge meta={ALLOCATION[a.status] ?? STAGE.pending} label={a.status} title={a.failure_reason || undefined} /></td>
              <td>{shortId(a.route_id)}</td>
              <td>{a.fuel_type}</td>
              <td className={styles.num}>{liters(a.quantity)}</td>
              <td>{a.created_tick}</td>
              <td>{a.actual_arrival_tick ?? a.expected_arrival_tick ?? '–'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function SupplyTable({ supply, events }) {
  return (
    <>
      {events.length > 0 && (
        <ul className={styles.alerts}>
          {events.map((e) => (
            <li key={e.id}>
              <StatusBadge meta={e.status === 'ACTIVE' ? LEVEL.critical : LEVEL.info} label={e.status} />
              <span>{e.type} · ticks {e.start_tick}–{e.end_tick} · {JSON.stringify(e.parameters)}</span>
            </li>
          ))}
        </ul>
      )}
      {supply.length ? (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead><tr><th>Ship</th><th>Depot</th><th>Fuel</th><th className={styles.num}>Qty</th><th>Tick</th><th>Status</th></tr></thead>
            <tbody>
              {supply.map((s) => (
                <tr key={s.id}>
                  <td>{s.id}</td><td>{shortId(s.depot_id)}</td><td>{s.fuel_type}</td>
                  <td className={styles.num}>{liters(s.quantity)}</td><td>{s.planned_tick}</td>
                  <td><StatusBadge meta={s.status === 'DELAYED' ? LEVEL.warning : LEVEL.info} label={s.status} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <Empty>No upcoming ship arrivals.</Empty>
      )}
    </>
  )
}

export function RouteList({ routes }) {
  return (
    <ul className={styles.alerts}>
      {routes.map((r) => (
        <li key={r.id}>
          <StatusBadge meta={r.status === 'AVAILABLE' ? RISK.safe : RISK.urgent} label={r.status} />
          <span>{shortId(r.id)} · {r.transit_ticks} ticks · max {liters(r.max_shipment)}</span>
        </li>
      ))}
    </ul>
  )
}

const REC = {
  POSTED: STAGE.ok, APPROVED: { icon: '↺', color: 'var(--status-warning)' }, PENDING_APPROVAL: LEVEL.warning,
  REFUSED: STAGE.error, REJECTED: STAGE.skipped, EXPIRED: STAGE.skipped,
}

export function DecisionLog({ recs }) {
  if (!recs.length) return <Empty>No recommendations yet.</Empty>
  return (
    <div className={styles.tableWrap}>
      <table className={styles.table}>
        <thead>
          <tr><th>#</th><th>Tick</th><th>Status</th><th>Mode</th><th>Station</th><th>Fuel</th><th className={styles.num}>Qty</th><th>Route</th><th>Result</th></tr>
        </thead>
        <tbody>
          {recs.map((r) => (
            <tr key={r.id} title={r.explanation}>
              <td>{r.id}</td>
              <td>{r.tick}</td>
              <td><StatusBadge meta={REC[r.status] ?? STAGE.pending} label={r.status} /></td>
              <td>{r.decision_mode}</td>
              <td>{shortId(r.station_id)}</td>
              <td>{r.fuel_type}</td>
              <td className={styles.num}>
                {liters(r.quantity)}
                {r.quantity !== r.proposed_quantity && <span className={styles.muted}> (was {liters(r.proposed_quantity)})</span>}
              </td>
              <td>{shortId(r.route_id)}</td>
              <td>{r.allocation_id ? `allocation ${r.allocation_id}` : r.error_code || r.error_message || r.operator_note || '–'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
