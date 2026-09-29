import { useCallback, useEffect, useRef, useState } from 'react'

/** Legacy path: works without focus/permissions and on plain http origins. */
function legacyCopy(text) {
  const el = document.createElement('textarea')
  el.value = text
  el.setAttribute('readonly', '')
  el.style.position = 'fixed'
  el.style.opacity = '0'
  document.body.appendChild(el)
  el.select()
  try {
    return document.execCommand('copy')
  } finally {
    el.remove()
  }
}

/** `const { copy, copied } = useCopyToClipboard(); await copy(text)` - `copied` resets after `resetMs`. */
export function useCopyToClipboard(resetMs = 1800) {
  const [copied, setCopied] = useState(false)
  const timer = useRef(null)

  useEffect(() => () => clearTimeout(timer.current), [])

  const copy = useCallback(
    async (text) => {
      let ok = false
      try {
        await navigator.clipboard.writeText(text)
        ok = true
      } catch {
        // No Clipboard API, no permission, or the document isn't focused.
        try {
          ok = legacyCopy(text)
        } catch {
          ok = false
        }
      }
      if (ok) {
        setCopied(true)
        clearTimeout(timer.current)
        timer.current = setTimeout(() => setCopied(false), resetMs)
      }
      return ok
    },
    [resetMs],
  )

  return { copy, copied }
}
