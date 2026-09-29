import { useCallback, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { explainApi, recommendationsApi } from '../api/api'
import { DEMO_LOOP, DEMO_START, DEMO_STATES, buildDemoModel, demoDecisionEntry } from '../utils/console/demo'
import { fmt } from '../utils/console/format'
import { buildLiveModel } from '../utils/console/live'
import { useDashboard } from './useDashboard'

const DEMO_TICK_MS = 3000
const THEME_KEY = 'fuelops.theme'
const AI_BADGE = 'Written by AI'
const TEMPLATE_BADGE = 'Template text · AI unavailable'
const ENGINE_BADGE = 'Written by the decision engine'
// demo answers are keyed by these (utils/console/demo.js); live questions come from the backend
const DEMO_QUESTIONS = ['Why not Patiya?', 'Wait an hour?', 'If the road closes?']
const WHY = {
  rec: 'Why is this shipment recommended?',
  log: 'Why was this action taken, and what happened to it?',
}

const providerName = (p) => (p ? p.charAt(0).toUpperCase() + p.slice(1) : null)
/** A stored backend Q&A → the answer shape the console shows. */
export const toAnswer = (qa) => ({
  q: qa.question, text: qa.answer, at: qa.tick, context: qa.context,
  badge: qa.provider === 'template' ? ENGINE_BADGE
    : providerName(qa.provider) ? `${AI_BADGE} (${providerName(qa.provider)} · ${qa.model})` : AI_BADGE,
})

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

  /**
   * Suggested questions for an action (queue item or log entry) and the answers already stored.
   * Live: GET /explain/recommendations/{id} (suggestions depend on the recommendation's status).
   */
  const questions = useCallback(
    async (item, kind = 'rec') => {
      if (source === 'demo') return { suggestions: kind === 'rec' ? DEMO_QUESTIONS : [], history: [] }
      try {
        const res = await explainApi.questions(item.id)
        return { suggestions: res.suggestions ?? [], history: (res.items ?? []).map(toAnswer) }
      } catch {
        return { suggestions: [], history: [] } // "Ask why" and the free-text box still work
      }
    },
    [source],
  )

  /**
   * Ask about an action. `question` is 'why' or free text. Resolves to {q, text, badge, context?}.
   * Live: POST /explain/recommendations/{id}: the backend builds the metrics for this action (pipeline
   * forecasts/alerts, its truck, demand history from the simulator), asks Gemini and stores the answer.
   */
  const ask = useCallback(
    async (item, question, kind = 'rec') => {
      if (source === 'demo') {
        await new Promise((r) => setTimeout(r, 800))
        if (demo === 'aidown') return { q: question, text: item.tpl, badge: TEMPLATE_BADGE }
        const why = item.why ?? item.summary
        return { q: question, text: question === 'why' ? why : item.answers?.[question] ?? why, badge: `${AI_BADGE} (Gemini)` }
      }
      try {
        return { ...toAnswer(await explainApi.ask(item.id, question === 'why' ? WHY[kind] : question)), q: question }
      } catch (err) {
        const why = err?.code === 'RATE_LIMITED' ? ` · too many questions, retry in ${err.retryAfter ?? 60} s` : ''
        return { q: question, text: item.tpl, badge: `${TEMPLATE_BADGE}${why}` }
      }
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
    questions,
    // badge for stored explanations (log modal): the backend's are engine-written templates
    logBadge: model?.aiDown ? TEMPLATE_BADGE : source === 'demo' ? `${AI_BADGE} (Gemini)` : ENGINE_BADGE,
  }
}
