import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { jsonResponse } from '../test/utils'
import { API_BASE_URL, ApiError, AUTH_UNAUTHORIZED_EVENT, clearToken, filesApi, getToken, itemsApi, request, setToken } from './api'

describe('api.js', () => {
  let fetchMock

  beforeEach(() => {
    fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => clearToken())

  const lastCall = () => {
    const [url, init] = fetchMock.mock.calls.at(-1)
    return { url: new URL(url), init }
  }

  it('builds URLs from VITE_API_BASE_URL and skips empty params', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ items: [], total: 0, page: 1, page_size: 20, pages: 0 }))
    await itemsApi.list({ page: 2, page_size: 20, search: '', is_active: null })

    expect(API_BASE_URL).toBe('http://api.test/api/v1')
    const { url, init } = lastCall()
    expect(url.origin + url.pathname).toBe('http://api.test/api/v1/items')
    expect(Object.fromEntries(url.searchParams)).toEqual({ page: '2', page_size: '20' })
    expect(init.method).toBe('GET')
  })

  it('JSON-encodes plain object bodies', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ id: 1, name: 'A' }, { status: 201 }))
    const item = await itemsApi.create({ name: 'A', price: 2 })

    const { init } = lastCall()
    expect(init.method).toBe('POST')
    expect(init.headers['Content-Type']).toBe('application/json')
    expect(init.body).toBe(JSON.stringify({ name: 'A', price: 2 }))
    expect(item).toEqual({ id: 1, name: 'A' })
  })

  it('sends FormData untouched (no JSON, no Content-Type so the browser sets the boundary)', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ path: 'docs/a.txt' }, { status: 201 }))
    const file = new File(['hello'], 'a.txt', { type: 'text/plain' })
    await filesApi.upload(file, { folder: 'docs' })

    const { init } = lastCall()
    expect(init.body).toBeInstanceOf(FormData)
    expect(init.body.get('file')).toBeInstanceOf(File)
    expect(init.body.get('folder')).toBe('docs')
    expect(init.headers['Content-Type']).toBeUndefined()
  })

  it('attaches the Bearer token only when one is stored', async () => {
    fetchMock.mockImplementation(() => Promise.resolve(jsonResponse({ status: 'ok' })))

    await request('/health')
    expect(lastCall().init.headers.Authorization).toBeUndefined()

    setToken('secret-token')
    expect(getToken()).toBe('secret-token')
    await request('/health')
    expect(lastCall().init.headers.Authorization).toBe('Bearer secret-token')

    await request('/health', { auth: false })
    expect(lastCall().init.headers.Authorization).toBeUndefined()
  })

  it('returns null for 204 No Content', async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }))
    await expect(itemsApi.remove(5)).resolves.toBeNull()
    expect(lastCall().init.method).toBe('DELETE')
    expect(lastCall().url.pathname).toBe('/api/v1/items/5')
  })

  it('parses the backend error shape into ApiError, with per-field errors', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        {
          success: false,
          error: {
            code: 'VALIDATION_ERROR',
            message: 'Request validation failed',
            details: [
              { field: 'body.name', message: 'String should have at least 1 character', type: 'string_too_short' },
              { field: 'body.price', message: 'Input should be greater than or equal to 0', type: 'greater_than_equal' },
            ],
            request_id: 'abc123',
          },
        },
        { status: 422 },
      ),
    )

    const error = await itemsApi.create({ name: '' }).catch((e) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({ status: 422, code: 'VALIDATION_ERROR', message: 'Request validation failed', requestId: 'abc123' })
    expect(error.isValidationError).toBe(true)
    expect(error.fieldErrors).toEqual({
      name: 'String should have at least 1 character',
      price: 'Input should be greater than or equal to 0',
    })
  })

  it('maps CONFLICT details {field} and reads Retry-After on 429', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({ success: false, error: { code: 'CONFLICT', message: 'Name taken', details: { field: 'name' }, request_id: 'r1' } }, { status: 409 }),
    )
    const conflict = await itemsApi.create({ name: 'dup' }).catch((e) => e)
    expect(conflict.fieldErrors).toEqual({ name: 'Name taken' })

    fetchMock.mockResolvedValueOnce(
      jsonResponse({ success: false, error: { code: 'RATE_LIMITED', message: 'Too many', details: null, request_id: 'r2' } }, { status: 429, headers: { 'Retry-After': '42' } }),
    )
    const limited = await request('/ai/chat', { method: 'POST', body: {} }).catch((e) => e)
    expect(limited).toMatchObject({ status: 429, code: 'RATE_LIMITED', retryAfter: 42 })
  })

  it('falls back gracefully for non-JSON error bodies', async () => {
    fetchMock.mockResolvedValue(new Response('Bad gateway', { status: 502, statusText: 'Bad Gateway', headers: { 'Content-Type': 'text/plain', 'X-Request-ID': 'gw' } }))
    const error = await request('/health').catch((e) => e)
    expect(error).toMatchObject({ status: 502, code: 'HTTP_502', message: 'Bad gateway', requestId: 'gw' })
  })

  it('on 401 clears the token and emits auth:unauthorized', async () => {
    setToken('expired')
    const listener = vi.fn()
    window.addEventListener(AUTH_UNAUTHORIZED_EVENT, listener)
    fetchMock.mockResolvedValue(jsonResponse({ success: false, error: { code: 'UNAUTHORIZED', message: 'Token expired', details: null, request_id: 'x' } }, { status: 401 }))

    const error = await request('/items').catch((e) => e)
    window.removeEventListener(AUTH_UNAUTHORIZED_EVENT, listener)

    expect(error).toMatchObject({ status: 401, code: 'UNAUTHORIZED' })
    expect(getToken()).toBeNull()
    expect(listener).toHaveBeenCalledTimes(1)
    expect(listener.mock.calls[0][0].detail.error).toBe(error)
  })

  it('turns network failures into NETWORK_ERROR', async () => {
    fetchMock.mockRejectedValue(new TypeError('Failed to fetch'))
    const error = await request('/health').catch((e) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect(error.isNetworkError).toBe(true)
    expect(error.status).toBe(0)
  })

  it('aborts slow requests with a TIMEOUT error', async () => {
    fetchMock.mockImplementation(
      (_url, { signal }) =>
        new Promise((_resolve, reject) => {
          signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')))
        }),
    )
    const error = await request('/health', { timeout: 20 }).catch((e) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect(error.isTimeout).toBe(true)
  })

  it('lets caller cancellation bubble up as AbortError', async () => {
    fetchMock.mockImplementation(
      (_url, { signal }) =>
        new Promise((_resolve, reject) => {
          signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')))
        }),
    )
    const controller = new AbortController()
    const pending = request('/health', { signal: controller.signal }).catch((e) => e)
    controller.abort()
    const error = await pending
    expect(error.name).toBe('AbortError')
    expect(error).not.toBeInstanceOf(ApiError)
  })
})
