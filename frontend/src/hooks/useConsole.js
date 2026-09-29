import { useCallback, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { aiApi, recommendationsApi } from '../api/api'
import { DEMO_LOOP, DEMO_START, DEMO_STATES, buildDemoModel, demoDecisionEntry } from '../utils/console/demo'
import { fmt } from '../utils/console/format'
import { ASK_SYSTEM, askPrompt, isGrounded } from '../utils/console/grounding'
import { buildLiveModel } from '../utils/console/live'
import { useDashboard } from './useDashboard'

const DEMO_TICK_MS = 3000
const THEME_KEY = 'fuelops.theme'
const AI_BADGE = 'Written by AI'
const TEMPLATE_BADGE = 'Template text · AI unavailable'

function readTheme() {
  try {
    return localStorage.getItem(THEME_KEY) === 'dark' ? 'dark' : 'light'
  } catch {
    return 'light'
  }
}

/**
 * Everything the operator console needs: the model (live backend data, or the demo scenario)
 * plus the operator actions. Live data comes from useDashboard; `?demo=<state>` forces demo mode,
 * and the demo is also used when the backend can't be reached.
 */
export function useConsole() {
  const [params, setParams] = useSearchParams()
  const forced = DEMO_STATES[params.get('demo')] ? params.get('demo') : null
  const { state, link, error, refresh } = useDashboard({ enabled: !forced })

  const offline = !forced && !state && (!!error || link === 'offline')
  const demo = forced ?? (offline ? 'crisis' : null)
  const source = demo ? 'demo' : state ? 'live' : 'loading'

  // demo-only state
  const [t, setT] = useState(DEMO_START)
  const [playing, setPlaying] = useState(true)
  const [handled, setHandled] = useState({})
  const [extraLog, setExtraLog] = useState([])
  const [autopilot, setAutopilot] = useState(true)

  const [theme, setTheme] = useState(readTheme)
  useEffect(() => {
    try {
      localStorage.setItem(THEME_KEY, theme)
    } catch {
      /* storage unavailable: the theme just won't persist */
    }
  }, [theme])

  useEffect(() => {
    if (source !== 'demo' || !playing || demo === 'simdown') return undefined
    const iv = setInterval(() => setT((x) => (x + 15 > DEMO_START + DEMO_LOOP ? DEMO_START : x + 15)), DEMO_TICK_MS)
    return () => clearInterval(iv)
  }, [source, playing, demo])

  const model = useMemo(() => {
    if (source === 'demo') return buildDemoModel({ demo, t, handled, extraLog, autopilot, playing })
    if (source === 'live') return buildLiveModel(state, { link })
    return null
  }, [source, demo, t, handled, extraLog, autopilot, playing, state, link])

  const setDemo = useCallback(
    (key) => {
      const next = new URLSearchParams(params)
      if (key) next.set('demo', key)
      else next.delete('demo')
      setParams(next, { replace: true })
      setHandled({})
      setExtraLog([])
    },
    [params, setParams],
  )

  /** Approve (optionally with an edited quantity). Resolves to the toast text. */
  const approve = useCallback(
    async (rec, qty) => {
      if (source === 'demo') {
        const simDown = demo === 'simdown'
        setHandled((h) => ({ ...h, [rec.id]: 'approve' }))
        setExtraLog((l) => [demoDecisionEntry(rec, 'approve', { t, qty, simDown }), ...l])
        return simDown ? 'Approved. It will send when the simulator responds.' : `Sent ${fmt(qty)} L. Tracking in the action log.`
      }
      const body = qty !== rec.qty ? { quantity: qty } : {}
      const res = await recommendationsApi.approve(rec.id, body)
      await refresh()
      return res?.status === 'POSTED' ? `Sent ${fmt(res.quantity)} L. Tracking in the action log.`
        : res?.status === 'REFUSED' ? `The simulator refused it: ${res.error_message || res.error_code}`
          : 'Approved. It will send when the simulator responds.'
    },
    [source, demo, t, refresh],
  )

  const reject = useCallback(
    async (rec) => {
      if (source === 'demo') {
        setHandled((h) => ({ ...h, [rec.id]: 'reject' }))
        setExtraLog((l) => [demoDecisionEntry(rec, 'reject', { t }), ...l])
        return 'Rejected and logged.'
      }
      await recommendationsApi.reject(rec.id)
      await refresh()
      return 'Rejected and logged.'
    },
    [source, t, refresh],
  )

  /** Ask a question about a recommendation. Resolves to {text, badge}. */
  const ask = useCallback(
    async (rec, question) => {
      if (source === 'demo') {
        await new Promise((r) => setTimeout(r, 800))
        if (demo === 'aidown') return { text: rec.tpl, badge: TEMPLATE_BADGE }
        return { text: question === 'why' ? rec.why : rec.answers?.[question] ?? rec.why, badge: `${AI_BADGE} (Gemini)` }
      }
      try {
        const res = await aiApi.generate({ prompt: askPrompt(rec.facts, question), system: ASK_SYSTEM, max_tokens: 220, temperature: 0.2 })
        const text = (res?.text || '').trim()
        if (text && isGrounded(text, rec.facts)) {
          const provider = res.provider ? res.provider.charAt(0).toUpperCase() + res.provider.slice(1) : null
          return { text, badge: provider ? `${AI_BADGE} (${provider})` : AI_BADGE }
        }
      } catch {
        /* AI unavailable or rate limited: fall back to the template below */
      }
      return { text: rec.tpl, badge: TEMPLATE_BADGE }
    },
    [source, demo],
  )

  return {
    model,
    source,
    demo,
    offline,
    setDemo,
    theme,
    toggleTheme: () => setTheme((x) => (x === 'light' ? 'dark' : 'light')),
    togglePlay: () => setPlaying((p) => !p),
    toggleAutopilot: () => setAutopilot((a) => !a),
    approve,
    reject,
    ask,
    // badge for stored explanations (log modal): the backend's are engine-written templates
    logBadge: model?.aiDown ? TEMPLATE_BADGE : source === 'demo' ? `${AI_BADGE} (Gemini)` : 'Written by the decision engine',
  }
}
