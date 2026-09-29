import { useState } from 'react'
import { recommendationsApi } from '../../api/api'
import { hours, liters, RISK, shortId } from '../../utils/format'
import { Button } from '../ui'
import styles from './Dashboard.module.css'
import { StatusBadge } from './StatusBadge'

/** A recommendation waiting for the operator: approve (optionally with an edited quantity) or reject. */
export function ApprovalCard({ rec, tickMinutes, maxQuantity, onDone }) {
  const [quantity, setQuantity] = useState(String(rec.quantity))
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(null)
  const [error, setError] = useState(null)

  const act = async (kind) => {
    setBusy(kind)
    setError(null)
    try {
      if (kind === 'approve') {
        const qty = Number(quantity)
        const body = { note: note || undefined, quantity: qty !== rec.quantity ? qty : undefined }
        const result = await recommendationsApi.approve(rec.id, body)
        if (result.status === 'REFUSED') setError(`Simulator refused: ${result.error_code}`)
      } else {
        await recommendationsApi.reject(rec.id, { note: note || undefined })
      }
      onDone?.()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(null)
    }
  }

  const invalid = !(Number(quantity) > 0) || (maxQuantity && Number(quantity) > maxQuantity)
  return (
    <article className={styles.approval}>
      <header className={styles.panelHead}>
        <strong>
          {shortId(rec.station_id)} · {rec.fuel_type} · {liters(rec.quantity)}
        </strong>
        <StatusBadge meta={RISK[rec.risk] ?? RISK.unknown} />
      </header>
      <p className={styles.muted}>
        {shortId(rec.depot_id)} → {shortId(rec.station_id)} via {rec.route_id} · proposed at tick {rec.tick} · empty in{' '}
        {hours(rec.ticks_until_empty, tickMinutes)}
      </p>
      <ul className={styles.reasons}>
        {rec.reasons.map((r) => <li key={r}>{r}</li>)}
      </ul>
      <details className={styles.explanation}>
        <summary>Why?</summary>
        {rec.explanation}
      </details>
      <div className={styles.approvalForm}>
        <label>
          Quantity (L)
          <input type="number" min="1" max={maxQuantity} step="100" value={quantity}
                 onChange={(e) => setQuantity(e.target.value)} aria-invalid={invalid || undefined} />
        </label>
        <label className={styles.grow}>
          Note
          <input type="text" value={note} maxLength={500} placeholder="optional" onChange={(e) => setNote(e.target.value)} />
        </label>
        <Button variant="primary" loading={busy === 'approve'} disabled={invalid || !!busy} onClick={() => act('approve')}>
          {Number(quantity) !== rec.quantity ? 'Approve edited' : 'Approve'}
        </Button>
        <Button loading={busy === 'reject'} disabled={!!busy} onClick={() => act('reject')}>Reject</Button>
      </div>
      {maxQuantity && <p className={styles.muted}>Route max {liters(maxQuantity)}</p>}
      {error && <p className={styles.error} role="alert">{error}</p>}
    </article>
  )
}
