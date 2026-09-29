import { describe, expect, it } from 'vitest'
import { buildDemoModel } from './demo'
import { dur, hm, lvlColor, when } from './format'
import { isGrounded } from './grounding'
import { buildLiveModel } from './live'

describe('format', () => {
  it('formats clock times and durations', () => {
    expect(hm(2250)).toBe('13:30')
    expect(when(2400, 2250)).toBe('16:00')
    expect(when(2880 + 375, 2250)).toBe('Day 3 06:15')
    expect(dur(135)).toBe('2h 15m')
    expect(dur(0)).toBe('overdue')
  })

  it('applies the level colour rule', () => {
    expect(lvlColor(17)).toBe('var(--low)')
    expect(lvlColor(31)).toBe('var(--mid)')
    expect(lvlColor(62)).toBe('var(--good)')
  })
})

describe('buildDemoModel', () => {
  it('has no queue in the empty state and a frozen clock when the simulator is down', () => {
    expect(buildDemoModel({ demo: 'empty' }).queue).toHaveLength(0)
    const down = buildDemoModel({ demo: 'simdown' })
    expect(down.simDown).toBe(true)
    expect(down.autopilot.state).toBe('Paused')
    expect(down.playLabel).toBe('Frozen')
  })
})

describe('buildLiveModel', () => {
  const base = {
    sim: { connected: true, stale: false, tick: 150, tick_minutes: 15 },
    pipeline: { acting: true, stages: [] },
    recommendations: { open: [], recent: [] },
    stations: [{ id: 'station-coxsbazar', name: "Cox's Bazar Fuel Station", region_id: 'region-chattogram', status: 'OPEN',
      demand_profile: 'regional', demand_multiplier: 1, fuels: [{ fuel_type: 'DIESEL', inventory: 5280, capacity: 12000, ticks_until_empty: 32, lead_ticks: 3, risk: 'watch', incoming: 0 }] }],
    depots: [{ id: 'depot-patiya', name: 'Patiya Depot', region_id: 'region-chattogram', fuels: [] }],
    routes: [{ id: 'route-patiya-coxsbazar', source_depot_id: 'depot-patiya', destination_station_id: 'station-coxsbazar', transit_ticks: 3, max_shipment: 6000, status: 'AVAILABLE' }],
    events: [{ id: 2, type: 'route_disruption', start_tick: 168, end_tick: 192, status: 'SCHEDULED', parameters: { route_ids: ['route-patiya-coxsbazar'] } }],
    allocations: [], supply: [], metrics: {},
  }

  it('maps ids to map keys, single-road stations and scheduled closures', () => {
    const m = buildLiveModel(base)
    expect(m.stations[0]).toMatchObject({ key: 'coxs', name: "Cox's Bazar", single: true, rush: '07:00–20:59' })
    expect(m.stations[0].fuels[0]).toMatchObject({ empty: '21:30', orderBy: '20:30' })
    expect(m.roads[0]).toMatchObject({ id: 'patiya-coxsbazar', b: 'coxs', main: true, closure: true, status: 'Closes 18:00' })
    expect(m.incidents[0]).toMatchObject({ title: "Road closure: Patiya → Cox's Bazar", when: 'in 4h 30m' })
  })

  it('reports the simulator as down and pauses autopilot', () => {
    const m = buildLiveModel({ ...base, sim: { ...base.sim, connected: false } })
    expect(m.simDown).toBe(true)
    expect(m.health.text).toBe('Simulator down')
    expect(m.autopilot.state).toBe('Paused')
  })
})

describe('isGrounded', () => {
  const facts = { quantity_l: 7000, empty_at: '16:45', road_max_l: 5000 }
  it('accepts answers that only use numbers from the facts', () => {
    expect(isGrounded('Send 7,000 L before 16:45; the backup road carries 5,000 L.', facts)).toBe(true)
  })
  it('rejects invented numbers', () => {
    expect(isGrounded('About 900 L goes unserved.', facts)).toBe(false)
  })
})
