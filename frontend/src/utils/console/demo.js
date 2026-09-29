/**
 * Demo scenario from the design handoff (Day 2 13:30, Dhaka spike). Used when the page is opened
 * with ?demo=<state>, or when the backend is unreachable. Everything here is sample data.
 */
import { clock, dayTime, dur, fmt, pct, pctN } from './format'

export const DEMO_STATES = {
  normal: 'Normal',
  crisis: 'Crisis',
  simdown: 'Simulator down',
  aidown: 'AI down',
  empty: 'Empty queue',
}

export const DEMO_START = 2250 // Day 2 13:30
export const DEMO_LOOP = 135 // the clock loops back after 2h 15m

const ROADS = [
  { id: 'gazipur-mirpur', a: 'gazipur', b: 'mirpur', name: 'Gazipur → Mirpur', main: true, min: 30, max: 7000 },
  { id: 'gazipur-tongi', a: 'gazipur', b: 'tongi', name: 'Gazipur → Tongi', main: true, min: 30, max: 6500 },
  { id: 'patiya-karnaphuli', a: 'patiya', b: 'karnaphuli', name: 'Patiya → Karnaphuli', main: true, min: 30, max: 7000 },
  { id: 'patiya-coxs', a: 'patiya', b: 'coxs', name: "Patiya → Cox's Bazar", main: true, min: 45, max: 6000 },
  { id: 'gazipur-karnaphuli', a: 'gazipur', b: 'karnaphuli', name: 'Gazipur → Karnaphuli', main: false, min: 60, max: 5000 },
  { id: 'patiya-mirpur', a: 'patiya', b: 'mirpur', name: 'Patiya → Mirpur', main: false, min: 60, max: 5000 },
]

const STATIONS = [
  { id: 'mirpur', name: 'Mirpur', region: 'Dhaka', single: false, rush: '16:00–20:00', demand: '+78%',
    fuels: [{ f: 'Diesel', lvl: 9300, cap: 15000, risk: 'safe', empty: 'Day 3 07:00', orderBy: 'Day 3 06:15', transit: 0 },
      { f: 'Petrol', lvl: 2400, cap: 14000, risk: 'urgent', empty: '16:45', orderBy: '16:00', transit: 0 },
      { f: 'Octane', lvl: 4320, cap: 9000, risk: 'safe', empty: 'Day 3 02:30', orderBy: 'Day 3 01:45', transit: 0 }] },
  { id: 'tongi', name: 'Tongi', region: 'Dhaka', single: true, rush: 'until 17:59', demand: '+64%',
    fuels: [{ f: 'Diesel', lvl: 5580, cap: 18000, risk: 'watch', empty: '20:15', orderBy: '19:30', transit: 0 },
      { f: 'Petrol', lvl: 4950, cap: 9000, risk: 'safe', empty: 'Day 3 09:00', orderBy: 'Day 3 08:15', transit: 0 },
      { f: 'Octane', lvl: 2400, cap: 6000, risk: 'safe', empty: 'Day 3 14:00', orderBy: 'Day 3 13:15', transit: 0 }] },
  { id: 'karnaphuli', name: 'Karnaphuli', region: 'Chattogram', single: false, rush: '16:00–20:00', demand: '+4%',
    fuels: [{ f: 'Diesel', lvl: 8120, cap: 14000, risk: 'safe', empty: 'Day 3 02:00', orderBy: 'Day 3 01:15', transit: 0 },
      { f: 'Petrol', lvl: 7500, cap: 15000, risk: 'safe', empty: 'Day 3 01:00', orderBy: 'Day 3 00:15', transit: 0 },
      { f: 'Octane', lvl: 1980, cap: 9000, risk: 'safe', empty: 'Day 3 03:00', orderBy: 'Day 3 02:15', transit: 3000, transitAt: '13:45' }] },
  { id: 'coxs', name: "Cox's Bazar", region: 'Chattogram', single: true, rush: 'until 20:59', demand: '+2%',
    fuels: [{ f: 'Diesel', lvl: 5280, cap: 12000, risk: 'plan', empty: '21:30', orderBy: '17:00', transit: 0 },
      { f: 'Petrol', lvl: 7320, cap: 12000, risk: 'safe', empty: 'Day 3 06:00', orderBy: 'Day 3 05:15', transit: 0 },
      { f: 'Octane', lvl: 3640, cap: 7000, risk: 'safe', empty: 'Day 3 10:00', orderBy: 'Day 3 09:15', transit: 0 }] },
]

