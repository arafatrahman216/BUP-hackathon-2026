import { DEMO_STATES } from '../../utils/console/demo'
import { cv } from '../../utils/console/format'
import styles from './Console.module.css'

export function NavBar({ model, source, demo, offline, onDemo, theme, onToggleTheme, onTogglePlay }) {
  return (
    <nav className={styles.nav} aria-label="Console">
      <div className={styles.brand}>
        <div className={styles.logo} aria-hidden="true">F</div>
        <span className={styles.brandName}>Fuel Ops</span>
        <span className={styles.tag}>SIMULATED NETWORK</span>
        {source === 'demo' && (
          <span className={styles.demoTag} title={offline ? 'The backend is unreachable, so sample data is shown' : 'Sample scenario'}>
            {offline ? 'DEMO DATA · BACKEND OFFLINE' : 'DEMO DATA'}
          </span>
        )}
      </div>
      <div className={styles.spacer} />
      {source === 'demo' && !offline && (
        <label className={styles.health}>
          <span>Demo state</span>
          <select className={styles.demoSelect} value={demo} onChange={(e) => onDemo(e.target.value)}>
            {Object.entries(DEMO_STATES).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
          </select>
        </label>
      )}
      <div className={styles.clockPill}>
        <span className={styles.clock}>{model.clock}</span>
        <button
          type="button"
          className={styles.btnSmall}
          onClick={onTogglePlay}
          disabled={!model.canPlay}
          title={model.canPlay ? undefined : source === 'live' ? 'The simulator controls the clock' : 'No fresh data'}
        >
          {model.playLabel}
        </button>
      </div>
      <div className={styles.health} role="status">
        <span className={styles.dot} style={cv(model.health.c)} />
        {model.health.text}
      </div>
      <button type="button" className={styles.btn} onClick={onToggleTheme}>
        {theme === 'light' ? 'Dark mode' : 'Light mode'}
      </button>
    </nav>
  )
}

export function Incidents({ incidents }) {
  if (!incidents.length) return null
  return (
    <div className={styles.incidents}>
      {incidents.map((inc) => (
        <div key={inc.key} className={styles.incident}>
          <span className={styles.incidentDot} style={cv(inc.c)} aria-hidden="true" />
          <div className={styles.incidentBody}>
            <div className={styles.incidentHead}>
              <span className={styles.incidentTitle}>{inc.title}</span>
              <span className={styles.incidentWhen}>{inc.when}</span>
            </div>
            <span className={styles.incidentDetail}>{inc.detail}</span>
          </div>
        </div>
      ))}
    </div>
  )
}

export function SimDownBanner({ text }) {
  return (
    <div className={styles.banner} role="alert">
      <span className={styles.dot} style={cv('var(--urgent)')} />
      <span className={styles.bannerTitle}>Simulator not responding</span>
      <span className={styles.muted}>{text}</span>
    </div>
  )
}

function Kpi({ label, children, sub }) {
  return (
    <div className={styles.kpi}>
      <span className={styles.kpiLabel}>{label}</span>
      {children}
      <span className={styles.kpiSub}>{sub}</span>
    </div>
  )
}

export function KpiCards({ model, onToggleAutopilot }) {
  const { mode, service, autopilot, queue } = model
  return (
    <div className={styles.kpis}>
      <Kpi label="Mode" sub={mode.reason}>
        <span className={styles.kpiValue}><span className={styles.kpiDot} style={cv(mode.c)} />{mode.label}</span>
      </Kpi>
      <Kpi label="Service level" sub={service.sub}>
        <span className={styles.kpiValue}>{service.value}</span>
      </Kpi>
      <Kpi label="Trucks on the road" sub={queue.length ? `${queue.length} actions waiting` : 'Nothing waiting'}>
        <span className={styles.kpiValue}>{model.trucksCount}</span>
      </Kpi>
      <Kpi label="Autopilot" sub={autopilot.label}>
        <div className={styles.switchRow}>
          <button
            type="button"
            role="switch"
            aria-checked={autopilot.on}
            aria-label="Autopilot"
            className={styles.switch}
            onClick={onToggleAutopilot}
            disabled={!autopilot.canToggle}
            title={autopilot.canToggle ? undefined : 'Set on the backend'}
          >
            <span className={styles.knob} />
          </button>
          <span className={styles.switchState}>{autopilot.state}</span>
        </div>
      </Kpi>
    </div>
  )
}
