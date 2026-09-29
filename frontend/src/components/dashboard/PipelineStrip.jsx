import { STAGE } from '../../utils/format'
import styles from './Dashboard.module.css'

const ORDER = ['read', 'validate', 'save', 'detect', 'predict', 'decide', 'explain', 'post']

/** One chip per pipeline stage for the last run: status icon, name, duration, detail on hover. */
export function PipelineStrip({ pipeline }) {
  const byName = Object.fromEntries((pipeline.stages || []).map((s) => [s.name, s]))
  return (
    <div className={styles.stages}>
      {ORDER.map((name, i) => {
        const stage = byName[name] || { status: 'pending' }
        const meta = STAGE[stage.status] ?? STAGE.pending
        return (
          <div key={name} className={styles.stageWrap}>
            {i > 0 && <span className={styles.arrow} aria-hidden="true">→</span>}
            <div className={styles.stage} title={stage.detail || stage.status}>
              <span aria-hidden="true" style={{ color: meta.color }}>{meta.icon}</span>
              <span>{name}</span>
              <span className={styles.muted}>{stage.ms ? `${Math.round(stage.ms)}ms` : stage.status}</span>
            </div>
          </div>
        )
      })}
      <div className={styles.stageSummary}>
        {pipeline.acting ? 'acting on live data' : 'NOT acting (stale / invalid data)'} · run #{pipeline.runs}
        {pipeline.last_run?.duration_ms ? ` · ${Math.round(pipeline.last_run.duration_ms)} ms` : ''}
      </div>
    </div>
  )
}