const DEPOTS = [
  { id: 'gazipur', name: 'Gazipur', region: 'Dhaka', statusLabel: 'open', used: 0, max: 12000,
    fuels: [{ f: 'Diesel', lvl: 86000, cap: 90000, runway: '~52 h' }, { f: 'Petrol', lvl: 41000, cap: 70000, runway: '~30 h' },
      { f: 'Octane', lvl: 22000, cap: 45000, runway: '~44 h' }],
    ship: 'Diesel +12,000 L, Day 3 00:00', shipShort: 'Day 3 00:00', overflow: '8,000 L · covered by plan' },
  { id: 'patiya', name: 'Patiya', region: 'Chattogram', statusLabel: 'open', used: 3000, max: 11000,
    fuels: [{ f: 'Diesel', lvl: 48000, cap: 85000, runway: '~40 h' }, { f: 'Petrol', lvl: 58000, cap: 65000, runway: '~48 h' },
      { f: 'Octane', lvl: 19000, cap: 40000, runway: '~36 h' }],
    ship: 'Petrol +8,000 L, Day 3 04:00', shipShort: 'Day 3 04:00', overflow: '1,000 L · covered by plan' },
]

const RECS = [
  { id: 42, sev: 'urgent', st: 'mirpur', title: 'Mirpur · Petrol', fuel: 'Petrol', deadline: 2400, dl: '16:00', qty: 7000,
    roadId: 'gazipur-mirpur', road: 'Gazipur → Mirpur', travel: 30, arrives: '16:30', maxL: 7000,
    emptyAt: '16:45', unserved: 4800, level: 2400, cap: 14000, demandNow: '+78%', signal: 'Dhaka spike ×1.8',
    conf: 'High', needs: null, importance: 92, riskB: '88%', riskA: '6%',
    why: "The Dhaka spike and the 16:00 rush will empty Mirpur's petrol at 16:45. A 7,000 L truck from Gazipur arrives at 16:30 and keeps it safe until Day 3 06:00.",
    answers: {
      'Why not Patiya?': 'The backup road takes 60 minutes and carries 5,000 L at most. Sent at 16:00 it arrives after the tank is empty.',
      'Wait an hour?': 'The truck would arrive at 17:30, 45 minutes after Mirpur runs dry. About 900 L goes unserved.',
      'If the road closes?': 'The backup road from Patiya can carry 5,000 L. It would need to leave by 15:30.',
    },
    tpl: 'Mirpur petrol empties at 16:45. 7,000 L via Gazipur → Mirpur arrives 16:30. Without it: ~4,800 L unserved.' },
  { id: 44, sev: 'plan', st: 'coxs', title: "Cox's Bazar · Diesel", fuel: 'Diesel', deadline: 2460, dl: '17:00', qty: 6000,
    roadId: 'patiya-coxs', road: "Patiya → Cox's Bazar", travel: 45, arrives: '17:45', maxL: 6000,
    emptyAt: '21:30', unserved: 1600, level: 5280, cap: 12000, demandNow: '+2%', signal: 'Only road closes 18:00',
    conf: 'High', needs: null, importance: 74, riskB: '71%', riskA: '8%',
    why: "Cox's Bazar's only road closes 18:00–24:00. Without a delivery, diesel runs out at 21:30. 6,000 L sent now arrives at 17:45, before the closure.",
    answers: {
      'Why not Patiya?': "Patiya is already the source; it is the only depot that reaches Cox's Bazar.",
      'Wait an hour?': 'The truck would reach the road as it closes. The shipment would fail.',
      'If the road closes?': 'The closure is already planned for. There is no backup road, so this must arrive by 18:00.',
    },
    tpl: "Cox's Bazar diesel empties at 21:30; its only road closes at 18:00. 6,000 L via Patiya arrives 17:45." },
  { id: 45, sev: 'watch', st: 'tongi', title: 'Tongi · Diesel', fuel: 'Diesel', deadline: 2610, dl: '19:30', qty: 6500,
    roadId: 'gazipur-tongi', road: 'Gazipur → Tongi', travel: 30, arrives: '20:00', maxL: 6500,
    emptyAt: '20:15', unserved: 2300, level: 5580, cap: 18000, demandNow: '+64%', signal: 'Forecast error 22%',
    conf: 'Medium', needs: 'Forecast error 22%', importance: 63, riskB: '54%', riskA: '11%',
    why: "Tongi's diesel demand is 64% above forecast, so the tank empties around 20:15. 6,500 L from Gazipur arrives at 20:00. It needs your review because the forecast has been off by 22% today.",
    answers: {
      'Why not Patiya?': 'Tongi has one road, from Gazipur. Patiya cannot reach it.',
      'Wait an hour?': 'The truck would arrive 45 minutes after the tank empties. About 500 L goes unserved.',
      'If the road closes?': 'No fuel could reach Tongi. Sending before 18:00 would be safer.',
    },
    tpl: 'Tongi diesel empties at 20:15. 6,500 L via Gazipur arrives 20:00. Needs review: forecast error 22%.' },
]

