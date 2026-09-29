/**
 * Formatting and colour helpers for the operator console.
 * Time is always "minutes since Day 1 00:00" (simulator tick × tick_minutes).
 */

export const FUELS = ['DIESEL', 'PETROL', 'OCTANE']
export const FUEL_LABEL = { DIESEL: 'Diesel', PETROL: 'Petrol', OCTANE: 'Octane' }

/** Recommendation / fuel risk → label, colour token, sort rank. */
export const RISK = {
  urgent: { label: 'Urgent', c: 'var(--urgent)', rank: 3 },
  outage: { label: 'Outage', c: 'var(--urgent)', rank: 3 },
  watch: { label: 'Watch', c: 'var(--watch)', rank: 2 },
  plan: { label: 'Plan ahead', c: 'var(--plan)', rank: 1 },
  safe: { label: 'Safe', c: 'var(--safe)', rank: 0 },
  unknown: { label: 'Unknown', c: 'var(--faint)', rank: 0 },
}
export const riskOf = (key) => RISK[key] ?? RISK.unknown

/** Level colour rule used everywhere: < 25% low, 25–50% medium, > 50% good. */
export const lvlColor = (p) => (p < 25 ? 'var(--low)' : p < 50 ? 'var(--mid)' : 'var(--good)')

export const fmt = (n) => Math.round(Number(n) || 0).toLocaleString('en-US')
export const pctN = (a, b) => (b ? Math.round((a / b) * 100) : 0)
export const pct = (a, b) => `${pctN(a, b)}%`

/** 135 → "2h 15m"; ≤ 0 → "overdue". */
export function dur(minutes) {
  const m = Math.round(minutes)
  if (m <= 0) return 'overdue'
  const h = Math.floor(m / 60)
  return (h ? `${h}h ` : '') + `${m % 60}m`
}

const pad = (n) => String(n).padStart(2, '0')
const dayOf = (t) => Math.floor(t / 1440) + 1

/** 2250 → "13:30" */
export function hm(t) {
  const m = ((Math.round(t) % 1440) + 1440) % 1440
  return `${pad(Math.floor(m / 60))}:${pad(m % 60)}`
}

/** 2250 → "Day 2 · 13:30" (nav clock). */
export const clock = (t) => `Day ${dayOf(t)} · ${hm(t)}`

/** 2250 → "Day 2 13:30" (log timestamps). */
export const dayTime = (t) => `Day ${dayOf(t)} ${hm(t)}`

/** A time relative to now: "16:00" on the same day, "Day 3 06:15" otherwise. */
export const when = (t, now) => (dayOf(t) === dayOf(now) ? hm(t) : dayTime(t))

export const clamp = (x, lo, hi) => Math.min(hi, Math.max(lo, x))

/** Per-item colour for CSS modules: style={cv('var(--urgent)')} → the class reads var(--c). */
export const cv = (c) => ({ '--c': c })
