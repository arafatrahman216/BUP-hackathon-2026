import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { jsonResponse, renderWithProviders } from '../../test/utils'
import ConsolePage from './ConsolePage'

const rec = {
  id: 7, tick: 150, station_id: 'station-mirpur', fuel_type: 'PETROL', depot_id: 'depot-gazipur',
  route_id: 'route-gazipur-mirpur', quantity: 7000, proposed_quantity: 7000, risk: 'urgent', ticks_until_empty: 13,
  important: true, decision_mode: 'operator', reasons: ['urgent: station may run dry before the truck arrives'],
  explanation: 'Mirpur Fuel Station PETROL holds 2,400 of 14,000 L.', planner: 'rules', status: 'PENDING_APPROVAL',
  operator_note: null, idempotency_key: null, allocation_id: null, posted_tick: null, error_code: null, error_message: null,
}
const done = { ...rec, id: 5, tick: 140, station_id: 'station-tongi', fuel_type: 'DIESEL', decision_mode: 'auto', status: 'POSTED', allocation_id: 3, posted_tick: 140 }

const state = {
  sim: { connected: true, link: 'sse', stale: false, data_age_seconds: 2, tick: 150, sim_time: '2026-01-02T13:30:00', status: 'RUNNING', tick_minutes: 15 },
  pipeline: { acting: true, runs: 3, last_run: null, stages: [{ name: 'explain', status: 'ok' }], validation_issues: [] },
  alerts: [], blocked: [],
  recommendations: { open: [rec], recent: [rec, done] },
  stations: [
    { id: 'station-mirpur', name: 'Mirpur Fuel Station', region_id: 'region-dhaka', status: 'OPEN', demand_profile: 'urban_high', demand_multiplier: 1.8,
      fuels: [{ fuel_type: 'PETROL', inventory: 2400, capacity: 14000, rate_per_tick: 180, incoming: 0, ticks_until_empty: 13, cover_ticks: 13, lead_ticks: 2, risk: 'urgent' }] },
    { id: 'station-tongi', name: 'Tongi Fuel Station', region_id: 'region-dhaka', status: 'OPEN', demand_profile: 'industrial', demand_multiplier: 1,
      fuels: [{ fuel_type: 'DIESEL', inventory: 9000, capacity: 18000, rate_per_tick: 220, incoming: 6500, ticks_until_empty: 40, cover_ticks: 70, lead_ticks: 2, risk: 'safe' }] },
  ],
  depots: [{ id: 'depot-gazipur', name: 'Gazipur Depot', region_id: 'region-dhaka', status: 'OPEN', dispatch_capacity_per_tick: 12000, dispatch_used: 0,
    fuels: [{ fuel_type: 'DIESEL', inventory: 86000, capacity: 90000 }, { fuel_type: 'PETROL', inventory: 41000, capacity: 70000 }] }],
  routes: [
    { id: 'route-gazipur-mirpur', source_depot_id: 'depot-gazipur', destination_station_id: 'station-mirpur', transit_ticks: 2, max_shipment: 7000, status: 'AVAILABLE' },
    { id: 'route-gazipur-tongi', source_depot_id: 'depot-gazipur', destination_station_id: 'station-tongi', transit_ticks: 2, max_shipment: 6500, status: 'AVAILABLE' },
  ],
  supply: [{ id: 'supply-301', depot_id: 'depot-gazipur', fuel_type: 'DIESEL', quantity: 12000, planned_tick: 192, actual_tick: null, status: 'SCHEDULED' }],
  events: [{ id: 1, type: 'demand_spike', start_tick: 144, end_tick: 184, status: 'ACTIVE', parameters: { region_ids: ['region-dhaka'], multiplier: 1.8 } }],
  allocations: [{ id: 3, route_id: 'route-gazipur-tongi', source_depot_id: 'depot-gazipur', destination_station_id: 'station-tongi', fuel_type: 'DIESEL',
    quantity: 6500, created_tick: 140, departure_tick: 141, expected_arrival_tick: 143, actual_arrival_tick: 143, status: 'ARRIVED' }],
  metrics: { service_level: 0.964, unmet_demand_liters: 420, served_demand_liters: 11200, allocation_liters: 6500, allocation_failures: 0 },
}

