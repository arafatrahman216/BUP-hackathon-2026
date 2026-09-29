import { ApiError } from '../api/api'

/** A short, human message for any error (used by toasts and error states). */
export function getErrorMessage(error) {
  if (!error) return ''
  if (error instanceof ApiError) {
    switch (error.code) {
      case 'RATE_LIMITED':
        return error.retryAfter
          ? `Too many requests. Try again in ${error.retryAfter}s.`
          : 'Too many requests. Please slow down and try again shortly.'
      case 'AI_PROVIDERS_FAILED':
        return 'No AI provider could answer. Add an API key in backend/.env or pick another provider.'
      case 'VALIDATION_ERROR':
        return firstValidationMessage(error) || error.message
      default:
        return error.message
    }
  }
  return error.message || String(error)
}

function firstValidationMessage(error) {
  const entries = Object.entries(error.fieldErrors)
  if (!entries.length) return null
  const [field, message] = entries[0]
  // Model-level validators report the whole body as the field.
  return field === 'body' ? message.replace(/^Value error, /, '') : `${field}: ${message}`
}

export function getErrorTitle(error) {
  if (!(error instanceof ApiError)) return 'Something went wrong'
  if (error.isNetworkError) return 'Backend unreachable'
  if (error.isTimeout) return 'Request timed out'
  if (error.code === 'RATE_LIMITED') return 'Rate limited'
  if (error.code === 'AI_PROVIDERS_FAILED') return 'No AI provider available'
  if (error.status >= 500) return 'Server error'
  return 'Request failed'
}
