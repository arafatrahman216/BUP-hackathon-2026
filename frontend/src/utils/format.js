/** Display helpers for the dashboard. */

export const liters = (n) => (n === null || n === undefined ? '–' : `${Math.round(n).toLocaleString()} L`)

export const num = (n, digits = 0) =>
  n === null || n === undefined ? '–' : Number(n).toLocaleString(undefined, { maximumFractionDigits: digits })

/** ticks -> "3.2 h" using the simulator's tick length. */
export function hours(ticks, tickMinutes = 15) {
  if (ticks === null || ticks === undefined) return '–'
  const h = (ticks * tickMinutes) / 60
  return h >= 48 ? `${(h / 24).toFixed(1)} d` : `${h.toFixed(1)} h`
}

export const percent = (x, digits = 1) => (x === null || x === undefined ? '–' : `${(x * 100).toFixed(digits)}%`)

export const shortId = (id = '') => id.replace(/^(station|depot|route)-/, '')

export const simTime = (iso) => (iso ? iso.replace('T', ' ').slice(0, 16) : '–')

/** Risk -> label, icon and status color. Color never carries meaning alone. */
export const RISK = {
  safe: { label: 'Safe', icon: '●', color: 'var(--status-good)' },
  watch: { label: 'Watch', icon: '▲', color: 'var(--status-warning)' },
  urgent: { label: 'Urgent', icon: '■', color: 'var(--status-critical)' },
  outage: { label: 'Outage', icon: '✕', color: 'var(--status-serious)' },
  unknown: { label: 'Unknown', icon: '?', color: 'var(--status-muted)' },
}

export const LEVEL = {
  critical: { icon: '■', color: 'var(--status-critical)' },
  warning: { icon: '▲', color: 'var(--status-warning)' },
  info: { icon: 'ℹ', color: 'var(--status-muted)' },
}

export const STAGE = {
  ok: { icon: '✓', color: 'var(--status-good)' },
  fallback: { icon: '↺', color: 'var(--status-warning)' },
  skipped: { icon: '–', color: 'var(--status-muted)' },
  error: { icon: '✕', color: 'var(--status-critical)' },
  pending: { icon: '…', color: 'var(--status-muted)' },
}