describe('ConsolePage · demo', () => {
  it('shows the crisis scenario and handles an approval', async () => {
    renderWithProviders(<ConsolePage />, { route: '/?demo=crisis' })

    expect(screen.getByRole('heading', { name: 'Operations' })).toBeInTheDocument()
    expect(screen.getByText('Dhaka demand spike ×1.8')).toBeInTheDocument()
    expect(screen.getByText('DEMO DATA')).toBeInTheDocument()

    const queue = screen.getByRole('region', { name: 'Action queue' })
    const items = within(queue).getAllByRole('button')
    expect(items[0]).toHaveTextContent('Mirpur · Petrol') // earliest deadline first
    expect(items).toHaveLength(3)

    await userEvent.click(items[0])
    const dialog = screen.getByRole('dialog')
    expect(within(dialog).getByText('Send 7,000 L · Gazipur → Mirpur')).toBeInTheDocument()

    await userEvent.click(within(dialog).getByRole('button', { name: 'Why not Patiya?' }))
    expect(await within(dialog).findByText(/backup road takes 60 minutes/, {}, { timeout: 2000 })).toBeInTheDocument()
    expect(within(dialog).getByText('Written by AI (Gemini)')).toBeInTheDocument()

    await userEvent.click(within(dialog).getByRole('button', { name: 'Approve' }))
    expect(await screen.findByText('Sent 7,000 L. Tracking in the action log.')).toBeInTheDocument()
    expect(within(queue).getAllByRole('button')).toHaveLength(2)
    expect(screen.getByRole('region', { name: 'Action log' })).toHaveTextContent('Departing')
  })

  it('switches to the table view and opens a station panel', async () => {
    renderWithProviders(<ConsolePage />, { route: '/?demo=normal' })
    await userEvent.click(screen.getByRole('button', { name: 'All states' }))
    await userEvent.click(within(screen.getByRole('region', { name: 'Network' })).getByRole('button', { name: /Tongi/ }))
    const panel = screen.getByRole('dialog')
    expect(within(panel).getByText('Station · Dhaka · single road')).toBeInTheDocument()
  })

  it('uses template text when the AI is down', async () => {
    renderWithProviders(<ConsolePage />, { route: '/?demo=aidown' })
    expect(screen.getByText('AI explainer down')).toBeInTheDocument()
    await userEvent.click(within(screen.getByRole('region', { name: 'Action queue' })).getAllByRole('button')[0])
    await userEvent.click(screen.getByRole('button', { name: 'Ask why' }))
    expect(await screen.findByText('Template text · AI unavailable', {}, { timeout: 2000 })).toBeInTheDocument()
  })
})

describe('ConsolePage · live backend', () => {
  it('renders backend data and posts an edited approval', async () => {
    vi.stubGlobal('EventSource', undefined) // jsdom has none: the hook falls back to REST
    const fetchMock = vi.fn((url, init) =>
      Promise.resolve(init?.method === 'POST' ? jsonResponse({ ...rec, status: 'POSTED', quantity: 6500 }) : jsonResponse(state)),
    )
    vi.stubGlobal('fetch', fetchMock)
    renderWithProviders(<ConsolePage />)

    expect(await screen.findByText('96.4%')).toBeInTheDocument()
    expect(screen.getByText('Day 2 · 13:30')).toBeInTheDocument()
    expect(screen.getAllByText('Dhaka demand spike ×1.8')).toHaveLength(2) // incident card + mode reason
    expect(screen.getByRole('region', { name: 'Action log' })).toHaveTextContent('Arrived')

    // 13 ticks to empty − 2 transit − 1 buffer = 10 ticks = 2h 30m → decide by 16:00
    const item = within(screen.getByRole('region', { name: 'Action queue' })).getByRole('button')
    expect(item).toHaveTextContent('16:00')
    expect(item).toHaveTextContent('2h 30m left')

    await userEvent.click(item)
    const dialog = screen.getByRole('dialog')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Edit quantity' }))
    await userEvent.click(within(dialog).getByRole('button', { name: 'Decrease quantity' }))
    await userEvent.click(within(dialog).getByRole('button', { name: 'Approve' }))

    await waitFor(() => {
      const post = fetchMock.mock.calls.find(([, init]) => init?.method === 'POST')
      expect(String(post[0])).toMatch(/\/recommendations\/7\/approve$/)
      expect(JSON.parse(post[1].body)).toEqual({ quantity: 6500 })
    })
    expect(await screen.findByText('Sent 6,500 L. Tracking in the action log.')).toBeInTheDocument()
  })

  it('falls back to the demo scenario when the backend is unreachable', async () => {
    vi.stubGlobal('EventSource', undefined)
    vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new TypeError('Failed to fetch'))))
    renderWithProviders(<ConsolePage />)
    expect(await screen.findByText('DEMO DATA · BACKEND OFFLINE')).toBeInTheDocument()
  })
})