const tMin = (x) => {
  const m = /Day (\d+) (\d+):(\d+)/.exec(x)
  return m ? (+m[1] - 1) * 1440 + +m[2] * 60 + +m[3] : 0
}

const LOG = [
  { id: 43, title: 'Karnaphuli · Octane · 3,000 L', actor: 'Autopilot', taken: 'Day 2 13:15', status: 'In transit', c: 'var(--accent)', done: 2,
    steps: ['13:15', '13:15', '~13:45', '—'],
    summary: 'Autopilot sent 3,000 L of octane from Patiya because Karnaphuli would have run out at 18:30. It met every autopilot rule.',
    state: [['Octane', '1,980 L (22%)'], ['Empty at', '18:30'], ['Demand', '+4%']], check: 'Arrival predicted 13:45', verdict: 'Waiting', vc: 'var(--faint)' },
  { id: 38, title: 'Mirpur · Petrol · 5,000 L', actor: 'Operator', taken: 'Day 1 12:15', status: 'Verified', c: 'var(--safe)', done: 4,
    steps: ['12:15', '12:15', '12:45', '13:00'],
    summary: 'Approved ahead of the lunchtime peak. It arrived at 12:45 as predicted, and the lowest level stayed close to the forecast.',
    state: [['Petrol', '3,100 L (22%)'], ['Empty at', '14:30'], ['Demand', '+6%']], check: 'Lowest level: predicted 1,400 L · actual 1,520 L', verdict: 'Prediction held', vc: 'var(--safe)' },
  { id: 40, title: 'Tongi · Diesel · 6,500 L', actor: 'Operator', taken: 'Day 2 06:10', status: 'Missed', c: 'var(--urgent)', done: 4,
    steps: ['06:10', '06:15', '06:45', '13:00'],
    summary: 'Arrived on time, but the level fell lower than forecast once the Dhaka spike began. The forecaster was rescaled at 12:30.',
    state: [['Diesel', '4,200 L (23%)'], ['Empty at', '09:15'], ['Demand', '+2%']], check: 'Lowest level: predicted 2,000 L · actual 1,150 L', verdict: 'Forecast too low', vc: 'var(--urgent)' },
  { id: 37, title: "Cox's Bazar · Petrol · 4,000 L", actor: 'Autopilot', taken: 'Day 2 09:00', status: 'Verified', c: 'var(--safe)', done: 4,
    steps: ['09:00', '09:00', '09:45', '10:30'],
    summary: 'Sent ahead of daytime demand. Arrived at 09:45 and stayed above the safety level.',
    state: [['Petrol', '3,400 L (28%)'], ['Empty at', '13:45'], ['Demand', '+1%']], check: 'Lowest level: predicted 1,900 L · actual 2,050 L', verdict: 'Prediction held', vc: 'var(--safe)' },
  { id: 36, title: 'Mirpur · Diesel · 3,000 L', actor: 'Operator', taken: 'Day 2 08:30', status: 'Rejected', c: 'var(--faint)', done: 1,
    steps: ['08:30', '—', '—', '—'],
    summary: 'Rejected by the operator. Diesel stayed above 55% all morning, so it was not needed.',
    state: [['Diesel', '8,900 L (59%)'], ['Empty at', 'Day 3 04:00'], ['Demand', '+3%']], check: 'Lowest level: predicted 6,800 L · actual 7,100 L', verdict: 'Not sent', vc: 'var(--faint)' },
]

