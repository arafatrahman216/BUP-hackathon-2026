import { useCallback, useEffect, useState } from 'react'

const KEY = 'hackathon.theme'
const media = () => window.matchMedia?.('(prefers-color-scheme: dark)')

function readStored() {
  try {
    const value = localStorage.getItem(KEY)
    return value === 'light' || value === 'dark' ? value : null
  } catch {
    return null
  }
}

/**
 * Light/dark theme with OS fallback. Sets html[data-theme] which global.css
 * reads; `null` means "follow the system".
 */
export function useTheme() {
  const [override, setOverride] = useState(readStored)
  const [systemDark, setSystemDark] = useState(() => Boolean(media()?.matches))

  useEffect(() => {
    const mq = media()
    if (!mq) return undefined
    const onChange = (e) => setSystemDark(e.matches)
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [])

  useEffect(() => {
    const root = document.documentElement
    if (override) root.dataset.theme = override
    else delete root.dataset.theme
    try {
      if (override) localStorage.setItem(KEY, override)
      else localStorage.removeItem(KEY)
    } catch {
      /* ignore */
    }
  }, [override])

  const resolved = override ?? (systemDark ? 'dark' : 'light')
  const toggle = useCallback(() => setOverride(resolved === 'dark' ? 'light' : 'dark'), [resolved])

  return { theme: resolved, override, setTheme: setOverride, toggle }
}
