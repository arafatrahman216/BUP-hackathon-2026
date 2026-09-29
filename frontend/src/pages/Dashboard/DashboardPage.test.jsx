import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { jsonResponse, renderWithProviders } from '../../test/utils'
import DashboardPage from './DashboardPage'

const rec = {
  id: 7, tick: 100, station_id: 'station-mirpur', fuel_type: 'PETROL', depot_id: 'depot-gazipur',
  route_id: 'route-gazipur-mirpur', quantity: 7000, proposed_quantity: 7000, risk: 'urgent', ticks_until_empty: 3,
  important: true, decision_mode: 'operator', reasons: ['urgent: station may run dry before the truck arrives'],
  explanation: 'Mirpur PETROL holds 300 L.', planner: 'rules', status: 'PENDING_APPROVAL', operator_note: null,
  idempotency_key: null, allocation_id: null, posted_tick: null, error_code: null, error_message: null,
}

const state = {
  sim: { connected: true, link: 'sse', stale: false, tick: 100, sim_time: '2026-01-02T01:00:00', status: 'RUNNING', tick_minutes: 15 },
  pipeline: { acting: true, runs: 3, last_run: { duration_ms: 120 }, stages: [{ name: 'read', status: 'ok', ms: 40 }], validation_issues: [] },
  alerts: [{ level: 'critical', code: 'STOCKOUT_RISK', message: 'station-mirpur PETROL covers 3.0 ticks' }],
  blocked: [],
  recommendations: { open: [rec], recent: [rec] },
  stations: [{
    id: 'station-mirpur', name: 'Mirpur Fuel Station', region_id: 'region-dhaka', status: 'OPEN', demand_profile: 'urban_high',
    demand_multiplier: 1, fuels: [{ fuel_type: 'PETROL', inventory: 300, capacity: 14000, rate_per_tick: 100, incoming: 0,
      ticks_until_empty: 3, cover_ticks: 3, lead_ticks: 2, risk: 'urgent' }],
  }],
  depots: [], routes: [{ id: 'route-gazipur-mirpur', transit_ticks: 2, max_shipment: 7000, status: 'AVAILABLE' }],
  supply: [], events: [], allocations: [],
  metrics: { service_level: 0.9512, unmet_demand_liters: 1200, served_demand_liters: 23400, allocation_liters: 0, allocation_failures: 0 },
}

describe('DashboardPage', () => {
  it('shows state and posts an edited approval', async () => {
    vi.stubGlobal('EventSource', undefined) // jsdom has none: the hook falls back to REST
    const fetchMock = vi.fn((url, init) =>
      Promise.resolve(init?.method === 'POST' ? jsonResponse({ ...rec, status: 'POSTED', quantity: 5000 }) : jsonResponse(state)),
    )
    vi.stubGlobal('fetch', fetchMock)
    renderWithProviders(<DashboardPage />)

    expect(await screen.findByText('95.12%')).toBeInTheDocument()
    expect(screen.getByText('Mirpur Fuel Station')).toBeInTheDocument()
    expect(screen.getByText('STOCKOUT_RISK')).toBeInTheDocument()

    const qty = screen.getByLabelText('Quantity (L)')
    await userEvent.clear(qty)
    await userEvent.type(qty, '5000')
    await userEvent.click(screen.getByRole('button', { name: 'Approve edited' }))

    await waitFor(() => {
      const post = fetchMock.mock.calls.find(([, init]) => init?.method === 'POST')
      expect(String(post[0])).toMatch(/\/recommendations\/7\/approve$/)
      expect(JSON.parse(post[1].body)).toEqual({ quantity: 5000 })
    })
  })

  it('shows a stale banner when the simulator is unreachable', async () => {
    vi.stubGlobal('EventSource', undefined)
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(jsonResponse({
      ...state, sim: { ...state.sim, connected: false, stale: true, error: 'SimulatorError: down', data_age_seconds: 12 },
    }))))
    renderWithProviders(<DashboardPage />)
    expect(await screen.findByText(/Showing cached data from 12 s ago/)).toBeInTheDocument()
  })
})