function demoStations(calm, empty) {
  return STATIONS.map((s) => {
    const fuels = s.fuels.map((f) => ({ ...f }))
    let demand = s.demand
    if (calm) {
      demand = '+2%'
      if (s.id === 'mirpur') Object.assign(fuels[1], { lvl: 9800, risk: 'safe', empty: 'Day 3 03:00', orderBy: 'Day 3 02:15' })
      if (s.id === 'coxs') Object.assign(fuels[0], { lvl: 7400, risk: 'safe', empty: 'Day 3 05:00', orderBy: 'Day 3 04:15' })
      if (s.id === 'tongi' && empty) Object.assign(fuels[0], { lvl: 11200, risk: 'safe', empty: 'Day 3 08:00', orderBy: 'Day 3 07:15' })
    }
    return withSummary({ ...s, key: s.id, demand, fuels })
  })
}

/** Adds minP (lowest fuel %) and the "next order" line shared by the map, tables and panel. */
export function withSummary(station) {
  const minP = Math.min(...station.fuels.map((f) => pctN(f.lvl, f.cap)))
  const next = station.fuels.find((f) => f.risk !== 'safe' && f.orderBy && f.orderBy !== '—')
  return { ...station, minP, nextOrder: station.nextOrder ?? (next ? `${next.f} order by ${next.orderBy}` : 'No order needed today') }
}

/**
 * Build the console model for a demo state.
 * @param {{demo: string, t: number, handled: object, extraLog: object[], autopilot: boolean, playing: boolean}} s
 */
