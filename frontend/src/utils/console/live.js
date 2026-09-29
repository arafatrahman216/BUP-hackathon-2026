/**
 * Adapter: backend GET /dashboard payload → the console model (same shape as buildDemoModel).
 * Fields the backend does not compute yet (importance, risk before/after, runway…) show "—".
 */
import { withSummary } from './demo'
import { FUEL_LABEL, RISK, clamp, clock, dayTime, dur, fmt, hm, when } from './format'
import { RUSH, nodeKey, regionName, shortName } from './network'

const ACTIVE = ['PENDING', 'IN_TRANSIT']

const EVENT_TITLE = {
  demand_spike: (p, where) => `${where ? `${where} demand spike` : 'Demand spike'} ×${p.multiplier ?? 1.5}`,
  route_disruption: (p, where) => `Road closure${where ? `: ${where}` : ''}`,
  station_outage: (p, where) => `Station outage${where ? `: ${where}` : ''}`,
  depot_constraint: (p, where) => `Depot constrained${where ? `: ${where}` : ''}`,
  shipment_delay: (p, where) => `Ship delay${where ? ` at ${where}` : ''}`,
  supply_shortfall: (p, where) => `Supply shortfall${where ? ` at ${where}` : ''} ×${p.factor ?? 0.5}`,
}

/** "Simulator copy: unserved in the next hours 1,902 L -> 124 L" → {before, after} */
function parseImpact(text = '') {
  const m = /(\d[\d,]*(?:\.\d+)?) L -> (\d[\d,]*(?:\.\d+)?) L/.exec(text)
  return m ? { before: Number(m[1].replace(/,/g, '')), after: Number(m[2].replace(/,/g, '')) } : null
}

const confLabel = (c) => (c == null ? null : c >= 0.8 ? 'High' : c >= 0.6 ? 'Medium' : 'Low')

const ALERT_TITLE = {
  UNMET_DEMAND: 'Demand going unserved',
  STOCKOUT_RISK: 'Stations about to run dry',
  DEMAND_ANOMALY: 'Unusual demand',
  SUPPLY_DELAYED: 'Supply ship delayed',
  SUPPLY_SHORTFALL: 'Supply ship short',
  ROUTE_DISRUPTED: 'Road closed',
  STATION_OUTAGE: 'Station outage',
  DEPOT_CONSTRAINED: 'Depot constrained',
  DEPOT_OVERFLOW: 'Depot overflow ahead',
  CRISIS_ACTIVE: 'Crisis in progress',
  CRISIS_SCHEDULED: 'Crisis coming up',
  DEMAND_SPIKE: 'Demand spike',
  DISPATCH_BOTTLENECK: 'Depot dispatch limit reached',
  FUEL_WASTED: 'Fuel wasted at a full depot',
  INVENTORY_MISMATCH: 'Inventory mismatch',
  SHIPMENT_FAILED: 'Shipment failed',
  SHIPMENT_OVERDUE: 'Shipment overdue',
  SINGLE_ROUTE_CUT: 'Station cut off (only road closed)',
  SINGLE_ROUTE_THREAT: 'Only road to a station at risk',
  TICKS_SKIPPED: 'Missed simulator updates',
}

function logStatus(rec, alloc) {
  switch (rec.status) {
    case 'APPROVED':
      return { status: 'Held', c: 'var(--watch)' }
    case 'REJECTED':
      return { status: 'Rejected', c: 'var(--faint)' }
    case 'EXPIRED':
      return { status: 'Expired', c: 'var(--faint)' }
    case 'REFUSED':
      return { status: 'Refused', c: 'var(--urgent)' }
    case 'POSTED':
      if (!alloc) return { status: 'Sent', c: 'var(--accent)' }
      return {
        PENDING: { status: 'Departing', c: 'var(--accent)' },
        IN_TRANSIT: { status: 'In transit', c: 'var(--accent)' },
        ARRIVED: { status: 'Arrived', c: 'var(--safe)' },
        FAILED: { status: 'Failed', c: 'var(--urgent)' },
        CANCELLED: { status: 'Cancelled', c: 'var(--faint)' },
      }[alloc.status] ?? { status: alloc.status, c: 'var(--faint)' }
    default:
      return { status: rec.status, c: 'var(--faint)' }
  }
}

