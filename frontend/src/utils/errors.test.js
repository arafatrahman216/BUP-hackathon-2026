import { describe, expect, it } from 'vitest'
import { ApiError } from '../api/api'
import { getErrorMessage, getErrorTitle } from './errors'
import { formatBytes } from './format'

describe('error helpers', () => {
  it('turns 429 into a friendly retry message', () => {
    const error = new ApiError({ status: 429, code: 'RATE_LIMITED', message: 'Too many', retryAfter: 42 })
    expect(getErrorTitle(error)).toBe('Rate limited')
    expect(getErrorMessage(error)).toBe('Too many requests. Try again in 42s.')
  })

  it('explains AI_PROVIDERS_FAILED and model-level validation errors', () => {
    expect(getErrorMessage(new ApiError({ status: 502, code: 'AI_PROVIDERS_FAILED' }))).toMatch(/No AI provider could answer/)
    const bodyError = new ApiError({ status: 422, code: 'VALIDATION_ERROR', details: [{ field: 'body', message: 'Value error, `model` needs `provider`' }] })
    expect(getErrorMessage(bodyError)).toBe('`model` needs `provider`')
  })

  it('formats bytes', () => {
    expect(formatBytes(0)).toBe('0 B')
    expect(formatBytes(1536)).toBe('1.5 KB')
    expect(formatBytes(10 * 1024 * 1024)).toBe('10 MB')
  })
})
