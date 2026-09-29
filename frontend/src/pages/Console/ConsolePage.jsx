import { useEffect, useRef, useState } from 'react'
import {
  ActionLog, ActionQueue, Incidents, KpiCards, LogModal, NavBar, NetworkPanel, RecommendationModal, SidePanel, SimDownBanner,
} from '../../components/console'
import styles from '../../components/console/Console.module.css'
import { useConsole } from '../../hooks'

const TOAST_MS = 3000

/** Operator console (design: design_handoff_fuel_ops_console). Live backend data, or the demo scenario. */
export default function ConsolePage() {
  const c = useConsole()
  const { model } = c
  const [drawer, setDrawer] = useState(null) // station/depot id
  const [recId, setRecId] = useState(null)
  const [logId, setLogId] = useState(null)
  const [toast, setToast] = useState(null)
  const toastTimer = useRef(null)

  useEffect(() => () => clearTimeout(toastTimer.current), [])

  const notify = (msg) => {
    clearTimeout(toastTimer.current)
    setToast(msg)
    toastTimer.current = setTimeout(() => setToast(null), TOAST_MS)
  }

  const run = async (fn) => {
    try {
      notify(await fn())
      setRecId(null)
    } catch (err) {
      notify(err?.message || 'Something went wrong. Nothing was sent.')
    }
  }

  if (!model) {
    return (
      <div className={styles.root} data-theme={c.theme}>
        <p className={styles.loading} role="status">Connecting to the backend…</p>
      </div>
    )
  }

  const rec = model.queue.find((r) => r.id === recId)
  const entry = model.log.find((l) => l.id === logId)
  const station = model.stations.find((s) => s.id === drawer)
  const depot = model.depots.find((d) => d.id === drawer)
  const stationRec = station && model.queue.find((r) => r.st === station.id)

  return (
    <div className={styles.root} data-theme={c.theme}>
      <NavBar model={model} source={c.source} demo={c.demo} offline={c.offline} onDemo={c.setDemo}
              theme={c.theme} onToggleTheme={c.toggleTheme} onTogglePlay={c.togglePlay} />

      <div className={styles.top}>
        <div className={styles.titleBlock}>
          <h1 className={styles.h1}>Operations</h1>
          <span className={styles.subtitle}>Dhaka and Chattogram fuel network</span>
        </div>
        <Incidents incidents={model.incidents} />
        {model.simDown && <SimDownBanner text={model.simDownText} />}
        <KpiCards model={model} onToggleAutopilot={c.toggleAutopilot} />
      </div>

      <main className={styles.main}>
        <NetworkPanel model={model} onOpen={setDrawer} />
        <div className={styles.rightCol}>
          <ActionQueue queue={model.queue} emptyText={model.emptyText} onOpen={setRecId} />
          <ActionLog log={model.log} onOpen={setLogId} />
        </div>
      </main>

      {(station || depot) && (
        <SidePanel entity={station || depot} kind={station ? 'station' : 'depot'} rec={stationRec}
                   onClose={() => setDrawer(null)}
                   onOpenRec={(id) => { setDrawer(null); setRecId(id) }} />
      )}

      {rec && (
        <RecommendationModal key={rec.id} rec={rec} simDown={model.simDown} onClose={() => setRecId(null)} onAsk={c.ask}
                             onQuestions={c.questions}
                             onApprove={(r, qty) => run(() => c.approve(r, qty))}
                             onReject={(r) => run(() => c.reject(r))} />
      )}

      {entry && (
        <LogModal key={entry.id} entry={entry} badge={c.logBadge} aiDown={model.aiDown} onClose={() => setLogId(null)}
                  onAsk={c.ask} onQuestions={c.questions} />
      )}

      {toast && <div className={styles.toast} role="status">{toast}</div>}
    </div>
  )
}
