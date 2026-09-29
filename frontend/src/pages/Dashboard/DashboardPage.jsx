import { useState } from 'react'
import { dashboardApi } from '../../api/api'
import {
  AlertList, ApprovalCard, DecisionLog, DepotCard, PipelineStrip, RouteList, ShipmentTable, StationCard,
  StatusBadge, SupplyTable,
} from '../../components/dashboard'
import styles from '../../components/dashboard/Dashboard.module.css'
import { Button, Card, Spinner } from '../../components/ui'
import { useDashboard } from '../../hooks'
import { liters, LEVEL, percent, RISK, simTime, STAGE } from '../../utils/format'

const LINK = {
  live: { ...STAGE.ok, label: 'Live (SSE)' },
  polling: { ...STAGE.fallback, label: 'Polling' },
  connecting: { ...STAGE.pending, label: 'Connecting' },
  offline: { ...STAGE.error, label: 'Backend offline' },
}
const SIM_LINK = { sse: STAGE.ok, polling: STAGE.fallback, down: STAGE.error, starting: STAGE.pending }

function Stat({ label, value, sub }) {
  return (
    <div className={styles.stat}>
      <span className={styles.statLabel}>{label}</span>
      <span className={styles.statValue}>{value}</span>
      {sub && <span className={styles.muted}>{sub}</span>}
    </div>
  )
}

/** Operator view of the whole pipeline: world state, risk, approvals, shipments and decisions. */
export default function DashboardPage() {
  const { state, link, error, refresh } = useDashboard()
  const [running, setRunning] = useState(false)

  if (!state) {
    return error ? <p className={styles.error}>{error.message}</p> : <Spinner label="Loading dashboard" />
  }

  const { sim, pipeline, metrics, recommendations } = state
  const pending = recommendations.open.filter((r) => r.status === 'PENDING_APPROVAL')
  const waiting = recommendations.open.filter((r) => r.status === 'APPROVED')
  const routeMax = Object.fromEntries(state.routes.map((r) => [r.id, r.max_shipment]))

  const runNow = async () => {
    setRunning(true)
    try {
      await dashboardApi.run()
      await refresh()
    } finally {
      setRunning(false)
    }
  }

  return (
    <div className={styles.page}>
      <section className={styles.topbar}>
        <div className={styles.row}>
          <StatusBadge meta={LINK[link]} label={LINK[link].label} title="Browser ↔ backend" />
          <StatusBadge meta={SIM_LINK[sim.link] ?? STAGE.pending} label={`Simulator: ${sim.connected ? sim.link : 'unreachable'}`}
                       title={sim.error || 'Backend ↔ simulator'} />
          <span className={styles.muted}>Tick <strong>{sim.tick ?? '–'}</strong> · {simTime(sim.sim_time)} · {sim.status ?? '–'}</span>
        </div>
        <Button onClick={runNow} loading={running}>Run pipeline now</Button>
      </section>

      {sim.stale && (
        <div className={styles.banner} role="status">
          <StatusBadge meta={LEVEL.warning} label="STALE" />
          Showing cached data{sim.data_age_seconds != null ? ` from ${Math.round(sim.data_age_seconds)} s ago` : ''}.
          {' '}{sim.error || 'The simulator flagged its data as stale.'}
          {pipeline.cautious
            ? ' Cautious mode: only urgent needs are planned, with smaller shipments.'
            : ' No shipments are posted until fresh data arrives.'}
        </div>
      )}

      <section className={styles.stats}>
        <Stat label="Service level" value={percent(metrics.service_level, 2)} sub="served / (served + unmet)" />
        <Stat label="Unmet demand" value={liters(metrics.unmet_demand_liters)} />
        <Stat label="Served demand" value={liters(metrics.served_demand_liters)} />
        <Stat label="Shipped" value={liters(metrics.allocation_liters)} sub={`${metrics.allocation_failures ?? 0} failed`} />
        <Stat label="Awaiting operator" value={pending.length} sub={waiting.length ? `${waiting.length} approved, waiting to post` : undefined} />
      </section>

      <Card title="Pipeline (last run)">
        <PipelineStrip pipeline={pipeline} />
        {pipeline.validation_issues.length > 0 && (
          <ul className={styles.reasons}>{pipeline.validation_issues.map((i) => <li key={i}>{i}</li>)}</ul>
        )}
      </Card>

      <div className={styles.split}>
        <div className={styles.main}>
          <h2 className={styles.h2}>Stations</h2>
          <div className={styles.grid2}>
            {state.stations.map((s) => <StationCard key={s.id} station={s} tickMinutes={sim.tick_minutes} />)}
          </div>
          <p className={styles.legend}>
            {Object.values(RISK).map((r) => <StatusBadge key={r.label} meta={r} />)}
            <span className={styles.legendIncoming} /> incoming
          </p>
        </div>
        <aside className={styles.side}>
          <Card title={`Needs approval (${pending.length})`}>
            {pending.length ? (
              <div className={`${styles.stack} ${styles.queue}`}>
                {pending.map((rec) => (
                  <ApprovalCard key={rec.id} rec={rec} tickMinutes={sim.tick_minutes} maxQuantity={routeMax[rec.route_id]} onDone={refresh} />
                ))}
              </div>
            ) : (
              <p className={styles.muted}>Nothing to approve. Routine refills are posted automatically.</p>
            )}
          </Card>
          <Card title={`Alerts (${state.alerts.length + state.blocked.length})`}>
            <AlertList alerts={state.alerts} blocked={state.blocked} />
          </Card>
        </aside>
      </div>

      <h2 className={styles.h2}>Depots and routes</h2>
      <div className={styles.grid3}>
        {state.depots.map((d) => <DepotCard key={d.id} depot={d} />)}
        <Card title="Routes"><RouteList routes={state.routes} /></Card>
      </div>

      <div className={styles.grid2}>
        <Card title="Trucks (allocations)"><ShipmentTable allocations={state.allocations} /></Card>
        <Card title="Crises and incoming ships"><SupplyTable supply={state.supply} events={state.events} /></Card>
      </div>

      <Card title="Decision log (latest 25)">
        <DecisionLog recs={recommendations.recent} />
      </Card>
    </div>
  )
}
