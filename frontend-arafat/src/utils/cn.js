/**
 * Join class names, skipping falsy values.
 *   cn('btn', isActive && 'active', { disabled: isDisabled })
 */
export function cn(...args) {
  const out = []
  for (const arg of args) {
    if (!arg) continue
    if (typeof arg === 'string' || typeof arg === 'number') out.push(arg)
    else if (Array.isArray(arg)) out.push(cn(...arg))
    else if (typeof arg === 'object') {
      for (const [key, value] of Object.entries(arg)) if (value) out.push(key)
    }
  }
  return out.filter(Boolean).join(' ')
}