/**
 * @param {object} state  GET /dashboard payload
 * @param {{link?: string}} [opts]  browser ↔ backend link state from useDashboard
 */
export function buildLiveModel(state, { link } = {}) {
  const sim = state.sim ?? {}
  const tm = sim.tick_minutes || 15
  const tick = sim.tick ?? 0
  const now = tick * tm
  const at = (ticks) => now + ticks * tm

  const stationsById = Object.fromEntries((state.stations ?? []).map((s) => [s.id, s]))
  const depotsById = Object.fromEntries((state.depots ?? []).map((d) => [d.id, d]))
  const routes = state.routes ?? []
  const routesById = Object.fromEntries(routes.map((r) => [r.id, r]))
  const allocations = state.allocations ?? []
  const events = state.events ?? []
  const nameOf = (id) => shortName(stationsById[id]?.name || depotsById[id]?.name || nodeKey(id), id)
  const forecastOf = (sid, fuel) => stationsById[sid]?.fuels?.find((f) => f.fuel_type === fuel)

  // --- roads (and which ones close soon) ---
  const scheduledClosure = {}
  for (const e of events) {
    if (e.type !== 'route_disruption' || e.status !== 'SCHEDULED') continue
    const ids = e.parameters?.route_ids?.length ? e.parameters.route_ids : routes.map((r) => r.id)
    for (const id of ids) scheduledClosure[id] = Math.min(scheduledClosure[id] ?? Infinity, e.start_tick)
  }
  const roads = routes.map((r) => {
    const depot = depotsById[r.source_depot_id]
    const station = stationsById[r.destination_station_id]
    const closed = r.status !== 'AVAILABLE'
    const soon = scheduledClosure[r.id]
    return {
      id: nodeKey(r.id), a: nodeKey(r.source_depot_id), b: nodeKey(r.destination_station_id),
      name: `${nameOf(r.source_depot_id)} → ${nameOf(r.destination_station_id)}`,
      main: depot && station ? depot.region_id === station.region_id : r.transit_ticks < 4,
      min: r.transit_ticks * tm, max: r.max_shipment,
      closure: closed || soon !== undefined,
      status: closed ? 'Closed' : soon !== undefined ? `Closes ${hm(soon * tm)}` : 'Open',
      c: closed || soon !== undefined ? 'var(--urgent)' : 'var(--safe)',
    }
  })

  // --- stations ---
  const stations = (state.stations ?? []).map((s) => {
    const outage = s.status === 'OUTAGE'
    const m = Number(s.demand_multiplier ?? 1)
    const fuels = (s.fuels ?? []).map((fc) => {
      const tue = fc.ticks_until_empty
      const orderTicks = fc.order_by_tick != null ? Math.max(0, fc.order_by_tick - tick)
        : tue == null ? null : Math.max(0, tue - (fc.lead_ticks ?? 0) - 1)
      return {
        f: FUEL_LABEL[fc.fuel_type] ?? fc.fuel_type, fuel: fc.fuel_type, lvl: fc.inventory, cap: fc.capacity,
        risk: RISK[fc.risk] ? fc.risk : 'unknown',
        empty: tue == null ? 'Not soon' : when(at(tue), now),
        orderBy: orderTicks == null ? '—' : when(at(orderTicks), now),
        transit: fc.incoming || 0,
        transitAt: fc.incoming ? 'soon' : null,
        rate: fc.rate_per_tick || 0,
      }
    })
    return withSummary({
      id: s.id, key: nodeKey(s.id), name: shortName(s.name, s.id), region: regionName(s.region_id),
      single: routes.filter((r) => r.destination_station_id === s.id).length === 1,
      rush: RUSH[s.demand_profile] ?? '—',
      demand: m === 1 ? 'Normal' : `×${Number(m.toFixed(2))}`,
      nextOrder: outage ? 'Station closed (outage)' : undefined,
      fuels,
    })
  })

  // --- depots ---
  const supply = [...(state.supply ?? [])].sort((a, b) => a.planned_tick - b.planned_tick)
  const depots = (state.depots ?? []).map((d) => {
    const served = routes.filter((r) => r.source_depot_id === d.id && roads.find((x) => x.id === nodeKey(r.id))?.main)
    const fuels = (d.fuels ?? []).map((fl) => {
      const rate = served.reduce((sum, r) => sum + (forecastOf(r.destination_station_id, fl.fuel_type)?.rate_per_tick || 0), 0)
      const hours = rate > 0 ? (fl.inventory / rate) * (tm / 60) : null
      return { f: FUEL_LABEL[fl.fuel_type] ?? fl.fuel_type, lvl: fl.inventory, cap: fl.capacity, runway: hours == null ? '—' : `~${Math.round(hours)} h` }
    })
    const ship = supply.find((a) => a.depot_id === d.id)
    let overflow = 'None'
    const ov = (state.outlook?.depots ?? []).filter((x) => x.depot_id === d.id && x.overflow_liters > 0)
    if (ov.length) {
      overflow = ov.map((x) => `${FUEL_LABEL[x.fuel_type] ?? x.fuel_type} ${fmt(x.overflow_liters)} L${x.overflow_in_ticks != null ? ` in ${dur(x.overflow_in_ticks * tm)}` : ''}`).join(' · ')
    } else if (ship) {
      const fl = d.fuels?.find((x) => x.fuel_type === ship.fuel_type)
      const over = fl ? fl.inventory + ship.quantity - fl.capacity : 0
      if (over > 0) overflow = `${fmt(over)} L at risk`
    }
    return {
      id: d.id, key: nodeKey(d.id), name: shortName(d.name, d.id), region: regionName(d.region_id),
      statusLabel: (d.status || 'open').toLowerCase(), used: d.dispatch_used || 0, max: d.dispatch_capacity_per_tick || 0,
      fuels,
      ship: ship ? `${FUEL_LABEL[ship.fuel_type] ?? ship.fuel_type} +${fmt(ship.quantity)} L, ${dayTime(ship.planned_tick * tm)}` : 'None scheduled',
      shipShort: ship ? when(ship.planned_tick * tm, now) : 'none',
      overflow,
    }
  })

  // --- trucks on the road ---
  const trucks = allocations
    .filter((a) => ACTIVE.includes(a.status))
    .map((a) => {
      const dep = a.departure_tick
      const arr = a.expected_arrival_tick
      const p = a.status === 'IN_TRANSIT' && dep != null && arr > dep ? clamp((tick - dep) / (arr - dep), 0.05, 0.95) : 0.05
      return { road: nodeKey(a.route_id), p }
    })

  // --- action queue: recommendations waiting for the operator ---
  const open = state.recommendations?.open ?? []
  const queue = open
    .filter((r) => r.status === 'PENDING_APPROVAL' && r.tick <= tick)
    .map((r) => {
      const fc = forecastOf(r.station_id, r.fuel_type)
      const route = routesById[r.route_id]
      const transit = route?.transit_ticks ?? 0
      const remaining = fc?.ticks_until_empty != null ? fc.ticks_until_empty
        : r.ticks_until_empty != null ? Math.max(0, r.ticks_until_empty - (tick - r.tick)) : null
      const leftTicks = fc?.order_by_tick != null ? fc.order_by_tick - tick
        : remaining == null ? transit + 96 : remaining - transit - 1
      const impact = parseImpact(r.explanation)
      const p = fc?.p_stockout
      const conf = confLabel(fc?.confidence)
      const station = nameOf(r.station_id)
      const fuel = FUEL_LABEL[r.fuel_type] ?? r.fuel_type
      const reasons = r.reasons ?? []
      return {
        id: r.id, sev: r.risk === 'urgent' || r.risk === 'watch' ? r.risk : 'safe', st: r.station_id,
        title: `${station} · ${fuel}`, fuel, leftMin: leftTicks * tm, dl: when(at(leftTicks), now),
        qty: r.quantity, roadId: nodeKey(r.route_id), road: `${nameOf(r.depot_id)} → ${station}`,
        travel: transit * tm, arrives: hm(at(transit)), maxL: route?.max_shipment ?? r.quantity,
        emptyAt: remaining == null ? 'Not soon' : when(at(remaining), now),
        level: fc?.inventory ?? 0, cap: fc?.capacity ?? 0,
        demandNow: stationsById[r.station_id]?.demand_multiplier === 1 ? 'Normal' : `×${stationsById[r.station_id]?.demand_multiplier ?? '—'}`,
        signal: (reasons[0] ?? '—').replace(/^\w+: /, ''), conf: conf ?? `${r.planner} plan`,
        needs: reasons.length ? reasons.join('; ') : null,
        importance: impact ? `${fmt(impact.before)} L` : fc?.unmet_horizon != null ? `${fmt(fc.unmet_horizon)} L` : '—',
        importanceCap: 'unserved if not sent',
        riskB: p != null ? `${Math.round(p * 100)}%` : '—',
        riskBCap: 'chance to run dry',
        riskA: p != null && impact && impact.before > 0 ? `${Math.round(p * 100 * (impact.after / impact.before))}%` : '—',
        riskACap: impact ? `${fmt(impact.after)} L unserved with it` : null,
        why: r.explanation, tpl: r.explanation,
        facts: {
          station, fuel, quantity_l: r.quantity, depot: nameOf(r.depot_id), road: route?.id, road_max_l: route?.max_shipment,
          travel_min: transit * tm, level_l: fc?.inventory, capacity_l: fc?.capacity, use_per_15min_l: fc?.rate_per_tick,
          empty_at: remaining == null ? null : when(at(remaining), now), decide_by: when(at(leftTicks), now),
          risk: r.risk, reasons, now: clock(now),
          stockout_chance_pct: p != null ? Math.round(p * 100) : null, forecast_confidence: conf,
          unserved_without_l: impact?.before ?? null, unserved_with_l: impact?.after ?? null,
          station_has_one_road: routes.filter((x) => x.destination_station_id === r.station_id).length === 1,
          other_roads: routes
            .filter((x) => x.destination_station_id === r.station_id && x.id !== r.route_id)
            .map((x) => ({ road: `${nameOf(x.source_depot_id)} → ${station}`, travel_min: x.transit_ticks * tm, max_l: x.max_shipment,
              status: x.status === 'AVAILABLE' ? 'open' : 'closed', depot_stock_l: depotsById[x.source_depot_id]?.fuels?.find((f) => f.fuel_type === r.fuel_type)?.inventory })),
          chosen_road_closes_at: scheduledClosure[r.route_id] != null ? hm(scheduledClosure[r.route_id] * tm) : null,
        },
      }
    })
    .sort((a, b) => a.leftMin - b.leftMin)

  // --- action log: every recommendation the system or operator acted on ---
  const allocById = Object.fromEntries(allocations.map((a) => [a.id, a]))
  const log = (state.recommendations?.recent ?? [])
    // rows stamped after "now" come from a run before a simulator reset
    .filter((r) => r.status !== 'PENDING_APPROVAL' && (r.posted_tick ?? r.tick) <= tick)
    .map((r) => {
      const alloc = r.allocation_id != null ? allocById[r.allocation_id] : null
      const { status, c } = logStatus(r, alloc)
      const t = (r.posted_tick ?? r.tick) * tm
      const departed = alloc?.departure_tick != null
      const arrived = alloc?.actual_arrival_tick != null
      const station = nameOf(r.station_id)
      const fuel = FUEL_LABEL[r.fuel_type] ?? r.fuel_type
      return {
        id: r.id, title: `${station} · ${fuel} · ${fmt(r.quantity)} L`,
        actor: r.decision_mode === 'auto' ? 'Autopilot' : 'Operator', taken: dayTime(t), sortKey: t + r.id / 1e6,
        status, c, done: 1 + (departed ? 1 : 0) + (arrived ? 1 : 0),
        steps: [hm(t), departed ? hm(alloc.departure_tick * tm) : '—',
          arrived ? hm(alloc.actual_arrival_tick * tm) : alloc?.expected_arrival_tick != null ? `~${hm(alloc.expected_arrival_tick * tm)}` : '—', '—'],
        summary: r.operator_note ? `${r.explanation} Operator note: ${r.operator_note}` : r.explanation,
        tpl: r.explanation,
        state: [
          ['Proposed', `${fmt(r.proposed_quantity)} L`],
          ['Sent', r.status === 'POSTED' ? `${fmt(r.quantity)} L` : '—'],
          ['Empty in', r.ticks_until_empty == null ? '—' : dur(r.ticks_until_empty * tm)],
        ],
        check: r.error_code ? `${r.error_code}: ${r.error_message ?? ''}` : alloc ? `Shipment #${alloc.id} · ${alloc.status.toLowerCase().replace('_', ' ')}` : 'Not sent to the simulator',
        verdict: alloc?.status === 'ARRIVED' ? 'Delivered' : alloc?.status === 'FAILED' || r.status === 'REFUSED' ? 'Failed' : status === 'Rejected' || status === 'Expired' ? 'Not sent' : 'Waiting',
        vc: alloc?.status === 'ARRIVED' ? 'var(--safe)' : alloc?.status === 'FAILED' || r.status === 'REFUSED' ? 'var(--urgent)' : 'var(--faint)',
      }
    })
    .sort((a, b) => b.sortKey - a.sortKey)

  // --- incidents: crisis events that are active or coming up ---
  const incidents = events
    .filter((e) => e.status === 'ACTIVE' || e.status === 'SCHEDULED')
    .map((e) => {
      const p = e.parameters ?? {}
      const ids = [...(p.region_ids ?? []), ...(p.station_ids ?? []), ...(p.route_ids ?? []), ...(p.depot_ids ?? [])]
      const where = ids.map((id) => (id.startsWith('region-') ? regionName(id) : id.startsWith('route-') ? roads.find((r) => r.id === nodeKey(id))?.name ?? id : nameOf(id))).join(', ')
      const active = e.status === 'ACTIVE'
      const title = (EVENT_TITLE[e.type] ?? (() => e.type.replace('_', ' ')))(p, where)
      const waiting = queue.length ? ` ${queue.length} ${queue.length === 1 ? 'shipment is' : 'shipments are'} proposed.` : ''
      return {
        key: `ev-${e.id}`, c: active ? 'var(--urgent)' : 'var(--watch)', title,
        when: active ? `${hm(e.start_tick * tm)} – ${hm(e.end_tick * tm)}` : `in ${dur((e.start_tick - tick) * tm)}`,
        detail: `${active ? 'Active now' : `Starts ${hm(e.start_tick * tm)}`}, ends ${hm(e.end_tick * tm)}.${waiting}`,
      }
    })

  for (const inc of (state.incidents ?? []).filter((x) => x.status === 'open').slice(0, 3)) {
    const a = inc.alerts?.[0]
    if (!a) continue
    const kinds = new Set((inc.alerts ?? []).map((x) => x.code)).size
    incidents.push({
      key: `inc-${inc.id}`, c: (inc.alerts ?? []).some((x) => x.level === 'critical') ? 'var(--urgent)' : 'var(--watch)',
      title: inc.combined ? 'Combined crisis' : ALERT_TITLE[a.code] ?? a.code.replace(/_/g, ' ').toLowerCase(),
      when: `since ${hm(inc.opened_tick * tm)}`,
      detail: `${a.message}${kinds > 1 ? ` · ${kinds} kinds of alert` : ''}.`,
    })
  }
  const outlook = state.outlook ?? {}
  const shortest = Object.entries(outlook.fuels ?? {}).sort((x, y) => (x[1].days_left ?? 99) - (y[1].days_left ?? 99))[0]
  if (outlook.rationing && shortest) {
    const [fuel, o] = shortest
    incidents.push({
      key: 'outlook', c: 'var(--watch)', title: `${FUEL_LABEL[fuel] ?? fuel} runs out in ${o.days_left} days`,
      when: o.runs_out_at_tick != null ? dayTime(o.runs_out_at_tick * tm) : '',
      detail: `${fmt(o.stock_liters)} L left network-wide, ${fmt(o.demand_per_day)} L needed per day. ${o.remaining_supply_liters ? `${fmt(o.remaining_supply_liters)} L still arriving.` : 'No more ships scheduled.'} Rationing is on.`,
    })
  }

  const firstActive = incidents.find((i) => i.key.startsWith('ev-') && i.c === 'var(--urgent)')
  const backendDown = link === 'offline'
  const simDown = !sim.connected || backendDown
  const aiDown = (state.pipeline?.stages ?? []).some((s) => s.name === 'explain' && s.status === 'fallback')
  const age = sim.data_age_seconds == null ? null : Math.round(sim.data_age_seconds)
  const acting = !!state.pipeline?.acting && !simDown
  const metrics = state.metrics ?? {}
  const onRoad = allocations.filter((a) => ACTIVE.includes(a.status)).length

  return {
    source: 'live',
    now,
    clock: sim.tick == null ? 'Waiting for data' : clock(now),
    playLabel: simDown ? 'Frozen' : sim.status === 'PAUSED' ? 'Paused' : 'Running',
    canPlay: false,
    health: backendDown ? { c: 'var(--urgent)', text: 'Backend offline' }
      : simDown ? { c: 'var(--urgent)', text: 'Simulator down' }
        : sim.stale ? { c: 'var(--watch)', text: `Data may be stale${age != null ? ` · ${age} s old` : ''}` }
          : aiDown ? { c: 'var(--watch)', text: `AI down${age != null ? ` · data ${age} s old` : ''}` }
            : { c: 'var(--safe)', text: `All systems healthy${age != null ? ` · data ${age} s old` : ''}` },
    simDown,
    simDownText: `Showing data from ${sim.tick == null ? '—' : hm(now)} · retrying · autopilot paused`,
    aiDown,
    mode: firstActive ? { label: 'Crisis', reason: firstActive.title, c: 'var(--urgent)' }
      : outlook.rationing ? { label: 'Save fuel', reason: shortest ? `${FUEL_LABEL[shortest[0]] ?? shortest[0]}: ${shortest[1].days_left} days left` : 'Rationing on', c: 'var(--watch)' }
        : { label: 'Normal', reason: 'All within plan', c: 'var(--safe)' },
    service: {
      value: metrics.service_level == null ? '—' : `${(metrics.service_level * 100).toFixed(1)}%`,
      sub: metrics.unmet_demand_liters == null ? 'No data yet' : `${fmt(metrics.unmet_demand_liters)} L unserved so far`,
    },
    trucksCount: onRoad,
    autopilot: { on: acting, state: acting ? 'On' : 'Paused', label: acting ? 'Safe decisions only' : 'No fresh data', canToggle: false },
    incidents,
    emptyText: 'No shipments waiting for you',
    stations,
    depots,
    roads,
    trucks,
    queue,
    log,
  }
}

