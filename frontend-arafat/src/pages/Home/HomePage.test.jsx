import { screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { jsonResponse, renderWithProviders } from '../../test/utils'
import HomePage from './HomePage'

describe('HomePage', () => {
  it('shows backend health and AI providers', async () => {
    vi.stubGlobal('fetch', vi.fn((url) =>
      Promise.resolve(
        String(url).endsWith('/health')
          ? jsonResponse({ status: 'ok', app: 'Hackathon API', env: 'development', database: 'ok' })
          : jsonResponse({ providers: [{ name: 'gemini', configured: true }, { name: 'groq', configured: false }] }),
      ),
    ))
    renderWithProviders(<HomePage />)
    expect(await screen.findByText('development')).toBeInTheDocument()
    expect(await screen.findByText('gemini ✓ · groq')).toBeInTheDocument()
  })

  it('shows a friendly error when the backend is down', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new TypeError('Failed to fetch'))))
    renderWithProviders(<HomePage />)
    expect(await screen.findByText(/Can't reach the API/)).toBeInTheDocument()
  })
})
