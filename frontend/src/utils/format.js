const dateTimeFormat = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' })
const dateFormat = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' })
const relativeFormat = new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' })
const currencyFormat = new Intl.NumberFormat(undefined, { style: 'currency', currency: 'USD' })
const numberFormat = new Intl.NumberFormat()

function toDate(value) {
  if (!value) return null
  const date = value instanceof Date ? value : new Date(value)
  return Number.isNaN(date.getTime()) ? null : date
}

export function formatDateTime(value) {
  const date = toDate(value)
  return date ? dateTimeFormat.format(date) : '—'
}

export function formatDate(value) {
  const date = toDate(value)
  return date ? dateFormat.format(date) : '—'
}

const UNITS = [
  ['year', 31_536_000],
  ['month', 2_592_000],
  ['week', 604_800],
  ['day', 86_400],
  ['hour', 3_600],
  ['minute', 60],
  ['second', 1],
]

/** "3 minutes ago", "yesterday", "in 2 days" */
export function formatRelative(value, now = Date.now()) {
  const date = toDate(value)
  if (!date) return '—'
  const seconds = Math.round((date.getTime() - now) / 1000)
  if (Math.abs(seconds) < 10) return 'just now'
  for (const [unit, size] of UNITS) {
    if (Math.abs(seconds) >= size || unit === 'second') {
      return relativeFormat.format(Math.round(seconds / size), unit)
    }
  }
  return '—'
}

/** 1536 -> "1.5 KB" */
export function formatBytes(bytes, decimals = 1) {
  if (bytes === null || bytes === undefined || Number.isNaN(Number(bytes))) return '—'
  const n = Number(bytes)
  if (n === 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.min(Math.floor(Math.log(Math.abs(n)) / Math.log(1024)), units.length - 1)
  const value = n / 1024 ** i
  return `${i === 0 ? value : value.toFixed(decimals).replace(/\.0+$/, '')} ${units[i]}`
}

export function formatCurrency(value) {
  return currencyFormat.format(Number(value) || 0)
}

export function formatNumber(value) {
  return value === null || value === undefined ? '—' : numberFormat.format(value)
}

export function formatDuration(ms) {
  if (ms === null || ms === undefined) return '—'
  return ms < 1000 ? `${Math.round(ms)} ms` : `${(ms / 1000).toFixed(2)} s`
}

export function truncate(text, max = 80) {
  if (!text) return ''
  return text.length > max ? `${text.slice(0, max - 1).trimEnd()}…` : text
}
