/**
 * api.js - the ONLY module that talks HTTP.
 *
 * - Base URL comes from VITE_API_BASE_URL (see .env / .env.example).
 * - `request()` wraps fetch: JSON in/out, FormData passthrough, query params,
 *   timeouts via AbortController, Bearer token, and a single error type (ApiError).
 * - Endpoints are grouped per backend resource (healthApi, aiApi, ...).
 *   To add one: write a function here that calls `request()`, then use it from a hook.
 */

export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8001/api/v1').replace(
  /\/+$/,
  '',
)
export const DEFAULT_TIMEOUT_MS = Number(import.meta.env.VITE_API_TIMEOUT_MS) || 30_000
export const AI_TIMEOUT_MS = Math.max(DEFAULT_TIMEOUT_MS, 90_000)

/** Fired on `window` whenever the API answers 401. AuthProvider listens for it. */
export const AUTH_UNAUTHORIZED_EVENT = 'auth:unauthorized'

// ---------------------------------------------------------------------------
// Token storage
// ---------------------------------------------------------------------------
const TOKEN_KEY = 'hackathon.auth_token'

export function getToken() {
  try {
    return localStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

export function setToken(token) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token)
    else localStorage.removeItem(TOKEN_KEY)
  } catch {
    /* storage unavailable (private mode) - token just won't persist */
  }
}

export function clearToken() {
  setToken(null)
}

// ---------------------------------------------------------------------------
// Errors
// ---------------------------------------------------------------------------
/**
 * Mirrors the backend error shape:
 *   {"success": false, "error": {"code", "message", "details", "request_id"}}
 * Network failures and timeouts are ApiErrors too (status 0), so callers only
 * ever need to handle one type.
 */
export class ApiError extends Error {
  constructor({ status = 0, code = 'UNKNOWN_ERROR', message = 'Something went wrong', details = null, requestId = null, retryAfter = null } = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.details = details
    this.requestId = requestId
    this.retryAfter = retryAfter
  }

  get isNetworkError() {
    return this.code === 'NETWORK_ERROR'
  }

  get isTimeout() {
    return this.code === 'TIMEOUT'
  }

  get isValidationError() {
    return this.code === 'VALIDATION_ERROR'
  }

  /**
   * Per-field messages for forms: {"name": "String should have at least 1 character"}.
   * Handles VALIDATION_ERROR details ([{field: "body.name", message}]) and
   * details of the form {field: "name"} (e.g. CONFLICT).
   */
  get fieldErrors() {
    const errors = {}
    if (Array.isArray(this.details)) {
      for (const d of this.details) {
        if (!d || typeof d.field !== 'string') continue
        const field = d.field.replace(/^(body|query|path|form)\./, '')
        if (!errors[field]) errors[field] = d.message || 'Invalid value'
      }
    } else if (this.details && typeof this.details.field === 'string') {
      errors[this.details.field] = this.message
    }
    return errors
  }
}

async function toApiError(response, requestId) {
  const payload = await parseBody(response).catch(() => null)
  const err = payload && typeof payload === 'object' ? payload.error : null
  const retryAfter = Number(response.headers.get('Retry-After')) || null
  return new ApiError({
    status: response.status,
    code: err?.code || `HTTP_${response.status}`,
    message: err?.message || (typeof payload === 'string' && payload) || response.statusText || `Request failed (${response.status})`,
    details: err?.details ?? null,
    requestId: err?.request_id || requestId,
    retryAfter,
  })
}

// ---------------------------------------------------------------------------
// Core request
// ---------------------------------------------------------------------------
export function buildUrl(path, params) {
  const url = new URL(API_BASE_URL + (path.startsWith('/') ? path : `/${path}`))
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value === undefined || value === null || value === '') continue
      url.searchParams.set(key, String(value))
    }
  }
  return url.toString()
}

function isRawBody(body) {
  return (
    (typeof FormData !== 'undefined' && body instanceof FormData) ||
    (typeof Blob !== 'undefined' && body instanceof Blob) ||
    (typeof URLSearchParams !== 'undefined' && body instanceof URLSearchParams) ||
    body instanceof ArrayBuffer
  )
}

async function parseBody(response) {
  if (response.status === 204 || response.status === 205) return null
  const text = await response.text()
  if (!text) return null
  const type = response.headers.get('Content-Type') || ''
  if (type.includes('json')) return JSON.parse(text)
  return text
}

/**
 * @param {string} path             e.g. "/items"
 * @param {object} [options]
 * @param {string} [options.method] GET | POST | PATCH | PUT | DELETE
 * @param {object} [options.params] query params (null/undefined/"" are skipped)
 * @param {*}      [options.body]   plain objects are JSON-encoded; FormData/Blob are sent as-is
 * @param {object} [options.headers]
 * @param {number} [options.timeout] ms, default DEFAULT_TIMEOUT_MS
 * @param {AbortSignal} [options.signal] cancel from the caller (e.g. on unmount)
 * @param {boolean} [options.auth]  attach the stored token (default true)
 * @returns {Promise<any>} parsed JSON (or null for 204)
 */
