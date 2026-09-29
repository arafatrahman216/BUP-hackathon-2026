import { useEffect, useRef, useState } from 'react'
import { RISK, cv, dur, fmt, lvlColor, pct, pctN } from '../../utils/console/format'
import styles from './Console.module.css'

/** Close on Escape and move focus into the overlay when it opens. */
function useOverlay(onClose) {
  const ref = useRef(null)
  const close = useRef(onClose)
  useEffect(() => {
    close.current = onClose
  })
  useEffect(() => {
    const prev = document.activeElement
    ref.current?.focus()
    const onKey = (e) => e.key === 'Escape' && close.current()
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('keydown', onKey)
      if (prev instanceof HTMLElement) prev.focus()
    }
  }, [])
  return ref
}

function Figures({ items }) {
  return (
    <div className={styles.figures}>
      {items.map(([k, v]) => (
        <div key={k} className={styles.figure}>
          <span className={styles.figureK}>{k}</span>
          <span className={styles.figureV}>{v}</span>
        </div>
      ))}
    </div>
  )
}

function LevelRow({ f, line, cap }) {
  const p = pctN(f.lvl, f.cap)
  return (
    <div className={styles.drawerFuel}>
      <div className={styles.drawerFuelHead}>
        <span className={styles.strong}>{f.f}</span>
        <span className={styles.num}><span className={styles.strong}>{pct(f.lvl, f.cap)}</span> <span className={styles.faint}>· {fmt(f.lvl)} / {cap}</span></span>
      </div>
      <div className={styles.bar}><div className={styles.barFill} style={{ width: `${Math.min(100, p)}%`, ...cv(lvlColor(p)) }} /></div>
      <span className={styles.hint}>{line}</span>
    </div>
  )
}

/** Right drawer for a clicked station or depot. */
export function SidePanel({ entity, kind, rec, onClose, onOpenRec }) {
  const ref = useOverlay(onClose)
  const isStation = kind === 'station'
  const stats = isStation
    ? [['Demand vs forecast', entity.demand], ['Next rush', entity.rush]]
    : [['Next ship', entity.ship], ['Overflow risk', entity.overflow], ['Dispatch this step', `${fmt(entity.used)} / ${fmt(entity.max)} L`]]
  return (
    <>
      <div className={styles.scrim} onClick={onClose} />
      <aside ref={ref} tabIndex={-1} className={styles.drawer} role="dialog" aria-modal="true" aria-labelledby="drawer-title">
        <div className={styles.drawerHead}>
          <div className={styles.titleBlock}>
            <span className={styles.kicker}>
              {isStation ? `Station · ${entity.region}${entity.single ? ' · single road' : ''}` : `Depot · ${entity.region} · ${entity.statusLabel}`}
            </span>
            <h2 id="drawer-title" className={styles.drawerName}>{entity.name}</h2>
          </div>
          <button type="button" className={styles.btnClose} onClick={onClose}>Close</button>
        </div>
        {entity.fuels.map((f) => (
          <LevelRow key={f.f} f={f} cap={`${fmt(f.cap)} L`}
                    line={isStation
                      ? `Empty ${f.empty} · order by ${f.orderBy}${f.transit ? ` · +${fmt(f.transit)} L arriving ${f.transitAt ?? 'soon'}` : ''}`
                      : `Runway ${f.runway}`} />
        ))}
        <div className={styles.stats}>
          {stats.map(([k, v]) => (
            <div key={k} className={styles.statRow}><span className={styles.muted}>{k}</span><span className={styles.statVal}>{v}</span></div>
          ))}
        </div>
        {rec && (
          <button type="button" className={styles.drawerBtn} onClick={() => onOpenRec(rec.id)}>Open action · by {rec.dl}</button>
        )}
      </aside>
    </>
  )
}

const QUESTIONS = ['Why not Patiya?', 'Wait an hour?', 'If the road closes?']
const STEP_L = 500