export function buildDemoModel({ demo = 'crisis', t = DEMO_START, handled = {}, extraLog = [], autopilot = true, playing = true }) {
  const simDown = demo === 'simdown'
  const aiDown = demo === 'aidown'
  const crisis = !(demo === 'normal' || demo === 'empty')

  const stations = demoStations(!crisis, demo === 'empty')
  let recs = RECS
  if (demo === 'empty') recs = []
  if (demo === 'normal') recs = [{ ...RECS[2], needs: null, conf: 'High', demandNow: '+3%', signal: 'Industrial hours' }]

  const queue = recs
    .filter((r) => !handled[r.id])
    .map((r) => ({ ...r, leftMin: r.deadline - t }))
    .sort((a, b) => a.leftMin - b.leftMin)

  const log = [...extraLog, ...LOG]
    .map((l) => ({ ...l, sortKey: l.sortKey ?? tMin(l.taken) }))
    .sort((a, b) => b.sortKey - a.sortKey)

  const roads = ROADS.map((r) => {
    const closure = crisis && r.id === 'patiya-coxs'
    return { ...r, closure, status: closure ? 'Closes 18:00' : 'Open', c: closure ? 'var(--urgent)' : 'var(--safe)' }
  })
  const trucks = [{ road: 'patiya-karnaphuli', p: 0.6 }, ...extraLog.filter((l) => l.roadId).map((l) => ({ road: l.roadId, p: 0.25 }))]

  const incidents = []
  if (crisis) {
    incidents.push({ key: 'spike', c: 'var(--urgent)', title: 'Dhaka demand spike ×1.8', when: '12:00 – 22:00',
      detail: 'Demand is up at Mirpur and Tongi. Two shipments are proposed.' })
    const closing = t < 2520
    incidents.push({ key: 'closure', c: 'var(--watch)', title: closing ? "Cox's Bazar road closes soon" : "Cox's Bazar road closed",
      when: closing ? `in ${dur(2520 - t)}` : 'until 24:00',
      detail: "Patiya → Cox's Bazar, 18:00 – 24:00. There is no backup road." })
  }
  if (aiDown) incidents.push({ key: 'ai', c: 'var(--watch)', title: 'AI explainer down', when: 'now', detail: 'Explanations use template text. Nothing else changes.' })

  const autoOn = autopilot && !simDown
  return {
    source: 'demo',
    now: t,
    clock: clock(t),
    playLabel: simDown ? 'Frozen' : playing ? 'Pause' : 'Play',
    canPlay: !simDown,
    health: simDown ? { c: 'var(--urgent)', text: 'Simulator down' }
      : aiDown ? { c: 'var(--watch)', text: 'AI down · data 2 s old' }
        : { c: 'var(--safe)', text: 'All systems healthy · data 2 s old' },
    simDown,
    simDownText: 'Showing data from 13:28 · retrying · autopilot paused',
    aiDown,
    mode: crisis ? { label: 'Crisis', reason: 'Dhaka spike ×1.8', c: 'var(--urgent)' } : { label: 'Normal', reason: 'All within plan', c: 'var(--safe)' },
    service: { value: '96.4%', sub: '+15.2 pts vs no action' },
    trucksCount: trucks.length,
    autopilot: { on: autoOn, state: simDown ? 'Paused' : autoOn ? 'On' : 'Off',
      label: simDown ? 'No fresh data' : autoOn ? 'Safe decisions only' : 'Every shipment needs you', canToggle: true },
    incidents,
    emptyText: 'All stations covered until 18:00',
    stations,
    depots: DEPOTS.map((d) => ({ ...d, key: d.id })),
    roads,
    trucks,
    queue,
    log,
  }
}

/** The log entry the demo adds when the operator approves or rejects. */
export function demoDecisionEntry(rec, kind, { t, qty, simDown }) {
  const taken = dayTime(t)
  const at = taken.split(' ').pop()
  const state = [[rec.fuel, `${fmt(rec.level)} L (${pct(rec.level, rec.cap)})`], ['Empty at', rec.emptyAt], ['Demand', rec.demandNow]]
  if (kind === 'approve') {
    return { id: `${rec.id}-${t}`, roadId: simDown ? null : rec.roadId, title: `${rec.title} · ${fmt(qty)} L`, actor: 'Operator', taken, sortKey: t + 0.5,
      status: simDown ? 'Held' : 'Departing', c: simDown ? 'var(--watch)' : 'var(--accent)', done: 1, steps: [at, '—', `~${rec.arrives}`, '—'],
      summary: rec.why, tpl: rec.tpl, state, check: `Arrival predicted ${rec.arrives}`, verdict: 'Waiting', vc: 'var(--faint)' }
  }
  return { id: `${rec.id}-${t}`, title: `${rec.title} · ${fmt(rec.qty)} L`, actor: 'Operator', taken, sortKey: t + 0.5, status: 'Rejected',
    c: 'var(--faint)', done: 1, steps: [at, '—', '—', '—'],
    summary: `Rejected by the operator. Without it the station is projected to run empty at ${rec.emptyAt}.`, tpl: rec.tpl, state,
    check: `Projected unserved ${fmt(rec.unserved)} L`, verdict: 'Not sent', vc: 'var(--faint)' }
}