export async function request(path, { method = 'GET', params, body, headers = {}, timeout = DEFAULT_TIMEOUT_MS, signal, auth = true } = {}) {
  const finalHeaders = { Accept: 'application/json', ...headers }
  let finalBody = body

  if (body !== undefined && body !== null && !isRawBody(body)) {
    finalHeaders['Content-Type'] = 'application/json'
    finalBody = JSON.stringify(body)
  }

  const token = auth ? getToken() : null
  if (token) finalHeaders.Authorization = `Bearer ${token}`

  // One controller aborts on either timeout or the caller's signal.
  const controller = new AbortController()
  let timedOut = false
  const timer =
    timeout > 0
      ? setTimeout(() => {
          timedOut = true
          controller.abort()
        }, timeout)
      : null
  const onCallerAbort = () => controller.abort()
  if (signal) {
    if (signal.aborted) controller.abort()
    else signal.addEventListener('abort', onCallerAbort, { once: true })
  }

  let response
  try {
    response = await fetch(buildUrl(path, params), {
      method,
      headers: finalHeaders,
      body: finalBody,
      signal: controller.signal,
    })
  } catch (error) {
    if (timedOut) {
      throw new ApiError({ code: 'TIMEOUT', message: `The request took longer than ${Math.round(timeout / 1000)}s and was cancelled.` })
    }
    if (error?.name === 'AbortError') throw error // cancelled by the caller: let it bubble untouched
    throw new ApiError({ code: 'NETWORK_ERROR', message: `Can't reach the API at ${API_BASE_URL}. Is the backend running?` })
  } finally {
    if (timer) clearTimeout(timer)
    signal?.removeEventListener('abort', onCallerAbort)
  }

  const requestId = response.headers.get('X-Request-ID')

  if (!response.ok) {
    const error = await toApiError(response, requestId)
    if (response.status === 401) {
      clearToken()
      if (typeof window !== 'undefined') {
        window.dispatchEvent(new CustomEvent(AUTH_UNAUTHORIZED_EVENT, { detail: { error } }))
      }
    }
    throw error
  }

  return parseBody(response)
}

/** Shorthand verbs, if you prefer `api.post('/things', body)` over `request()`. */
export const api = {
  get: (path, options) => request(path, { ...options, method: 'GET' }),
  post: (path, body, options) => request(path, { ...options, method: 'POST', body }),
  put: (path, body, options) => request(path, { ...options, method: 'PUT', body }),
  patch: (path, body, options) => request(path, { ...options, method: 'PATCH', body }),
  delete: (path, options) => request(path, { ...options, method: 'DELETE' }),
}

// ---------------------------------------------------------------------------
// Endpoints (grouped by backend resource). `options` is forwarded to request(),
// so every call accepts {signal, timeout, headers}.
// ---------------------------------------------------------------------------
export const healthApi = {
  check: (options) => api.get('/health', options),
}

export const aiApi = {
  providers: (options) => api.get('/ai/providers', options),
  /** @param {{messages: {role: string, content: string}[], provider?, model?, temperature?, max_tokens?, json_mode?}} payload */
  chat: (payload, options) => api.post('/ai/chat', payload, { timeout: AI_TIMEOUT_MS, ...options }),
  /** @param {{prompt: string, system?, provider?, model?, temperature?, max_tokens?, json_mode?}} payload */
  generate: (payload, options) => api.post('/ai/generate', payload, { timeout: AI_TIMEOUT_MS, ...options }),
}

export const dashboardApi = {
  /** Latest cached pipeline state (same payload as the `state` SSE event). */
  get: (options) => api.get('/dashboard', options),
  /** Run the pipeline now, even if the current tick was already processed. */
  run: (options) => api.post('/pipeline/run', null, options),
  /** URL of the backend's SSE stream (use with EventSource). */
  streamUrl: () => buildUrl('/stream'),
}

export const recommendationsApi = {
  list: (params, options) => api.get('/recommendations', { ...options, params }),
  /** @param {{quantity?: number, note?: string}} body  quantity = operator edit */
  approve: (id, body = {}, options) => api.post(`/recommendations/${id}/approve`, body, options),
  reject: (id, body = {}, options) => api.post(`/recommendations/${id}/reject`, body, options),
}

export const explainApi = {
  /** Suggested questions for the recommendation's status + the questions already asked (newest first). */
  questions: (recId, options) => api.get(`/explain/recommendations/${recId}`, options),
  /** Ask the AI about one recommendation; the answer is stored. */
  ask: (recId, question, options) =>
    api.post(`/explain/recommendations/${recId}`, { question }, { timeout: AI_TIMEOUT_MS, ...options }),
}