/** Recommendation detail: deadline, shipment, station state, impact, Ask why, approve / edit / reject. */
export function RecommendationModal({ rec, simDown, onClose, onAsk, onApprove, onReject }) {
  const ref = useOverlay(onClose)
  const [editing, setEditing] = useState(false)
  const [qty, setQty] = useState(rec.qty)
  const [answer, setAnswer] = useState(null) // {q, loading, text, badge}
  const [busy, setBusy] = useState(false)
  const alive = useRef(true)
  useEffect(() => {
    alive.current = true // StrictMode mounts twice: set it again after the first cleanup
    return () => { alive.current = false }
  }, [])

  const risk = RISK[rec.sev] ?? RISK.safe
  const sendQty = editing ? qty : rec.qty

  const ask = async (q) => {
    setAnswer({ q, loading: true })
    const res = await onAsk(rec, q)
    if (alive.current) setAnswer((a) => (a?.q === q ? { q, loading: false, ...res } : a))
  }
  const act = async (fn) => {
    setBusy(true)
    try {
      await fn()
    } finally {
      if (alive.current) setBusy(false)
    }
  }

  const state = [
    [`${rec.fuel} now`, `${fmt(rec.level)} L · ${pct(rec.level, rec.cap)}`],
    ['Empty at', rec.emptyAt],
    ['Demand', rec.demandNow],
    ['Cause', rec.signal],
  ]

  return (
    <div className={styles.modalScrim} onClick={onClose}>
      <div ref={ref} tabIndex={-1} className={styles.modal} role="dialog" aria-modal="true" aria-labelledby="rec-title"
           onClick={(e) => e.stopPropagation()}>
        <div className={styles.modalHead}>
          <div className={styles.modalTitleCol}>
            <span id="rec-title" className={styles.sevLine}><span className={styles.sevLineDot} style={cv(risk.c)} />{risk.label} · {rec.title}</span>
            <div className={styles.decideRow}>
              <span className={styles.faint}>Decide by</span>
              <span className={styles.decideBig}>{rec.dl}</span>
              <span className={styles.muted}>{rec.leftMin > 0 ? `${dur(rec.leftMin)} left` : 'overdue'}</span>
            </div>
          </div>
          <button type="button" className={styles.btnClose} onClick={onClose}>Close</button>
        </div>

        <div className={styles.shipBox}>
          <span className={styles.shipLine}>Send {fmt(sendQty)} L · {rec.road}</span>
          <span className={styles.hint}>
            Arrives ~{rec.arrives} · {rec.travel} min · {rec.needs ? `needs review: ${rec.needs}` : `confidence ${String(rec.conf).toLowerCase()}`}
          </span>
        </div>

        <div className={styles.section}>
          <span className={styles.sectionLabel}>Station state</span>
          <Figures items={state} />
        </div>

        <div className={styles.tiles}>
          <div className={styles.tile}><span className={styles.hint}>Importance</span><span className={styles.tileV}>{rec.importance}</span></div>
          <div className={styles.tile}><span className={styles.hint}>Risk before</span><span className={styles.tileV} style={cv('var(--urgent)')}>{rec.riskB}</span></div>
          <div className={styles.tile}><span className={styles.hint}>Risk after</span><span className={styles.tileV} style={cv('var(--safe)')}>{rec.riskA}</span></div>
        </div>

        <div className={styles.section}>
          <div className={styles.askRow}>
            <button type="button" className={styles.askBtn} onClick={() => ask('why')}>Ask why</button>
            {QUESTIONS.map((q) => (
              <button key={q} type="button" className={styles.qBtn} aria-pressed={answer?.q === q} onClick={() => ask(q)}>{q}</button>
            ))}
          </div>
          {answer && (
            <div className={styles.answer} aria-live="polite">
              {!answer.loading && <span className={styles.badge}>{answer.badge}</span>}
              <p className={styles.answerText}>{answer.loading ? 'Reading engine data…' : answer.text}</p>
            </div>
          )}
        </div>

        <div className={styles.footer}>
          {editing && (
            <div className={styles.stepper}>
              <button type="button" className={styles.stepBtn} aria-label="Decrease quantity" onClick={() => setQty((x) => Math.max(STEP_L, x - STEP_L))}>−</button>
              <span className={styles.stepQty} aria-live="polite">{fmt(qty)} L</span>
              <button type="button" className={styles.stepBtn} aria-label="Increase quantity" onClick={() => setQty((x) => Math.min(rec.maxL, x + STEP_L))}>+</button>
            </div>
          )}
          <button type="button" className={styles.btnLarge} disabled={busy} onClick={() => act(() => onReject(rec))}>Reject</button>
          <button type="button" className={styles.btnLarge} onClick={() => { if (!editing) setQty(rec.qty); setEditing((e) => !e) }}>
            {editing ? 'Done' : 'Edit quantity'}
          </button>
          <button type="button" className={styles.btnPrimary} disabled={busy} onClick={() => act(() => onApprove(rec, sendQty))}>
            {simDown ? 'Approve (held)' : 'Approve'}
          </button>
        </div>
      </div>
    </div>
  )
}

const STEPS = ['Action taken', 'Departed', 'Arrived', 'Verified']

/** Action log detail: lifecycle, summary, state when decided, prediction check. */
export function LogModal({ entry, badge, aiDown, onClose }) {
  const ref = useOverlay(onClose)
  const progress = `${(Math.max(0, entry.done - 1) / 3) * 75}%`
  return (
    <div className={styles.modalScrim} onClick={onClose}>
      <div ref={ref} tabIndex={-1} className={styles.modalLog} role="dialog" aria-modal="true" aria-labelledby="log-modal-title"
           onClick={(e) => e.stopPropagation()}>
        <div className={styles.modalHead}>
          <div className={styles.titleBlock} style={{ gap: 4 }}>
            <span className={styles.kicker}>{entry.taken} · {entry.actor}</span>
            <span id="log-modal-title" className={styles.logTitleBig}>{entry.title}</span>
          </div>
          <button type="button" className={styles.btnClose} onClick={onClose}>Close</button>
        </div>

        <div className={styles.progress}>
          <div className={styles.track} />
          <div className={styles.trackFill} style={{ width: progress }} />
          {STEPS.map((label, i) => (
            <div key={label} className={styles.step}>
              <div className={i < entry.done ? styles.stepDone : styles.stepDot} />
              <span className={styles.stepLabel}>{label}</span>
              <span className={styles.stepAt}>{entry.steps[i]}</span>
            </div>
          ))}
        </div>

        <div className={styles.summaryBlock}>
          <span className={styles.badge}>{badge}</span>
          <p className={styles.answerText}>{aiDown ? entry.tpl || entry.summary : entry.summary}</p>
        </div>

        <div className={styles.section}>
          <span className={styles.sectionLabel}>State when decided</span>
          <Figures items={entry.state} />
        </div>

        <div className={styles.verdictRow}>
          <span className={styles.muted}>{entry.check}</span>
          <span className={styles.verdict}><span className={styles.dot} style={cv(entry.vc)} />{entry.verdict}</span>
        </div>
      </div>
    </div>
  )
}
